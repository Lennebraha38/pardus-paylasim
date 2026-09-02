"""PardusAgent orkestratör testleri.

ECC: AAA deseni, açıklayıcı adlar, yetenek enjeksiyonu ile izolasyon.
"""

from __future__ import annotations

from pardus_paylasim_agent.agent import PardusAgent
from pardus_paylasim_agent.capabilities import AgentCapabilities

# Tüm bağımlılıklar false → sunucu/keşif başlamaz ama __init__ güvenli.
_MINIMAL_CAPS = AgentCapabilities(
    has_mss=False,
    has_pynput=False,
    has_pillow=False,
    has_zeroconf=False,
    has_cryptography=False,
    has_gstreamer=False,
)


class TestPardusAgentInit:
    """Constructor ve property testleri."""

    def test_varsayilan_cihaz_adi_agent_icerir(self) -> None:
        agent = PardusAgent(capabilities=_MINIMAL_CAPS)
        assert "Agent" in agent._device_name

    def test_ozel_cihaz_adi(self) -> None:
        agent = PardusAgent(device_name="TestPC", capabilities=_MINIMAL_CAPS)
        assert agent._device_name == "TestPC"

    def test_yetenek_enjeksiyonu(self) -> None:
        agent = PardusAgent(capabilities=_MINIMAL_CAPS)
        assert agent.capabilities is _MINIMAL_CAPS

    def test_baslangicta_calisiyor_false(self) -> None:
        agent = PardusAgent(capabilities=_MINIMAL_CAPS)
        assert agent.is_running is False

    def test_baslangicta_pin_none(self) -> None:
        agent = PardusAgent(capabilities=_MINIMAL_CAPS)
        assert agent.pin is None

    def test_varsayilan_port(self) -> None:
        agent = PardusAgent(capabilities=_MINIMAL_CAPS)
        assert agent._port == 52345

    def test_ozel_port(self) -> None:
        agent = PardusAgent(port=12345, capabilities=_MINIMAL_CAPS)
        assert agent._port == 12345


class TestPardusAgentYasamDongusu:
    """Start/stop yaşam döngüsü."""

    def test_calismiyorken_stop_idempotent(self) -> None:
        agent = PardusAgent(capabilities=_MINIMAL_CAPS)
        agent.stop()  # hata fırlatmamalı
        assert agent.is_running is False

    def test_stop_iki_kez_idempotent(self) -> None:
        agent = PardusAgent(capabilities=_MINIMAL_CAPS)
        agent.stop()
        agent.stop()  # ikinci çağrı da güvenli
        assert agent.is_running is False


class TestImportGuvenligi:
    """Windows'ta GTK olmadan import güvenliği."""

    def test_pardus_paylasim_agent_import(self) -> None:
        import pardus_paylasim_agent

        assert hasattr(pardus_paylasim_agent, "AgentCapabilities")
        assert hasattr(pardus_paylasim_agent, "detect_agent_capabilities")

    def test_version_mevcut(self) -> None:
        import pardus_paylasim_agent

        assert hasattr(pardus_paylasim_agent, "__version__")
        assert isinstance(pardus_paylasim_agent.__version__, str)
