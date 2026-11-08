"""
IPC (Inter-Process Communication) for NebulaFlow using UNIX domain sockets.
Enables instant hotkey toggling (<5ms) from GNOME keybindings or CLI triggers.
"""

import os
import socket
import threading
from pathlib import Path
from typing import Callable, Optional

def get_socket_path() -> str:
    uid = os.getuid()
    return f"/tmp/nebulaflow_{uid}.sock"

class IPCServer:
    def __init__(self, on_command: Callable[[str], str]):
        self.on_command = on_command
        self.socket_path = get_socket_path()
        self.server_sock: Optional[socket.socket] = None
        self.is_running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        if self.is_running:
            return

        # Clean existing stale socket
        if os.path.exists(self.socket_path):
            try:
                # Test if another instance is alive
                test_s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                test_s.connect(self.socket_path)
                test_s.close()
                raise RuntimeError("Another instance of NebulaFlow is already running!")
            except ConnectionRefusedError:
                # Stale file, remove it
                os.remove(self.socket_path)
            except Exception:
                if os.path.exists(self.socket_path):
                    os.remove(self.socket_path)

        self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_sock.bind(self.socket_path)
        self.server_sock.listen(5)
        self.is_running = True

        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print(f"[IPC] Listening on {self.socket_path}")

    def _loop(self):
        while self.is_running and self.server_sock:
            try:
                conn, _ = self.server_sock.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
            except Exception:
                break

    def _handle_client(self, conn: socket.socket):
        try:
            data = conn.recv(1024).decode("utf-8").strip()
            if data:
                resp = self.on_command(data)
                conn.sendall(resp.encode("utf-8"))
        except Exception as e:
            print(f"[IPC] Client error: {e}")
        finally:
            conn.close()

    def stop(self):
        self.is_running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except Exception:
                pass


def send_ipc_command(cmd: str, timeout: float = 1.0) -> Optional[str]:
    """Sends a command to the running NebulaFlow instance."""
    sock_path = get_socket_path()
    if not os.path.exists(sock_path):
        return None

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(sock_path)
        s.sendall(cmd.encode("utf-8"))
        resp = s.recv(1024).decode("utf-8").strip()
        s.close()
        return resp
    except Exception:
        return None
