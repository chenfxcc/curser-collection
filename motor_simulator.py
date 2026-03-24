from __future__ import annotations

import os
import time
import threading
from enum import Enum
from typing import Any, Dict, Optional
"""
MotorSimulator class Design description:
- main status: pwm_duty, direction, enabled are set through set_* methods
- Algorithm Engine: _update_simulation(dt) calculate the speed, current, temperature through current status
- Update rules:
   *set mothod call _update_simulation(dt) immediately (immediate drive)
   *backend periodic call through thread to update the status (time drive)
- interface:get_status() return the current status
"""


class MotorState(str, Enum):
    """High-level motor state machine (operational + fault)."""

    STOPPED = "STOPPED"
    RUNNING_FORWARD = "RUNNING_FORWARD"
    RUNNING_BACKWARD = "RUNNING_BACKWARD"
    FAULT = "FAULT"


class MotorSimulator:
    def __init__(self, name: str = "Motor"):
        """
        Initialize the motor simulator.

        Args:
            name: Human-readable motor identifier (exposed in :meth:`get_status`).
        """
        self.name = str(name)
        self.load_config()
        self.enabled = False
        self.pwm_duty = 0.0  # PWM value 0-100
        self.direction = 0  # direction, 1=Forward rotration , -1=Reverse rotation , 0=stop
        self.speed = 0.0   #current speed 
        self.current = 0.0   #current simulation
        self.temperature = 25.0  # temperature 
        self.ambient_temperature = 25.0
        self._last_update_ts = time.monotonic()
        self._last_update = time.time()
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._state = MotorState.STOPPED

    def _transition_state(self, new_state: MotorState, detail: str = "") -> None:
        """Record state change and print a log line. Caller must hold ``self._lock``."""
        if self._state == new_state:
            return
        old = self._state
        self._state = new_state
        msg = f"[MotorSimulator:{self.name}] state: {old.value} -> {new_state.value}"
        if detail:
            msg += f" | {detail}"
        print(msg)

    def _ensure_not_fault(self) -> None:
        """Caller must hold ``self._lock``."""
        if self._state == MotorState.FAULT:
            raise RuntimeError("Motor in FAULT: operation not allowed; call fault_reset() first")

    def _refresh_operational_state(self) -> None:
        """Map ``enabled`` + ``direction`` to STOPPED / RUNNING_*. Caller must hold lock; not used in FAULT."""
        if self._state == MotorState.FAULT:
            return
        if not self.enabled or self.direction == 0:
            self._transition_state(MotorState.STOPPED, "disabled or direction stop")
        elif self.direction == 1:
            self._transition_state(MotorState.RUNNING_FORWARD, "forward")
        else:
            self._transition_state(MotorState.RUNNING_BACKWARD, "reverse")

    def load_config(self, path: str | None = None) -> Dict[str, Any]:
        """
        Load simulator parameters from YAML.

        Keys:

        - ``max_speed``: Maximum simulated speed magnitude at 100% PWM (RPM scale).
        - ``current_factor``: Multiplier for load-dependent current (see :meth:`_update_simulation`).
        - ``temp_rise_rate``: Temperature rise per (ampere × second), °C/(A·s).

        If the file is missing, a default file is created and defaults are used.

        Args:
            path: YAML file path. If ``None``, uses ``motor_config.yaml`` in the same
                directory as this module (not the process current working directory),
                so edits in the project folder always apply when you run scripts from elsewhere.

        Returns:
            The merged configuration dict actually applied.
        """
        if path is None:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "motor_config.yaml")

        defaults: Dict[str, Any] = {
            "max_speed": 100.0,
            "current_factor": 0.03,
            "temp_rise_rate": 0.15,
        }
        if not os.path.exists(path):
            self._write_default_motor_config(path, defaults)
            merged = dict(defaults)
        else:
            loaded = self._read_motor_config(path)
            merged = dict(defaults)
            if loaded:
                for k in defaults:
                    if k in loaded:
                        merged[k] = loaded[k]

        max_speed = float(merged["max_speed"])
        current_factor = float(merged["current_factor"])
        temp_rise_rate = float(merged["temp_rise_rate"])

        if max_speed <= 0:
            max_speed = float(defaults["max_speed"])
        if current_factor < 0:
            current_factor = float(defaults["current_factor"])
        if temp_rise_rate < 0:
            temp_rise_rate = float(defaults["temp_rise_rate"])

        self.max_speed = max_speed
        self.current_factor = current_factor
        self.temp_rise_rate = temp_rise_rate

        merged["max_speed"] = max_speed
        merged["current_factor"] = current_factor
        merged["temp_rise_rate"] = temp_rise_rate
        return merged

    def _write_default_motor_config(self, path: str, cfg: Dict[str, Any]) -> None:
        content = (
            "# Motor simulator configuration\n"
            "# max_speed: simulated RPM at 100% PWM (magnitude)\n"
            "# current_factor: scales load current vs normalized duty (0..100)\n"
            "# temp_rise_rate: heating °C per (A * s)\n"
            f"max_speed: {cfg['max_speed']}\n"
            f"current_factor: {cfg['current_factor']}\n"
            f"temp_rise_rate: {cfg['temp_rise_rate']}\n"
        )
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    def _read_motor_config(self, path: str) -> Optional[Dict[str, Any]]:
        try:
            import yaml  # type: ignore

            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else None
        except Exception:
            return self._simple_motor_yaml_load(path)

    def _simple_motor_yaml_load(self, path: str) -> Optional[Dict[str, Any]]:
        out: Dict[str, Any] = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.split("#", 1)[0].strip()
                    if not line or ":" not in line:
                        continue
                    k, v = line.split(":", 1)
                    k, v = k.strip(), v.strip()
                    if not k:
                        continue
                    try:
                        if "." in v or "e" in v.lower():
                            out[k] = float(v)
                        else:
                            out[k] = int(v)
                    except ValueError:
                        out[k] = v
            return out
        except OSError:
            return None

    def set_pwm(self, pwm_duty):
        """
        Set PWM duty cycle.

        Args:
            pwm_duty: Duty cycle percentage in range [0, 100].

        Raises:
            ValueError: If pwm_duty is outside [0, 100].
            RuntimeError: If the motor is in ``FAULT``.
        """
        if not (0 <= pwm_duty <= 100):
            raise ValueError(f"pwm_duty must be in range [0, 100], got {pwm_duty!r}")
        with self._lock:
            self._ensure_not_fault()
            self.pwm_duty = float(pwm_duty)
            self._update_simulation(dt=0.0)

    def set_direction(self, direction):
        """
        Set motor rotation direction.

        Args:
            direction: Integer only. ``1`` = forward, ``-1`` = reverse, ``0`` = stop.

        Raises:
            ValueError: If ``direction`` is not an integer in ``{1, -1, 0}``.
            RuntimeError: If the motor is in ``FAULT`` (use :meth:`fault_reset` first).
        """
        if isinstance(direction, bool) or not isinstance(direction, int):
            raise ValueError(
                "direction must be an integer: 1 (forward), -1 (reverse), 0 (stop); "
                f"got {direction!r}"
            )
        if direction not in (-1, 0, 1):
            raise ValueError(
                "direction must be one of 1 (forward), -1 (reverse), 0 (stop); "
                f"got {direction!r}"
            )
        with self._lock:
            self._ensure_not_fault()
            self.direction = int(direction)
            self._refresh_operational_state()
            self._update_simulation(0)

    def enable(self):
        """
        Turn the motor on (software enable).

        Sets ``self.enabled`` to ``True`` and refreshes simulation state
        without advancing the thermal time step (``dt=0``).

        Raises:
            RuntimeError: If the motor is in ``FAULT``.
        """
        with self._lock:
            self._ensure_not_fault()
            self.enabled = True
            self._refresh_operational_state()
            self._update_simulation(0)

    def disable(self):
        """
        Turn the motor off (software disable).

        Sets ``self.enabled`` to ``False`` and refreshes simulation state
        without advancing the thermal time step (``dt=0``).

        Raises:
            RuntimeError: If the motor is in ``FAULT``.
        """
        with self._lock:
            self._ensure_not_fault()
            self.enabled = False
            self._refresh_operational_state()
            self._update_simulation(0)

    def raise_fault(self, reason: str = "") -> None:
        """
        Enter ``FAULT`` (simulator / protection trip). Disables outputs and blocks
        control until :meth:`fault_reset`.

        Args:
            reason: Optional text included in the state-change log.
        """
        with self._lock:
            if self._state == MotorState.FAULT:
                return
            self.enabled = False
            self.direction = 0
            self._transition_state(MotorState.FAULT, detail=reason or "fault asserted")
            self._update_simulation(0.0)

    def fault_reset(self) -> None:
        """
        Leave ``FAULT`` and return to ``STOPPED`` (disabled, direction 0).

        Raises:
            ValueError: If not currently in ``FAULT``.
        """
        with self._lock:
            if self._state != MotorState.FAULT:
                raise ValueError("fault_reset only valid in FAULT state")
            self.enabled = False
            self.direction = 0
            self._transition_state(MotorState.STOPPED, detail="fault cleared")
            self._update_simulation(0.0)

    def get_status(self):
        """
        Return a fresh snapshot of the motor state.

        First advances the internal simulation by elapsed real time (so e.g.
        temperature reflects time since the last update), then builds a new
        ``dict`` whose values are plain copies (not references to mutable
        internals).

        Returns:
            dict: Keys and meaning:

            - ``name`` (``str``): Motor label.
            - ``enabled`` (``bool``): Whether the motor is enabled.
            - ``direction`` (``int``): ``1`` forward, ``-1`` reverse, ``0`` stop.
            - ``pwm_duty`` (``float``): PWM duty in ``[0, 100]``.
            - ``speed`` (``float``): Simulated signed speed (0 if disabled/stopped).
            - ``current`` (``float``): Simulated current (A).
            - ``temperature`` (``float``): Simulated temperature (°C).
            - ``state`` (``str``): ``MotorState`` value (``STOPPED``, ``RUNNING_FORWARD``, …).
        """
        with self._lock:
            self._update_simulation()
            return {
                "name": str(self.name),
                "enabled": bool(self.enabled),
                "direction": int(self.direction),
                "pwm_duty": float(self.pwm_duty),
                "speed": float(self.speed),
                "current": float(self.current),
                "temperature": float(self.temperature),
                "state": self._state.value,
            }

    def _monitor_loop(self, interval: float = 0.1):
        """Background loop that periodically updates simulation state."""
        while self._running:
            now = time.time()
            with self._lock:
                dt = now - self._last_update
                if dt < 0:
                    dt = 0.0
                self._update_simulation(dt)
                self._last_update = now
            time.sleep(interval)

    def start_monitoring(self, interval: float = 0.1):
        """
        Start the background monitoring thread.

        Args:
            interval: Update period in seconds. Smaller values update faster
                with higher CPU usage.
        """
        if interval <= 0:
            raise ValueError(f"interval must be > 0, got {interval!r}")

        with self._lock:
            if self._running:
                return
            self._running = True
            self._last_update = time.time()

        self._thread = threading.Thread(
            target=self._monitor_loop,
            args=(float(interval),),
            daemon=True,
        )
        self._thread.start()

    def stop_monitoring(self, timeout: float | None = 2.0):
        """
        Stop the background monitoring thread safely.

        Args:
            timeout: Max seconds to wait for the thread to exit.
        """
        with self._lock:
            self._running = False
            thread = self._thread

        if thread is not None:
            thread.join(timeout=timeout)

        with self._lock:
            self._thread = None
    def _update_simulation(self, dt: float | None = None):
        """
        Update simulation status internally.

        Rules:
        - If not enabled or direction == 0 -> speed = 0
        - Else speed = (pwm_duty/100) * max_speed * direction_factor (forward:+, reverse:-)
        - current uses ``current_factor`` with load normalized by ``max_speed``
        - temperature heating uses ``temp_rise_rate`` * current * dt (plus fixed cooling)
        """
        now = time.monotonic()
        if dt is None:
            dt = now - self._last_update_ts
        self._last_update_ts = now
        if dt < 0:
            dt = 0.0

        # Speed
        if self._state == MotorState.FAULT:
            self.speed = 0.0
        else:
            enabled = bool(self.enabled)
            direction = self.direction
            if (not enabled) or direction == 0:
                self.speed = 0.0
            else:
                direction_factor = 1.0 if direction > 0 else -1.0
                pwm = float(self.pwm_duty)
                self.speed = (pwm / 100.0) * float(self.max_speed) * direction_factor

        # Current (simple proportional model)
        # Use a small baseline while enabled (to mimic control electronics),
        # and increase with load proportional to normalized duty (0..100).
        if self._state == MotorState.FAULT:
            base_current = 0.0
        elif bool(self.enabled) and self.direction != 0:
            base_current = 0.2
        else:
            base_current = 0.0
        load_0_100 = abs(self.speed) / float(self.max_speed) * 100.0 if self.max_speed > 0 else 0.0
        self.current = base_current + float(self.current_factor) * load_0_100

        # Temperature (slow heating + cooling to ambient)
        cooling_coeff = 0.05  # 1/s (fixed; not in motor_config.yaml)
        heat = float(self.temp_rise_rate) * self.current * dt
        cool = cooling_coeff * (self.temperature - self.ambient_temperature) * dt
        self.temperature = float(self.temperature + heat - cool)