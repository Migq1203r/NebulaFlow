"""
Audio Engine for NebulaFlow.
Handles microphone recording, real-time RMS audio level calculation for the visualizer,
silence detection, and procedural futuristic sound effects.
"""

import time
import math
import threading
import numpy as np
import sounddevice as sd
from typing import Callable, Optional, List
from config import config

SAMPLE_RATE = 16000  # Native Whisper rate
CHANNELS = 1

class SoundEffects:
    """Procedurally synthesizes smooth sci-fi chimes using sounddevice and numpy."""
    
    @staticmethod
    def play_start():
        if not config.get("sound_effects", True):
            return
        def _run():
            try:
                sr = 44100
                t1 = np.linspace(0, 0.08, int(sr * 0.08), False)
                t2 = np.linspace(0, 0.12, int(sr * 0.12), False)
                # Soft sine wave blip rising
                w1 = 0.08 * np.sin(2 * np.pi * 587.33 * t1) * np.hanning(len(t1))  # D5
                w2 = 0.12 * np.sin(2 * np.pi * 880.00 * t2) * np.hanning(len(t2))  # A5
                wave = np.concatenate([w1, w2])
                sd.play(wave, sr)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    @staticmethod
    def play_stop():
        if not config.get("sound_effects", True):
            return
        def _run():
            try:
                sr = 44100
                t = np.linspace(0, 0.10, int(sr * 0.10), False)
                # Soft descending chime
                freq = np.linspace(880, 520, len(t))
                wave = 0.09 * np.sin(2 * np.pi * freq * t) * np.hanning(len(t))
                sd.play(wave, sr)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    @staticmethod
    def play_success():
        if not config.get("sound_effects", True):
            return
        def _run():
            try:
                sr = 44100
                t = np.linspace(0, 0.18, int(sr * 0.18), False)
                # Harmonious chord (A5 + C#6 + E6)
                c1 = np.sin(2 * np.pi * 880.0 * t)
                c2 = np.sin(2 * np.pi * 1108.7 * t)
                c3 = np.sin(2 * np.pi * 1318.5 * t)
                envelope = np.exp(-t * 12)
                wave = (0.05 * c1 + 0.04 * c2 + 0.03 * c3) * envelope
                sd.play(wave.astype(np.float32), sr)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()


class AudioRecorder:
    def __init__(self,
                 on_level_update: Optional[Callable[[float], None]] = None,
                 on_silence_timeout: Optional[Callable[[], None]] = None):
        self.on_level_update = on_level_update
        self.on_silence_timeout = on_silence_timeout
        
        self.is_recording = False
        self.stream: Optional[sd.InputStream] = None
        self.audio_frames: List[np.ndarray] = []
        
        self.last_speech_time = 0.0
        self.noise_floor = 0.015
        self.speech_threshold = 0.035
        self.calibration_frames = 0
        self.silence_timeout = float(config.get("silence_timeout", 1.4))
        self.has_spoken = False
        self.start_time = 0.0
        self.max_recording_seconds = 45.0

    def start(self, device_index: Optional[int] = None, play_sound: bool = True):
        if self.is_recording:
            return

        self.audio_frames.clear()
        self.is_recording = True
        self.has_spoken = False
        self.calibration_frames = 0
        self.noise_floor = 0.015
        self.speech_threshold = 0.035
        self.start_time = time.time()
        self.last_speech_time = time.time()
        self.silence_timeout = float(config.get("silence_timeout", 1.4))
        
        if device_index is None:
            device_index = config.get("mic_device_index", None)

        if play_sound:
            SoundEffects.play_start()

        def audio_callback(indata, frames, time_info, status):
            if not self.is_recording:
                return

            # Keep copy of audio buffer
            audio_copy = indata[:, 0].copy()
            self.audio_frames.append(audio_copy)

            # Compute RMS level
            rms = float(np.sqrt(np.mean(audio_copy ** 2)))
            
            # Dynamic calibration during first ~0.4s (12 blocks of 512 samples)
            if self.calibration_frames < 12:
                self.calibration_frames += 1
                if self.calibration_frames == 1:
                    self.noise_floor = rms
                else:
                    self.noise_floor = 0.7 * self.noise_floor + 0.3 * rms
                self.speech_threshold = max(0.020, self.noise_floor * 1.55 + 0.015)
                level = 0.0
            else:
                # Slowly adapt noise floor down if quieter ambient is found
                if rms < self.noise_floor:
                    self.noise_floor = 0.95 * self.noise_floor + 0.05 * rms
                    self.speech_threshold = max(0.020, self.noise_floor * 1.55 + 0.015)

                # Signal above ambient noise floor
                excess = max(0.0, rms - self.noise_floor)
                # Level scaled from 0.0 to 1.0 for the nebula visualizer
                level = min(1.0, math.sqrt(excess * 10.0))

            if self.on_level_update:
                self.on_level_update(level)

            now = time.time()
            if self.calibration_frames >= 12:
                if rms > self.speech_threshold:
                    self.last_speech_time = now
                    if not self.has_spoken:
                        self.has_spoken = True
                        print(f"[AudioRecorder] Speech detected! (RMS: {rms:.4f} > Threshold: {self.speech_threshold:.4f})")
                elif self.has_spoken and self.silence_timeout > 0:
                    if (now - self.last_speech_time) >= self.silence_timeout:
                        # Silence detected after speech!
                        print(f"[AudioRecorder] Silence detected ({self.silence_timeout:.1f}s), finishing dictation...")
                        if self.on_silence_timeout:
                            self.on_silence_timeout()
                elif (now - self.start_time) >= self.max_recording_seconds:
                    # Max recording limit reached
                    print("[AudioRecorder] Max recording limit reached, stopping...")
                    if self.on_silence_timeout:
                        self.on_silence_timeout()

        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                device=device_index,
                blocksize=512,  # ~32ms blocks for ultra-low latency visualization
                callback=audio_callback
            )
            self.stream.start()
        except Exception as e:
            print(f"[AudioRecorder] Error starting stream: {e}")
            self.is_recording = False
            raise

    def stop(self, play_sound: bool = True) -> np.ndarray:
        if not self.is_recording:
            return np.array([], dtype=np.float32)

        self.is_recording = False
        if play_sound:
            SoundEffects.play_stop()

        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                print(f"[AudioRecorder] Error closing stream: {e}")
            finally:
                self.stream = None

        if not self.audio_frames:
            return np.array([], dtype=np.float32)

        audio_data = np.concatenate(self.audio_frames)
        self.audio_frames.clear()
        return audio_data

    @staticmethod
    def get_input_devices() -> List[dict]:
        devices = []
        try:
            dev_list = sd.query_devices()
            for idx, dev in enumerate(dev_list):
                if dev.get("max_input_channels", 0) > 0:
                    devices.append({
                        "index": idx,
                        "name": dev.get("name", f"Microphone {idx}"),
                        "channels": dev.get("max_input_channels", 1),
                        "default": idx == sd.default.device[0]
                    })
        except Exception as e:
            print(f"[AudioRecorder] Error querying devices: {e}")
        return devices
