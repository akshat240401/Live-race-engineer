from __future__ import annotations

import socket
from threading import Thread, Event
from time import sleep
from typing import Callable

from app.f1.packets import parse_packet, PacketParseError, ParsedPacket


class UDPListener:
    def __init__(self, host: str, port: int, on_packet: Callable[[ParsedPacket], None]) -> None:
        self.host = host
        self.port = port
        self.on_packet = on_packet
        self._thread: Thread | None = None
        self._stop = Event()
        self._socket: socket.socket | None = None
        self.running = False
        self.last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name="f1-udp-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._socket:
                self._socket.close()
        except Exception:
            pass
        self.running = False

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    self._socket = sock
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind((self.host, self.port))
                    sock.settimeout(0.5)
                    self.running = True
                    self.last_error = None
                    while not self._stop.is_set():
                        try:
                            data, _addr = sock.recvfrom(4096)
                        except socket.timeout:
                            continue
                        except OSError:
                            break
                        try:
                            parsed = parse_packet(data)
                            self.on_packet(parsed)
                        except PacketParseError as exc:
                            self.last_error = str(exc)
                        except Exception as exc:
                            self.last_error = f"packet handling failed: {exc}"
            except OSError as exc:
                self.running = False
                self.last_error = f"UDP bind/listen failed: {exc}"
                sleep(1.0)
            finally:
                self.running = False
                self._socket = None
