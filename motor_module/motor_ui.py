"""
电机模拟器可视化界面（面向非开发人员）

- 大号数字显示：转速、温度、电流
- 三条简易曲线：展示最近约 1 分钟内的变化趋势
- 常用操作：上电/断电、PWM 调节、正转/反转/停止
"""

from __future__ import annotations

import time
from collections import deque
import tkinter as tk
from tkinter import ttk

from motor_simulator import MotorSimulator

# 历史窗口：约 1 分钟
HISTORY_SECONDS = 60.0
# UI 刷新间隔（毫秒）
UPDATE_MS = 500
# 每条曲线最多保留点数（防止极端高频刷新）
MAX_POINTS = 200


class _TrendCanvas(ttk.Frame):
    """简易趋势图：在 Canvas 上绘制折线，无第三方依赖。"""

    def __init__(
        self,
        master: tk.Widget,
        title: str,
        unit: str,
        line_color: str,
        height: int = 100,
    ) -> None:
        super().__init__(master)
        self._title = title
        self._unit = unit
        self._color = line_color
        self._height = height

        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text=title, font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self.range_var = tk.StringVar(value="—")
        ttk.Label(head, textvariable=self.range_var, font=("Segoe UI", 9), foreground="#555").pack(
            side="right"
        )

        self.canvas = tk.Canvas(self, height=height, background="#fafafa", highlightthickness=1, highlightbackground="#ddd")
        self.canvas.pack(fill="both", expand=True, pady=(2, 0))

    def draw(self, points: list[tuple[float, float]]) -> None:
        """points: (timestamp, value) 列表，按时间递增。"""
        self.canvas.delete("all")
        w = max(self.canvas.winfo_width(), 2)
        h = max(self.canvas.winfo_height(), 2)

        if len(points) < 2:
            self.canvas.create_text(
                w // 2,
                h // 2,
                text="暂无足够数据，稍候…",
                fill="#888",
                font=("Microsoft YaHei UI", 9),
            )
            self.range_var.set("—")
            return

        t0, t1 = points[0][0], points[-1][0]
        span = max(t1 - t0, 1e-6)
        vals = [p[1] for p in points]
        vmin, vmax = min(vals), max(vals)
        if abs(vmax - vmin) < 1e-9:
            pad = max(abs(vmax) * 0.05, 0.01)
            vmin -= pad
            vmax += pad
        else:
            pad = (vmax - vmin) * 0.1
            vmin -= pad
            vmax += pad

        self.range_var.set(f"约 {vmin:.2f} ~ {vmax:.2f} {self._unit}")

        coords: list[float] = []
        for ts, val in points:
            x = (ts - t0) / span * (w - 8) + 4
            y = h - 4 - (val - vmin) / (vmax - vmin) * (h - 8)
            coords.extend([x, y])

        self.canvas.create_line(*coords, fill=self._color, width=2, smooth=True)
        # 网格线（弱）
        for frac in (0.25, 0.5, 0.75):
            yy = 4 + frac * (h - 8)
            self.canvas.create_line(4, yy, w - 4, yy, fill="#e8e8e8")


class MotorUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("电机模拟监控")
        self.root.minsize(720, 620)

        self.motor = MotorSimulator(name="演示电机")
        self.motor.start_monitoring(interval=0.1)

        # 历史数据：(时间戳, 值)
        self._hist_speed: deque[tuple[float, float]] = deque(maxlen=MAX_POINTS)
        self._hist_temp: deque[tuple[float, float]] = deque(maxlen=MAX_POINTS)
        self._hist_curr: deque[tuple[float, float]] = deque(maxlen=MAX_POINTS)

        self._build_widgets()
        self._schedule_update()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_widgets(self) -> None:
        pad = {"padx": 12, "pady": 6}
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True, **pad)

        # 标题说明
        ttk.Label(
            main,
            text="电机运行状态一览",
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            main,
            text="下方大数字为当前值；曲线展示「最近约 1 分钟」的变化（横轴为时间流逝）。",
            font=("Microsoft YaHei UI", 10),
            foreground="#444",
            wraplength=680,
        ).pack(anchor="w", pady=(0, 8))

        # 当前数值（一目了然）
        big = ttk.LabelFrame(main, text="当前读数", padding=8)
        big.pack(fill="x", pady=(0, 8))

        row = ttk.Frame(big)
        row.pack(fill="x")

        def make_big(parent, title, var, unit, col):
            f = ttk.Frame(parent)
            f.grid(row=0, column=col, padx=16, pady=4, sticky="n")
            ttk.Label(f, text=title, font=("Microsoft YaHei UI", 11)).pack()
            ttk.Label(f, textvariable=var, font=("Segoe UI", 22, "bold")).pack()
            ttk.Label(f, text=unit, font=("Microsoft YaHei UI", 10), foreground="#666").pack()

        self.var_speed = tk.StringVar(value="—")
        self.var_temp = tk.StringVar(value="—")
        self.var_curr = tk.StringVar(value="—")
        make_big(row, "转速（模拟）", self.var_speed, "相对值 · 与 PWM 同向", 0)
        make_big(row, "温度", self.var_temp, "摄氏度 °C", 1)
        make_big(row, "电流", self.var_curr, "安培 A", 2)

        # 趋势图
        trend_frame = ttk.LabelFrame(main, text=f"最近约 {int(HISTORY_SECONDS)} 秒变化曲线", padding=8)
        trend_frame.pack(fill="both", expand=True, pady=(0, 8))

        self.trend_speed = _TrendCanvas(trend_frame, "转速变化", "", "#1f77b4", height=95)
        self.trend_speed.pack(fill="x", pady=4)
        self.trend_temp = _TrendCanvas(trend_frame, "温度变化", "°C", "#d62728", height=95)
        self.trend_temp.pack(fill="x", pady=4)
        self.trend_curr = _TrendCanvas(trend_frame, "电流变化", "A", "#2ca02c", height=95)
        self.trend_curr.pack(fill="x", pady=4)

        # 操作区
        ctrl = ttk.LabelFrame(main, text="操作（无需写代码）", padding=8)
        ctrl.pack(fill="x", pady=(0, 4))

        btn_row = ttk.Frame(ctrl)
        btn_row.pack(fill="x", pady=4)
        ttk.Button(btn_row, text="上电（允许运行）", command=self._on_enable).pack(side="left", padx=4)
        ttk.Button(btn_row, text="断电（立即停止）", command=self._on_disable).pack(side="left", padx=4)

        dir_row = ttk.Frame(ctrl)
        dir_row.pack(fill="x", pady=4)
        ttk.Label(dir_row, text="旋转方向：", font=("Microsoft YaHei UI", 10)).pack(side="left")
        ttk.Button(dir_row, text="正转", command=lambda: self._set_dir(1)).pack(side="left", padx=4)
        ttk.Button(dir_row, text="反转", command=lambda: self._set_dir(-1)).pack(side="left", padx=4)
        ttk.Button(dir_row, text="停止转动", command=lambda: self._set_dir(0)).pack(side="left", padx=4)

        pwm_row = ttk.Frame(ctrl)
        pwm_row.pack(fill="x", pady=6)
        ttk.Label(pwm_row, text="动力大小（PWM 占空比 0～100%）：", font=("Microsoft YaHei UI", 10)).pack(
            side="left"
        )
        self.pwm_var = tk.IntVar(value=0)
        scale = ttk.Scale(pwm_row, from_=0, to=100, orient="horizontal", length=320, command=self._on_pwm_scale)
        scale.pack(side="left", padx=8, fill="x", expand=True)
        self.pwm_label = ttk.Label(pwm_row, text="0 %", width=6)
        self.pwm_label.pack(side="left")

        self.status_var = tk.StringVar(value="状态：监控运行中")
        ttk.Label(main, textvariable=self.status_var, font=("Microsoft YaHei UI", 10), foreground="#2e7d32").pack(
            anchor="w"
        )

    def _on_enable(self) -> None:
        self.motor.enable()
        self.status_var.set("状态：已上电（若方向与 PWM 已设置，电机将按设定运行）")

    def _on_disable(self) -> None:
        self.motor.disable()
        self.status_var.set("状态：已断电，电机不运行")

    def _set_dir(self, d: int) -> None:
        try:
            self.motor.set_direction(d)
        except ValueError as e:
            self.status_var.set(f"操作提示：{e}")
            return
        names = {1: "正转", -1: "反转", 0: "已停止转动"}
        self.status_var.set(f"状态：方向已设为「{names[d]}」")

    def _on_pwm_scale(self, value: str) -> None:
        try:
            v = int(round(float(value)))
        except ValueError:
            return
        v = max(0, min(100, v))
        self.pwm_label.configure(text=f"{v} %")
        try:
            self.motor.set_pwm(float(v))
        except ValueError:
            pass

    def _trim_history(self, dq: deque[tuple[float, float]], now: float) -> list[tuple[float, float]]:
        cutoff = now - HISTORY_SECONDS
        return [(t, v) for t, v in dq if t >= cutoff]

    def _schedule_update(self) -> None:
        self._tick_ui()
        self.root.after(UPDATE_MS, self._schedule_update)

    def _tick_ui(self) -> None:
        now = time.time()
        st = self.motor.get_status()
        speed = float(st["speed"])
        temp = float(st["temperature"])
        curr = float(st["current"])

        self.var_speed.set(f"{speed:.1f}")
        self.var_temp.set(f"{temp:.2f}")
        self.var_curr.set(f"{curr:.2f}")

        self._hist_speed.append((now, speed))
        self._hist_temp.append((now, temp))
        self._hist_curr.append((now, curr))

        self.trend_speed.draw(self._trim_history(self._hist_speed, now))
        self.trend_temp.draw(self._trim_history(self._hist_temp, now))
        self.trend_curr.draw(self._trim_history(self._hist_curr, now))

    def _on_close(self) -> None:
        try:
            self.motor.stop_monitoring()
        except Exception:
            pass
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.15)
    except tk.TclError:
        pass
    MotorUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
