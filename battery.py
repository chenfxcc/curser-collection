import random
import threading

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
       #TODO: start monitoring thread
    
    def _monitor_loop(self):
        while True:
            if self.source == "simulator":
                self._simulate_data()
            else:
                self._read_from_bms()
            threading.Event().wait(self.update_interval)

    def start_monitoring(self):
        """Start a background thread to update the battery data periodically."""
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()

    def get_status(self):
        """ Get the latest battery status.
        Returns:
            dict with keys "soc", "voltage", and "soh"
        """
        return {
            "soc": self._soc,
            "voltage": self._voltage,
            "soh": self._soh
        }
    
    def _simulate_data(self):
        """Generate simulated battery data(internal use only)."""

        # 模拟逐渐降低的SOC (0-1% 随机下降), 保证在0-100间
        soc_drop = random.uniform(0, 1)
        self._soc = max(0, self._soc - soc_drop)

        # 构建SOC与电压线性关系, soc=100%→25.2V, soc=0%→22.0V, 可加少许小扰动
        min_voltage = 22.0
        max_voltage = 25.2
        voltage = min_voltage + (max_voltage - min_voltage) * (self._soc / 100)
        voltage += random.uniform(-0.05, 0.05)  # 小扰动
        self._voltage = round(voltage, 2)

        # SOH缓慢下降，每次减少0.01%，不低于0
        self._soh = max(0, self._soh - 0.01)

        # 返回最新状态
        return self._soc, self._voltage, self._soh
        #TODO: implement

    def _read_from_bms(self):
        """Read real battery data from the BMS(placeholder)."""
        #TODO: implement
        