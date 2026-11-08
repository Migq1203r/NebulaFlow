"""
Shortcuts manager for NebulaFlow.
Manages global GNOME/Ubuntu media-keys keybindings via gsettings,
and provides background fallback hotkey listening.
"""

import os
import sys
import ast
import shutil
import subprocess
from pathlib import Path
from typing import Tuple, Optional, Callable

from config import config

APP_DIR = Path(__file__).resolve().parent
MAIN_SCRIPT = APP_DIR / "main.py"
TOGGLE_CMD = f"{sys.executable} {MAIN_SCRIPT} --toggle"
BINDING_NAME = "NebulaFlow-Dictation"
CUSTOM_PATH_BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"

def register_gnome_shortcut(binding: Optional[str] = None) -> Tuple[bool, str]:
    """
    Registers a custom global shortcut in GNOME settings daemon.
    Works seamlessly across all modern Ubuntu / Fedora GNOME Wayland sessions.
    """
    if not shutil.which("gsettings"):
        return False, "gsettings não encontrado no sistema."

    if not binding:
        binding = config.get("hotkey", "<Super><Alt>space")

    try:
        # Get existing bindings
        out = subprocess.check_output(
            ["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"],
            timeout=2.0
        ).decode().strip()

        try:
            bindings = ast.literal_eval(out)
        except Exception:
            bindings = []

        # Find existing NebulaFlow path or create a new slot
        target_path = None
        for path in bindings:
            try:
                name = subprocess.check_output(
                    ["gsettings", "get", f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{path}", "name"],
                    timeout=1.0
                ).decode().strip().strip("'\"")
                if name == BINDING_NAME:
                    target_path = path
                    break
            except Exception:
                continue

        if not target_path:
            # Create a unique path index
            existing_indices = []
            for path in bindings:
                cleaned = path.rstrip("/").split("/")[-1]
                if cleaned.startswith("custom") and cleaned[6:].isdigit():
                    existing_indices.append(int(cleaned[6:]))
            next_idx = max(existing_indices, default=-1) + 1
            target_path = f"{CUSTOM_PATH_BASE}custom{next_idx}/"
            bindings.append(target_path)
            
            # Update the list
            list_str = str(bindings)
            subprocess.run(
                ["gsettings", "set", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings", list_str],
                check=True, timeout=2.0
            )

        # Set binding properties
        schema = f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{target_path}"
        subprocess.run(["gsettings", "set", schema, "name", f"'{BINDING_NAME}'"], check=True, timeout=2.0)
        subprocess.run(["gsettings", "set", schema, "command", f"'{TOGGLE_CMD}'"], check=True, timeout=2.0)
        subprocess.run(["gsettings", "set", schema, "binding", f"'{binding}'"], check=True, timeout=2.0)

        config.set("hotkey", binding)
        print(f"[Shortcuts] Registered GNOME shortcut '{binding}' -> '{TOGGLE_CMD}' at {target_path}")
        return True, f"Atalho '{binding}' registrado com sucesso!"
    except Exception as e:
        print(f"[Shortcuts] Error registering shortcut: {e}")
        return False, str(e)


def unregister_gnome_shortcut() -> Tuple[bool, str]:
    """Removes the NebulaFlow keybinding from GNOME."""
    if not shutil.which("gsettings"):
        return False, "gsettings não encontrado."
    try:
        out = subprocess.check_output(
            ["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"],
            timeout=2.0
        ).decode().strip()
        bindings = ast.literal_eval(out)
        
        remaining = []
        for path in bindings:
            try:
                name = subprocess.check_output(
                    ["gsettings", "get", f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{path}", "name"],
                    timeout=1.0
                ).decode().strip().strip("'\"")
                if name == BINDING_NAME:
                    subprocess.run(
                        ["gsettings", "reset-recursively", f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{path}"],
                        timeout=1.0
                    )
                    continue
            except Exception:
                pass
            remaining.append(path)

        subprocess.run(
            ["gsettings", "set", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings", str(remaining)],
            check=True, timeout=2.0
        )
        return True, "Atalho desvinculado com sucesso."
    except Exception as e:
        return False, str(e)
