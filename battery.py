import random
import threading
import os
import csv
from datetime import datetime
import math
from typing import Any, Dict, Optional

class BatteryMonitor:
    """Battery monitering module, simulates or reads real battery data."""
    def __init__(self, source="simulator", update_interval=0.1):
        """Initialize the battery monitor.
           :param source: "simulator" or "BMS"
           :param update_interval: float, update interval in seconds
        """
        self.source = source
        self.update_interval = update_interval
        self._soc = 100.0
        self._voltage = 25
        self._soh = 100.0
        self._temperature = 25.0  # °C
        self._ambient_temperature = 25.0  # °C, environmental temperature baseline
        self._sim_time_s = 0.0
        self._sim_update_count = 0

        # 用“容量（Ah）”来驱动 SOC，这样 SOH 变化会影响可用容量
        self._nominal_capacity_ah = 100.0
        self._remaining_capacity_ah = (
            self._nominal_capacity_ah * (self._soh / 100.0) * (self._soc / 100.0)
        )

        # 放电曲线相关参数（可由配置覆盖）
        self._v_full = 25.2
        self._v_plateau_hi = 24.7
        self._v_plateau_lo = 24.4
        self._v_empty = 22.0

        # 尝试加载配置（如果不存在会创建默认配置）
        self.load_config()

        # 告警状态（用于抑制重复打印）
        self._alarm_low_voltage_active = False
        self._alarm_low_battery_active = False
       #TODO: start monitoring thread
    
    def _monitor_loop(self):
        while True:
            if self.source == "simulator":
                self._simulate_data()
            else:
                self._read_from_bms()
            self._check_alarms()
            threading.Event().wait(self.update_interval)#在后台线程中添加检查，保证每次数据更新都会执行告警逻辑
    

    def _log_data(self):
        filename = "battery_log.csv"
        with open(filename, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                self._voltage,
                self._soc,
                self._soh,
                self._temperature,
            ])

    def load_config(self, path: str = "config.yaml") -> Dict[str, Any]:
        """Load config from config.yaml; create defaults if missing.

        Supported keys (all optional):
          - source: "simulator" or "BMS"
          - update_interval: float seconds
          - nominal_capacity_ah: float
          - ambient_temperature: float °C
          - voltage_curve: {v_full, v_plateau_hi, v_plateau_lo, v_empty}
        """
        default_config: Dict[str, Any] = {
            "source": self.source,
            "update_interval": float(self.update_interval),
            "nominal_capacity_ah": float(self._nominal_capacity_ah),
            "ambient_temperature": float(self._ambient_temperature),
            "voltage_curve": {
                "v_full": float(self._v_full),
                "v_plateau_hi": float(self._v_plateau_hi),
                "v_plateau_lo": float(self._v_plateau_lo),
                "v_empty": float(self._v_empty),
            },
        }

        if not os.path.exists(path):
            self._write_default_config_yaml(path, default_config)
            cfg = default_config
        else:
            cfg = self._read_yaml_config(path) or {}
            cfg = self._merge_dicts(default_config, cfg)

        # 应用配置
        self.source = str(cfg.get("source", self.source))
        self.update_interval = float(cfg.get("update_interval", self.update_interval))
        self._nominal_capacity_ah = float(cfg.get("nominal_capacity_ah", self._nominal_capacity_ah))
        self._ambient_temperature = float(cfg.get("ambient_temperature", self._ambient_temperature))

        vc = cfg.get("voltage_curve", {}) if isinstance(cfg.get("voltage_curve", {}), dict) else {}
        self._v_full = float(vc.get("v_full", self._v_full))
        self._v_plateau_hi = float(vc.get("v_plateau_hi", self._v_plateau_hi))
        self._v_plateau_lo = float(vc.get("v_plateau_lo", self._v_plateau_lo))
        self._v_empty = float(vc.get("v_empty", self._v_empty))

        # 重新对齐“剩余可用容量”到当前 SOH / SOC
        effective_capacity_ah = self._nominal_capacity_ah * (self._soh / 100.0)
        self._remaining_capacity_ah = max(0.0, min(effective_capacity_ah, effective_capacity_ah * (self._soc / 100.0)))

        return cfg

    def _write_default_config_yaml(self, path: str, cfg: Dict[str, Any]) -> None:
        # 手写 YAML，避免强依赖第三方库
        vc = cfg.get("voltage_curve", {}) if isinstance(cfg.get("voltage_curve", {}), dict) else {}
        content = (
            "# Battery monitor config\n"
            "# source: simulator | BMS\n"
            f"source: {cfg.get('source', 'simulator')}\n"
            f"update_interval: {cfg.get('update_interval', 0.1)}\n"
            f"nominal_capacity_ah: {cfg.get('nominal_capacity_ah', 100.0)}\n"
            f"ambient_temperature: {cfg.get('ambient_temperature', 25.0)}\n"
            "voltage_curve:\n"
            f"  v_full: {vc.get('v_full', 25.2)}\n"
            f"  v_plateau_hi: {vc.get('v_plateau_hi', 24.7)}\n"
            f"  v_plateau_lo: {vc.get('v_plateau_lo', 24.4)}\n"
            f"  v_empty: {vc.get('v_empty', 22.0)}\n"
        )
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    def _read_yaml_config(self, path: str) -> Optional[Dict[str, Any]]:
        # 优先用 PyYAML（如果安装了）；否则用简易解析器支持默认格式
        try:
            import yaml  # type: ignore

            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else None
        except Exception:
            return self._simple_yaml_load(path)

    def _simple_yaml_load(self, path: str) -> Optional[Dict[str, Any]]:
        # 仅支持：key: value 以及一层缩进字典（用于 voltage_curve）
        def _coerce(val: str) -> Any:
            v = val.strip()
            if v.lower() in ("true", "false"):
                return v.lower() == "true"
            try:
                if "." in v or "e" in v.lower():
                    return float(v)
                return int(v)
            except Exception:
                return v.strip("\"'")

        root: Dict[str, Any] = {}
        current_map: Optional[Dict[str, Any]] = None
        current_key: Optional[str] = None

        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.rstrip("\n")
                    if not line.strip() or line.lstrip().startswith("#"):
                        continue

                    if line.startswith("  ") and current_map is not None and ":" in line:
                        k, v = line.strip().split(":", 1)
                        current_map[k.strip()] = _coerce(v)
                        continue

                    if ":" not in line:
                        continue
                    k, v = line.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if v == "":
                        # start nested map
                        m: Dict[str, Any] = {}
                        root[k] = m
                        current_map = m
                        current_key = k
                    else:
                        root[k] = _coerce(v)
                        current_map = None
                        current_key = None

            return root
        except Exception:
            return None

    def _merge_dicts(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = dict(base)
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = self._merge_dicts(out[k], v)  # type: ignore[arg-type]
            else:
                out[k] = v
        return out
            
    def start_monitoring(self):
        """Start a background thread to update the battery data periodically."""
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()

    def _check_alarms(self) -> None:
        low_voltage = self._voltage < 21
        low_battery = self._soc < 20

        # 只在“首次触发”时打印，避免每次更新刷屏
        if low_voltage and (not self._alarm_low_voltage_active):
            print("Warning: Low voltage!")
        if low_battery and (not self._alarm_low_battery_active):
            print("Warning: Low battery!")

        # 更新告警状态；恢复后，下次再次触发会重新打印
        self._alarm_low_voltage_active = low_voltage
        self._alarm_low_battery_active = low_battery

    def get_status(self):
        """ Get the latest battery status.
        Returns:
            dict with keys "soc", "voltage", "soh", and "temperature"
        """
        return {
            "soc": self._soc,
            "voltage": self._voltage,
            "soh": self._soh,
            "temperature": self._temperature,
        }
    
    def _simulate_data(self):
        """Generate simulated battery data(internal use only)."""
        self._sim_update_count += 1

        # 温度随时间漂移/环境变化的模拟（简化）
        # - 环境温度围绕 self._ambient_temperature 缓慢波动
        # - 电池温度以热惯性追随环境，并叠加少量自发热（与放电强度相关）
        dt = float(self.update_interval) if self.update_interval is not None else 0.0
        if dt > 0.0:
            self._sim_time_s += dt
            # 一个“日变化/环境变化”的低频正弦 + 微小随机扰动
            # 这里用 10 分钟周期作为可视化演示；实际可以按需要调大
            env_wave = 2.0 * math.sin(2.0 * math.pi * (self._sim_time_s / 600.0))
            ambient = self._ambient_temperature + env_wave + random.uniform(-0.1, 0.1)
            # 一阶热模型：电池温度向环境靠拢
            alpha = 0.03  # 越大变化越快
            self._temperature += (ambient - self._temperature) * alpha
            # 限幅到合理范围，防止长期漂移到极端值
            self._temperature = max(-20.0, min(60.0, self._temperature))

        # 按“每秒”放电速率来模拟，避免 update_interval 很小时 SOC 掉得过快
        # base_soc_drop_per_sec 代表“每秒最多掉多少百分比”
        base_soc_drop_per_sec = random.uniform(0.0, 1.0)
        base_soc_drop = base_soc_drop_per_sec * max(dt, 0.001)
        # 温度对可用容量的影响（简化模型）
        # 低温(<10°C)：容量变小，表现为SOC下降稍快
        if self._temperature < 10.0:
            soc_drop = base_soc_drop * 1.25
        else:
            soc_drop = base_soc_drop

        # 自发热：放电越“猛”温度越容易上升（简化）
        # 为了不让温度变化太剧烈，系数取很小
        if dt > 0.0:
            self._temperature += 0.06 * base_soc_drop
            self._temperature = max(-20.0, min(60.0, self._temperature))

        # 以“可用容量（受 SOH 影响）”来计算 SOC
        effective_capacity_ah = self._nominal_capacity_ah * (self._soh / 100.0)
        if effective_capacity_ah <= 0.0:
            self._remaining_capacity_ah = 0.0
        else:
            ah_draw = effective_capacity_ah * (soc_drop / 100.0)
            self._remaining_capacity_ah = max(0.0, self._remaining_capacity_ah - ah_draw)

        # 更真实的锂电池放电曲线（分三段）
        # 100%-90%：电压缓慢下降
        # 90%-20%：平台期几乎不变（仅轻微下滑）
        # 20%-0%：电压快速下降
        #
        # 这里用平滑插值（smoothstep）避免分段处出现“折线感”
        # 该平滑函数只在这个方法里面用，在内部可以清楚看到他的作用域
        def _smoothstep01(t: float) -> float:
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            return t * t * (3.0 - 2.0 * t)

        # SOH 按“每 100 次更新下降 0.1%（百分点）”模拟，不低于 0
        if (self._sim_update_count % 100) == 0:
            self._soh = max(0.0, self._soh - 0.1)

        # SOH 下降后，可用容量变小；超过新可用容量的部分视作不可用
        effective_capacity_ah = self._nominal_capacity_ah * (self._soh / 100.0)
        if effective_capacity_ah <= 0.0:
            self._remaining_capacity_ah = 0.0
            self._soc = 0.0
        else:
            self._remaining_capacity_ah = min(self._remaining_capacity_ah, effective_capacity_ah)
            self._soc = max(0.0, min(100.0, (self._remaining_capacity_ah / effective_capacity_ah) * 100.0))

        soc = float(self._soc)
        v_full = self._v_full
        v_plateau_hi = self._v_plateau_hi
        v_plateau_lo = self._v_plateau_lo
        v_empty = self._v_empty

        if soc >= 90.0:
            # 100 -> 90 映射到 1 -> 0
            t = (100.0 - soc) / 10.0
            s = _smoothstep01(t)
            voltage = v_full + (v_plateau_hi - v_full) * s
        elif soc >= 20.0:
            # 90 -> 20 映射到 0 -> 1
            t = (90.0 - soc) / 70.0
            s = _smoothstep01(t)
            voltage = v_plateau_hi + (v_plateau_lo - v_plateau_hi) * s
        else:
            # 20 -> 0 映射到 0 -> 1
            t = (20.0 - soc) / 20.0
            s = _smoothstep01(t)
            voltage = v_plateau_lo + (v_empty - v_plateau_lo) * s

        # 高温(>35°C)：等效内阻上升/端电压略降（简化模型）
        if self._temperature > 35.0:
            voltage -= 0.08 + 0.004 * (self._temperature - 35.0)

        # 叠加小扰动 + 轻微“负载下垂”（与本次SOC下降量相关）
        voltage += random.uniform(-0.02, 0.02)
        voltage -= 0.03 * (soc_drop / 1.0)

        # 电压下限保护（避免噪声造成低于空载电压）
        self._voltage = round(max(v_empty, voltage), 2)

        # 返回最新状态
        self._log_data()
        return self._soc, self._voltage, self._soh
        
        #TODO: implement

    def _read_from_bms(self):
        """Read real battery data from the BMS(placeholder)."""
        #TODO: implement

#天际一个主函数供客户进行交互，输入 s 查看当前状态， 输入 q 退出
def main() -> None:
    monitor = BatteryMonitor()
    monitor.start_monitoring()
    print("BatteryMonitor started. Type 's' to show status, 'q' to quit.")
    try:
        while True:
            cmd = input("> ").strip().lower()
            if cmd == "s":
                status = monitor.get_status()
                print(
                    f"SOC={status['soc']:.2f}%, Voltage={status['voltage']:.2f}V, "
                    f"SOH={status['soh']:.2f}%, Temp={status['temperature']:.1f}C"
                )
            elif cmd == "q":
                break
            elif cmd == "":
                continue
            else:
                print("Unknown command. Type 's' (status) or 'q' (quit).")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()