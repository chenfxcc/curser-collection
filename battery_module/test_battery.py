"""Short demo: prints a few samples. Interactive mode: ``python battery_simulator.py``."""

import time

from battery_simulator import BatteryMonitor


def main() -> None:
    monitor = BatteryMonitor()
    monitor.start_monitoring()
    for i in range(10):
        st = monitor.get_status()
        print(
            f"{i + 1}/10 SOC={st['soc']:.2f}% V={st['voltage']:.2f}V "
            f"SOH={st['soh']:.2f}% T={st['temperature']:.1f}C"
        )
        time.sleep(max(float(monitor.update_interval), 0.05))


if __name__ == "__main__":
    main()
