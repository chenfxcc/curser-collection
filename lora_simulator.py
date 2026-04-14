"""
LoRa 通讯行为模拟器（框架占位）。

本模块只定义类与方法签名及说明，具体逻辑待后续实现。
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Optional


class LoRaSimulator:
    """
    模拟 LoRa 链路层行为：发送队列、ACK、加解密、周期上报、接收回调等。

    配置项包括：周期性上报间隔、ACK 超时、最大重试次数、加密密钥、数据包头等；
    内部维护发送/接收队列及线程运行标志。
    """

    def __init__(
        self,
        periodic_interval_s: float = 10.0,
        ack_timeout_s: float = 0.5,
        max_retries: int = 3,
        encryption_key: Optional[bytes] = None,
        packet_header: Optional[bytes] = None,
    ) -> None:
        """
        初始化模拟器：保存配置参数，创建发送/接收队列，初始化线程与停止标志。

        Args:
            periodic_interval_s: 周期上报默认间隔（秒），默认 10。
            ack_timeout_s: 等待 ACK 的超时时间（秒），默认 0.5。
            max_retries: 单包最大重传次数，默认 3。
            encryption_key: 对称加密密钥占位；为 None 时使用单字节 0x5A。
            packet_header: 固定或前缀包头字节占位；为 None 时使用 b'\\xAA\\x55'。
        """
        # ---- 可配置链路参数（供周期上报、重传与加解密等后续逻辑使用）----
        self.periodic_interval_s = float(periodic_interval_s)
        self.ack_timeout_s = float(ack_timeout_s)
        self.max_retries = int(max_retries)
        self.encryption_key = encryption_key if encryption_key is not None else b"\x5A"
        self.packet_header = packet_header if packet_header is not None else b"\xAA\x55"

        # ---- 内部队列与状态 ----
        self.send_queue: list[dict[str, Any]] = []  # 待发送任务队列（载荷、ACK需求、重试次数）
        self.recv_queue: list[bytes] = []  # 接收到的原始链路层字节，待解析
        self.running = False  # 后台工作线程运行标志；True 表示应尝试拉队列/周期任务
        self.receive_callback: Optional[Callable[[Any], None]] = (
            None  # on_receive 注册的回调；解析成功后调用
        )
        self.periodic_task: Optional[Any] = None  # 周期上报任务配置（内容、间隔等，由 set_periodic 填充）
        self._send_thread: Optional[threading.Thread] = None
        self._pending_acks: dict[Any, threading.Event] = {}
        self._ack_lock = threading.Lock()
        self._packet_seq = 0

    def configure(self, **kwargs: Any) -> None:
        """
        运行时按关键字动态覆盖配置；未出现的键对应属性保持不变。

        Args:
            **kwargs: 仅识别以下键，其余键静默忽略：
                periodic_interval_s, ack_timeout_s, max_retries,
                encryption_key, packet_header。
        """
        # 白名单：只处理这些键，防止 **kwargs 中的无关项污染实例属性。
        allowed = frozenset(
            {
                "periodic_interval_s",
                "ack_timeout_s",
                "max_retries",
                "encryption_key",
                "packet_header",
            }
        )

        for name, value in kwargs.items():
            if name not in allowed:
                continue

            if name == "periodic_interval_s":
                # 周期上报时间基准（秒）
                self.periodic_interval_s = float(value)
            elif name == "ack_timeout_s":
                # 等待 ACK 的超时（秒）
                self.ack_timeout_s = float(value)
            elif name == "max_retries":
                # 单包最大重传次数
                self.max_retries = int(value)
            elif name == "encryption_key":
                # 对称密钥占位（字节）；调用方保证类型与后续加密实现一致
                self.encryption_key = value
            elif name == "packet_header":
                # 包头 / 前缀占位（字节）
                self.packet_header = value

    # -------------------------------------------------------------------------
    # 发送相关
    # -------------------------------------------------------------------------

    def send_data(self, data: Any, need_ack: bool = True) -> None:
        """
        外部调用：将待发送数据放入发送队列（非阻塞）；实际发送由内部工作线程处理。

        Args:
            data: 待发送数据，支持 str 或 dict。
            need_ack: 是否需要等待 ACK。
        """
        # 统一将业务数据转为 JSON 字符串，再编码为 UTF-8 字节。
        if isinstance(data, str):
            payload_json = json.dumps({"data": data}, ensure_ascii=False)
        elif isinstance(data, dict):
            payload_json = json.dumps(data, ensure_ascii=False)
        else:
            raise TypeError("data must be str or dict")

        task = {
            "data_bytes": payload_json.encode("utf-8"),
            "need_ack": bool(need_ack),
            "retries": 0,
        }

        # 记录入队前状态，若此前为空且已在运行，触发发送线程处理。
        queue_was_empty = len(self.send_queue) == 0
        self.send_queue.append(task)

        # 若尚未启动，则进行懒启动，保证发送闭环可直接工作。
        if not self.running:
            self.running = True

        if queue_was_empty and (
            self._send_thread is None or not self._send_thread.is_alive()
        ):
            self._send_thread = threading.Thread(
                target=self._process_send_queue,
                name="lora-send-worker",
                daemon=True,
            )
            self._send_thread.start()

    def _process_send_queue(self) -> None:
        """
        内部：从发送队列取包，调用组包/发送/等待 ACK，根据策略重试或丢弃。
        """
        while self.running:
            if not self.send_queue:
                time.sleep(0.1)
                continue

            task = self.send_queue[0]
            ok = self._send_packet(task["data_bytes"], task["need_ack"], task["retries"])
            if ok:
                # 成功发送并（如需要）收到 ACK，移除当前任务。
                self.send_queue.pop(0)
            else:
                # 发送失败或 ACK 超时：增加重试计数，超过阈值则丢弃。
                task["retries"] += 1
                if task["retries"] >= self.max_retries:
                    print(
                        f"[LoRa] drop packet after retries={task['retries']} "
                        f"(max={self.max_retries})"
                    )
                    self.send_queue.pop(0)

            # 短暂休眠，避免空转占用 CPU。
            time.sleep(0.1)

    def _send_packet(self, raw_bytes: bytes, need_ack: bool, retries: int) -> bool:
        """
        内部：模拟射频发送一帧（可对接 inject_received_packet 侧的对端模拟）。
        """
        # 使用单字节密钥进行按字节 XOR 加密。
        key = self.encryption_key[0] if self.encryption_key else 0x00
        encrypted = bytes((b ^ key) for b in raw_bytes)

        # 组包：header(2) + length(1) + payload + checksum(1)
        header = self.packet_header
        length = bytes([len(encrypted)])
        body = header + length + encrypted
        checksum = 0
        for b in body:
            checksum ^= b
        packet = body + bytes([checksum])

        print(
            f"[LoRa] sending packet(len={len(packet)}), "
            f"need_ack={need_ack}, retries={retries}"
        )

        if not need_ack:
            return True

        # 使用自增序号作为 packet_id，等待接收侧后续填充 ACK 触发事件。
        self._packet_seq += 1
        packet_id = self._packet_seq
        return self._wait_for_ack(packet_id)

    def _wait_for_ack(self, packet_id: Any, timeout: Optional[float] = None) -> bool:
        """
        内部：在 ack_timeout_s 内等待对端 ACK；超时则触发重试逻辑（由调用方协调）。
        """
        ack_timeout = self.ack_timeout_s if timeout is None else float(timeout)
        event = threading.Event()

        # 在等待前登记 ACK 事件，供接收线程在解析到 ACK 包后 set()。
        with self._ack_lock:
            self._pending_acks[packet_id] = event

        try:
            received = event.wait(ack_timeout)
            if not received:
                print(f"[LoRa] ACK timeout for packet_id={packet_id}")
            return received
        finally:
            # 无论成功/超时都清理，避免 pending 表增长。
            with self._ack_lock:
                self._pending_acks.pop(packet_id, None)

    # -------------------------------------------------------------------------
    # 接收相关
    # -------------------------------------------------------------------------

    def _process_recv_queue(self) -> None:
        """
        内部：处理接收队列中的原始帧：解包、校验、必要时解密，再分发或自动回复。
        """
        # 持续轮询接收队列；由 self.running 控制退出。
        while self.running:
            if self.recv_queue:
                packet_bytes = self.recv_queue.pop(0)
                data = self._parse_packet(packet_bytes)
                if data is None:
                    print(f"[LoRa] Invalid packet: {packet_bytes!r}")
                else:
                    self._auto_reply(data)
                    if self.receive_callback is not None:
                        self.receive_callback(data)

            # 小睡避免空转导致 CPU 占用过高。
            time.sleep(0.01)

    def _parse_packet(self, raw: bytes) -> Optional[Any]:
        """
        内部：解包、完整性校验、解密；成功则返回业务载荷或结构化结果，失败返回 None。

        Args:
            raw: 链路层收到的原始字节。

        Returns:
            解析后的对象或载荷；无效包返回 None（具体类型由实现约定）。
        """
        # 至少包含 header(2) + len(1) + checksum(1)。
        if len(raw) < 4:
            return None

        # 包头校验。
        if raw[:2] != self.packet_header:
            return None

        payload_len = raw[2]
        expected_len = 2 + 1 + payload_len + 1
        if len(raw) != expected_len:
            return None

        encrypted_payload = raw[3 : 3 + payload_len]
        received_checksum = raw[-1]

        # 对 header + len + payload 做异或校验。
        calc_checksum = 0
        for b in raw[:-1]:
            calc_checksum ^= b
        if calc_checksum != received_checksum:
            return None

        # 采用单字节密钥做 XOR 解密。
        key = self.encryption_key[0] if self.encryption_key else 0x00
        decrypted_bytes = bytes((b ^ key) for b in encrypted_payload)

        # 优先按 UTF-8 文本解析；若是 JSON 则转换为 Python 对象。
        try:
            text = decrypted_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return decrypted_bytes

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def _auto_reply(self, parsed: Any) -> None:
        """
        内部：根据解析结果决定是否需要自动 ACK 或其它固定响应（不经过用户回调时）。
        """
        reply_data: Optional[Any] = None

        if isinstance(parsed, dict) and "cmd" in parsed:
            cmd = parsed.get("cmd")
            if cmd == "Ping":
                reply_data = {"res": "pong"}
            elif cmd == "get_status":
                reply_data = {"battery": 85, "motor": 0}
            else:
                reply_data = {"error": "unknow cmd"}
        elif isinstance(parsed, str) and parsed == "PING":
            reply_data = "PONG"

        if reply_data is None:
            print(f"[LoRa] No auto-reply rule matched for: {parsed!r}")
            return

        print(f"[LoRa] Auto reply: {reply_data!r}")
        self.send_data(reply_data, need_ack=False)

    def on_receive(self, callback: Callable[[Any], None]) -> None:
        """
        注册接收回调：在用户数据成功解析后调用（线程与调用约定由实现定义）。

        Args:
            callback: 接收处理函数，参数一般为解析后的载荷或消息对象。
        """
        # 仅保存回调引用；解析成功时由接收线程调用。
        self.receive_callback = callback

    # -------------------------------------------------------------------------
    # 周期上报
    # -------------------------------------------------------------------------

    def set_periodic_report(self, content: bytes, interval_s: Optional[float] = None) -> None:
        """
        设置周期上报的内容与可选的新间隔；若 interval_s 为 None 则沿用当前周期配置。

        Args:
            content: 周期性上报的负载字节。
            interval_s: 覆盖全局周期间隔（秒）；None 表示不改变当前间隔。
        """
        pass

    def _periodic_report_loop(self) -> None:
        """
        内部：在独立循环中按间隔将周期内容入队或发送，直至线程停止标志置位。
        """
        pass

    # -------------------------------------------------------------------------
    # 线程管理
    # -------------------------------------------------------------------------

    def start(self) -> None:
        """启动后台工作线程（发送队列处理、接收队列处理、周期上报等，具体拆分由实现决定）。"""
        pass

    def stop(self) -> None:
        """请求停止所有后台线程并等待其退出（超时策略由实现定义）。"""
        pass

    # -------------------------------------------------------------------------
    # 测试辅助
    # -------------------------------------------------------------------------

    def inject_received_packet(self, raw: bytes) -> None:
        """
        测试/联调用：模拟从“空中”收到一帧 raw 数据，等价于写入接收队列或触发接收路径。

        Args:
            raw: 模拟接收到的完整链路层帧字节。
        """
        pass
