"""
Settings Window for NebulaFlow.
Modern, fully responsive, and robust preferences window.
Features:
- Scrollable layout that fits any screen resolution
- Thread-safe live microphone preview
- 3 ways to configure shortcuts: Quick presets, interactive recorder, or direct text
- Microphone device selection
- Silence timeout slider and HUD position selection
"""

from typing import Optional, Tuple
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QPushButton, QFrame, QMessageBox, QGroupBox, QScrollArea,
    QLineEdit, QSlider
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent

from config import config
from audio_engine import AudioRecorder
from nebula_widget import DottedNebulaBar
import shortcuts

def format_human_from_gnome(gnome_str: str) -> str:
    """Converts a GNOME keybinding like '<Super><Alt>space' to 'Super + Alt + Espaço'."""
    s = gnome_str or "<Super><Alt>space"
    s = s.replace("<Super>", "Super + ")
    s = s.replace("<Control>", "Ctrl + ")
    s = s.replace("<Ctrl>", "Ctrl + ")
    s = s.replace("<Alt>", "Alt + ")
    s = s.replace("<Shift>", "Shift + ")
    s = s.replace("space", "Espaço")
    s = s.replace("Return", "Enter")
    s = s.replace("period", ".")
    s = s.replace("comma", ",")
    return s.strip(" +")


class ShortcutCaptureButton(QPushButton):
    """Interactive button that records key combinations when clicked."""
    shortcut_changed = Signal(str, str)  # (human_readable, gnome_format)

    def __init__(self, current_gnome_str: str, parent=None):
        super().__init__(parent)
        self.gnome_binding = current_gnome_str or "<Super><Alt>space"
        self.is_recording = False
        self.held_modifiers = set()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_text()
        self._apply_style()

    def _update_text(self):
        human = format_human_from_gnome(self.gnome_binding)
        self.setText(f"⌨️ Gravar: {human}")

    def _apply_style(self):
        if self.is_recording:
            self.setStyleSheet("""
                QPushButton {
                    background: rgba(236, 72, 153, 0.25);
                    border: 2px solid #EC4899;
                    color: #FFFFFF;
                    font-weight: bold;
                    border-radius: 8px;
                    padding: 8px 12px;
                    font-size: 12px;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: #1E2336;
                    border: 1px solid rgba(139, 92, 246, 0.4);
                    color: #FFFFFF;
                    font-weight: 600;
                    border-radius: 8px;
                    padding: 8px 12px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: #282E45;
                    border-color: #8B5CF6;
                }
            """)

    def mousePressEvent(self, event):
        if not self.is_recording:
            self.start_recording()
        super().mousePressEvent(event)

    def start_recording(self):
        self.is_recording = True
        self.held_modifiers.clear()
        self.setText("🔴 Aperte as teclas... (Esc p/ sair)")
        self._apply_style()
        self.setFocus()

    def stop_recording(self, restore: bool = True):
        self.is_recording = False
        self.held_modifiers.clear()
        if restore:
            self._update_text()
        self._apply_style()

    def keyPressEvent(self, event: QKeyEvent):
        if not self.is_recording:
            super().keyPressEvent(event)
            return

        key = event.key()
        mods = event.modifiers()

        if key == Qt.Key.Key_Escape:
            self.stop_recording(restore=True)
            event.accept()
            return

        # Check modifier keys (including Qt Linux Super_L/Super_R and Meta)
        modifier_keys = {
            Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
            Qt.Key.Key_AltGr, Qt.Key.Key_Meta
        }
        if hasattr(Qt.Key, "Key_Super_L"):
            modifier_keys.add(Qt.Key.Key_Super_L)
        if hasattr(Qt.Key, "Key_Super_R"):
            modifier_keys.add(Qt.Key.Key_Super_R)

        is_super = bool(mods & Qt.KeyboardModifier.MetaModifier) or key in (
            Qt.Key.Key_Meta, getattr(Qt.Key, "Key_Super_L", None), getattr(Qt.Key, "Key_Super_R", None)
        )
        is_ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier) or key in (Qt.Key.Key_Control,)
        is_alt = bool(mods & Qt.KeyboardModifier.AltModifier) or key in (Qt.Key.Key_Alt, Qt.Key.Key_AltGr)
        is_shift = bool(mods & Qt.KeyboardModifier.ShiftModifier) or key in (Qt.Key.Key_Shift,)

        if is_super: self.held_modifiers.add("Super")
        if is_ctrl: self.held_modifiers.add("Ctrl")
        if is_alt: self.held_modifiers.add("Alt")
        if is_shift: self.held_modifiers.add("Shift")

        if key in modifier_keys:
            # Standalone modifier pressed - keep recording and show feedback
            parts = []
            if "Super" in self.held_modifiers: parts.append("Super")
            if "Ctrl" in self.held_modifiers: parts.append("Ctrl")
            if "Alt" in self.held_modifiers: parts.append("Alt")
            if "Shift" in self.held_modifiers: parts.append("Shift")
            if parts:
                self.setText(f"🔴 {' + '.join(parts)} + ...")
            event.accept()
            return

        # Regular key pressed with active modifiers
        human, gnome = self._convert_key(
            key,
            "Super" in self.held_modifiers,
            "Ctrl" in self.held_modifiers,
            "Alt" in self.held_modifiers,
            "Shift" in self.held_modifiers
        )
        if human and gnome:
            self.gnome_binding = gnome
            self.is_recording = False
            self.held_modifiers.clear()
            self.setText(f"✓ {human}")
            self._apply_style()
            self.shortcut_changed.emit(human, gnome)
            event.accept()
        else:
            self.stop_recording(restore=True)

    def _convert_key(self, key: int, is_super: bool, is_ctrl: bool, is_alt: bool, is_shift: bool) -> Tuple[Optional[str], Optional[str]]:
        parts = []
        gnome_parts = []

        if is_super:
            parts.append("Super")
            gnome_parts.append("<Super>")
        if is_ctrl:
            parts.append("Ctrl")
            gnome_parts.append("<Control>")
        if is_alt:
            parts.append("Alt")
            gnome_parts.append("<Alt>")
        if is_shift:
            parts.append("Shift")
            gnome_parts.append("<Shift>")

        names = {
            Qt.Key.Key_Space: ("Espaço", "space"),
            Qt.Key.Key_Return: ("Enter", "Return"),
            Qt.Key.Key_Tab: ("Tab", "Tab"),
            Qt.Key.Key_Period: (".", "period"),
            Qt.Key.Key_Comma: (",", "comma"),
            Qt.Key.Key_Slash: ("/", "slash"),
            Qt.Key.Key_Backslash: ("\\", "backslash"),
            Qt.Key.Key_Minus: ("-", "minus"),
            Qt.Key.Key_Equal: ("=", "equal"),
            Qt.Key.Key_Semicolon: (";", "semicolon"),
        }

        if key in names:
            h, g = names[key]
            parts.append(h)
            gnome_parts.append(g)
        elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            ch = chr(key).upper()
            parts.append(ch)
            gnome_parts.append(ch.lower())
        elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            ch = chr(key)
            parts.append(ch)
            gnome_parts.append(ch)
        elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
            f = f"F{key - Qt.Key.Key_F1 + 1}"
            parts.append(f)
            gnome_parts.append(f)
        else:
            return None, None

        if not gnome_parts:
            return None, None

        return " + ".join(parts), "".join(gnome_parts)


class SettingsWindow(QMainWindow):
    mic_level_signal = Signal(float)

    def __init__(self, on_close_callback=None):
        super().__init__()
        self.on_close_callback = on_close_callback
        self.setWindowTitle("NebulaFlow • Configurações")
        self.resize(540, 680)
        self.setMinimumSize(480, 500)
        
        self.test_recorder = None
        self.is_testing_mic = False

        # Thread-safe mic visualization
        self.mic_level_signal.connect(self._on_mic_level_safe)

        self._apply_styles()
        self._init_ui()

    def _apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0E1017;
                color: #F3F4F6;
                font-family: 'Segoe UI', 'Cantarell', sans-serif;
            }
            QWidget#ScrollContainer {
                background-color: #0E1017;
            }
            QScrollArea {
                border: none;
                background-color: #0E1017;
            }
            QScrollBar:vertical {
                border: none;
                background: #141722;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #2D3748;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4B5563;
            }
            QLabel {
                color: #E2E8F0;
                font-size: 13px;
            }
            QLabel#TitleLabel {
                font-size: 20px;
                font-weight: 700;
                color: #FFFFFF;
                letter-spacing: 0.5px;
            }
            QLabel#SubTitle {
                font-size: 12px;
                color: #94A3B8;
            }
            QGroupBox {
                background-color: #141722;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                margin-top: 14px;
                padding-top: 16px;
                font-size: 12px;
                font-weight: 600;
                color: #A78BFA;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 4px;
            }
            QComboBox {
                background-color: #1D2130;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QComboBox:focus {
                border: 1px solid #8B5CF6;
            }
            QComboBox QAbstractItemView {
                background-color: #1D2130;
                color: #FFFFFF;
                selection-background-color: #6D28D9;
                border: 1px solid rgba(255, 255, 255, 0.12);
            }
            QLineEdit {
                background-color: #1D2130;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #8B5CF6;
            }
            QCheckBox {
                color: #E2E8F0;
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 1px solid #4B5563;
                background-color: #1D2130;
            }
            QCheckBox::indicator:checked {
                background-color: #8B5CF6;
                border-color: #8B5CF6;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #1D2130;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #8B5CF6;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8B5CF6, stop:1 #06B6D4);
                color: white;
                font-weight: 600;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9333EA, stop:1 #0891B2);
            }
            QPushButton#SecondaryBtn {
                background: #1D2130;
                border: 1px solid rgba(255, 255, 255, 0.12);
                color: #E2E8F0;
            }
            QPushButton#SecondaryBtn:hover {
                background: #252B3D;
                border-color: rgba(255, 255, 255, 0.2);
            }
            QPushButton#PresetBtn {
                background: #161A26;
                border: 1px solid rgba(255, 255, 255, 0.09);
                color: #C4B5FD;
                font-size: 11px;
                padding: 4px 8px;
                border-radius: 6px;
            }
            QPushButton#PresetBtn:hover {
                background: #252B3D;
                color: #FFFFFF;
                border-color: #8B5CF6;
            }
        """)

    def _init_ui(self):
        # Create scroll area wrapper to prevent clipping on any resolution
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)

        container = QWidget()
        container.setObjectName("ScrollContainer")
        scroll.setWidget(container)

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(24, 20, 24, 24)
        main_layout.setSpacing(14)

        # Header
        lbl_title = QLabel("NebulaFlow • Configurações")
        lbl_title.setObjectName("TitleLabel")
        lbl_subtitle = QLabel("Ditado por voz com inteligência artificial e visualizador de nebulosa")
        lbl_subtitle.setObjectName("SubTitle")
        main_layout.addWidget(lbl_title)
        main_layout.addWidget(lbl_subtitle)

        # -------------------------------------------------------------
        # Live Preview & Mic Test Box
        # -------------------------------------------------------------
        preview_box = QGroupBox("PRÉVIA EM TEMPO REAL & TESTE DE ÁUDIO")
        prev_layout = QVBoxLayout(preview_box)
        prev_layout.setContentsMargins(14, 12, 14, 12)
        prev_layout.setSpacing(10)

        pill_container_wrapper = QHBoxLayout()
        pill_frame = QFrame()
        pill_frame.setFixedSize(200, 38)
        pill_frame.setStyleSheet("""
            background: #181A22;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 19px;
        """)
        pill_layout = QHBoxLayout(pill_frame)
        pill_layout.setContentsMargins(12, 0, 12, 0)

        self.preview_dots = DottedNebulaBar(pill_frame, dot_count=21, width=148, height=32)
        pill_layout.addWidget(self.preview_dots, alignment=Qt.AlignmentFlag.AlignCenter)
        pill_container_wrapper.addWidget(pill_frame, alignment=Qt.AlignmentFlag.AlignCenter)
        prev_layout.addLayout(pill_container_wrapper)

        test_row = QHBoxLayout()
        self.btn_test_mic = QPushButton("🎙️ Testar Microfone (Fale para testar)")
        self.btn_test_mic.setObjectName("SecondaryBtn")
        self.btn_test_mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test_mic.clicked.connect(self._toggle_mic_test)
        test_row.addWidget(self.btn_test_mic)
        prev_layout.addLayout(test_row)

        main_layout.addWidget(preview_box)

        # -------------------------------------------------------------
        # Section: Atalho Global (3 métodos: Presets, Gravar, Digitar)
        # -------------------------------------------------------------
        shortcut_box = QGroupBox("ATALHO GLOBAL NO UBUNTU/GNOME")
        shortcut_layout = QVBoxLayout(shortcut_box)
        shortcut_layout.setSpacing(10)

        lbl_s_info = QLabel("Escolha um atalho rápido, grave com o botão ou digite manualmente:")
        lbl_s_info.setStyleSheet("color: #94A3B8; font-size: 11px;")
        shortcut_layout.addWidget(lbl_s_info)

        # Row 1: Presets
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        presets = [
            ("Super + Alt + Espaço", "<Super><Alt>space"),
            ("Ctrl + Alt + Espaço", "<Control><Alt>space"),
            ("Super + V", "<Super>v"),
            ("Super + D", "<Super>d"),
            ("Alt + Espaço", "<Alt>space"),
            ("F9", "F9"),
        ]
        for name, key_val in presets:
            btn = QPushButton(name)
            btn.setObjectName("PresetBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=key_val, n=name: self._apply_preset_shortcut(k, n))
            preset_row.addWidget(btn)
        shortcut_layout.addLayout(preset_row)

        # Row 2: Recorder Button + Direct Text Field
        rec_row = QHBoxLayout()
        rec_row.setSpacing(8)

        current_key = config.get("hotkey", "<Super><Alt>space")
        self.btn_shortcut_rec = ShortcutCaptureButton(current_key, self)
        self.btn_shortcut_rec.shortcut_changed.connect(self._on_shortcut_captured)
        rec_row.addWidget(self.btn_shortcut_rec)

        self.txt_manual_key = QLineEdit(current_key)
        self.txt_manual_key.setPlaceholderText("<Super><Alt>space")
        self.txt_manual_key.setToolTip("Digite o código GNOME (ex: <Super><Alt>space, <Super>v)")
        rec_row.addWidget(self.txt_manual_key)

        btn_apply_manual = QPushButton("Aplicar")
        btn_apply_manual.setObjectName("SecondaryBtn")
        btn_apply_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_apply_manual.clicked.connect(self._apply_manual_shortcut)
        rec_row.addWidget(btn_apply_manual)

        shortcut_layout.addLayout(rec_row)

        self.lbl_shortcut_feedback = QLabel("")
        self.lbl_shortcut_feedback.setStyleSheet("color: #34D399; font-size: 11px; font-weight: 600;")
        shortcut_layout.addWidget(self.lbl_shortcut_feedback)

        main_layout.addWidget(shortcut_box)

        # -------------------------------------------------------------
        # Section: Transcrição & IA (Whisper)
        # -------------------------------------------------------------
        whisper_box = QGroupBox("MODELO DE INTELIGÊNCIA ARTIFICIAL")
        whisper_layout = QVBoxLayout(whisper_box)
        whisper_layout.setSpacing(10)

        row_model = QHBoxLayout()
        lbl_m = QLabel("Modelo Whisper:")
        lbl_m.setFixedWidth(120)
        self.combo_model = QComboBox()
        self.combo_model.addItem("small (Recomendado • Alta Precisão)", "small")
        self.combo_model.addItem("base (Rápido • Boa Precisão)", "base")
        self.combo_model.addItem("tiny (Instantâneo • Ultraleve)", "tiny")
        cur_m = config.get("whisper_model", "small")
        for i in range(self.combo_model.count()):
            if self.combo_model.itemData(i) == cur_m:
                self.combo_model.setCurrentIndex(i)
                break
        row_model.addWidget(lbl_m)
        row_model.addWidget(self.combo_model)
        whisper_layout.addLayout(row_model)

        row_lang = QHBoxLayout()
        lbl_l = QLabel("Idioma:")
        lbl_l.setFixedWidth(120)
        self.combo_lang = QComboBox()
        self.combo_lang.addItem("Português (pt)", "pt")
        self.combo_lang.addItem("English (en)", "en")
        self.combo_lang.addItem("Español (es)", "es")
        self.combo_lang.addItem("Auto-detectar", "auto")
        cur_l = config.get("language", "pt")
        for i in range(self.combo_lang.count()):
            if self.combo_lang.itemData(i) == cur_l:
                self.combo_lang.setCurrentIndex(i)
                break
        row_lang.addWidget(lbl_l)
        row_lang.addWidget(self.combo_lang)
        whisper_layout.addLayout(row_lang)

        main_layout.addWidget(whisper_box)

        # -------------------------------------------------------------
        # Section: Microfone & Pausa
        # -------------------------------------------------------------
        audio_box = QGroupBox("ENTRADA DE ÁUDIO & PAUSA")
        audio_layout = QVBoxLayout(audio_box)
        audio_layout.setSpacing(10)

        # Mic Device row
        row_mic = QHBoxLayout()
        lbl_mic = QLabel("Microfone:")
        lbl_mic.setFixedWidth(120)
        self.combo_mic = QComboBox()
        self.combo_mic.addItem("Padrão do Sistema (PipeWire/ALSA)", None)
        devices = AudioRecorder.get_input_devices()
        cur_mic_idx = config.get("mic_device_index", None)
        for dev in devices:
            self.combo_mic.addItem(f"{dev['name']}", dev["index"])
            if cur_mic_idx is not None and dev["index"] == cur_mic_idx:
                self.combo_mic.setCurrentIndex(self.combo_mic.count() - 1)
        row_mic.addWidget(lbl_mic)
        row_mic.addWidget(self.combo_mic)
        audio_layout.addLayout(row_mic)

        # Silence timeout row
        row_silence = QHBoxLayout()
        lbl_sil = QLabel("Pausa para digitar:")
        lbl_sil.setFixedWidth(120)
        self.slider_silence = QSlider(Qt.Orientation.Horizontal)
        self.slider_silence.setRange(8, 30)  # 0.8s to 3.0s
        current_to = int(float(config.get("silence_timeout", 1.4)) * 10)
        self.slider_silence.setValue(max(8, min(30, current_to)))
        
        self.lbl_silence_val = QLabel(f"{self.slider_silence.value() / 10:.1f}s")
        self.lbl_silence_val.setFixedWidth(40)
        self.slider_silence.valueChanged.connect(lambda v: self.lbl_silence_val.setText(f"{v / 10:.1f}s"))
        
        row_silence.addWidget(lbl_sil)
        row_silence.addWidget(self.slider_silence)
        row_silence.addWidget(self.lbl_silence_val)
        audio_layout.addLayout(row_silence)

        main_layout.addWidget(audio_box)

        # -------------------------------------------------------------
        # Section: Comportamento & Posição
        # -------------------------------------------------------------
        action_box = QGroupBox("COMPORTAMENTO & POSIÇÃO")
        action_layout = QVBoxLayout(action_box)
        action_layout.setSpacing(8)

        self.chk_autopaste = QCheckBox("Digitar / colar automaticamente no app ativo após falar")
        self.chk_autopaste.setChecked(config.get("auto_paste", True))
        action_layout.addWidget(self.chk_autopaste)

        self.chk_autocopy = QCheckBox("Salvar também uma cópia na área de transferência (desativado por padrão)")
        self.chk_autocopy.setChecked(config.get("auto_copy", False))
        action_layout.addWidget(self.chk_autocopy)

        self.chk_sounds = QCheckBox("Efeitos sonoros suaves (início e término)")
        self.chk_sounds.setChecked(config.get("sound_effects", True))
        action_layout.addWidget(self.chk_sounds)

        row_pos = QHBoxLayout()
        lbl_pos_hint = QLabel("Você pode arrastar a barra flutuante livremente para onde quiser.")
        lbl_pos_hint.setStyleSheet("color: #94A3B8; font-size: 11px;")
        btn_reset_pos = QPushButton("🎯 Centralizar Barra")
        btn_reset_pos.setObjectName("SecondaryBtn")
        btn_reset_pos.clicked.connect(self._reset_position)
        row_pos.addWidget(lbl_pos_hint)
        row_pos.addWidget(btn_reset_pos)
        action_layout.addLayout(row_pos)

        main_layout.addWidget(action_box)

        # Bottom buttons
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        btn_save = QPushButton("Salvar e Fechar")
        btn_save.setMinimumWidth(160)
        btn_save.clicked.connect(self._save_and_close)
        bottom_row.addWidget(btn_save)
        main_layout.addLayout(bottom_row)

    def _on_mic_level_safe(self, lvl: float):
        self.preview_dots.set_audio_level(lvl)

    def _apply_preset_shortcut(self, gnome_key: str, human_name: str):
        self.txt_manual_key.setText(gnome_key)
        self.btn_shortcut_rec.gnome_binding = gnome_key
        self.btn_shortcut_rec._update_text()
        self._on_shortcut_captured(human_name, gnome_key)

    def _apply_manual_shortcut(self):
        gnome_key = self.txt_manual_key.text().strip()
        if not gnome_key:
            return
        human = format_human_from_gnome(gnome_key)
        self.btn_shortcut_rec.gnome_binding = gnome_key
        self.btn_shortcut_rec._update_text()
        self._on_shortcut_captured(human, gnome_key)

    def _on_shortcut_captured(self, human: str, gnome: str):
        self.txt_manual_key.setText(gnome)
        config.set("hotkey", gnome)
        ok, msg = shortcuts.register_gnome_shortcut(gnome)
        if ok:
            self.lbl_shortcut_feedback.setText(f"✓ Atalho '{human}' registrado no GNOME!")
        else:
            self.lbl_shortcut_feedback.setText(f"⚠️ Erro ao registrar atalho: {msg}")

    def _reset_position(self):
        config.set("hud_custom_pos", None)
        QMessageBox.information(self, "Posição", "A barra flutuante foi redefinida para a posição central inferior padrão.")

    def _toggle_mic_test(self):
        if self.is_testing_mic:
            self._stop_mic_test()
        else:
            self._start_mic_test()

    def _start_mic_test(self):
        self.is_testing_mic = True
        self.btn_test_mic.setText("⏹️ Parar Teste do Microfone")
        mic_idx = self.combo_mic.currentData()
        self.test_recorder = AudioRecorder(
            on_level_update=lambda lvl: self.mic_level_signal.emit(lvl)
        )
        try:
            self.test_recorder.start(device_index=mic_idx, play_sound=False)
        except Exception as e:
            QMessageBox.warning(self, "Erro no Microfone", f"Não foi possível acessar o microfone: {e}")
            self._stop_mic_test()

    def _stop_mic_test(self):
        self.is_testing_mic = False
        self.btn_test_mic.setText("🎙️ Testar Microfone (Fale para testar)")
        if self.test_recorder:
            try:
                self.test_recorder.stop(play_sound=False)
            except Exception:
                pass
            self.test_recorder = None
        self.preview_dots.set_audio_level(0.0)

    def _save_and_close(self):
        self._stop_mic_test()

        # Save & register hotkey if modified
        manual_key = self.txt_manual_key.text().strip()
        if manual_key:
            config.set("hotkey", manual_key)
            shortcuts.register_gnome_shortcut(manual_key)

        # Save AI model & reload if changed
        prev_model = config.get("whisper_model", "base")
        new_model = self.combo_model.currentData() or "base"
        config.set("whisper_model", new_model)
        if new_model != prev_model:
            from speech_engine import transcriber
            transcriber.preload_async()

        config.set("language", self.combo_lang.currentData())
        config.set("mic_device_index", self.combo_mic.currentData())
        config.set("silence_timeout", self.slider_silence.value() / 10.0)
        config.set("auto_paste", self.chk_autopaste.isChecked())
        config.set("auto_copy", self.chk_autocopy.isChecked())
        config.set("sound_effects", self.chk_sounds.isChecked())
        self.close()

    def closeEvent(self, event):
        self._stop_mic_test()
        if self.on_close_callback:
            self.on_close_callback()
        event.accept()

# Alias for compatibility
SettingsDialog = SettingsWindow
