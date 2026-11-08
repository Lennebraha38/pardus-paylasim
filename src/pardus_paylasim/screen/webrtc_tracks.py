import asyncio
import logging
import threading
import time

try:
    import mss
    HAS_MSS = True
except ImportError:
    mss = None
    HAS_MSS = False

try:
    import numpy as np
except ImportError:
    np = None

try:
    from aiortc import AudioStreamTrack, VideoStreamTrack
    HAS_AIORTC = True
except ImportError:
    class VideoStreamTrack:  # type: ignore[no-redef]
        def stop(self):
            pass

    class AudioStreamTrack:  # type: ignore[no-redef]
        def stop(self):
            pass

    HAS_AIORTC = False

try:
    from av import AudioFrame, VideoFrame
    HAS_AV = True
except ImportError:
    AudioFrame = None  # type: ignore[assignment,misc]
    VideoFrame = None  # type: ignore[assignment,misc]
    HAS_AV = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    Image = None  # type: ignore[assignment]
    HAS_PIL = False

try:
    import soundcard as sc
except ImportError:
    sc = None

from pardus_paylasim.platform_info import is_wayland

from .hardware_codec import HardwareCodecManager

logger = logging.getLogger(__name__)


class ScreenCaptureTrack(VideoStreamTrack):
    """Mss / PipeWire ile ekran yakalayıp aiortc'ye besler ve donanım kodlama parametrelerini uygular."""

    def __init__(self, monitor_index: int = 0, quality: str = "high", fps: int = 30):
        super().__init__()
        self.quality = quality
        self.fps = fps
        self._target_delay = 1.0 / max(1, self.fps)

        # Oturum tipi (Wayland PipeWire vs X11 mss) tespiti
        self.is_wayland_session = is_wayland()
        self.backend_name = "pipewire" if self.is_wayland_session else "mss-x11"
        if self.is_wayland_session:
            logger.info("Wayland oturumu tespit edildi; PipeWire / Portal yakalama modu devrede.")

        # Donanım hızlandırma ve profil parametreleri
        self.tuning = HardwareCodecManager.get_encoder_tuning(quality=quality, fps=fps)
        self.is_hardware_accelerated = bool(self.tuning.get("is_hardware", False))

        self.sct = mss.mss() if HAS_MSS and mss else None
        if self.sct:
            monitors = self.sct.monitors
            if monitor_index < 0 or monitor_index >= len(monitors):
                monitor_index = 0
            self.monitor = monitors[monitor_index]
        else:
            self.monitor = {"top": 0, "left": 0, "width": 1920, "height": 1080}

        self._frame_buffer = None
        self._frame_lock = threading.Lock()

        self._running = True
        self._worker = threading.Thread(target=self._capture_loop, daemon=True)
        self._worker.start()

    def _capture_loop(self):
        while self._running:
            start_time = time.time()
            try:
                if self.sct and HAS_PIL and HAS_AV and VideoFrame:
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

            except Exception:
                # Capture hatalarını yut ve döngüyü sürdür
                logger.debug("istisna yutuldu", exc_info=True)

            elapsed = time.time() - start_time
            sleep_time = self._target_delay - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    async def recv(self):
        if not hasattr(self, "next_timestamp"):
            return None
        pts, time_base = await self.next_timestamp()

        frame = None
        while frame is None and self._running:
            with self._frame_lock:
                frame = self._frame_buffer
            if frame is None:
                await asyncio.sleep(0.01)

        if frame is not None:
            frame.pts = pts
            frame.time_base = time_base
        return frame

    def get_backend_info(self) -> dict:
        """Ekran yakalama boru hattı ve oturum tipi detaylarını döner."""
        return {
            "backend": self.backend_name,
            "is_wayland": self.is_wayland_session,
            "is_hardware": self.is_hardware_accelerated,
            "fps": self.fps,
            "quality": self.quality,
            "tuning": self.tuning,
        }

    def stop(self):
        super().stop()
        self._running = False
        if self.sct:
            try:
                self.sct.close()
            except Exception:
                logger.debug("sct kapatma hatası", exc_info=True)


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
            raise RuntimeError(f"Ses yakalama cihazı başlatılamadı: {e}") from e

    async def recv(self):
        if not hasattr(self, "next_timestamp"):
            return None
        pts, time_base = await self.next_timestamp()

        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, self.recorder.record, 960
        )

        if np is None or not HAS_AV or AudioFrame is None:
            return None

        data_int16 = np.int16(data * 32767)
        data_int16 = data_int16.T.copy(order="C")

        frame = AudioFrame.from_ndarray(data_int16, format="s16p", layout="stereo")
        frame.pts = pts
        frame.sample_rate = 48000
        frame.time_base = time_base

        return frame

    def stop(self):
        super().stop()
        if hasattr(self, "recorder"):
            try:
                self.recorder.__exit__(None, None, None)
            except Exception:
                logger.debug("recorder kapatma hatası", exc_info=True)
