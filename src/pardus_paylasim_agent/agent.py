"""
PardusAgent — GTK-free orkestrasyon çekirdeği (Windows companion agent).

Mevcut sunucu/protokol katmanlarını yeniden kullanır:
  - ScreenStreamServer (HTTP/MJPEG + /control WS + TLS)
  - MDNSDiscovery (zeroconf yayın)
  - ControlChannelServer (stream_server içinde gömülü)

GTK/GStreamer/Linux-only modüllere DOĞRUDAN bağımlı DEĞİL.
Yakalama backend'i: Faz 3.2'de CaptureBackend Protocol (mss).

ECC: tüm imzalarda tip anotasyonları, logging (kütüphanede print yok),
erken dönüşler, fonksiyonlar <50 satır, KISS.
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from typing import Optional

from pardus_paylasim.platform_info import current_os_label
from pardus_paylasim.screen.stream_config import StreamConfig
from pardus_paylasim_agent.capabilities import (
    AgentCapabilities,
    detect_agent_capabilities,
)

logger = logging.getLogger(__name__)

# Adlandırılmış sabitler (ECC: sihirli sayı yok)
_DEFAULT_PORT = 52345
_DEFAULT_DEVICE_PREFIX = "Windows Agent"


class PardusAgent:
    """GTK-free Windows companion agent (Faz 3 orkestratör).

    ScreenStreamServer'ı ve MDNSDiscovery'yi GTK olmadan başlatır.
    Yakalama: Faz 3.2'de mss backend bağlanacak (şimdilik sunucu GStreamer-
    fallback yolunu deneyecek, Windows'ta başarısız olup capture_error
    raporlayacak → /info dürüst).
    """

    def __init__(
        self,
        device_name: Optional[str] = None,
        port: int = _DEFAULT_PORT,
        *,
        capabilities: Optional[AgentCapabilities] = None,
    ) -> None:
        self._caps = capabilities or detect_agent_capabilities()
        self._device_name = device_name or f"{_DEFAULT_DEVICE_PREFIX} ({current_os_label()})"
        self._port = port
        self._server = None  # ScreenStreamServer (tembel)
        self._discovery = None  # MDNSDiscovery (tembel)
        self._capture_loop = None  # AgentCaptureLoop (Faz 3.2, tembel)
        self._file_receiver = None  # FileReceiverServer (Faz 5.2, tembel)
        self._running = threading.Event()
        self._pin: Optional[str] = None

    @property
    def capabilities(self) -> AgentCapabilities:
        """Mevcut yetenekler (değiştirilemez)."""
        return self._caps

    @property
    def pin(self) -> Optional[str]:
        """Aktif oturum PIN'i veya None."""
        return self._pin

    @property
    def is_running(self) -> bool:
        """Agent çalışıyor mu?"""
        return self._running.is_set()

    def start(self) -> str:
        """Agent'ı başlat: stream sunucu + mDNS yayını. PIN döner.

        ECC: erken dönüş koruması, kapsamlı hata yönetimi.
        """
        if self._running.is_set():
            raise RuntimeError("Agent zaten çalışıyor")

        logger.info(
            "Agent başlıyor: %s (port=%d, yetenekler=%s)",
            self._device_name,
            self._port,
            self._caps.summary(),
        )

        # 1. Stream sunucu (mevcut yeniden kullan — DRY)
        from pardus_paylasim.screen.stream_server import ScreenStreamServer

        config = StreamConfig(port=self._port)
        self._server = ScreenStreamServer(
            device_name=self._device_name,
            config=config,
        )

        def on_pin_requested(new_pin: str) -> None:
            self._pin = new_pin
            # Faz 1: PIN loglanmamalı.
            logger.info("Yeni PIN üretildi (UI'da gösterilecek).")

        self._pin = self._server.start_server(pin_callback=on_pin_requested)
        logger.info("Sunucu başlatıldı (port %d)", self._port)

        # 2. Agent-taraflı yakalama (mss) — Faz 3.2
        if self._caps.can_capture:
            self._start_agent_capture()

        # Faz 5.2: Dosya alıcı servisi (her zaman aktif olabilir)
        self._start_file_receiver()

        # 3. mDNS keşif (opsiyonel — zeroconf yoksa atla)
        if self._caps.can_discover:
            self._start_discovery()
        else:
            logger.warning("zeroconf yok: mDNS keşfi devre dışı")

        self._running.set()
        return self._pin

    def _start_agent_capture(self) -> None:
        """Agent-taraflı mss yakalama döngüsü başlat (Faz 3.2)."""
        from pardus_paylasim_agent.capture import AgentCaptureLoop, MssCaptureBackend

        backend = MssCaptureBackend()
        self._capture_loop = AgentCaptureLoop(
            backend=backend,
            server=self._server,
            fps=self._server._config.framerate,
            quality=self._server._config.jpeg_quality,
        )
        self._capture_loop.start()
        logger.info("Agent yakalama döngüsü başlatıldı (mss)")

    def _start_file_receiver(self) -> None:
        import ctypes

        from pardus_paylasim.discovery.transfer import FileReceiverServer
        from pardus_paylasim.platform_info import downloads_dir

        def _on_file_req(name: str, size: int, sender: str) -> bool:
            try:
                MB_YESNO = 0x04
                MB_ICONQUESTION = 0x20
                MB_TOPMOST = 0x40000
                IDYES = 6
                msg = (
                    f"{sender} size {name} ({size} byte) göndermek istiyor.\nKabul ediyor musunuz?"
                )
                res = ctypes.windll.user32.MessageBoxW(
                    0, msg, "Dosya İsteği", MB_YESNO | MB_ICONQUESTION | MB_TOPMOST
                )
                return res == IDYES
            except Exception:
                # Faz 1: Agent MessageBox/notification hatası -> False (Fail-closed)
                return False

        def _on_file_rcv(path: str) -> None:
            try:
                from pardus_paylasim_agent.notification import AgentNotificationSink

                sink = AgentNotificationSink()
                sink.send(
                    "Dosya Alındı",
                    f"Dosya İndirilenler klasörüne kaydedildi:\n{path}",
                    "file-received",
                )
            except Exception:
                pass

        self._file_receiver = FileReceiverServer(
            downloads_dir(), port=0, ssl_context=self._server._ssl_context if self._server else None
        )  # Auto port
        self._file_receiver.on_file_request = _on_file_req
        self._file_receiver.on_file_received = _on_file_rcv
        self._file_receiver.start()
        logger.info("Dosya alıcısı başlatıldı, port: %d", self._file_receiver.port)

    def _start_discovery(self) -> None:
        """mDNS yayını başlat (zeroconf mevcut)."""
        from pardus_paylasim.discovery.mdns_discovery import MDNSDiscovery

        caps = ["screen_share", "control_share", "file_share"]
        file_port = self._file_receiver.port if self._file_receiver else 0

        self._discovery = MDNSDiscovery(
            device_name=self._device_name,
            port=self._port,
            control_port=self._port,  # Kontrol aynı port (/control WS)
            file_port=file_port,
            capabilities=caps,
        )
        self._discovery.start_broadcasting_and_scanning(
            on_device_found=self._on_device_found,
            on_error=self._on_discovery_error,
        )

    def _on_device_found(self, name: str, ip: str, port: int, info: dict) -> None:
        logger.info("Cihaz bulundu: %s (%s:%d)", name, ip, port)

    def _on_discovery_error(self, msg: str) -> None:
        logger.warning("mDNS hatası: %s", msg)

    def stop(self) -> None:
        """Agent'ı durdur: sunucu + mDNS kapatma.

        ECC: çalışmıyorsa erken dönüş, kapsamlı try/except.
        """
        if not self._running.is_set():
            return

        logger.info("Agent durduruluyor...")
        self._running.clear()

        # Yakalama döngüsü (Faz 3.2)
        if self._capture_loop is not None:
            try:
                self._capture_loop.stop()
            except Exception as exc:
                logger.debug("Yakalama döngüsü durdurma hatası: %s", exc)
            self._capture_loop = None

        if self._discovery is not None:
            try:
                self._discovery.stop()
            except Exception as exc:
                logger.debug("mDNS durdurma hatası: %s", exc)
            self._discovery = None

        if self._file_receiver is not None:
            try:
                self._file_receiver.stop()
            except Exception as exc:
                logger.debug("Dosya alıcısı durdurma hatası: %s", exc)
            self._file_receiver = None

        if self._server is not None:
            try:
                self._server.stop_server()
            except Exception as exc:
                logger.debug("Sunucu durdurma hatası: %s", exc)
            self._server = None

        self._pin = None
        logger.info("Agent durduruldu.")


def main(argv: Optional[list] = None) -> int:
    """CLI giriş noktası: pardus-paylasim-agent.

    ECC: print yalnız kullanıcıya yönelik CLI banner'ı için
    (kütüphane kodunda değil).
    """
    parser = argparse.ArgumentParser(
        prog="pardus-paylasim-agent",
        description="Pardus Paylaşım Windows Companion Agent",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_DEFAULT_PORT,
        help=f"Akış/kontrol portu (varsayılan: {_DEFAULT_PORT})",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Cihaz adı (varsayılan: Windows Agent (OS))",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Ayrıntılı loglama",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    caps = detect_agent_capabilities()
    logger.info("Yetenekler: %s", caps.summary())

    if not caps.can_capture:
        logger.warning(
            "mss ve/veya Pillow kurulu değil: ekran yakalama devre dışı. "
            "Kurulum: pip install mss pillow"
        )

    agent = PardusAgent(
        device_name=args.name,
        port=args.port,
        capabilities=caps,
    )

    shutdown = threading.Event()

    def _signal_handler(sig: int, frame: object) -> None:
        logger.info("Sinyal %s alındı, kapatılıyor...", sig)
        shutdown.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    pin = agent.start()
    # CLI banner — print burada OK (kullanıcıya yönelik CLI, kütüphane kodu değil)
    banner = (
        f"\n{'=' * 50}\n"
        f"  Pardus Paylaşım Agent\n"
        f"  PIN:  {pin}\n"
        f"  Port: {args.port}\n"
        f"  Yetenekler: {caps.summary()}\n"
        f"{'=' * 50}\n\n"
        f"Ctrl+C ile durdurun."
    )
    print(banner)  # noqa: T201 — kasıtlı CLI çıktısı

    try:
        from pardus_paylasim_agent.tray import AgentTray

        tray = AgentTray(agent, shutdown)

        def wait_for_shutdown():
            shutdown.wait()
            if tray.icon:
                tray.icon.stop()

        threading.Thread(target=wait_for_shutdown, daemon=True).start()
        tray.run()  # Bu çağrı bloklar (pystray main loop)

    except ImportError:
        logger.debug("pystray bulunamadı, CLI modunda devam ediliyor.")
        shutdown.wait()

    agent.stop()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
