"""
GTK4 Screen Sharing View Controller (AirPlay / Sidecar style).
"""

from typing import Callable, Optional

from pardus_paylasim.screen.control_client import ControlChannelClient
from pardus_paylasim.screen.stream_client import ScreenStreamClient
from pardus_paylasim.screen.stream_config import DEFAULT_PORT
from pardus_paylasim.screen.stream_server import ScreenStreamServer


class ScreenShareViewHandler:
    """Controller for Screen Sharing Stream & Receive operations."""

    def __init__(self, device_name: str = "Pardus Ekran Sunucusu"):
        self.device_name = device_name
        self.server = ScreenStreamServer(device_name=device_name)
        self.client = ScreenStreamClient()
        # Uzaktan kontrol istemcisi (yalnız client tarafında, "Kontrolü İste"
        # sonrası kurulur). Host tarafı server.control_server üstünden yönetilir.
        self.control_client: Optional[ControlChannelClient] = None

    @property
    def host_port(self) -> int:
        """Sunucunun gerçek dinlediği port (config'ten türetilir)."""
        return self.server.port

    def start_host_stream(self, on_pin_generated: Callable[[str], None]) -> str:
        """Starts hosting screen stream over Wi-Fi network and returns PIN."""
        return self.server.start_server(pin_callback=on_pin_generated)

    def stop_host_stream(self):
        self.server.stop_server()

    def connect_to_remote_screen(
        self,
        host_ip: str,
        port: int = DEFAULT_PORT,
        pin: str = "",
        on_frame: Optional[Callable[[bytes], None]] = None,
    ) -> bool:
        """Connects to remote host's screen stream."""
        return self.client.connect_to_stream(host_ip, port, pin, on_frame)

    def disconnect_remote_screen(self):
        self.client.disconnect()

    # --- Uzaktan kontrol (Faz 1) -----------------------------------------

    def start_control_host(self) -> None:
        """Host tarafında kontrol yetkisini açar (default KAPALI → AÇIK).

        Kanal zaten mevcut TLS HTTP sunucusunda `/control` upgrade ile
        dinlenir; burada yalnız consent kapısını açarız. Kapalıyken geçerli
        PIN'le bile `/control` reddedilir (C4-1).
        """
        self.server.control_server.set_control_allowed(True)

    def stop_control_host(self) -> None:
        """Host tarafında kontrolü kapatır ve tüm oturum token'larını düşürür.

        Kill-switch/kapatma yolu: `set_control_allowed(False)` sunucu tarafında
        `_tokens`'ı temizler → mevcut bağlı istemciler anında yetkisiz kalır.
        """
        self.server.control_server.set_control_allowed(False)

    def set_control_allowed(self, allowed: bool) -> None:
        """Host kontrol iznini doğrudan ayarlar (UI switch bağı)."""
        self.server.control_server.set_control_allowed(bool(allowed))

    def is_control_allowed(self) -> bool:
        """Host kontrol izninin açık olup olmadığını döndürür."""
        return self.server.control_server.is_control_allowed()

    def request_control(self, timeout: float = 10.0) -> bool:
        """Client tarafında kontrol kanalını açar (ekran bağlantısı sonrası).

        Ekran akışı için öğrenilen host/port/TLS/parmak-izi/PIN bilgilerini
        `self.client`'tan devralarak `ControlChannelClient` kurar ve el sıkışır.
        Sunucu grant verirse True; reddederse kanal kapatılır ve False döner.
        """
        client = self.client
        if not client.target_ip:
            return False
        self.release_control()  # Varsa eski kanalı temizle.
        control = ControlChannelClient(
            host=client.target_ip,
            port=client.target_port,
            pin=client._pin,
            pinned_fingerprint=client.pinned_fingerprint,
            use_tls=client.use_tls,
        )
        if not control.connect(timeout=timeout):
            control.close()
            return False
        self.control_client = control
        return True

    def release_control(self) -> None:
        """Client tarafında kontrol kanalını kapatır (varsa)."""
        if self.control_client is not None:
            try:
                self.control_client.close()
            finally:
                self.control_client = None
