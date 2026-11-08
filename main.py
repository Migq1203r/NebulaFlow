"""
NebulaFlow - Voice dictation app with minimalist dotted nebula visualizer.
Wispr Flow & native OS HUD dictation for Linux/GNOME.

Usage:
  nebulaflow                  # Launches app and opens Settings Window
  nebulaflow --toggle         # Triggers floating dotted dictation bar (global shortcut)
  nebulaflow --config         # Opens Settings Window
"""

import os
import sys
import argparse
import signal
from pathlib import Path

# Add current directory to path
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Use XCB platform on Wayland so the floating bar stays strictly on top of all applications
if "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "xcb"

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtGui import QIcon, QPixmap, QPainter, QRadialGradient, QColor

from config import config
from speech_engine import transcriber
from ui_hud import FloatingHUD
from ui_settings import SettingsWindow
from ipc import IPCServer, send_ipc_command
import shortcuts


def create_tray_icon() -> QIcon:
    """Generates an elegant cosmic nebula icon for the system tray."""
    sz = 64
    pixmap = QPixmap(sz, sz)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    cx, cy = sz / 2.0, sz / 2.0

    grad = QRadialGradient(cx, cy, sz * 0.45)
    grad.setColorAt(0.0, QColor(0, 242, 254, 255))      # Cyan
    grad.setColorAt(0.45, QColor(168, 85, 247, 220))    # Violet
    grad.setColorAt(0.85, QColor(236, 72, 153, 180))    # Magenta
    grad.setColorAt(1.0, QColor(0, 0, 0, 0))

    painter.setBrush(grad)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, sz, sz)

    core_grad = QRadialGradient(cx, cy, sz * 0.16)
    core_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
    core_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setBrush(core_grad)
    painter.drawEllipse(int(cx - sz * 0.16), int(cy - sz * 0.16), int(sz * 0.32), int(sz * 0.32))

    painter.end()
    return QIcon(pixmap)


class CommandDispatcher(QObject):
    command_received = Signal(str)

    def __init__(self, hud: FloatingHUD, get_settings_fn):
        super().__init__()
        self.hud = hud
        self.get_settings_fn = get_settings_fn
        self.command_received.connect(self._handle)

    def _handle(self, cmd: str):
        if cmd == "TOGGLE":
            self.hud.toggle_hud()
        elif cmd == "SHOW":
            self.hud.show_and_trigger(auto_record=True)
        elif cmd == "HIDE":
            self.hud.hide_hud()
        elif cmd == "CONFIG":
            settings = self.get_settings_fn()
            settings.show()
            settings.raise_()
            settings.activateWindow()


def main():
    parser = argparse.ArgumentParser(description="NebulaFlow - Dotted Voice Dictation")
    parser.add_argument("--toggle", action="store_true", help="Toggle floating dotted dictation bar")
    parser.add_argument("--show", action="store_true", help="Show dictation bar")
    parser.add_argument("--hide", action="store_true", help="Hide dictation bar")
    parser.add_argument("--config", action="store_true", help="Open Settings Window")
    parser.add_argument("--register", action="store_true", help="Register GNOME shortcut in system")
    parser.add_argument("--unregister", action="store_true", help="Remove GNOME shortcut")
    args = parser.parse_args()

    # Handle shortcut registration directly
    if args.register:
        ok, msg = shortcuts.register_gnome_shortcut()
        print(f"Status: {msg}")
        sys.exit(0 if ok else 1)

    if args.unregister:
        ok, msg = shortcuts.unregister_gnome_shortcut()
        print(f"Status: {msg}")
        sys.exit(0 if ok else 1)

    # Handle IPC commands if daemon is already running
    # If flags specified, send that command; if no flags, opening nebulaflow opens CONFIG settings
    cmd = "TOGGLE" if args.toggle else ("SHOW" if args.show else ("HIDE" if args.hide else "CONFIG"))
    resp = send_ipc_command(cmd)
    if resp is not None:
        print(f"[NebulaFlow] Sent '{cmd}' to running daemon -> {resp}")
        sys.exit(0)

    # Initialize Qt Application
    app = QApplication(sys.argv)
    app.setApplicationName("NebulaFlow")
    app.setOrganizationName("MigRDev")
    app.setQuitOnLastWindowClosed(False)

    icon = create_tray_icon()
    app.setWindowIcon(icon)

    # Settings Window (lazy loaded or persistent)
    settings_win = None
    def get_settings():
        nonlocal settings_win
        if settings_win is None:
            settings_win = SettingsWindow()
        return settings_win

    hud = FloatingHUD(on_open_settings_callback=lambda: get_settings().show())

    dispatcher = CommandDispatcher(hud, get_settings)

    # Start IPC Server
    def ipc_callback(cmd: str) -> str:
        dispatcher.command_received.emit(cmd)
        return "OK"

    ipc_server = IPCServer(on_command=ipc_callback)
    try:
        ipc_server.start()
    except RuntimeError as e:
        print(f"[NebulaFlow] {e}")
        sys.exit(0)

    # Preload Whisper in background
    transcriber.preload_async(on_ready=lambda: print("[NebulaFlow] Whisper model preloaded & ready on GPU!"))

    # Auto-register GNOME shortcut if needed
    QTimer.singleShot(1000, lambda: shortcuts.register_gnome_shortcut())

    # Setup System Tray
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("NebulaFlow - Ditado por Voz")

    menu = QMenu()
    act_toggle = menu.addAction("🎙️ Gravar / Ditar (Atalho)")
    act_toggle.triggered.connect(hud.toggle_hud)

    act_settings = menu.addAction("⚙️ Configurações...")
    act_settings.triggered.connect(lambda: get_settings().show())

    menu.addSeparator()
    act_quit = menu.addAction("✕ Sair do NebulaFlow")
    def quit_app():
        ipc_server.stop()
        app.quit()
    act_quit.triggered.connect(quit_app)

    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: hud.toggle_hud() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()

    # Launch behavior:
    if args.toggle or args.show:
        # User triggered shortcut -> show floating dotted bar immediately
        QTimer.singleShot(100, lambda: hud.show_and_trigger(auto_record=True))
    else:
        # User opened the app directly -> show Settings Window as requested!
        QTimer.singleShot(100, lambda: get_settings().show())

    # Signal handling
    signal.signal(signal.SIGINT, lambda sig, frame: quit_app())

    # Keep Python event loop processing
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(500)

    print("🌌 NebulaFlow is running in background!")
    print(f"👉 Press your global shortcut ({config.get('hotkey', '<Super><Alt>space')}) anytime to dictate!")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
