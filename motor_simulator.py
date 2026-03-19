from __future__ import annotations

import time
import threading
"""
MotorSimulator class Design description:
- main status: pwm_duty, direction, enabled are set through set_* methods
- Algorithm Engine: _update_simulation(dt) calculate the speed, current, temperature through current status
- Update rules:
   *set mothod call _update_simulation(dt) immediately (immediate drive)
   *backend periodic call through thread to update the status (time drive)
- interface:get_status() return the current status
"""

class MotorSimulator:
    def __init__(self, name: str = "Motor"):
        """
        Initialize the motor simulator.

        Args:
            name: Human-readable motor identifier (exposed in :meth:`get_status`).
        """
        self.name = str(name)
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

    def set_pwm(self, pwm_duty):
        """
        Set PWM duty cycle.

        Args:
            pwm_duty: Duty cycle percentage in range [0, 100].

        Raises:
            ValueError: If pwm_duty is outside [0, 100].
        """
        if not (0 <= pwm_duty <= 100):
            raise ValueError(f"pwm_duty must be in range [0, 100], got {pwm_duty!r}")
        with self._lock:
            self.pwm_duty = float(pwm_duty)
            self._update_simulation(dt=0.0)

    def set_direction(self, direction):
        """
        Set motor rotation direction.

        Args:
            direction: Integer only. ``1`` = forward, ``-1`` = reverse, ``0`` = stop.

        Raises:
            ValueError: If ``direction`` is not an integer in ``{1, -1, 0}``.
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
            self.direction = int(direction)
            self._update_simulation(0)

    def enable(self):
        """
        Turn the motor on (software enable).

        Sets ``self.enabled`` to ``True`` and refreshes simulation state
        without advancing the thermal time step (``dt=0``).
        """
        with self._lock:
            self.enabled = True
            self._update_simulation(0)

    def disable(self):
        """
        Turn the motor off (software disable).

        Sets ``self.enabled`` to ``False`` and refreshes simulation state
        without advancing the thermal time step (``dt=0``).
        """
        with self._lock:
            self.enabled = False
            self._update_simulation(0)

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
        - Else speed = pwm_duty * direction_factor (forward:+, reverse:-)
        - current increases with |speed|
        - temperature rises slowly over time (with some cooling)
        """
        now = time.monotonic()
        if dt is None:
            dt = now - self._last_update_ts
        self._last_update_ts = now
        if dt < 0:
            dt = 0.0

        # Speed
        enabled = bool(self.enabled)
        direction = self.direction
        if (not enabled) or direction == 0:
            self.speed = 0.0
        else:
            direction_factor = 1.0 if direction > 0 else -1.0
            self.speed = float(self.pwm_duty) * direction_factor

        # Current (simple proportional model)
        # Use a small baseline while enabled (to mimic control electronics),
        # and increase with load proportional to |speed|.
        if enabled and direction != 0:
            base_current = 0.2
        else:
            base_current = 0.0
        k_current = 0.03
        self.current = base_current + k_current * abs(self.speed)

        # Temperature (slow heating + cooling to ambient)
        heat_coeff = 0.15  # degC per (A*s)
        cooling_coeff = 0.05  # 1/s
        heat = heat_coeff * self.current * dt
        cool = cooling_coeff * (self.temperature - self.ambient_temperature) * dt
        self.temperature = float(self.temperature + heat - cool)