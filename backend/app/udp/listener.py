from __future__ import annotations

import socket
from collections import deque
from statistics import median
from threading import Event, Lock, Thread, current_thread
from time import perf_counter, time
from typing import Callable

from app.f1.packets import (
    PacketParseError,
    ParsedPacket,
    parse_packet,
)


class UDPListener:
    """Receive, timestamp and parse F1 UDP packets on one background thread."""

    def __init__(
        self,
        host: str,
        port: int,
        on_packet: Callable[[ParsedPacket], None],
    ) -> None:
        self.host = host
        self.port = int(port)
        self.on_packet = on_packet

        self.running = False
        self.last_error: str | None = None

        self._stop_event = Event()
        self._thread: Thread | None = None
        self._socket: socket.socket | None = None
        self._lock = Lock()

        self._received_count = 0
        self._parsed_count = 0
        self._parse_error_count = 0
        self._callback_error_count = 0
        self._last_datagram_unix_s: float | None = None
        self._last_parsed_unix_s: float | None = None
        self._parse_latency_ms: deque[float] = deque(maxlen=512)
        self._callback_latency_ms: deque[float] = deque(maxlen=512)

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            self._stop_event.clear()
            self._thread = Thread(
                target=self._run,
                name="f1-udp-listener",
                daemon=True,
            )
            self.running = True
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        sock = self._socket
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

        thread = self._thread
        if (
            thread is not None
            and thread.is_alive()
            and thread is not current_thread()
        ):
            thread.join(timeout=2.0)

        with self._lock:
            self.running = False
            self._thread = None
            self._socket = None

    def _run(self) -> None:
        sock: socket.socket | None = None
        try:
            sock = socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM,
            )
            sock.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_REUSEADDR,
                1,
            )
            try:
                sock.setsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_RCVBUF,
                    4 * 1024 * 1024,
                )
            except OSError:
                # Some operating systems cap the receive buffer.
                pass

            sock.settimeout(0.5)
            sock.bind((self.host, self.port))
            self._socket = sock
            self.last_error = None

            while not self._stop_event.is_set():
                try:
                    data, address = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                except OSError as exc:
                    if self._stop_event.is_set():
                        break
                    self.last_error = str(exc)
                    continue

                received_unix_s = time()
                received_monotonic_s = perf_counter()
                with self._lock:
                    self._received_count += 1
                    self._last_datagram_unix_s = (
                        received_unix_s
                    )

                parse_started = perf_counter()
                try:
                    packet = parse_packet(data)
                except PacketParseError as exc:
                    with self._lock:
                        self._parse_error_count += 1
                    self.last_error = f"Packet parse error: {exc}"
                    continue
                except Exception as exc:
                    with self._lock:
                        self._parse_error_count += 1
                    self.last_error = (
                        f"Unexpected packet parse error: {exc}"
                    )
                    continue

                parsed_monotonic_s = perf_counter()
                parse_latency_ms = max(
                    0.0,
                    (
                        parsed_monotonic_s
                        - parse_started
                    )
                    * 1000.0,
                )

                packet.meta.update(
                    {
                        "received_at_unix_s": (
                            received_unix_s
                        ),
                        "received_at_monotonic_s": (
                            received_monotonic_s
                        ),
                        "parsed_at_monotonic_s": (
                            parsed_monotonic_s
                        ),
                        "parse_latency_ms": parse_latency_ms,
                        "source_host": address[0],
                        "source_port": int(address[1]),
                        "datagram_size": len(data),
                    }
                )

                with self._lock:
                    self._parsed_count += 1
                    self._last_parsed_unix_s = time()
                    self._parse_latency_ms.append(
                        parse_latency_ms
                    )

                callback_started = perf_counter()
                packet.meta["callback_started_monotonic_s"] = (
                    callback_started
                )
                try:
                    self.on_packet(packet)
                except Exception as exc:
                    with self._lock:
                        self._callback_error_count += 1
                    self.last_error = (
                        f"Packet callback error: {exc}"
                    )
                    continue
                finally:
                    callback_latency_ms = max(
                        0.0,
                        (
                            perf_counter()
                            - callback_started
                        )
                        * 1000.0,
                    )
                    with self._lock:
                        self._callback_latency_ms.append(
                            callback_latency_ms
                        )

                self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            with self._lock:
                self.running = False
                self._socket = None

    @staticmethod
    def _summary(values: deque[float]) -> dict[str, float | int]:
        rows = list(values)
        if not rows:
            return {
                "latest_ms": 0.0,
                "median_ms": 0.0,
                "max_ms": 0.0,
                "sample_count": 0,
            }
        return {
            "latest_ms": round(rows[-1], 3),
            "median_ms": round(median(rows), 3),
            "max_ms": round(max(rows), 3),
            "sample_count": len(rows),
        }

    def diagnostics(self) -> dict:
        with self._lock:
            now = time()
            return {
                "running": self.running,
                "host": self.host,
                "port": self.port,
                "last_error": self.last_error,
                "received_count": self._received_count,
                "parsed_count": self._parsed_count,
                "parse_error_count": (
                    self._parse_error_count
                ),
                "callback_error_count": (
                    self._callback_error_count
                ),
                "last_datagram_age_s": (
                    None
                    if self._last_datagram_unix_s is None
                    else round(
                        max(
                            0.0,
                            now - self._last_datagram_unix_s,
                        ),
                        4,
                    )
                ),
                "last_parsed_age_s": (
                    None
                    if self._last_parsed_unix_s is None
                    else round(
                        max(
                            0.0,
                            now - self._last_parsed_unix_s,
                        ),
                        4,
                    )
                ),
                "parse_latency": self._summary(
                    self._parse_latency_ms
                ),
                "callback_latency": self._summary(
                    self._callback_latency_ms
                ),
            }
