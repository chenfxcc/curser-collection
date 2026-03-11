import random
import threading
import os
import csv
from datetime import datetime
import math

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
        self._soh= 100.0
        self._temperature = 25.0  # °C
        self._ambient_temperature = 25.0  # °C, environmental temperature baseline
        self._sim_time_s = 0.0
       #TODO: start monitoring thread
    
    def _monitor_loop(self):
        while True:
            if self.source == "simulator":
                self._simulate_data()
            else:
                self._read_from_bms()
            threading.Event().wait(self.update_interval)
    

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
            
    def start_monitoring(self):
        """Start a background thread to update the battery data periodically."""
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()

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

        # 模拟逐渐降低的SOC (0-1% 随机下降), 保证在0-100间
        if self._soc < 0:
            self._soc = 0.0
        if self._soc > 100:
            self._soc = 100.0

        base_soc_drop = random.uniform(0.0, 1.0)
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
        self._soc = max(0.0, self._soc - soc_drop)

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

        soc = float(self._soc)
        v_full = 25.2
        v_plateau_hi = 24.7
        v_plateau_lo = 24.4
        v_empty = 22.0

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

        # SOH缓慢下降，每次减少0.01%，不低于0
        self._soh = max(0, self._soh - 0.01)

        # 返回最新状态
        self._log_data()
        return self._soc, self._voltage, self._soh
        
        #TODO: implement

    def _read_from_bms(self):
        """Read real battery data from the BMS(placeholder)."""
        #TODO: implement
        