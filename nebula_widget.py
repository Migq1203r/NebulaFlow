"""
Dotted Nebula Visualizer for NebulaFlow.
Renders an ultra-minimal horizontal dotted audio bar.
When silent/idle: 100% calm monochrome gray dots.
When speaking: vivid colorful nebula wave rises dynamically to the voice.
"""

import math
import time
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QBrush

class DottedNebulaBar(QWidget):
    def __init__(self, parent=None, dot_count: int = 21, width: int = 148, height: int = 32):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.dot_count = dot_count
        self.audio_level = 0.0          # Current smoothed level (0.0 to 1.0)
        self.target_level = 0.0         # Incoming level from mic
        self.is_transcribing = False
        self.transcribe_start_time = 0.0
        
        self.anim_time = 0.0
        self.last_time = time.time()

        # Dot dimensions
        self.dot_width = 2.6
        self.base_dot_height = 4.5
        self.max_dot_height = 20.0

        # Colors
        self.color_idle = QColor(115, 122, 138, 190)         # Calm subtle gray (from reference image)
        self.color_cyan = QColor(0, 242, 254)                 # Electric Cyan
        self.color_violet = QColor(168, 85, 247)              # Cosmic Violet
        self.color_magenta = QColor(236, 72, 153)             # Neon Magenta
        self.color_white = QColor(255, 255, 255)              # Starlight White

        # 60 FPS animation timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(16)

    def set_audio_level(self, level: float):
        self.target_level = max(0.0, min(1.0, level))

    def set_transcribing(self, transcribing: bool):
        self.is_transcribing = transcribing
        if transcribing:
            self.transcribe_start_time = time.time()
        self.update()

    def _on_tick(self):
        now = time.time()
        dt = min(0.05, now - self.last_time)
        self.last_time = now
        self.anim_time += dt

        # Smooth audio level with fast attack and gradual release
        if self.target_level > self.audio_level:
            self.audio_level += (self.target_level - self.audio_level) * 0.45
        else:
            self.audio_level += (self.target_level - self.audio_level) * 0.20

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cy = h / 2.0
        t = self.anim_time
        lvl = self.audio_level

        n = self.dot_count
        center_idx = (n - 1) / 2.0
        spread = n * 0.32

        # Dynamically calculate spacing so dots fit symmetrically and comfortably
        available_w = max(20.0, w - 14.0)
        spacing = available_w / max(1, n - 1)
        total_content_width = (n - 1) * spacing + self.dot_width
        start_x = (w - total_content_width) / 2.0

        is_trans = self.is_transcribing
        trans_phase = (t * 3.0) % 1.0 if is_trans else 0.0

        # Strict speech threshold: only show nebula colors when genuinely speaking
        is_speaking = (lvl > 0.05 and not is_trans)

        for i in range(n):
            dx = start_x + i * spacing
            gaussian = math.exp(-((i - center_idx) / spread) ** 2)

            if is_trans:
                # Transcribing fast sweep shimmer
                wave_dist = abs((i / float(max(1, n - 1))) - trans_phase)
                if wave_dist > 0.5:
                    wave_dist = 1.0 - wave_dist
                sweep = max(0.0, 1.0 - wave_dist * 4.5)
                dot_h = self.base_dot_height + sweep * 10.0
                
                c = QColor(
                    int(self.color_idle.red() * (1 - sweep) + self.color_cyan.red() * sweep),
                    int(self.color_idle.green() * (1 - sweep) + self.color_cyan.green() * sweep),
                    int(self.color_idle.blue() * (1 - sweep) + self.color_cyan.blue() * sweep),
                    int(190 + 65 * sweep)
                )
            elif is_speaking:
                # SPEAKING: Harmonic wave deformation + Colorful Nebula
                wave1 = math.sin(t * 14.0 + i * 0.50)
                wave2 = math.cos(t * 8.5 - i * 0.35)
                combined_wave = 0.65 * wave1 + 0.35 * wave2

                # Height modulated by mic volume & position
                dyn_amp = gaussian * (0.45 + 0.55 * (combined_wave + 1.0) / 2.0)
                dot_h = self.base_dot_height + (self.max_dot_height - self.base_dot_height) * (lvl * dyn_amp)

                # Nebula color ONLY for the raised wave portion
                energy = min(1.0, max(0.0, (dot_h - self.base_dot_height) / (self.max_dot_height - self.base_dot_height)))
                
                if energy < 0.12:
                    # Low/edge dots remain calm gray
                    c = self.color_idle
                elif energy < 0.55:
                    # Transition gray -> cyan / violet
                    ratio = (energy - 0.12) / 0.43
                    c = QColor(
                        int(self.color_idle.red() * (1 - ratio) + self.color_cyan.red() * ratio),
                        int(self.color_idle.green() * (1 - ratio) + self.color_violet.green() * ratio),
                        int(self.color_idle.blue() * (1 - ratio) + self.color_cyan.blue() * ratio),
                        240
                    )
                else:
                    # High wave peaks: magenta / violet -> starlight white crest
                    ratio = (energy - 0.55) / 0.45
                    c = QColor(
                        int(self.color_violet.red() * (1 - ratio) + self.color_white.red() * ratio),
                        int(self.color_magenta.green() * (1 - ratio) + self.color_white.green() * ratio),
                        int(self.color_cyan.blue() * (1 - ratio) + self.color_white.blue() * ratio),
                        255
                    )
            else:
                # SILENCE / IDLE: Pure monochrome calm gray dots (from reference image)
                dot_h = self.base_dot_height
                c = self.color_idle

            # Draw vertical rounded dot
            top_y = cy - dot_h / 2.0
            painter.setBrush(QBrush(c))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(dx, top_y, self.dot_width, dot_h, self.dot_width / 2.0, self.dot_width / 2.0)

        painter.end()


# Alias for compatibility
NebulaWidget = DottedNebulaBar
