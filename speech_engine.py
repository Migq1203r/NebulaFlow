"""
Speech Engine for NebulaFlow.
Loads OpenAI Whisper on CUDA/CPU with background preloading,
transcribes voice audio, copies text to clipboard (wl-copy) and auto-pastes into active applications.
"""

import time
import subprocess
import threading
import numpy as np
import torch
import whisper
from typing import Optional, Callable
from config import config
from audio_engine import SoundEffects

def preprocess_audio(audio: np.ndarray, sr: int = 16000) -> np.ndarray:
    """
    Normalizes volume and trims non-speech silence padding from start/end
    to maximize Whisper accuracy and eliminate hallucinations.
    """
    if len(audio) < sr * 0.1:
        return audio

    # 1. Normalize peak amplitude to standard dynamic range
    peak = float(np.max(np.abs(audio)))
    if peak > 0.005:
        audio = (audio / peak) * 0.92

    # 2. Trim silence padding from edges (20ms frames)
    frame_size = int(sr * 0.02)
    num_frames = len(audio) // frame_size
    if num_frames < 5:
        return audio

    energies = [
        float(np.sqrt(np.mean(audio[i * frame_size : (i + 1) * frame_size] ** 2)))
        for i in range(num_frames)
    ]
    
    thresh = 0.025
    start_frame = 0
    end_frame = num_frames - 1

    # Speech onset with 140ms pre-roll
    for i in range(num_frames):
        if energies[i] > thresh:
            start_frame = max(0, i - 7)
            break

    # Speech offset with 200ms post-roll
    for i in range(num_frames - 1, -1, -1):
        if energies[i] > thresh:
            end_frame = min(num_frames - 1, i + 10)
            break

    if start_frame < end_frame:
        start_idx = start_frame * frame_size
        end_idx = min(len(audio), (end_frame + 1) * frame_size)
        trimmed = audio[start_idx:end_idx]
        if len(trimmed) > sr * 0.2:
            return trimmed

    return audio


class SpeechTranscriber:
    def __init__(self):
        self.model = None
        self.current_model_name = ""
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.is_loading = False
        self.is_transcribing = False
        self._lock = threading.Lock()

    def preload_async(self, on_ready: Optional[Callable[[], None]] = None):
        """Asynchronously pre-loads whisper model on app launch."""
        thread = threading.Thread(target=self._load_model, args=(on_ready,), daemon=True)
        thread.start()

    def _load_model(self, on_ready: Optional[Callable[[], None]] = None):
        with self._lock:
            model_name = config.get("whisper_model", "small")
            # Guard against medium model causing system OOM crash on 8GB RAM machines
            if model_name == "medium":
                print("[SpeechEngine] Switching 'medium' to 'small' for optimal speed and accuracy.")
                model_name = "small"
                config.set("whisper_model", "small")

            user_device = config.get("device", "auto")
            if user_device in ["cuda", "cpu"]:
                self.device = user_device if (user_device != "cuda" or torch.cuda.is_available()) else "cpu"
            else:
                self.device = "cuda" if torch.cuda.is_available() else "cpu"

            if self.model is not None and self.current_model_name == model_name:
                if on_ready:
                    on_ready()
                return

            self.is_loading = True
            print(f"[SpeechEngine] Loading Whisper '{model_name}' on {self.device.upper()}...")
            t0 = time.time()
            try:
                self.model = whisper.load_model(model_name, device=self.device)
                self.current_model_name = model_name
                print(f"[SpeechEngine] Model '{model_name}' loaded in {time.time() - t0:.2f}s!")
            except Exception as e:
                print(f"[SpeechEngine] Error loading model '{model_name}': {e}")
                # Fallback to base or tiny if small fails
                fallback = "base" if model_name != "base" else "tiny"
                print(f"[SpeechEngine] Falling back to '{fallback}'...")
                self.model = whisper.load_model(fallback, device=self.device)
                self.current_model_name = fallback
            finally:
                self.is_loading = False
                if on_ready:
                    on_ready()

    def transcribe(self, audio: np.ndarray, language: Optional[str] = None) -> dict:
        """
        Transcribes 16kHz float32 audio with preprocessing and high-accuracy settings.
        Returns dict with: 'text', 'language', 'duration_s', 'latency_s'
        """
        if self.model is None or self.is_loading:
            self._load_model()

        if len(audio) < 1600:  # Less than 0.1s
            return {"text": "", "language": "", "duration_s": 0.0, "latency_s": 0.0}

        # Preprocess audio (peak normalize and trim silence)
        cleaned_audio = preprocess_audio(audio)
        audio_duration = len(cleaned_audio) / 16000.0
        
        if language is None:
            language = config.get("language", "pt")
        if language == "auto":
            language = None

        self.is_transcribing = True
        print(f"[SpeechEngine] Transcribing {audio_duration:.1f}s of clean audio with '{self.current_model_name}'...")
        t0 = time.time()
        try:
            fp16 = (self.device == "cuda")
            result = self.model.transcribe(
                cleaned_audio,
                language=language or "pt",
                initial_prompt="Transcrição em português brasileiro, mantendo pontuação natural, clareza e termos exatos.",
                condition_on_previous_text=False,
                beam_size=1,
                temperature=0.0,
                compression_ratio_threshold=2.2,
                no_speech_threshold=0.6,
                logprob_threshold=-1.0,
                fp16=fp16
            )
            # Filter low-confidence or no-speech segments
            valid_segments = []
            for seg in result.get("segments", []):
                no_speech = seg.get("no_speech_prob", 0.0)
                avg_logprob = seg.get("avg_logprob", 0.0)
                comp_ratio = seg.get("compression_ratio", 0.0)
                if no_speech > 0.60 or avg_logprob < -1.1 or comp_ratio > 2.2:
                    continue
                valid_segments.append(seg.get("text", ""))

            raw_text = " ".join(valid_segments).strip() if valid_segments else result.get("text", "").strip()
            detected_lang = result.get("language", language or "pt")
            latency = time.time() - t0

            # Clean leading/trailing artifacts and repetitive loops
            cleaned_text = self._clean_text(raw_text)
            print(f"[SpeechEngine] Transcribed: \"{cleaned_text}\" (latency: {latency:.2f}s)")

            return {
                "text": cleaned_text,
                "language": detected_lang,
                "duration_s": audio_duration,
                "latency_s": latency
            }
        except Exception as e:
            print(f"[SpeechEngine] Transcribe error: {e}")
            return {"text": "", "error": str(e), "duration_s": audio_duration, "latency_s": 0.0}
        finally:
            self.is_transcribing = False

    def _clean_text(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""

        lower = text.lower().strip(".!?,")
        hallucinations = {
            "obrigado", "obrigada", "obrigado por assistir", "obrigada por assistir",
            "thank you", "thank you for watching", "subtitles by", "legendas",
            "legendas por", "se inscreva no canal", "inscreva-se no canal",
            "se inscreva no canal e se inscreva no canal", "deixe seu like",
            "deixe o like", "tchau", "valeu", "até a próxima", "ate a proxima",
            "fui", "...", ".", ","
        }
        if lower in hallucinations:
            return ""

        # Suppress repetitive phrase loops (e.g. "o que é o que é o que é...")
        words = text.split()
        if len(words) >= 4:
            for n in (1, 2, 3, 4):
                ngrams = [" ".join(words[i : i + n]).lower() for i in range(0, len(words) - n + 1, n)]
                if len(ngrams) >= 3:
                    most_common = max(set(ngrams), key=ngrams.count)
                    if ngrams.count(most_common) >= 3 and (ngrams.count(most_common) / len(ngrams)) > 0.45:
                        return ""

        # Clean repetitive start phrases
        for h in hallucinations:
            if len(h) > 5 and lower.startswith(h):
                remainder = lower.replace(h, "").strip(" e,.!-")
                if not remainder:
                    return ""

        return text

    @staticmethod
    def copy_to_clipboard(text: str) -> bool:
        """Copies text to both Wayland and X11 system clipboards."""
        if not text:
            return False

        copied = False
        # Try wl-copy (standard Wayland tool)
        try:
            proc = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-8"), timeout=1.0)
            if proc.returncode == 0:
                copied = True
        except Exception:
            pass

        # Also populate xclip for X11/XWayland compatibility
        try:
            proc = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-8"), timeout=1.0)
            if proc.returncode == 0:
                copied = True
        except Exception:
            pass

        if copied:
            SoundEffects.play_success()

        return copied

    @staticmethod
    def _is_emojify_available() -> bool:
        """Checks if the GNOME Shell EmojifyBridge extension is active."""
        try:
            res = subprocess.run(
                ["gnome-extensions", "list", "--enabled"],
                capture_output=True,
                text=True,
                timeout=0.5
            )
            return "emojify-extension@riothedev.xyz" in res.stdout
        except Exception:
            return False

    @staticmethod
    def paste_into_active_window(text: str = ""):
        """
        Pastes text directly into the currently active window (e.g. Google Chrome, text editor, chat).
        Uses GNOME Shell's native Clutter virtual keyboard (Emojify extension) if available,
        or xdotool as fallback.
        Preserves the user's existing clipboard so voice dictation never overwrites copied items.
        """
        if not text:
            return

        def _paste():
            # 1. Capture the user's existing clipboard before pasting
            orig_clip: Optional[str] = None
            try:
                out = subprocess.check_output(
                    ["xclip", "-o", "-selection", "clipboard"],
                    stderr=subprocess.DEVNULL,
                    timeout=0.25
                ).decode("utf-8", errors="ignore")
                if out:
                    orig_clip = out
            except Exception:
                pass

            # Allow Mutter/GNOME Shell 200ms to return focus to the target window
            time.sleep(0.20)
            print(f"[SpeechEngine] Injected text: \"{text}\" -> Pasting into active window...")

            # 2. Prefer GNOME Shell native virtual keyboard via Emojify extension
            pasted = False
            if SpeechTranscriber._is_emojify_available():
                try:
                    res = subprocess.run([
                        "gdbus", "emit",
                        "--session",
                        "--object-path", "/xyz/riothedev/EmojifyBridge",
                        "--signal", "xyz.riothedev.EmojifyBridge.EmojiSelected",
                        text
                    ], capture_output=True, timeout=1.0)
                    if res.returncode == 0:
                        pasted = True
                except Exception as e:
                    print(f"[SpeechEngine] D-Bus virtual keyboard error: {e}")

            # 3. ONLY if GNOME virtual keyboard is not available, fallback to xdotool
            if not pasted:
                try:
                    SpeechTranscriber.copy_to_clipboard(text)
                    time.sleep(0.05)
                    subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"], timeout=1.0)
                    pasted = True
                except Exception as e:
                    print(f"[SpeechEngine] xdotool fallback error: {e}")

            # 4. If auto_copy is disabled, RESTORE the user's original clipboard!
            if not config.get("auto_copy", False):
                time.sleep(0.40)  # Wait for target app to finish pasting (emojify takes 250ms + 50ms)
                if orig_clip:
                    try:
                        p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
                        p.communicate(orig_clip.encode("utf-8"), timeout=0.5)
                    except Exception:
                        pass
                    try:
                        p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
                        p.communicate(orig_clip.encode("utf-8"), timeout=0.5)
                    except Exception:
                        pass
                    print("[SpeechEngine] Original clipboard restored successfully.")
                else:
                    # Clear temporary paste text from clipboard
                    try:
                        subprocess.run(["wl-copy", "--clear"], timeout=0.5)
                    except Exception:
                        pass
                    try:
                        p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
                        p.communicate(b"", timeout=0.5)
                    except Exception:
                        pass
                    print("[SpeechEngine] Temporary paste buffer cleared from clipboard.")

        threading.Thread(target=_paste, daemon=True).start()

    @staticmethod
    def get_active_window_id() -> Optional[str]:
        try:
            out = subprocess.check_output(["xdotool", "getactivewindow"], timeout=0.5).decode().strip()
            return out if out else None
        except Exception:
            return None


# Global transcriber singleton
transcriber = SpeechTranscriber()
