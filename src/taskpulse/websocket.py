from __future__ import annotations

import base64
import hashlib
import socket
import struct
import threading
from http.server import BaseHTTPRequestHandler
from threading import Lock
from typing import Callable


WEBSOCKET_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def compute_accept(key: str) -> str:
    digest = hashlib.sha1((key + WEBSOCKET_MAGIC).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


class WebSocketConnection:
    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._sock.settimeout(None)
        self._closed = False

    def send_text(self, message: str) -> None:
        if self._closed:
            return
        payload = message.encode("utf-8")
        header = self._build_header(0x1, payload)
        try:
            self._sock.sendall(header + payload)
        except OSError:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass

    def listen(self, on_close: Callable[[], None]) -> None:
        try:
            while not self._closed:
                header = self._recv_exact(2)
                if header is None:
                    break

                opcode = header[0] & 0x0F
                masked = bool(header[1] & 0x80)
                length = header[1] & 0x7F

                if length == 126:
                    extended = self._recv_exact(2)
                    if extended is None:
                        break
                    length = struct.unpack(">H", extended)[0]
                elif length == 127:
                    extended = self._recv_exact(8)
                    if extended is None:
                        break
                    length = struct.unpack(">Q", extended)[0]

                mask = None
                if masked:
                    mask = self._recv_exact(4)
                    if mask is None:
                        break

                payload = self._recv_exact(length) if length else b""
                if payload is None:
                    break

                if masked and mask is not None:
                    payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))

                if opcode == 0x8:
                    break
                if opcode == 0x9:
                    self._send_pong(payload)
        finally:
            self.close()
            on_close()

    def _send_pong(self, payload: bytes) -> None:
        header = self._build_header(0xA, payload)
        try:
            self._sock.sendall(header + payload)
        except OSError:
            self.close()

    def _build_header(self, opcode: int, payload: bytes) -> bytes:
        length = len(payload)
        first = 0x80 | opcode
        if length < 126:
            return bytes([first, length])
        if length < 65536:
            return bytes([first, 126]) + struct.pack(">H", length)
        return bytes([first, 127]) + struct.pack(">Q", length)

    def _recv_exact(self, size: int) -> bytes | None:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            try:
                chunk = self._sock.recv(remaining)
            except OSError:
                return None
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


class WebSocketHub:
    def __init__(self) -> None:
        self._clients: set[WebSocketConnection] = set()
        self._lock = Lock()

    def add(self, client: WebSocketConnection) -> None:
        with self._lock:
            self._clients.add(client)

    def remove(self, client: WebSocketConnection) -> None:
        with self._lock:
            self._clients.discard(client)

    def broadcast(self, message: str) -> None:
        with self._lock:
            clients = list(self._clients)

        stale: list[WebSocketConnection] = []
        for client in clients:
            try:
                client.send_text(message)
            except OSError:
                stale.append(client)

        if stale:
            with self._lock:
                for client in stale:
                    self._clients.discard(client)


def handle_websocket_upgrade(
    handler: BaseHTTPRequestHandler,
    hub: WebSocketHub,
) -> None:
    key = handler.headers.get("Sec-WebSocket-Key")
    if not key:
        handler.send_error(400, "Missing Sec-WebSocket-Key header.")
        return

    accept = compute_accept(key)
    handler.send_response(101, "Switching Protocols")
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", accept)
    handler.end_headers()

    client = WebSocketConnection(handler.connection)
    hub.add(client)

    def on_close() -> None:
        hub.remove(client)

    thread = threading.Thread(
        target=client.listen,
        args=(on_close,),
        daemon=True,
        name="taskpulse-ws-client",
    )
    thread.start()