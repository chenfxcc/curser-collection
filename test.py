from battery import BatteryMonitor
import time

def main():
    monitor = BatteryMonitor(source="simulator", update_interval=1)
    monitor.start_monitoring()
    try:
        for i in range(10):
            status = monitor.get_status()
            print(f"Iteration {i+1}: SOC={status['soc']:.2f}%, Voltage={status['voltage']:.2f}V, SOH={status['soh']:.2f}%")
            #验证数据范围
            assert  status['soc'] >= 0, f"soc too low: {status['soc']}"
            assert  status['voltage'] >= 20,  f"voltage too low: {status['voltage']}"
            assert 0 <= status['soh'] <= 100, f"soh out of range: {status['soh']}"
            print("data is valid")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Test stopped.")
if __name__ == "__main__":
    main()