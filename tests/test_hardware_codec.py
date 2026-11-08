"""
Pardus Paylaşım — Donanım Kodlayıcı ve Video Boru Hattı Testleri.
"""

from unittest import mock

import pytest

from pardus_paylasim.screen.hardware_codec import (
    AccelerationType,
    HardwareCodecManager,
    HardwareProfile,
)


@pytest.fixture(autouse=True)
def reset_codec_cache():
    HardwareCodecManager.reset_cache()
    yield
    HardwareCodecManager.reset_cache()


def test_detect_capabilities_software_fallback():
    with mock.patch("os.path.exists", return_value=False), mock.patch(
        "shutil.which", return_value=None
    ):
        profile = HardwareCodecManager.detect_capabilities(force_refresh=True)
        assert profile.accel_type == AccelerationType.SOFTWARE
        assert profile.encoder_name == "libx264"
        assert not profile.is_hardware
        assert profile.supports_zerolatency


def test_detect_capabilities_forced_software(monkeypatch):
    monkeypatch.setenv("PARDUS_FORCE_ACCEL", "software")
    profile = HardwareCodecManager.detect_capabilities(force_refresh=True)
    assert profile.accel_type == AccelerationType.SOFTWARE
    assert "Kullanıcı" in profile.description


def test_detect_capabilities_mock_nvenc():
    def fake_which(cmd):
        return "/usr/bin/nvidia-smi" if cmd == "nvidia-smi" else None

    fake_run = mock.MagicMock()
    fake_run.returncode = 0
    fake_run.stdout = "GPU 0: NVIDIA RTX 4090\n"

    with mock.patch("shutil.which", side_effect=fake_which), mock.patch(
        "os.path.exists", side_effect=lambda p: p == "/dev/nvidia0"
    ), mock.patch("subprocess.run", return_value=fake_run):
        profile = HardwareCodecManager.detect_capabilities(force_refresh=True)
        assert profile.accel_type == AccelerationType.NVENC
        assert profile.encoder_name == "h264_nvenc"
        assert profile.is_hardware
        assert "NVIDIA RTX 4090" in profile.description


def test_detect_capabilities_mock_vaapi():
    def fake_exists(p):
        return p == "/dev/dri/renderD128"

    def fake_which(cmd):
        return "/usr/bin/vainfo" if cmd == "vainfo" else None

    fake_run = mock.MagicMock()
    fake_run.returncode = 0
    fake_run.stdout = "VAProfileH264Main : VAEntrypointEncSlice\n"

    with mock.patch("shutil.which", side_effect=fake_which), mock.patch(
        "os.path.exists", side_effect=fake_exists
    ), mock.patch("subprocess.run", return_value=fake_run):
        profile = HardwareCodecManager.detect_capabilities(force_refresh=True)
        assert profile.accel_type == AccelerationType.VAAPI
        assert profile.encoder_name == "h264_vaapi"
        assert profile.is_hardware
        assert "VA-API" in profile.description


def test_detect_capabilities_mock_v4l2m2m():
    def fake_exists(p):
        return p == "/dev/video11"

    with mock.patch("shutil.which", return_value=None), mock.patch(
        "os.path.exists", side_effect=fake_exists
    ):
        profile = HardwareCodecManager.detect_capabilities(force_refresh=True)
        assert profile.accel_type == AccelerationType.V4L2M2M
        assert profile.encoder_name == "h264_v4l2m2m"
        assert profile.is_hardware


def test_build_gstreamer_pipeline():
    # Software pipeline
    sw_profile = HardwareProfile(
        accel_type=AccelerationType.SOFTWARE,
        device_path=None,
        encoder_name="libx264",
        description="Software",
        is_hardware=False,
        supports_zerolatency=True,
    )
    pipe_sw = HardwareCodecManager.build_gstreamer_pipeline(1920, 1080, 30, 3000, sw_profile)
    assert "x264enc" in pipe_sw
    assert "tune=zerolatency" in pipe_sw

    # VAAPI pipeline
    va_profile = HardwareProfile(
        accel_type=AccelerationType.VAAPI,
        device_path="/dev/dri/renderD128",
        encoder_name="h264_vaapi",
        description="VAAPI",
        is_hardware=True,
        supports_zerolatency=True,
    )
    pipe_va = HardwareCodecManager.build_gstreamer_pipeline(1280, 720, 60, 4000, va_profile)
    assert "vaapih264enc" in pipe_va
    assert "vaapipostproc" in pipe_va

    # NVENC pipeline
    nv_profile = HardwareProfile(
        accel_type=AccelerationType.NVENC,
        device_path="/dev/nvidia0",
        encoder_name="h264_nvenc",
        description="NVENC",
        is_hardware=True,
        supports_zerolatency=True,
    )
    pipe_nv = HardwareCodecManager.build_gstreamer_pipeline(1920, 1080, 60, 5000, nv_profile)
    assert "nvh264enc" in pipe_nv


def test_get_encoder_tuning():
    tuning_low = HardwareCodecManager.get_encoder_tuning(quality="low", fps=30)
    assert tuning_low["bitrate_kbps"] == 1200
    assert tuning_low["scale_factor"] == 0.5
    assert tuning_low["fps"] <= 20

    tuning_high = HardwareCodecManager.get_encoder_tuning(quality="high", fps=60)
    assert tuning_high["bitrate_kbps"] == 4500
    assert tuning_high["scale_factor"] == 1.0
