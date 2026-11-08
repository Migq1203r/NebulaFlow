"""
Text-to-Speech (TTS) Engine for NebulaFlow.
Speaks text using system tools (spd-say / espeak-ng) with real-time state tracking
and audio pulsation feedback for the Nebula visualizer.
"""

import math
import time
import shutil
import subprocess
import threading
from typing import Optional, Callable
from config import config

class TTSEngine:
    def __init__(self,
                 on_start: Optional[Callable[[], None]] = None,
                 on_finish: Optional[Callable[[], None]] = None,
                 on_level_update: Optional[Callable[[float], None]] = None):
        self.on_start = on_start
        self.on_finish = on_finish
        self.on_level_update = on_level_update
        self.is_speaking = False
        self._current_process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()

    def speak(self, text: str, language: str = "pt"):
        """Speaks the text aloud in a background thread."""
        if not text.strip():
            return

        self.stop()
        self._stop_event.clear()
        self.is_speaking = True

        def _worker():
            if self.on_start:
                self.on_start()

            # Launch visualizer pulsing simulator during speech
            anim_stop = threading.Event()
            def _pulse_sim():
                t = 0.0
                while not anim_stop.is_set():
                    # Generate natural speech-like undulating amplitude
                    level = 0.35 + 0.35 * math.sin(t * 8.0) * math.cos(t * 3.7) + 0.15 * math.sin(t * 14.0)
                    level = max(0.05, min(0.9, level))
                    if self.on_level_update:
                        self.on_level_update(level)
                    t += 0.03
                    time.sleep(0.03)

            pulse_thread = threading.Thread(target=_pulse_sim, daemon=True)
            pulse_thread.start()

            try:
                if shutil.which("spd-say"):
                    rate = str(config.get("tts_rate", 0))
                    cmd = ["spd-say", "-l", language, "-r", rate, text]
                    self._current_process = subprocess.Popen(cmd)
                    self._current_process.wait()
                elif shutil.which("espeak-ng"):
                    cmd = ["espeak-ng", "-v", language, text]
                    self._current_process = subprocess.Popen(cmd)
                    self._current_process.wait()
                else:
                    print("[TTSEngine] Neither spd-say nor espeak-ng is available.")
            except Exception as e:
                print(f"[TTSEngine] Playback error: {e}")
            finally:
                anim_stop.set()
                self.is_speaking = False
                self._current_process = None
                if self.on_level_update:
                    self.on_level_update(0.0)
                if self.on_finish:
                    self.on_finish()

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def stop(self):
        self._stop_event.set()
        if self._current_process and self._current_process.poll() is None:
            try:
                self._current_process.terminate()
            except Exception:
                pass
            self._current_process = None
        self.is_speaking = False


# Global TTS singleton
tts_engine = TTSEngine()
