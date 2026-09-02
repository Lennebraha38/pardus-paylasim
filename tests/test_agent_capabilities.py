"""AgentCapabilities tespit testleri.

ECC: pytest AAA deseni, açıklayıcı adlar, monkeypatch izolasyonu.
"""

from __future__ import annotations

import pytest

from pardus_paylasim_agent.capabilities import (
    AgentCapabilities,
    _probe_import,
    detect_agent_capabilities,
)


class TestProbeImport:
    """_probe_import modül mevcutluk tespiti."""

    def test_mevcut_modul_true_doner(self) -> None:
        # Düzenle/Çalıştır — stdlib modülü her zaman var
        result = _probe_import("os")
        # Doğrula
        assert result is True

    def test_varolmayan_modul_false_doner(self) -> None:
        result = _probe_import("varolmayan_modul_xyz_12345")
        assert result is False


class TestAgentCapabilities:
    """AgentCapabilities frozen DTO ve bileşik property'ler."""

    @pytest.fixture()
    def hepsi_true(self) -> AgentCapabilities:
        return AgentCapabilities(
            has_mss=True,
            has_pynput=True,
            has_pillow=True,
            has_zeroconf=True,
            has_cryptography=True,
            has_gstreamer=True,
        )

    @pytest.fixture()
    def hepsi_false(self) -> AgentCapabilities:
        return AgentCapabilities(
            has_mss=False,
            has_pynput=False,
            has_pillow=False,
            has_zeroconf=False,
            has_cryptography=False,
            has_gstreamer=False,
        )

    def test_frozen_degistirilemez(self, hepsi_true: AgentCapabilities) -> None:
        with pytest.raises(AttributeError):
            hepsi_true.has_mss = False  # type: ignore[misc]

    def test_can_capture_mss_ve_pillow_gerektirir(self) -> None:
        # Yalnız mss var, pillow yok → False
        caps = AgentCapabilities(
            has_mss=True,
            has_pynput=False,
            has_pillow=False,
            has_zeroconf=False,
            has_cryptography=False,
            has_gstreamer=False,
        )
        assert caps.can_capture is False

        # İkisi de var → True
        caps2 = AgentCapabilities(
            has_mss=True,
            has_pynput=False,
            has_pillow=True,
            has_zeroconf=False,
            has_cryptography=False,
            has_gstreamer=False,
        )
        assert caps2.can_capture is True

    def test_can_inject_pynput_gerektirir(self, hepsi_false: AgentCapabilities) -> None:
        assert hepsi_false.can_inject is False

    def test_can_serve_yakalama_ve_enjeksiyon_gerektirir(
        self, hepsi_true: AgentCapabilities
    ) -> None:
        assert hepsi_true.can_serve is True

    def test_can_discover_zeroconf_gerektirir(self, hepsi_false: AgentCapabilities) -> None:
        assert hepsi_false.can_discover is False

    def test_can_tls_cryptography_gerektirir(self, hepsi_true: AgentCapabilities) -> None:
        assert hepsi_true.can_tls is True

    def test_summary_hepsi_true(self, hepsi_true: AgentCapabilities) -> None:
        s = hepsi_true.summary()
        assert "capture(mss+PIL)" in s
        assert "inject(pynput)" in s
        assert "mdns(zeroconf)" in s
        assert "tls(cryptography)" in s

    def test_summary_hepsi_false(self, hepsi_false: AgentCapabilities) -> None:
        assert hepsi_false.summary() == "no_capabilities"

    def test_summary_kismi(self) -> None:
        caps = AgentCapabilities(
            has_mss=True,
            has_pynput=False,
            has_pillow=True,
            has_zeroconf=False,
            has_cryptography=True,
            has_gstreamer=False,
        )
        s = caps.summary()
        assert "capture(mss+PIL)" in s
        assert "inject(pynput)" not in s
        assert "tls(cryptography)" in s


class TestDetectAgentCapabilities:
    """detect_agent_capabilities() runtime entegrasyonu."""

    def test_agent_capabilities_ornegi_doner(self) -> None:
        caps = detect_agent_capabilities()
        assert isinstance(caps, AgentCapabilities)

    def test_stdlib_dogru_tespit_eder(self) -> None:
        caps = detect_agent_capabilities()
        # has_gstreamer Windows'ta tipik False, her zaman bool
        assert isinstance(caps.has_gstreamer, bool)
