"""
LoRaSimulator 功能测试脚本。

测试目标：
1) 验证发送能力（主动 send_data）。
2) 验证接收能力（inject_received_packet 注入完整协议包并解析）。
3) 验证周期上报能力（电池状态周期上报 + 报警信息独立周期线程）。
4) 验证回调能力（接收回调中打印数据并模拟执行电机动作）。
"""

from __future__ import annotations

import json
import random
import threading
import time
from typing import Any

from lora_simulator import LoRaSimulator


def log_out(message: str) -> None:
    """发送方向日志。"""
    print(f"[OUT ->] {message}")


def log_in(message: str) -> None:
    """接收方向日志。"""
    print(f"[IN <-] {message}")


def log_sys(message: str) -> None:
    """系统状态日志。"""
    print(f"[SYS] {message}")


def build_packet(sim: LoRaSimulator, payload_obj: Any) -> bytes:
    """
    复用 LoRaSimulator 的链路规则手动构造完整数据包：
    header(2) + length(1) + encrypted_payload + checksum(1)。
    """
    payload_json = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")
    key = sim.encryption_key[0] if sim.encryption_key else 0x00
    encrypted = bytes((b ^ key) for b in payload_json)

    body = sim.packet_header + bytes([len(encrypted)]) + encrypted
    checksum = 0
    for b in body:
        checksum ^= b
    return body + bytes([checksum])


def make_alarm_report() -> dict[str, Any]:
    """生成报警上报数据，随机给出是否触发报警。"""
    alarm_active = random.choice([True, False])
    return {
        "type": "alarm_report",
        "alarm": "overheat" if alarm_active else "none",
        "active": alarm_active,
        "ts": int(time.time()),
    }


def alarm_report_worker(sim: LoRaSimulator, stop_event: threading.Event, interval_s: float) -> None:
    """
    独立周期任务：每隔 interval_s 秒上报一次报警信息。
    这里使用单独线程来满足“第二个周期任务”的需求。
    """
    while not stop_event.is_set():
        report = make_alarm_report()
        sim.send_data(report, need_ack=False)
        log_out(f"报警周期上报: {report}")

        # 用 Event.wait 代替 sleep，便于 stop_event 触发后尽快退出。
        stop_event.wait(interval_s)


def on_receive(data: Any) -> None:
    """
    接收回调：打印接收到的数据，并根据指令模拟执行动作。
    """
    log_in(f"收到数据: {data}")

    # 按约定识别“驱动电机启动”指令，模拟执行日志。
    if isinstance(data, dict):
        cmd = data.get("cmd")
        action = data.get("action")
        target = data.get("target")
        speed = data.get("speed", 80)

        if cmd == "motor_control" and action == "start" and target == "drive_motor":
            print(f"[IN <-][执行] 电机正转，速度{speed}")


if __name__ == "__main__":
    # ---------------------------------------------------------------------
    # 1) 创建模拟器实例并配置参数
    # ---------------------------------------------------------------------
    sim = LoRaSimulator(
        periodic_interval_s=15.0,  # 默认周期上报间隔（场景要求 15s）
        ack_timeout_s=0.5,
        max_retries=3,
    )
    sim.configure(packet_header=b"\xAA\x55")

    # ---------------------------------------------------------------------
    # 2) 注册接收回调：打印数据 + 模拟电机执行
    # ---------------------------------------------------------------------
    sim.on_receive(on_receive)

    # ---------------------------------------------------------------------
    # 3) 启动模拟器后台线程
    # ---------------------------------------------------------------------
    sim.start()
    log_sys("LoRaSimulator 已启动")

    # ---------------------------------------------------------------------
    # 4) 设置周期上报任务
    #    - 主周期任务：每 15s 上报电池状态（带时间戳）
    #    - 第二个周期任务：独立线程每 20s 上报报警信息
    # ---------------------------------------------------------------------
    battery_report = {
        "type": "battery_report",
        "battery": 85,
        "ts": int(time.time()),
    }
    sim.set_periodic_report(battery_report, interval=15.0)
    log_sys(f"已设置电池周期上报: {battery_report}")

    alarm_stop_event = threading.Event()
    alarm_thread = threading.Thread(
        target=alarm_report_worker,
        args=(sim, alarm_stop_event, 20.0),
        daemon=True,
    )
    alarm_thread.start()
    log_sys("已启动报警周期上报线程（20s）")

    # ---------------------------------------------------------------------
    # 5) 主动发送一条电池状态信息
    # ---------------------------------------------------------------------
    active_battery = {
        "type": "battery_report_manual",
        "battery": random.choice([79, 80]),
        "ts": int(time.time()),
    }
    sim.send_data(active_battery, need_ack=False)
    log_out(f"主动发送电池状态: {active_battery}")

    # ---------------------------------------------------------------------
    # 6) 构造“驱动电机启动”完整协议包并注入接收队列
    # ---------------------------------------------------------------------
    motor_cmd = {
        "cmd": "motor_control",
        "target": "drive_motor",
        "action": "start",
        "speed": 80,
        "ts": int(time.time()),
    }
    motor_packet = build_packet(sim, motor_cmd)
    log_in(f"准备注入电机启动指令包（模拟外部输入）: {motor_cmd}")
    sim.inject_received_packet(motor_packet)
    log_in(f"已注入电机启动指令包，长度={len(motor_packet)}")

    # ---------------------------------------------------------------------
    # 7) 运行时长：演示用 10 秒，持续观察发送/接收/回调输出
    # ---------------------------------------------------------------------
    run_seconds = 10
    log_sys(f"开始观察 {run_seconds} 秒...")
    time.sleep(run_seconds)

    # ---------------------------------------------------------------------
    # 8) 停止测试：先停报警线程，再停止模拟器
    # ---------------------------------------------------------------------
    alarm_stop_event.set()
    if alarm_thread.is_alive():
        alarm_thread.join(timeout=2)

    sim.stop()
    log_sys("LoRaSimulator 已停止，测试结束")
