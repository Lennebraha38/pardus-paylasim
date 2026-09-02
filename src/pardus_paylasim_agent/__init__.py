"""
Pardus Paylaşım — Windows companion agent (Faz 3, GTK YOK).

Bu paket mevcut sunucu/protokol katmanlarını (`ScreenStreamServer`,
`ControlChannelServer`, `MDNSDiscovery`, `input_inject`) platform-nötr
backend'lerle yeniden kullanır: enjeksiyon `pynput` (Windows/X11), yakalama
`mss` (Faz 3.2). GTK/GStreamer/Linux-only araçlara bağlı DEĞİLDİR → Windows'ta
çalışır. Base view-only uygulama bu paketin bağımlılıklarını (mss/pynput)
KAZANMAZ; hepsi opsiyonel `agent` grubudur.

Genel API:
    PardusAgent               — GTK-free yönlendirme çekirdeği.
    detect_agent_capabilities — saf yetenek/bağımlılık tespiti.
    AgentCapabilities         — tespit sonucu (frozen dataclass).
    main                      — CLI giriş noktası (pardus-paylasim-agent).
"""

from pardus_paylasim_agent.capabilities import (
    AgentCapabilities,
    detect_agent_capabilities,
)

__all__ = [
    "AgentCapabilities",
    "PardusAgent",
    "detect_agent_capabilities",
    "main",
    "__version__",
]

__version__ = "0.1.0"


def __getattr__(name):
    # PardusAgent / main tembel yüklenir: `import pardus_paylasim_agent` yalnız
    # yetenek tespiti için çağrıldığında ScreenStreamServer ağır zincirini
    # (control_server/input_inject) çekmesin.
    if name in ("PardusAgent", "main"):
        from pardus_paylasim_agent import agent as _agent

        return getattr(_agent, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
