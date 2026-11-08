"""
Pardus Paylaşım — Donanım Hızlandırmalı Video Kodlayıcı & Boru Hattı Yöneticisi.

Intel/AMD (VA-API), NVIDIA (NVENC), Raspberry Pi/Rockchip (V4L2 M2M / OMX) ve
yazılımsal (x264/openh264/vpx) kodlayıcıların tespiti, otomatik seçimi ve
düşük gecikmeli ekran yayını optimizasyonunu yönetir.
"""

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class AccelerationType(str, Enum):
    VAAPI = "vaapi"
    NVENC = "nvenc"
    V4L2M2M = "v4l2m2m"
    QSV = "qsv"
    SOFTWARE = "software"
    NONE = "none"


@dataclass(frozen=True)
class HardwareProfile:
    accel_type: AccelerationType
    device_path: str | None
    encoder_name: str
    description: str
    is_hardware: bool
    supports_zerolatency: bool
    max_fps: int = 60


class HardwareCodecManager:
    """Sistem donanım kodlayıcılarını sorgular ve en uygun video boru hattını üretir."""

    _cached_profile: HardwareProfile | None = None

    @classmethod
    def reset_cache(cls) -> None:
        cls._cached_profile = None

    @classmethod
    def detect_capabilities(cls, force_refresh: bool = False) -> HardwareProfile:
        """Sistemdeki GPU donanım hızlandırma yeteneklerini tespit eder."""
        if cls._cached_profile is not None and not force_refresh:
            return cls._cached_profile

        # Ortam değişkeni zorlaması (PARDUS_FORCE_ACCEL=software/vaapi/nvenc)
        forced = os.getenv("PARDUS_FORCE_ACCEL", "").lower()
        if forced == "software":
            profile = cls._software_profile("Kullanıcı tarafından yazılımsal kodlayıcı zorlandı")
            cls._cached_profile = profile
            return profile

        # 1. NVIDIA NVENC Kontrolü
        nvenc_profile = cls._probe_nvenc()
        if nvenc_profile:
            cls._cached_profile = nvenc_profile
            return nvenc_profile

        # 2. Intel / AMD VA-API Kontrolü (/dev/dri/renderD128)
        vaapi_profile = cls._probe_vaapi()
        if vaapi_profile:
            cls._cached_profile = vaapi_profile
            return vaapi_profile

        # 3. V4L2 M2M (ARM / Raspberry Pi / Rockchip) Kontrolü
        v4l2_profile = cls._probe_v4l2m2m()
        if v4l2_profile:
            cls._cached_profile = v4l2_profile
            return v4l2_profile

        # 4. Yazılımsal Düşüş (Software Fallback)
        profile = cls._software_profile("Donanım kodlayıcı bulunamadı, CPU yazılım modu etkin")
        cls._cached_profile = profile
        return profile

    @classmethod
    def _probe_nvenc(cls) -> HardwareProfile | None:
        """NVIDIA NVENC donanım hızlandırmasını dener."""
        has_smi = shutil.which("nvidia-smi")
        has_dev = os.path.exists("/dev/nvidia0") or os.path.exists("/dev/nvidiactl")
        if has_smi or has_dev:
            # nvidia-smi başarılı mı kontrol et
            if has_smi:
                try:
                    res = subprocess.run(  # noqa: S603, S607
                        [has_smi, "-L"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if res.returncode == 0:
                        gpu_desc = res.stdout.strip().split("\n")[0]
                        return HardwareProfile(
                            accel_type=AccelerationType.NVENC,
                            device_path="/dev/nvidia0",
                            encoder_name="h264_nvenc",
                            description=f"NVIDIA NVENC Donanım Hızlandırma ({gpu_desc})",
                            is_hardware=True,
                            supports_zerolatency=True,
                            max_fps=60,
                        )
                except Exception:
                    logger.debug("nvidia-smi sorgusu başarısız", exc_info=True)
        return None

    @classmethod
    def _probe_vaapi(cls) -> HardwareProfile | None:
        """Intel/AMD VA-API render düğümlerini dener."""
        render_node = "/dev/dri/renderD128"
        if os.path.exists(render_node):
            # vainfo varsa teyit et
            vainfo = shutil.which("vainfo")
            desc = "Intel/AMD VA-API Donanım Hızlandırma"
            if vainfo:
                try:
                    res = subprocess.run(  # noqa: S603
                        [vainfo, "--display", "drm", "--device", render_node],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if "VAProfileH264" in res.stdout:
                        desc = "Intel/AMD VA-API (H.264 Donanım Kodlama Destekli)"
                except Exception:
                    logger.debug("vainfo sorgusu başarısız", exc_info=True)

            return HardwareProfile(
                accel_type=AccelerationType.VAAPI,
                device_path=render_node,
                encoder_name="h264_vaapi",
                description=desc,
                is_hardware=True,
                supports_zerolatency=True,
                max_fps=60,
            )
        return None

    @classmethod
    def _probe_v4l2m2m(cls) -> HardwareProfile | None:
        """ARM / Raspberry Pi donanım video kodlayıcısını dener."""
        for dev_node in ("/dev/video11", "/dev/video10", "/dev/video31"):
            if os.path.exists(dev_node):
                return HardwareProfile(
                    accel_type=AccelerationType.V4L2M2M,
                    device_path=dev_node,
                    encoder_name="h264_v4l2m2m",
                    description=f"V4L2 M2M ARM Donanım Kodlayıcı ({dev_node})",
                    is_hardware=True,
                    supports_zerolatency=True,
                    max_fps=30,
                )
        return None

    @classmethod
    def _software_profile(cls, reason: str) -> HardwareProfile:
        return HardwareProfile(
            accel_type=AccelerationType.SOFTWARE,
            device_path=None,
            encoder_name="libx264",
            description=reason,
            is_hardware=False,
            supports_zerolatency=True,
            max_fps=30,
        )

    @classmethod
    def build_gstreamer_pipeline(
        cls,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        bitrate_kbps: int = 3000,
        profile: HardwareProfile | None = None,
    ) -> str:
        """Seçilen donanım profiline göre optimize edilmiş GStreamer boru hattı döndürür."""
        if profile is None:
            profile = cls.detect_capabilities()

        if profile.accel_type == AccelerationType.VAAPI and profile.device_path:
            return (
                f"pipewiresrc ! videoconvert ! "
                f"vaapipostproc width={width} height={height} ! "
                f"vaapih264enc rate-control=cbr bitrate={bitrate_kbps} "
                f"tune=low-power keyframe-period={fps} ! "
                f"rtph264pay config-interval=1 pt=96"
            )
        elif profile.accel_type == AccelerationType.NVENC:
            return (
                f"pipewiresrc ! videoconvert ! videoscale ! "
                f"video/x-raw,width={width},height={height},framerate={fps}/1 ! "
                f"nvh264enc bitrate={bitrate_kbps} preset=low-latency-hq "
                f"gop-size={fps} rc-mode=cbr ! "
                f"rtph264pay config-interval=1 pt=96"
            )
        elif profile.accel_type == AccelerationType.V4L2M2M:
            return (
                f"v4l2src ! videoconvert ! "
                f"video/x-raw,width={width},height={height},framerate={fps}/1 ! "
                f"v4l2h264enc extra-controls=\"controls,h264_profile=4,video_bitrate={bitrate_kbps * 1000}\" ! "
                f"rtph264pay config-interval=1 pt=96"
            )
        else:
            # Düşük gecikmeli yazılımsal H.264
            return (
                f"pipewiresrc ! videoconvert ! videoscale ! "
                f"video/x-raw,width={width},height={height},framerate={fps}/1 ! "
                f"x264enc tune=zerolatency speed-preset=ultrafast bitrate={bitrate_kbps} "
                f"key-int-max={fps} ! "
                f"rtph264pay config-interval=1 pt=96"
            )

    @classmethod
    def get_encoder_tuning(
        cls,
        quality: str = "high",
        fps: int = 30,
    ) -> dict[str, int | str]:
        """Ekran yayını için kalite ve kare hızına göre kodlayıcı parametrelerini hesaplar."""
        quality_map = {
            "low": {"bitrate_kbps": 1200, "scale_factor": 0.5, "fps": min(fps, 20)},
            "medium": {"bitrate_kbps": 2400, "scale_factor": 0.75, "fps": min(fps, 30)},
            "high": {"bitrate_kbps": 4500, "scale_factor": 1.0, "fps": min(fps, 60)},
        }
        cfg = quality_map.get(quality, quality_map["high"])
        profile = cls.detect_capabilities()

        return {
            "encoder": profile.encoder_name,
            "is_hardware": profile.is_hardware,
            "accel_type": profile.accel_type.value,
            "bitrate_kbps": cfg["bitrate_kbps"],
            "fps": min(cfg["fps"], profile.max_fps),
            "scale_factor": cfg["scale_factor"],
            "preset": "zerolatency" if profile.supports_zerolatency else "fast",
        }
