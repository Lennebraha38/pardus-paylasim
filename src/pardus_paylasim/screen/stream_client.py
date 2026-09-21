"""
Screen Sharing Receiver Client for Pardus Linux.
Connects to remote Pardus screen streams over Wi-Fi with PIN authentication.

Akış TLS ile şifrelenir; sunucu self-signed sertifika sunar. Kimlik doğrulama
fingerprint pinning (TOFU) ile yapılır: parmak izi eşleşme (/request_pin,
/info) sırasında öğrenilir, akış açılmadan önce canlı sertifikayla yeniden
doğrulanır. Böylece oturum-ortası sertifika değişimi (MITM) yakalanır. Sunucu
cryptography'siz düz HTTP'ye düşerse istemci de düz HTTP'ye uyum sağlar.
"""

import json
import logging
import socket
import ssl
import threading
import urllib.error
import urllib.request
from typing import Callable, Optional

from pardus_paylasim.screen import tls_util
from pardus_paylasim.screen.stream_config import DEFAULT_PORT

logger = logging.getLogger(__name__)


class ScreenStreamClient:
    """Client for receiving and displaying remote Pardus screen streams."""

    def __init__(
        self,
        require_tls: Optional[bool] = None,
        trust_callback: Optional[Callable[[str], bool]] = None,
    ):
        self.is_connected = False
        self.target_ip: Optional[str] = None
        self.target_port: int = DEFAULT_PORT
        self.target_device_id: Optional[str] = None
        self._frame_callback: Optional[Callable[[bytes], None]] = None
        self._pin: str = ""
        self.trust_callback = trust_callback
        # /auth ile alınan oturum token'ı. PIN tek kullanımlık olduğu için
        # native istemci PIN'i bir kez /auth'a verir, ardından /stream ve
        # /control'ü bu token ile açar (web viewer ile aynı yol).
        self.session_token: Optional[str] = None
        # TLS durumu: sunucu keşfedildiğinde belirlenir. use_tls None iken
        # şema bilinmiyor; ilk /info veya /ping ile çözülür.
        self.use_tls: Optional[bool] = None
        self.pinned_fingerprint: Optional[str] = None
        self._ssl_context: Optional[ssl.SSLContext] = None
        # TLS-strip koruması: require_tls True iken düz HTTP'ye asla düşülmez
        # ve pinlenmemiş/şifresiz akış reddedilir. Varsayılan HAS_TLS: istemci
        # TLS yapabiliyorsa (cryptography kurulu → üretim) zorunlu kılar;
        # yapamıyorsa (asgari geliştirme kurulumu) düz HTTP'ye izin verilir.
        self.require_tls: bool = tls_util.HAS_TLS if require_tls is None else require_tls

    # ---- İç yardımcılar ---------------------------------------------------

    def _client_ctx(self, host_ip: str, port: int) -> ssl.SSLContext:
        """İstemci SSLContext'i (tek sefer kur, yeniden kullan)."""
        if self._ssl_context is None:
            if not self.pinned_fingerprint:
                raise ssl.SSLError("Güvenli bağlantı için fingerprint (parmak izi) zorunludur.")

            cert_path = tls_util.fetch_server_cert_to_tempfile(
                host_ip, port, self.pinned_fingerprint
            )
            if cert_path is None:
                raise ssl.SSLError(
                    "Sunucu sertifikası doğrulanamadı veya MITM tespit edildi (Fail-closed)."
                )
            try:
                self._ssl_context = tls_util.build_client_context(cert_path)
            finally:
                import os

                if cert_path and os.path.exists(cert_path):
                    try:
                        os.remove(cert_path)
                    except OSError:
                        pass
        return self._ssl_context

    def _open(self, host_ip: str, port: int, path: str, timeout: float):
        """Verilen yolu açar; şema self.use_tls'e göre https/http.

        use_tls henüz bilinmiyorsa (None) önce https, başarısızsa http dener
        ve öğrendiği şemayı self.use_tls'e yazar. Açık bağlantı nesnesini
        (context manager) döndürür.
        """
        # Şema biliniyorsa tek deneme.
        if self.use_tls is True:
            return self._open_scheme(host_ip, port, path, timeout, tls=True)
        if self.use_tls is False:
            return self._open_scheme(host_ip, port, path, timeout, tls=False)

        # Bilinmiyor: https dene, olmazsa http'ye düş.
        try:
            resp = self._open_scheme(host_ip, port, path, timeout, tls=True)
            self.use_tls = True
            return resp
        except (urllib.error.URLError, ssl.SSLError, OSError) as e:
            # require_tls iken düz HTTP'ye düşmek TLS-strip saldırısına kapı
            # açar (aktif MITM https'i bloklayıp http'ye zorlar). Sessizce
            # düşme; hatayı yükselt.
            if self.require_tls:
                logger.error(
                    "HTTPS başarısız ve require_tls açık; düz HTTP'ye "
                    "düşülmüyor (TLS-strip koruması): %s",
                    e,
                )
                raise
            logger.debug("HTTPS başarısız, düz HTTP deneniyor: %s", e)
            resp = self._open_scheme(host_ip, port, path, timeout, tls=False)
            self.use_tls = False
            return resp

    def _open_scheme(self, host_ip: str, port: int, path: str, timeout: float, tls: bool):
        """Tek şema ile bağlantı açar (fallback yok)."""
        scheme = "https" if tls else "http"
        url = f"{scheme}://{host_ip}:{port}{path}"
        req = urllib.request.Request(url)
        if tls:
            return urllib.request.urlopen(
                req, timeout=timeout, context=self._client_ctx(host_ip, port)
            )
        return urllib.request.urlopen(req, timeout=timeout)

    def _verify_pinned_fingerprint(self) -> bool:
        """Akıştan önce sunucu sertifikasını pinlenmiş parmak izine karşı
        doğrular. require_tls kapalı ve bağlantı düz HTTP ise doğrulama
        atlanır; require_tls açıkken düz HTTP akış reddedilir."""
        if not self.use_tls:
            if self.require_tls:
                logger.error(
                    "require_tls açık ama bağlantı TLS değil; akış reddedildi (TLS-strip koruması)."
                )
                return False
            return True

        from pardus_paylasim.screen import trust_store

        try:
            live_fp = tls_util.get_peer_fingerprint(self.target_ip, self.target_port)
            if live_fp is None:
                logger.error("Sunucu sertifikası okunamadı, akış iptal.")
                return False
        except Exception as e:
            logger.error("Sunucu sertifikası okunurken hata oluştu: %s", e)
            return False

        if not self.target_device_id:
            logger.error("Cihaz kimliği (device_id) eksik, MITM doğrulaması yapılamaz.")
            return False

        # Trust store kontrolü
        trusted_fp = trust_store.get_trusted_fingerprint(self.target_device_id)

        if trusted_fp:
            if live_fp != trusted_fp:
                logger.error(
                    "Sertifika parmak izi UYUŞMUYOR (MITM?). Beklenen %s, gelen %s.",
                    trusted_fp[:16],
                    live_fp[:16],
                )
                return False
            # Güvenli: Trust store ile uyuştu
            self.pinned_fingerprint = live_fp
            return True

        # Trust store'da yoksa (İlk Bağlantı):
        # Sertifika parmak izi onayı (callback veya pairing kanıtı ile) zorunludur.
        if self.pinned_fingerprint and self.pinned_fingerprint == live_fp:
            if self.trust_callback:
                if self.trust_callback(live_fp):
                    logger.info(
                        "Yeni cihaz (İlk Bağlantı), kullanıcı/pairing onayı alındı. Fingerprint kaydediliyor: %s",
                        live_fp,
                    )
                    trust_store.add_trusted_fingerprint(self.target_device_id, live_fp)
                    return True
                else:
                    logger.error("Kullanıcı/pairing onayı reddedildi, akış iptal.")
                    return False
            else:
                logger.error("Onay callback'i tanımlanmamış, TOFU işlemi reddedildi.")
                return False

        logger.error(
            "Sertifika parmak izi onaylanmadı veya pinlenmedi. MITM doğrulaması yapılamıyor."
        )
        return False

    # ---- Genel API --------------------------------------------------------

    def request_pin(self, host_ip: str, port: int = DEFAULT_PORT) -> Optional[str]:
        """Request a PIN from the remote server.

        Yanıttaki cert_fingerprint'i pinler (TOFU) — akış öncesi doğrulanır.
        """
        try:
            with self._open(host_ip, port, "/request_pin", 5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self._pin_fingerprint_from(data)
            return data.get("pin")
        except Exception as e:
            logger.warning("PIN isteği başarısız: %s", e)
            return None

    def get_server_info(self, host_ip: str, port: int = DEFAULT_PORT) -> Optional[dict]:
        """Get server information (cert_fingerprint dahil)."""
        try:
            with self._open(host_ip, port, "/info", 5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self._pin_fingerprint_from(data)
            return data
        except Exception as e:
            return None

    def _pin_fingerprint_from(self, data: dict) -> None:
        """Sunucu yanıtından cert_fingerprint'i pinler (varsa)."""
        fp = data.get("cert_fingerprint")
        if fp:
            self.pinned_fingerprint = fp

    @staticmethod
    def _extract_session_token(headers) -> Optional[str]:
        """Yanıt başlıklarından `pardus_session` cookie token'ını çözer."""
        values = []
        if hasattr(headers, "get_all"):
            try:
                values = headers.get_all("Set-Cookie") or []
            except Exception:
                values = []
        value = headers.get("Set-Cookie")
        if value:
            values.append(value)
        for cookie in values:
            if "pardus_session=" in cookie:
                for part in cookie.split(";"):
                    part = part.strip()
                    if part.startswith("pardus_session="):
                        return part[len("pardus_session="):]
        return None

    def authenticate(self, host_ip: str, port: int, pin: str, timeout: float = 10.0) -> bool:
        """PIN'i /auth ile tek kullanımlık oturum token'ına çevirir.

        Sunucu PIN'i istemcinin IP'sine bağlı doğrular (TTL+lockout), yanıtta
        `Set-Cookie: pardus_session=...` döner. Token sonrasında /stream ve
        /control kimliği olur. Başarısızsa False (fail-closed: akış açılmaz).
        """
        if not pin or self.session_token:
            return True
        tls = self.use_tls if self.use_tls is not None else tls_util.HAS_TLS
        scheme = "https" if tls else "http"
        url = f"{scheme}://{host_ip}:{port}/auth"
        body = json.dumps({"pin": pin}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        kwargs: dict = {"timeout": timeout}
        if tls:
            kwargs["context"] = self._client_ctx(host_ip, port)
        try:
            with urllib.request.urlopen(req, **kwargs) as resp:
                if resp.status != 200:
                    logger.warning("Kimlik doğrulama reddedildi (HTTP %s).", resp.status)
                    return False
                token = self._extract_session_token(resp.headers)
                if not token:
                    logger.error("Sunucu oturum token'ı döndürmedi; akış açılamaz.")
                    return False
                self.session_token = token
                return True
        except urllib.error.HTTPError as e:
            logger.warning("Kimlik doğrulama reddedildi (HTTP %s).", e.code)
            return False
        except Exception as e:
            logger.warning("Kimlik doğrulama başarısız: %s", e)
            return False

    def ping_server(self, host_ip: str, port: int = DEFAULT_PORT) -> bool:
        """Check if screen share server is reachable."""
        try:
            with self._open(host_ip, port, "/ping", 3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") == "ok"
        except Exception as e:
            # Ham soket ile son çare (şema/TLS bağımsız erişilebilirlik).
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((host_ip, port))
                sock.close()
                return result == 0
            except Exception as e:
                return False

    def connect_to_stream(
        self,
        host_ip: str,
        port: int = DEFAULT_PORT,
        pin: str = "",
        on_frame: Optional[Callable[[bytes], None]] = None,
        device_id: Optional[str] = None,
    ) -> bool:
        """Connect to remote host's screen stream with PIN authentication."""
        self.target_ip = host_ip
        self.target_port = port
        self.target_device_id = device_id
        self._pin = pin
        self._frame_callback = on_frame

        # Verify server is reachable (şemayı da çözer).
        if not self.ping_server(host_ip, port):
            logger.warning("Sunucuya ulaşılamıyor: %s:%s", host_ip, port)
            self.is_connected = False
            return False

        # Parmak izi henüz pinlenmemişse /info ile öğren (request_pin
        # çağrılmadan doğrudan bağlanılan yollar için).
        if self.use_tls and not self.pinned_fingerprint:
            self.get_server_info(host_ip, port)

        # Kimlik doğrulama: akış öncesi sertifikayı pine karşı doğrula.
        if not self._verify_pinned_fingerprint():
            self.is_connected = False
            return False

        # PIN'i tek kullanımlık oturum token'ına çevir (fail-closed: token yoksa
        # akış açılmaz). Sunucu X-Pardus-PIN'i değil, yalnız token/cookie kabul eder.
        if self._pin and not self.authenticate(host_ip, port, self._pin):
            self.is_connected = False
            return False

        self.is_connected = True
        threading.Thread(target=self._receive_loop, daemon=True).start()
        return True

    def _receive_loop(self):
        """Receive MJPEG stream frames from server."""
        scheme = "https" if self.use_tls else "http"
        url = f"{scheme}://{self.target_ip}:{self.target_port}/stream"

        try:
            req = urllib.request.Request(url)
            # PIN header ile gönderilir (URL'e sızmaz — access-log/proxy/Referer
            # güvenli). Sunucu X-Pardus-PIN'i query'den önce okur.
            if self._pin:
                req.add_header("X-Pardus-PIN", self._pin)
            # Native istemci /auth ile aldığı oturum token'ını da taşır
            # (sunucu yalnız token/cookie doğrular). Cookie tarayıcı uyumu.
            if self.session_token:
                req.add_header("X-Pardus-Session", self.session_token)
                req.add_header("Cookie", f"pardus_session={self.session_token}")
            # Use a socket with timeout for individual reads
            orig_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(5.0)  # 5 second read timeout
            # TLS akışlarında istemci context'i şart.
            open_kwargs = {"timeout": 10}
            if self.use_tls:
                open_kwargs["context"] = self._client_ctx(self.target_ip, self.target_port)
            try:
                with urllib.request.urlopen(req, **open_kwargs) as resp:
                    # Check if we got JSON error instead of stream
                    content_type = resp.headers.get("Content-type", "")
                    if "application/json" in content_type:
                        body = resp.read().decode("utf-8")
                        try:
                            err = json.loads(body)
                            logger.error(
                                "Kimlik doğrulama hatası: %s",
                                err.get("message", "Bilinmeyen hata"),
                            )
                        except Exception as e:
                            pass
                        self.is_connected = False
                        return

                    buffer = b""
                    MAX_BUFFER = 10000000  # 10MB (Must fit a full 4K JPEG frame)
                    while self.is_connected:
                        try:
                            chunk = resp.read(8192)
                        except Exception as e:
                            break  # Read timeout or connection error
                        if not chunk:
                            break
                        buffer += chunk

                        # Cap buffer to prevent unbounded growth before first boundary
                        if len(buffer) > MAX_BUFFER and buffer.find(b"--pardusjpg") == -1:
                            buffer = buffer[-MAX_BUFFER // 2 :]

                        # Extract JPEG frames from MJPEG stream
                        while True:
                            # Find boundary
                            boundary_idx = buffer.find(b"--pardusjpg")
                            if boundary_idx == -1:
                                # Also try legacy boundary
                                boundary_idx = buffer.find(b"--jpgboundary")

                            if boundary_idx == -1:
                                break

                            # Find JPEG start after headers
                            jpg_start = buffer.find(b"\xff\xd8", boundary_idx)
                            jpg_end = buffer.find(b"\xff\xd9", jpg_start + 2)

                            if jpg_start != -1 and jpg_end != -1 and jpg_end > jpg_start:
                                jpeg_bytes = buffer[jpg_start : jpg_end + 2]
                                buffer = buffer[jpg_end + 2 :]
                                if self._frame_callback and len(jpeg_bytes) > 100:
                                    self._frame_callback(jpeg_bytes)
                            else:
                                # Keep buffer for next read
                                if len(buffer) > MAX_BUFFER:
                                    buffer = buffer[-MAX_BUFFER // 2 :]
                                break
            finally:
                socket.setdefaulttimeout(orig_timeout)

        except urllib.error.HTTPError as e:
            if e.code == 403:
                logger.error("Erişim reddedildi: Geçersiz PIN kodu.")
            else:
                logger.error("HTTP hatası: %s", e.code)
            self.is_connected = False
        except Exception as e:
            logger.error("Bağlantı hatası: %s", e)
            self.is_connected = False

    def disconnect(self):
        """Disconnect from remote screen stream."""
        self.is_connected = False
