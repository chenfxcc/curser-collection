import tkinter as tk
from tkinter import ttk

from battery import BatteryMonitor

#简单界面交互窗口，
class BatteryUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Battery Monitor")

        self.monitor = BatteryMonitor()
        self.monitor.start_monitoring()

        self._build_widgets()
        self._schedule_update()

    def _build_widgets(self) -> None:
        padding = {"padx": 10, "pady": 5}

        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True, **padding)

        # SOC
        ttk.Label(frame, text="SOC:", font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w")
        self.soc_var = tk.StringVar()
        self.soc_label = ttk.Label(frame, textvariable=self.soc_var, font=("Segoe UI", 14, "bold"))
        self.soc_label.grid(row=0, column=1, sticky="w")

        # Voltage
        ttk.Label(frame, text="Voltage:", font=("Segoe UI", 11)).grid(row=1, column=0, sticky="w")
        self.voltage_var = tk.StringVar()
        self.voltage_label = ttk.Label(frame, textvariable=self.voltage_var, font=("Segoe UI", 12))
        self.voltage_label.grid(row=1, column=1, sticky="w")

        # SOH
        ttk.Label(frame, text="SOH:", font=("Segoe UI", 11)).grid(row=2, column=0, sticky="w")
        self.soh_var = tk.StringVar()
        self.soh_label = ttk.Label(frame, textvariable=self.soh_var, font=("Segoe UI", 12))
        self.soh_label.grid(row=2, column=1, sticky="w")

        # Temperature
        ttk.Label(frame, text="Temperature:", font=("Segoe UI", 11)).grid(row=3, column=0, sticky="w")
        self.temp_var = tk.StringVar()
        self.temp_label = ttk.Label(frame, textvariable=self.temp_var, font=("Segoe UI", 12))
        self.temp_label.grid(row=3, column=1, sticky="w")

        # Status / warnings
        ttk.Separator(frame, orient="horizontal").grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(10, 5)
        )
        ttk.Label(frame, text="Status:", font=("Segoe UI", 11)).grid(row=5, column=0, sticky="nw")
        self.status_var = tk.StringVar()
        self.status_label = ttk.Label(
            frame, textvariable=self.status_var, font=("Segoe UI", 11), foreground="green", wraplength=260
        )
        self.status_label.grid(row=5, column=1, sticky="w")

    def _schedule_update(self) -> None:
        self._update_status()
        # 500 ms update interval for UI
        self.root.after(500, self._schedule_update)

    def _update_status(self) -> None:
        status = self.monitor.get_status()
        soc = float(status["soc"])
        voltage = float(status["voltage"])
        soh = float(status["soh"])
        temp = float(status["temperature"])

        self.soc_var.set(f"{soc:.2f} %")
        self.voltage_var.set(f"{voltage:.2f} V")
        self.soh_var.set(f"{soh:.2f} %")
        self.temp_var.set(f"{temp:.1f} °C")

        # 状态与颜色
        messages = []
        color = "green"

        if voltage < 21:
            messages.append("Low voltage")
            color = "red"
        if soc < 20:
            messages.append("Low battery")
            color = "red"

        if not messages:
            messages.append("Normal")
            color = "green"

        self.status_var.set(", ".join(messages))
        self.status_label.configure(foreground=color)


def main() -> None:
    root = tk.Tk()
    BatteryUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

