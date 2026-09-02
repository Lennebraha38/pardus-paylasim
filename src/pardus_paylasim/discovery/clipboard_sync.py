"""
Cihazlar arası pano (clipboard) paylaşımı.

Basit metin-itme (push) protokolü: gönderici, panosundaki metni hedef cihaza
TCP üzerinden yollar; alıcı metni yerel panosuna yazar (UI callback ile).

Tel biçimi:
    magic(4) | length(!I, 4) | utf-8 metin(length bayt)
magic = b"PCLP" (Pardus CLiPboard) — yanlış porta bağlanan istemciyi ele.

Güvenlik notu: bu kanal düz metindir ve dosya transferinden ayrı bir yetenektir.
Hassas içerik için pano-maskeleme (SensitiveMasker) gönderim öncesi çağıranca
uygulanabilir. Boyut, kötüye-kullanımı sınırlamak için üst sınıra tabidir.
"""

import logging
import socket
import ssl
import struct
import threading
from typing import Callable, Optional

from . import net_util

logger = logging.getLogger(__name__)

# Protokol sabitleri.
CLIPBOARD_PORT = 8901
_MAGIC = b"PCLP"
_MAGIC_LEN = 4
# Tek panonun kabul edilen en büyük boyutu (2 MiB) — bellek koruması.
_MAX_CLIP_BYTES = 2 * 1024 * 1024
_RECV_TIMEOUT = 15.0


class ClipboardSyncClient:
    """Hedef cihaza pano metni gönderir."""

    def __init__(
        self,
        target_ip: str,
        target_port: int = CLIPBOARD_PORT,
        ssl_context: Optional[ssl.SSLContext] = None,
    ) -> None:
        self.target_ip = target_ip
        self.target_port = target_port
        self.ssl_context = ssl_context

    def send_text(self, text: str, timeout: float = 10.0) -> None:
        """Metni hedefe yollar. Hata durumunda istisna yükseltir."""
        payload = text.encode("utf-8")
        if len(payload) > _MAX_CLIP_BYTES:
            raise ValueError("Pano içeriği çok büyük.")

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            if self.ssl_context:
                conn = self.ssl_context.wrap_socket(s, server_hostname=self.target_ip)
            else:
                conn = s
            conn.connect((self.target_ip, self.target_port))
            conn.sendall(_MAGIC)
            conn.sendall(struct.pack("!I", len(payload)))
            conn.sendall(payload)
            # Alıcı onayı (\x01 = başarı).
            ack = conn.recv(1)
            if ack != b"\x01":
                raise ConnectionError("Alıcı panoyu kabul etmedi.")


class ClipboardSyncServer:
    """Gelen pano metnini dinler; alınca on_clipboard_received(metin, ip)."""

    def __init__(
        self, port: int = CLIPBOARD_PORT, ssl_context: Optional[ssl.SSLContext] = None
    ) -> None:
        self.port = port
        self.ssl_context = ssl_context
        self.server_socket: Optional[socket.socket] = None
        self._running = False
        # Callback(text, sender_ip); None ise alınan metin yalnız yutulur.
        self.on_clipboard_received: Optional[Callable[[str, str], None]] = None

    def start(self) -> None:
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("0.0.0.0", self.port))
        self.server_socket.listen(5)
        if self.ssl_context:
            self.server_socket = self.ssl_context.wrap_socket(self.server_socket, server_side=True)
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, _addr = self.server_socket.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
            except OSError:
                if not self._running:
                    break

    def _handle_client(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(_RECV_TIMEOUT)

            magic = net_util.recv_exact(conn, _MAGIC_LEN)
            if magic != _MAGIC:
                return  # Yanlış protokol/port.

            len_data = net_util.recv_exact(conn, 4)
            if len_data is None:
                return
            length = struct.unpack("!I", len_data)[0]
            if length > _MAX_CLIP_BYTES:
                return  # Aşırı büyük: reddet.

            payload = net_util.recv_exact(conn, length)
            if payload is None:
                return

            peer_ip = ""
            try:
                peer_ip = conn.getpeername()[0]
            except OSError:
                pass

            text = payload.decode("utf-8", errors="replace")
            conn.sendall(b"\x01")  # ACK

            if self.on_clipboard_received:
                self.on_clipboard_received(text, peer_ip)

        except Exception as e:
            logger.error("Pano alma hatası: %s", e)
        finally:
            conn.close()
