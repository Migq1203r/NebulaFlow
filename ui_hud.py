"""
Minimalist Floating Dictation Bar for NebulaFlow.
Ultra-sleek Wispr Flow-style floating pill displaying the reactive dotted nebula bar.
Draggable anywhere on screen, closable with Esc or '✕' button, and auto-pasting upon completion.
"""

import time
import threading
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QFrame, QGraphicsDropShadowEffect,
    QApplication, QPushButton, QMenu
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor, QCursor, QKeySequence, QShortcut, QKeyEvent

from config import config
from audio_engine import AudioRecorder
from speech_engine import transcriber
from nebula_widget import DottedNebulaBar

class FloatingHUD(QWidget):
    audio_level_signal = Signal(float)
    transcription_done_signal = Signal(dict)
    silence_timeout_signal = Signal()

    def __init__(self, on_open_settings_callback=None):
        super().__init__()
        self.on_open_settings_callback = on_open_settings_callback
        
        # Flags: Overlay window, always stay on top of ALL apps, frameless
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        
        self.target_window_id: Optional[str] = None
        self.is_recording = False
        self.record_start_time = 0.0

        # Dragging state
        self._drag_start_pos: Optional[QPoint] = None
        self._is_dragging = False

        # Audio Recorder
        self.recorder = AudioRecorder(
            on_level_update=lambda lvl: self.audio_level_signal.emit(lvl),
            on_silence_timeout=lambda: self.silence_timeout_signal.emit()
        )

        # Wire signals
        self.audio_level_signal.connect(self._on_audio_level)
        self.transcription_done_signal.connect(self._on_transcription_done)
        self.silence_timeout_signal.connect(self._on_silence_timeout)

        self._init_ui()
        self._setup_shortcuts()
        self._restore_position()

    def _init_ui(self):
        # Compact curved pill capsule
        self.setFixedSize(220, 44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)

        # Sleek dark pill frame with full capsule/stadium curvature
        self.container = QFrame(self)
        self.container.setObjectName("PillContainer")
        self.container.setCursor(Qt.CursorShape.SizeAllCursor)
        self._apply_container_style(speaking=False)

        # Soft subtle shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)

        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(14, 0, 8, 0)
        container_layout.setSpacing(4)

        # Compact Dotted Nebula Bar
        self.dots_bar = DottedNebulaBar(self, dot_count=21, width=148, height=32)
        container_layout.addWidget(self.dots_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        # Subtle close button '✕'
        self.btn_close = QPushButton("✕", self)
        self.btn_close.setFixedSize(18, 18)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setToolTip("Fechar (Esc)")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #64748B;
                border: none;
                font-size: 11px;
                font-weight: bold;
                border-radius: 9px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                background: rgba(239, 68, 68, 0.25);
            }
        """)
        self.btn_close.clicked.connect(lambda: self.hide_hud(discard=True))
        container_layout.addWidget(self.btn_close, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self.container)

    def _apply_container_style(self, speaking: bool = False):
        if speaking:
            self.container.setStyleSheet("""
                QFrame#PillContainer {
                    background: rgba(18, 20, 26, 0.96);
                    border: 1.5px solid rgba(168, 85, 247, 0.45);
                    border-radius: 18px;
                }
            """)
        else:
            self.container.setStyleSheet("""
                QFrame#PillContainer {
                    background: rgba(20, 22, 28, 0.95);
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-radius: 18px;
                }
            """)

    def _setup_shortcuts(self):
        # Escape key closes HUD immediately
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, lambda: self.hide_hud(discard=True))

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.hide_hud(discard=True)
            event.accept()
            return
        super().keyPressEvent(event)

    # -----------------------------------------------------------------
    # Position & Dragging ("mudar ele de lugar")
    # -----------------------------------------------------------------
    def _restore_position(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        screen_geo = screen.availableGeometry()

        custom_pos = config.get("hud_custom_pos", None)
        if custom_pos and isinstance(custom_pos, list) and len(custom_pos) == 2:
            x = max(screen_geo.x(), min(int(custom_pos[0]), screen_geo.x() + screen_geo.width() - self.width()))
            y = max(screen_geo.y(), min(int(custom_pos[1]), screen_geo.y() + screen_geo.height() - self.height()))
            self.move(x, y)
            return

        pos = config.get("hud_position", "bottom-center")
        x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
        
        if pos == "top-center":
            y = screen_geo.y() + 60
        elif pos == "center":
            y = screen_geo.y() + (screen_geo.height() - self.height()) // 2
        else:  # bottom-center
            y = screen_geo.y() + screen_geo.height() - self.height() - 65
            
        self.move(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging and self._drag_start_pos:
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            # Save user's custom position
            pos = self.pos()
            config.set("hud_custom_pos", [pos.x(), pos.y()])
            event.accept()

    def _show_context_menu(self, global_pt: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1A1D28;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #6D28D9;
            }
        """)
        act_reset = menu.addAction("🎯 Centralizar Posição")
        act_reset.triggered.connect(self._reset_position)

        if self.on_open_settings_callback:
            act_config = menu.addAction("⚙️ Configurações...")
            act_config.triggered.connect(self.on_open_settings_callback)

        menu.addSeparator()
        act_close = menu.addAction("✕ Fechar (Esc)")
        act_close.triggered.connect(lambda: self.hide_hud(discard=True))

        menu.exec(global_pt)

    def _reset_position(self):
        config.set("hud_custom_pos", None)
        self._restore_position()

    # -----------------------------------------------------------------
    # Show & Toggle
    # -----------------------------------------------------------------
    def show_and_trigger(self, auto_record: bool = True):
        self._restore_position()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.show()
        self.raise_()

        if auto_record and not self.is_recording:
            self.start_recording()

    def hide_hud(self, discard: bool = False):
        if self.is_recording:
            self.stop_recording(discard=discard)
        self.hide()

    def toggle_hud(self):
        if self.isVisible():
            if self.is_recording:
                # Finished speaking -> transcribe & insert immediately
                self.stop_recording()
            else:
                self.hide_hud(discard=True)
        else:
            self.show_and_trigger(auto_record=True)

    # -----------------------------------------------------------------
    # Recording Logic
    # -----------------------------------------------------------------
    def start_recording(self):
        if self.is_recording:
            return

        self.is_recording = True
        self.record_start_time = time.time()
        self._apply_container_style(speaking=True)
        self.dots_bar.set_transcribing(False)
        self.dots_bar.set_audio_level(0.0)

        try:
            self.recorder.start()
        except Exception as e:
            print(f"[HUD] Error starting recorder: {e}")
            self.is_recording = False
            self.hide()

    def stop_recording(self, discard: bool = False):
        if not self.is_recording:
            return

        self.is_recording = False
        self._apply_container_style(speaking=False)
        audio_data = self.recorder.stop()

        if discard or len(audio_data) < 2000:
            self.hide()
            return

        self.dots_bar.set_transcribing(True)

        def _transcribe():
            try:
                res = transcriber.transcribe(audio_data)
                self.transcription_done_signal.emit(res)
            except Exception as e:
                print(f"[HUD] Transcribe error: {e}")
                self.transcription_done_signal.emit({"text": ""})

        threading.Thread(target=_transcribe, daemon=True).start()

    def _on_audio_level(self, lvl: float):
        if self.is_recording:
            self.dots_bar.set_audio_level(lvl)

    def _on_silence_timeout(self):
        if self.is_recording:
            self.stop_recording()

    def _on_transcription_done(self, result: dict):
        text = result.get("text", "").strip()
        self.dots_bar.set_transcribing(False)
        # Hide HUD first so the OS/Mutter compositor restores focus to the user's active window
        self.hide()

        if text:
            print(f"[HUD] Transcribed: \"{text}\"")
            if config.get("auto_copy", False):
                transcriber.copy_to_clipboard(text)
            auto_paste = config.get("auto_paste", True)
            if auto_paste:
                transcriber.paste_into_active_window(text)
        else:
            print("[HUD] No speech detected.")
