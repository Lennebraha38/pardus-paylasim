import asyncio
import time

import mss
import numpy as np
from aiortc import AudioStreamTrack, VideoStreamTrack
from av import AudioFrame, VideoFrame
from PIL import Image

try:
    import soundcard as sc
except ImportError:
    sc = None

import threading


class ScreenCaptureTrack(VideoStreamTrack):
    """Mss ile ekran yakalayıp aiortc'ye besler (Faz 5.5 Worker Thread)."""

    def __init__(self, monitor_index=0, quality="high", fps=30):
        super().__init__()
        self.quality = quality
        self.fps = fps
        self._target_delay = 1.0 / self.fps

        self.sct = mss.mss()
        monitors = self.sct.monitors
        if monitor_index < 0 or monitor_index >= len(monitors):
            monitor_index = 0
        self.monitor = monitors[monitor_index]

        self._frame_buffer = None
        self._frame_lock = threading.Lock()

        self._running = True
        self._worker = threading.Thread(target=self._capture_loop, daemon=True)
        self._worker.start()

    def _capture_loop(self):
        while self._running:
            start_time = time.time()
            try:
                sct_img = self.sct.grab(self.monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                if self.quality == "low":
                    img = img.resize((img.width // 2, img.height // 2), Image.Resampling.LANCZOS)
                elif self.quality == "medium":
                    img = img.resize(
                        (int(img.width * 0.75), int(img.height * 0.75)), Image.Resampling.LANCZOS
                    )

                frame = VideoFrame.from_image(img)

                with self._frame_lock:
                    self._frame_buffer = frame

            except Exception as e:
                # Capture hatalarını yut ve döngüyü sürdür
                pass

            elapsed = time.time() - start_time
            sleep_time = self._target_delay - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        frame = None
        while frame is None:
            with self._frame_lock:
                frame = self._frame_buffer
            if frame is None:
                await asyncio.sleep(0.01)

        # Aiortc frame timestamp'i set eder
        frame.pts = pts
        frame.time_base = time_base
        return frame

    def stop(self):
        super().stop()
        self._running = False
        if self.sct:
            self.sct.close()


class AudioCaptureTrack(AudioStreamTrack):
    """Sistem sesini (loopback) yakalayıp aiortc'ye besler."""

    def __init__(self):
        super().__init__()
        self._timestamp = 0
        if sc is None:
            raise RuntimeError("soundcard modülü yüklü değil, ses aktarımı kullanılamaz.")

        try:
            self.mic = sc.default_speaker().name
            self.recorder = sc.default_speaker().recorder(samplerate=48000, channels=2)
            self.recorder.__enter__()  # Başlat
        except Exception as e:
            raise RuntimeError(f"Ses yakalama cihazı başlatılamadı: {e}")

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        # Sesi oku (bloklamaması için ufak chunk)
        # sc.recorder senkron okur, asyncio dünyasında event loop'u bloklamamak için küçük boyut
        # (Gerçek kullanımda run_in_executor önerilir ancak basit MVP için)
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, self.recorder.record, 960
        )  # 960 frame = 20ms @ 48kHz

        # data = (frames, channels) numpy array, float32, aralığı -1..1
        # av kütüphanesi için int16 array'e çevirmeliyiz (plan: s16)
        data_int16 = np.int16(data * 32767)
        # av AudioFrame beklenen format: channels x frames
        data_int16 = data_int16.T.copy(order="C")

        frame = AudioFrame.from_ndarray(data_int16, format="s16p", layout="stereo")
        frame.pts = pts
        frame.sample_rate = 48000
        frame.time_base = time_base

        return frame

    def stop(self):
        super().stop()
        if hasattr(self, "recorder"):
            self.recorder.__exit__(None, None, None)
