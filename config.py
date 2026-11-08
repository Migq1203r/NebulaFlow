"""
Configuration management for NebulaFlow.
Loads and saves user settings from ~/.config/nebulaflow/config.json.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

CONFIG_DIR = Path.home() / ".config" / "nebulaflow"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "whisper_model": "small",      # small (recommended high accuracy), base, tiny
    "device": "auto",              # auto, cuda, cpu
    "language": "pt",              # pt, en, es, auto
    "hotkey": "<Super><Alt>space", # GNOME custom shortcut
    "auto_paste": True,            # Auto-paste transcribed text to active window
    "auto_copy": False,            # Do not clobber user clipboard (only if explicitly enabled)
    "sound_effects": True,         # Futuristic audio cues
    "silence_timeout": 1.4,        # Seconds of silence before auto-finish (0 to disable)
    "hud_position": "bottom-center",  # bottom-center, top-center, center
    "theme": "dark",
    "nebula_particle_count": 45,
    "mic_device_index": None,      # None for system default
    "tts_voice": "default",        # spd-say / espeak-ng voice
    "tts_rate": 0,                 # Speech speed
}

class Config:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, Any] = DEFAULT_CONFIG.copy()
        self.load()

    def load(self) -> None:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.data.update(loaded)
            except Exception as e:
                print(f"[Config] Error loading config, using defaults: {e}")
        else:
            self.save()

    def save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] Error saving config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default if default is not None else DEFAULT_CONFIG.get(key))

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()

# Global singleton
config = Config()
