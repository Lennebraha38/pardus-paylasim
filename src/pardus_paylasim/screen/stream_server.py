"""
Screen Sharing Host Server for Pardus Linux (AirPlay/Sidecar style Wi-Fi streaming).
Uses GStreamer/PipeWire for real desktop capture with MJPEG HTTP streaming.
Includes proper PIN-code authentication for stream access.
"""

import http.server
import json
import logging
import os
import shlex
import shutil
import socketserver
import subprocess
import threading
import time
from dataclasses import replace
from typing import Callable, List, Optional, Tuple

from pardus_paylasim.platform_info import (
    SESSION_WAYLAND,
    SESSION_X11,
    session_type,
)
from pardus_paylasim.screen import tls_util
from pardus_paylasim.screen.pairing import ScreenPairingManager
from pardus_paylasim.screen.stream_config import (
    StreamConfig,
    parse_jpeg_dimensions,
)

logger = logging.getLogger(__name__)


def parse_allowed_origins(raw: object) -> frozenset:
    """CORS allowlist string'ini normalize origin kümesine çevir.

    Girdi virgülle ayrık origin listesi (ör. "https://a.local, https://b:8443").
    Boşluk kırpılır, boş parçalar atılır, joker '*' güvenlik gereği ASLA kabul
    edilmez (allowlist tam origin ister). Boş/None → boş küme (CORS kapalı).
    """
    if not raw:
        return frozenset()
    origins = set()
    for part in str(raw).split(","):
        origin = part.strip()
        # Joker asla allowlist'e giremez: '*' echo'lamak tüm origin'leri açar.
        if origin and origin != "*":
            origins.add(origin)
    return frozenset(origins)


# JPEG çerçeve sınırları: SOI (Start Of Image) / EOI (End Of Image) marker'ları.
_JPEG_SOI = b"\xff\xd8"
_JPEG_EOI = b"\xff\xd9"


def extract_jpeg_frames(buffer: bytes) -> Tuple[List[bytes], bytes]:
    """Bayt tamponundan tam JPEG karelerini ayıkla → (kareler, kalan).

    GStreamer `fdsink` stdout'u parça parça (chunk) akar: bir JPEG karesi
    birden çok okumaya bölünebilir ya da tek okumada birden çok kare gelebilir.
    SOI (0xFFD8) ile EOI (0xFFD9) arası tam kareler toplanır; yarım kalan
    (henüz EOI gelmemiş) kısım `remainder` olarak döner ve çağıran onu bir
    sonraki chunk'la birleştirir.

    Saf/stdlib (GStreamer/soket gerektirmez) → headless unit-test edilebilir.
    Davranış `_read_gst_frames`'in eski gömülü döngüsüyle birebir aynıdır.
    """
    frames: List[bytes] = []
    remainder = buffer
    while True:
        start = remainder.find(_JPEG_SOI)
        if start == -1:
            break
        end = remainder.find(_JPEG_EOI, start + 2)
        if end == -1:
            break
        frames.append(remainder[start : end + 2])
        remainder = remainder[end + 2 :]
    return frames, remainder


# --- Web viewer statik varlıkları (Faz 2: tarayıcıdan izle+kontrol) ---
#
# Windows Chrome → https://<pardus-ip>:52345/ → bu statik kabuk yüklenir; içindeki
# viewer.js <img src="/stream?pin=..."> ile MJPEG'i render eder ve wss://.../control
# WebSocket'iyle uzak kontrol yapar. Tarayıcı <img>/WS'e özel header ekleyemediği
# için PIN sorgu-parametresiyle taşınır (sunucu bunu destekler, deprecated fallback).
#
# GÜVENLİK — yol-geçişi (path traversal) imkansız: rasgele dosya yolu çözümü YOK.
# Yalnız aşağıdaki SABİT route → (dosya adı, içerik-tipi) eşlemesindeki üç dosya
# servis edilir. İstek yolu bu dict'te anahtar değilse 404. Dosya adları kod
# sabiti; hiçbir kullanıcı girdisi yola ulaşmaz.
_WEB_VIEWER_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/viewer.css": ("viewer.css", "text/css; charset=utf-8"),
    "/viewer.js": ("viewer.js", "application/javascript; charset=utf-8"),
    "/file-manager.html": ("file-manager.html", "text/html; charset=utf-8"),
    "/file-manager.css": ("file-manager.css", "text/css; charset=utf-8"),
    "/file-manager.js": ("file-manager.js", "application/javascript; charset=utf-8"),
}

# Katı CSP: tüm varlıklar 'self' origin'inden.
_VIEWER_CSP = (
    "default-src 'none'; "
    "img-src 'self'; "
    "media-src 'self'; "
    "style-src 'self'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "base-uri 'none'; "
    "object-src 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)

# Çözülen viewer dizini bir kez bulunup önbelleğe alınır (her istekte disk taraması
# değil). None = henüz çözülmedi; False sentinel yerine _VIEWER_DIR_UNSET kullan.
_VIEWER_DIR_UNSET = object()
_web_viewer_dir_cache = _VIEWER_DIR_UNSET


def _resolve_web_viewer_dir() -> Optional[str]:
    """Web viewer statik varlık dizinini çöz (dev repo-kökü / kurulu sistem yolu).

    Aday sırası: (1) geliştirme deposu kökü `<repo>/data/web-viewer`
    (`__file__`'ten yukarı 3 dizin), (2) kurulu sistem yolu
    `/usr/share/pardus-paylasim/web-viewer` (debian/install hedefi). İlk var
    olan dizin döner; hiçbiri yoksa None (route 404 verir, çökmez). Sonuç
    önbelleğe alınır — kurulu uygulamada yol sabittir.
    """
    global _web_viewer_dir_cache
    if _web_viewer_dir_cache is not _VIEWER_DIR_UNSET:
        return _web_viewer_dir_cache

    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        # <repo>/src/pardus_paylasim/screen → yukarı 3 → <repo>/data/web-viewer
        os.path.join(here, "..", "..", "..", "data", "web-viewer"),
        os.path.join("/usr", "share", "pardus-paylasim", "web-viewer"),
    ]
    resolved: Optional[str] = None
    for cand in candidates:
        norm = os.path.normpath(cand)
        if os.path.isdir(norm):
            resolved = norm
            break
    _web_viewer_dir_cache = resolved
    return resolved


def read_web_viewer_asset(route: str) -> Optional[Tuple[bytes, str]]:
    """Sabit-allowlist web viewer varlığını oku → (içerik, içerik-tipi) / None.

    Yalnız `_WEB_VIEWER_ASSETS` allowlist'indeki sabit route'lar servis edilir;
    rasgele yol çözümü / `..` geçişi imkansız (route → sabit dosya adı eşlemesi,
    kullanıcı girdisi yola karışmaz). Dizin/dosya yoksa None → çağıran 404 verir.
    Saf/stdlib (soket/GTK gerektirmez) → headless unit-test edilebilir.
    """
    mapping = _WEB_VIEWER_ASSETS.get(route)
    if mapping is None:
        return None
    filename, content_type = mapping
    base = _resolve_web_viewer_dir()
    if base is None:
        return None
    full = os.path.join(base, filename)
    try:
        with open(full, "rb") as handle:
            return handle.read(), content_type
    except OSError:
        return None


class MJPEGHandler(http.server.BaseHTTPRequestHandler):
    """Serves JPEG frame stream over HTTP multipart/x-mixed-replace.
    Requires valid PIN to access /stream endpoint."""

    server_instance = None

    def log_message(self, fmt, *args):
        """Suppress HTTP access logs."""
        pass

    def _check_auth(self) -> bool:
        # Faz 1: Auto-trust ve Device ID auth tamamen kapatıldı.
        # Faz 1: Query string üzerinden PIN taşınması yasaklandı.
        # Faz 2: PIN doğrulama sonrası verilen session token kullanılır. IP-based trust YOK.

        token = None
        # 1. Header (X-Pardus-Session)
        header_token = self.headers.get("X-Pardus-Session")
        if header_token:
            token = header_token.strip()

        # 2. Cookie (pardus_session) - Tarayıcı img/websocket entegrasyonu için
        if not token:
            cookie_header = self.headers.get("Cookie", "")
            if "pardus_session=" in cookie_header:
                for part in cookie_header.split(";"):
                    part = part.strip()
                    if part.startswith("pardus_session="):
                        token = part[len("pardus_session=") :]
                        break

        if token and self.server_instance.session_mgr.verify_token(token):
            return True

        return False

    def _cors_origin(self) -> Optional[str]:
        """İstek `Origin`'i allowlist'teyse onu döndür; değilse None.

        Asla '*' dönmez. Origin yoksa (same-origin/native istemci, tarayıcı
        değil) None → CORS header hiç gönderilmez, sorun olmaz."""
        origin = self.headers.get("Origin")
        if origin and origin in self.server_instance.allowed_web_origins:
            return origin
        return None

    def _send_cors(self) -> None:
        """Yalnız allowlist'teki origin için CORS header'ı yaz ('*' yok)."""
        allowed = self._cors_origin()
        if allowed is not None:
            self.send_header("Access-Control-Allow-Origin", allowed)
            self.send_header("Vary", "Origin")

    def _send_json(self, data: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self._send_cors()
        self.end_headers()
        self.wfile.write(data.encode("utf-8"))

    def do_GET(self):
        # CORS preflight
        path = self.path.split("?")[0]

        if path == "/ping":
            self._send_json('{"status":"ok","service":"pardus-screen-share"}')

        elif path == "/stream":
            if not self._check_auth():
                self._send_json(
                    '{"error":"INVALID_PIN","message":"Geçersiz PIN kodu. '
                    'Ekran paylaşımı için doğru PIN kodunu girin."}',
                    403,
                )
                return

            self.send_response(200)
            self.send_header("Content-type", "multipart/x-mixed-replace; boundary=--pardusjpg")
            self._send_cors()
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            frame_count = 0
            while getattr(self.server_instance, "is_streaming", False):
                frame = self.server_instance.get_current_frame()
                if frame:
                    try:
                        self.wfile.write(b"--pardusjpg\r\n")
                        self.wfile.write(b"Content-type: image/jpeg\r\n")
                        self.wfile.write(f"Content-length: {len(frame)}\r\n".encode())
                        self.wfile.write(b"X-Frame-Id: %d\r\n" % frame_count)
                        self.wfile.write(b"\r\n")
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                        frame_count += 1
                    except (BrokenPipeError, ConnectionResetError):
                        break
                # Servis hızı config'den (1/fps); hardcoded 0.04 değil.
                time.sleep(self.server_instance.frame_interval)

        elif path == "/info":
            info_dict = {
                "name": self.server_instance.device_name,
                "resolution": self.server_instance.capture_resolution,
                "status": "streaming" if self.server_instance.is_streaming else "stopped",
                "port": self.server_instance.port,
                "version": "1.0.0",
                "capture_error": self.server_instance.capture_error,
                "capture_backend": self.server_instance.capture_backend,
                # TLS durumu + parmak izi: istemci akış öncesi pinler (TOFU).
                "tls": self.server_instance.tls_enabled,
                "cert_fingerprint": self.server_instance.cert_fingerprint,
            }
            # Uzaktan kontrol durumu: istemci İSTEMEDEN önce kontrolün mümkün
            # olup olmadığını bilir. `control_backend` None → uygun enjeksiyon
            # backend'i yok (kontrol reddedilir). `control_allowed` host toggle'ı.
            control_server = getattr(self.server_instance, "control_server", None)
            if control_server is not None:
                info_dict["control_backend"] = control_server.available_backend_name()
                info_dict["control_allowed"] = control_server.is_control_allowed()
            else:
                info_dict["control_backend"] = None
                info_dict["control_allowed"] = False
            self._send_json(json.dumps(info_dict))

        elif path == "/request_pin":
            # Generate a PIN for a connecting client
            client_ip = self.client_address[0]
            pin = self.server_instance.pairing_mgr.generate_pin_for_request(
                client_ip, "Pardus Client"
            )
            # Host UI'ye PIN'i göster
            if hasattr(self.server_instance, "pin_callback") and self.server_instance.pin_callback:
                self.server_instance.pin_callback(pin)

            # PIN'i istemciye DÖNDÜRME (Güvenlik Faz 1: PIN disclosure kapatıldı)
            resp = {
                "expires_in": 180,
                "message": "PIN kodunu ana makine (host) ekranından okuyun.",
                "tls": self.server_instance.tls_enabled,
                "cert_fingerprint": self.server_instance.cert_fingerprint,
            }
            self._send_json(json.dumps(resp))

        elif path == "/api/v1/files/list":
            if not self._check_auth():
                self._send_json('{"error":"INVALID_PIN"}', 403)
                return
            try:
                import urllib.parse

                qs = self.path.split("?", 1)[1] if "?" in self.path else ""
                params = dict(urllib.parse.parse_qsl(qs))
                root = params.get("root", "downloads")
                subpath = params.get("path", "")

                from pardus_paylasim.screen.fs_server import PathTraversalError, list_directory

                self._send_json(list_directory(root, subpath), 200)
            except PathTraversalError as e:
                # Dışına çıkılmaya çalışılırsa session'ı düşür (Faz 1)
                self.server_instance.pairing_mgr.revoke_pin(self.client_address[0])
                logger.warning(
                    "Güvenlik İhlali (Path Traversal): %s -> Session düşürüldü.",
                    self.client_address[0],
                )
                self._send_json(f'{{"error":"SECURITY_VIOLATION", "message":"{str(e)}"}}', 403)
                self.close_connection = True
            except Exception as e:
                self._send_json(f'{{"error":"FS_ERROR", "message":"{str(e)}"}}', 400)

        elif path == "/api/v1/files/download":
            if not self._check_auth():
                self._send_json('{"error":"INVALID_PIN"}', 403)
                return
            try:
                import urllib.parse

                qs = self.path.split("?", 1)[1] if "?" in self.path else ""
                params = dict(urllib.parse.parse_qsl(qs))
                root = params.get("root", "downloads")
                subpath = params.get("path", "")

                from pardus_paylasim.screen.fs_server import PathTraversalError, serve_download

                serve_download(root, subpath, self)
            except PathTraversalError as e:
                # Dışına çıkılmaya çalışılırsa session'ı düşür (Faz 1)
                self.server_instance.pairing_mgr.revoke_pin(self.client_address[0])
                logger.warning(
                    "Güvenlik İhlali (Path Traversal): %s -> Session düşürüldü.",
                    self.client_address[0],
                )
                self._send_json(f'{{"error":"SECURITY_VIOLATION", "message":"{str(e)}"}}', 403)
                self.close_connection = True
            except Exception as e:
                self._send_json(f'{{"error":"FS_ERROR", "message":"{str(e)}"}}', 400)

        elif path == "/control":
            # AnyDesk-tarzı uzaktan kontrol kanalı: RFC6455 WebSocket upgrade.
            # ControlChannelServer host consent + PIN + per-mesaj token doğrular,
            # sonra girdi enjeksiyonuna dispatch eder. Upgrade reddedilirse düz
            # HTTP JSON hatası döner (handle_upgrade içinde).
            self.server_instance.control_server.handle_upgrade(self)

        elif path in _WEB_VIEWER_ASSETS:
            # Web viewer statik kabuğu (Faz 2): index.html + viewer.css + viewer.js.
            # KİMLİK DOĞRULAMASIZ — kabuk herkese açık (sır içermez); içindeki
            # /stream ve /control hâlâ PIN ister. Yalnız sabit-allowlist route'lar
            # (rasgele yol çözümü YOK → path-traversal imkansız). Katı CSP: her
            # şey 'self', satır-içi script/style yok.
            asset = read_web_viewer_asset(path)
            if asset is None:
                # Varlık dizini kurulu değil (ör. paketlenmemiş dev ortamı) →
                # 404, çökme değil. Kullanıcı yine de /stream'i doğrudan açabilir.
                self._send_json('{"error":"VIEWER_NOT_AVAILABLE"}', 404)
            else:
                body, content_type = asset
                self.send_response(200)
                self.send_header("Content-type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Security-Policy", _VIEWER_CSP)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        else:
            self._send_json('{"error":"NOT_FOUND"}', 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, X-Pardus-PIN")
        self.end_headers()

    def do_POST(self):
        path = self.path.split("?")[0]

        if path == "/auth":
            # Faz 2: Oturum token'ı altyapısı (IP-based trust kapalı)
            content_len = int(self.headers.get("Content-Length", 0))
            if content_len > 8192:
                self._send_json('{"error":"PAYLOAD_TOO_LARGE"}', 413)
                return
            post_data = self.rfile.read(content_len)
            try:
                import json

                data = json.loads(post_data)
                pin = data.get("pin", "")
                client_ip = self.client_address[0]
                if self.server_instance.pairing_mgr.verify_pin(client_ip, pin):
                    token = self.server_instance.session_mgr.create_session()
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    # Cookie browser entegrasyonu için. Secure session varsa Secure flag eklenebilir,
                    # ancak HTTP fallback (127.0.0.1) için SameSite=Strict yeterli.
                    self.send_header(
                        "Set-Cookie", f"pardus_session={token}; Path=/; HttpOnly; SameSite=Strict"
                    )
                    self._send_cors()
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')
                else:
                    self._send_json('{"error":"INVALID_PIN"}', 403)
            except Exception:
                self._send_json('{"error":"BAD_REQUEST"}', 400)
            return

        if path == "/api/v1/files/upload":
            if not self._check_auth():
                self._send_json('{"error":"INVALID_PIN"}', 403)
                return

            try:
                import hashlib
                import tempfile
                import urllib.parse
                import uuid

                qs = self.path.split("?", 1)[1] if "?" in self.path else ""
                params = dict(urllib.parse.parse_qsl(qs))
                user_filename = params.get("name", "uploaded_file")
                user_filename = os.path.basename(user_filename)

                content_len = int(self.headers.get("Content-Length", 0))
                # 100MB configurable limit per spec
                if content_len == 0 or content_len > 100 * 1024 * 1024:
                    self._send_json('{"error":"INVALID_SIZE"}', 400)
                    return

                from pardus_paylasim.platform_info import downloads_dir

                save_dir = downloads_dir()
                os.makedirs(save_dir, exist_ok=True)

                storage_id = str(uuid.uuid4())
                base, ext = os.path.splitext(user_filename)
                final_path = os.path.join(save_dir, f"{base}_{storage_id[:8]}{ext}")

                fd, temp_path = tempfile.mkstemp(dir=save_dir)
                hasher = hashlib.sha256()
                bytes_read = 0

                try:
                    with os.fdopen(fd, "wb") as f:
                        while bytes_read < content_len:
                            chunk_size = min(65536, content_len - bytes_read)
                            chunk = self.rfile.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            hasher.update(chunk)
                            bytes_read += len(chunk)

                        f.flush()
                        os.fsync(f.fileno())

                    if bytes_read != content_len:
                        raise ValueError("Eksik veri")

                    if os.path.exists(final_path):
                        raise FileExistsError("Dosya zaten var")
                    os.rename(temp_path, final_path)

                except Exception as e:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise e

                resp = {
                    "status": "ok",
                    "file_id": storage_id,
                    "bytes": bytes_read,
                    "sha256": hasher.hexdigest(),
                }
                self._send_json(json.dumps(resp), 200)

                try:
                    from pardus_paylasim.auth.audit_logger import log_event

                    client_ip = self.client_address[0]
                    log_event(
                        "file_uploaded",
                        {
                            "filename": final_path,
                            "size": bytes_read,
                            "ip": client_ip,
                            "sha256": hasher.hexdigest(),
                        },
                    )
                except Exception:
                    pass

                try:
                    from pardus_paylasim.notifications import send_notification

                    send_notification(
                        title="Dosya Alındı (Web)",
                        message=f"{os.path.basename(final_path)} indirilenlere kaydedildi.",
                        notification_id="file-received",
                    )
                except Exception:
                    pass

            except Exception as e:
                self._send_json(f'{{"error":"UPLOAD_FAILED", "detail":"{str(e)}"}}', 500)
        elif path == "/webrtc/offer":
            # Faz 1: Deneysel özellikler varsayılan olarak kapalı. Bypass yok.
            if os.environ.get("PARDUS_ENABLE_EXPERIMENTAL") != "1":
                self._send_json(
                    '{"error":"EXPERIMENTAL_FEATURE_DISABLED", "message":"WebRTC deneyseldir ve kapalıdır."}',
                    403,
                )
                return

            if not self._check_auth():
                self._send_json('{"error":"INVALID_PIN"}', 403)
                return
            content_len = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_len)
            try:
                offer_json = json.loads(post_data)
                sdp = offer_json["sdp"]
                type_ = offer_json["type"]
                monitor_index = int(offer_json.get("monitor_index", 0))
                quality = offer_json.get("quality", "high")

                try:
                    from pardus_paylasim.auth.audit_logger import log_event

                    log_event(
                        "webrtc_connection",
                        {
                            "ip": self.client_address[0],
                            "monitor": monitor_index,
                            "quality": quality,
                        },
                    )
                except Exception:
                    pass

                from pardus_paylasim.screen.webrtc_server import process_offer_sync

                answer = process_offer_sync(sdp, type_, monitor_index, quality)
                self._send_json(answer, 200)
            except Exception as e:
                self._send_json(f'{{"error":"WEBRTC_FAILED", "detail":"{str(e)}"}}', 500)
        else:
            self._send_json('{"error":"NOT_FOUND"}', 404)


class ScreenStreamServer:
    """Hosts screen sharing stream over Wi-Fi network with real desktop capture."""

    def __init__(
        self,
        device_name: str = "Pardus Ekran Sunucusu",
        port: Optional[int] = None,
        config: Optional[StreamConfig] = None,
    ):
        self.device_name = device_name
        # Akış parametreleri config'den (GSettings/JSON) gelir; hardcoded değil.
        # config verilmezse AppConfig'den kurulur, o da yoksa DTO varsayılanları.
        self._config = config if config is not None else self._load_config()
        # Geriye-uyum: açık `port` kwarg'ı config portunu ezer (mevcut çağıranlar).
        if port is not None:
            self._config = replace(self._config, port=port)
        self.port = self._config.port
        self._streaming_event = threading.Event()  # Thread-safe streaming flag
        self.httpd: Optional[socketserver.TCPServer] = None
        self.pairing_mgr = ScreenPairingManager()

        from pardus_paylasim.screen.pairing import SessionManager

        self.session_mgr = SessionManager()
        self._current_frame: Optional[bytes] = None
        self._frame_lock = threading.Lock()
        self._capture_thread: Optional[threading.Thread] = None
        # Denenen GStreamer backend'i; ilk kare gelince capture_backend'e yazılır.
        self._pending_backend: Optional[str] = None
        # Yakalanan gerçek çözünürlük. Native modda ilk JPEG'den doldurulur
        # (dürüst /info); ölçekli modda config'in çözünürlük etiketi.
        self.capture_resolution = (
            "unknown" if self._config.is_native_resolution else self._config.resolution_label
        )
        # Set when no working capture backend exists (honest state, not fake frames).
        self.capture_error: Optional[str] = None
        # Aktif yakalama backend'i ("pipewire"/"x11"/"scrot"/... ); /info'da göster.
        self.capture_backend: Optional[str] = None
        # Query-string PIN kullanımı bir kez uyarılır (log spam engelle).
        self._query_pin_warned = False
        # Web istemci CORS izin listesi (allowlist). Boş → hiçbir origin echo
        # edilmez, joker '*' ASLA gönderilmez (yalnız pinlenmiş origin'ler).
        self.allowed_web_origins: frozenset = self._load_allowed_origins()

        # Detect available capture methods
        self.has_gstreamer = shutil.which("gst-launch-1.0") is not None
        self.has_gnome_screenshot = shutil.which("gnome-screenshot") is not None
        self.has_import = shutil.which("import") is not None  # ImageMagick
        self.has_scrot = shutil.which("scrot") is not None
        self._gst_process: Optional[subprocess.Popen] = None

        # TLS: ephemeral self-signed cert şifreler; fingerprint PIN akışında
        # öğrenilip akıştan önce doğrulanır (MITM koruması). cryptography yoksa
        # düz HTTP'ye düşer (yalnız asgari geliştirme kurulumu).
        self.tls_enabled = tls_util.HAS_TLS
        self.cert_fingerprint: Optional[str] = None
        self._tls_cert_path: Optional[str] = None
        self._tls_key_path: Optional[str] = None
        self._ssl_context = None

        # Uzaktan kontrol kanalı (AnyDesk-tarzı). Default KAPALI; host açıkça
        # "Kontrole İzin Ver"i açana dek /control upgrade reddedilir. Tembel
        # import: control_server yalnız gerektiğinde yüklenir (Xlib/pynput
        # gibi Linux-only bağımlılıklar modül seviyesinde zorunlu olmasın).
        from pardus_paylasim.screen.control_server import ControlChannelServer

        self.control_server = ControlChannelServer(self)

    @staticmethod
    def _load_config() -> StreamConfig:
        """AppConfig'den StreamConfig kur; okunamazsa DTO varsayılanları.

        AppConfig import/erişimi (GSettings başlatma vb.) çökerse akış yine
        güvenli varsayılanlarla ayağa kalkar (fail-safe).
        """
        try:
            from pardus_paylasim.config import AppConfig

            return StreamConfig.from_app_config(AppConfig())
        except Exception as e:
            logger.warning("Akış yapılandırması okunamadı, varsayılan: %s", e)
            return StreamConfig()

    @staticmethod
    def _load_allowed_origins() -> frozenset:
        """AppConfig'ten CORS allowlist'i oku; okunamazsa boş (fail-safe).

        `allow_web_origin` virgülle ayrık origin listesi. Boş/okunamaz →
        boş küme: hiçbir origin echo edilmez, '*' asla gönderilmez.
        """
        try:
            from pardus_paylasim.config import AppConfig

            raw = AppConfig().get("allow_web_origin", "")
        except Exception as e:
            logger.warning("CORS allowlist okunamadı, boş: %s", e)
            return frozenset()
        return parse_allowed_origins(raw)

    def warn_query_pin_deprecated(self) -> None:
        """Query-string PIN kullanıldığında bir kez uyar. PIN URL'de sızar
        (access-log, proxy, Referer) → `X-Pardus-PIN` header tercih edilmeli."""
        if not self._query_pin_warned:
            self._query_pin_warned = True
            logger.warning(
                "DEPRECATED: PIN query-string ile geldi (?pin=). URL'e sızar; "
                "istemci X-Pardus-PIN header kullanmalı."
            )

    @property
    def frame_interval(self) -> float:
        """Kare servis aralığı (saniye) = 1/framerate. Handler döngüsü kullanır."""
        return self._config.frame_interval

    @property
    def is_streaming(self) -> bool:
        return self._streaming_event.is_set()

    @is_streaming.setter
    def is_streaming(self, value: bool):
        if value:
            self._streaming_event.set()
        else:
            self._streaming_event.clear()

    def start_server(self, pin_callback: Optional[Callable[[str], None]] = None) -> str:
        """Starts the screen stream server and returns the authorization PIN."""
        self.pin_callback = pin_callback
        # Generate initial PIN for any client
        pin = self.pairing_mgr.generate_pin_for_request("127.0.0.1", "Local Host")
        if pin_callback:
            pin_callback(pin)

        self.is_streaming = True
        MJPEGHandler.server_instance = self

        # TLS sertifikasını akıştan önce hazırla (fingerprint /info + /request_pin
        # ile istemciye ulaşır, o da pinler).
        self._setup_tls()

        # Start HTTP server
        threading.Thread(target=self._run_http_server, daemon=True).start()

        # Start frame capture
        self._start_frame_capture()

        return pin

    def _setup_tls(self):
        """Ephemeral self-signed sertifika üretir, SSLContext hazırlar."""
        if not self.tls_enabled:
            raise RuntimeError(
                "TLS (cryptography) eksik. Faz 1 Fail-closed: "
                "Ekran akışı ŞİFRESİZ (düz HTTP) BAŞLATILAMAZ. Lütfen python3-cryptography kurun."
            )
        try:
            cert_path, key_path, fingerprint = tls_util.generate_self_signed_cert()
            self._ssl_context = tls_util.build_server_context(cert_path, key_path)
            self._tls_cert_path = cert_path
            self._tls_key_path = key_path
            self.cert_fingerprint = fingerprint
            logger.info("TLS etkin. Sertifika parmak izi: %s", fingerprint[:16])
        except Exception as e:
            self.tls_enabled = False
            self._ssl_context = None
            raise RuntimeError(f"TLS kurulumu başarısız. Faz 1 Fail-closed: {e}")

    def _run_http_server(self):
        try:
            socketserver.TCPServer.allow_reuse_address = True
            self.httpd = socketserver.ThreadingTCPServer(("0.0.0.0", self.port), MJPEGHandler)
            # TLS sarımı: dinleyen soketi self-signed sertifika ile şifrele.
            if self.tls_enabled and self._ssl_context is not None:
                self.httpd.socket = self._ssl_context.wrap_socket(
                    self.httpd.socket, server_side=True
                )
            self.httpd.serve_forever()
        except OSError as e:
            logger.error("Port %s kullanılıyor: %s", self.port, e)
        except Exception as e:
            logger.error("Sunucu hatası: %s", e)

    def _start_frame_capture(self):
        """Start real screen capture using best available method."""
        self._capture_thread = threading.Thread(target=self._frame_capture_loop, daemon=True)
        self._capture_thread.start()

    def _frame_capture_loop(self):
        """Capture frames using the session-appropriate backend, then fallbacks.

        Oturum tipine göre GStreamer yolu sıralanır: Wayland'da ximagesrc
        (X11) çalışmaz → doomed süreç spawn etme, yalnız PipeWire dene. X11'de
        ximagesrc önce (PipeWire portal onayı/servis gerektirebilir). Bilinmeyen
        oturumda ikisi de denenir. Hepsi çökerse ekran-görüntüsü fallback.
        """
        if self.has_gstreamer:
            for backend in self._gstreamer_backend_order():
                if backend == "pipewire" and self._try_gstreamer_pipewire():
                    return
                if backend == "x11" and self._try_gstreamer_x11():
                    return

        # Son çare: ekran-görüntüsü aracı döngüsü (scrot/import/gnome-screenshot).
        self._fallback_screenshot_loop()

    def _gstreamer_backend_order(self) -> list:
        """Oturuma göre GStreamer backend deneme sırası döndür.

        Wayland → yalnız ['pipewire'] (ximagesrc Wayland'da kesin çöker,
        boşuna deneme). X11 → ['x11', 'pipewire'] (yerel ximagesrc önce).
        Bilinmeyen → ['pipewire', 'x11'] (eski davranış: en genel önce).
        """
        session = session_type()
        if session == SESSION_WAYLAND:
            return ["pipewire"]
        if session == SESSION_X11:
            return ["x11", "pipewire"]
        return ["pipewire", "x11"]

    def _try_gstreamer_pipewire(self) -> bool:
        """Try PipeWire-based screen capture via GStreamer."""
        # PipeWire screen capture pipeline
        # NOTE: multipartmux removed - HTTP handler adds multipart framing.
        # Output raw JPEG frames to stdout for proper extraction.
        # Ölçek/fps/kalite config'den (hardcoded değil); native → scale yok.
        pipeline = (
            "pipewiresrc do-timestamp=true ! "
            "videoconvert ! "
            f"{self._config.gst_scale_fragment()}"
            "videorate ! "
            f"{self._config.gst_framerate_caps()} ! "
            f"{self._config.gst_jpegenc()} ! "
            "fdsink fd=1"
        )
        return self._spawn_gstreamer("pipewire", pipeline)

    def _try_gstreamer_x11(self) -> bool:
        """Try X11-based screen capture via GStreamer."""
        # Detect display
        display = os.environ.get("DISPLAY", ":0")
        # Ölçek/fps/kalite config'den (hardcoded değil); native → scale yok.
        pipeline = (
            f"ximagesrc display={display} use-damage=false ! "
            f"videoconvert ! "
            f"{self._config.gst_scale_fragment()}"
            f"videorate ! "
            f"{self._config.gst_framerate_caps()} ! "
            f"{self._config.gst_jpegenc()} ! "
            f"fdsink fd=1"
        )
        return self._spawn_gstreamer("x11", pipeline)

    def _spawn_gstreamer(self, backend: str, pipeline: str) -> bool:
        """GStreamer sürecini başlat, stderr'i topla, kareleri oku.

        stderr=PIPE + ayrı drenaj thread'i: pipe deadlock olmaz (aksi halde
        GStreamer stderr'i doldurunca yazma bloke olurdu). Süreç kare üretmeden
        ölürse toplanan stderr `capture_error`'a yazılır → `/info` dürüst tanı.
        Başarılı yolda `capture_backend` set + `capture_error` temizlenir.
        """
        try:
            self._gst_process = subprocess.Popen(
                ["gst-launch-1.0", "-q"] + shlex.split(pipeline),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as e:
            self.capture_error = f"GStreamer ({backend}) başlatılamadı: {e}"
            logger.warning(self.capture_error)
            return False

        stderr_chunks: list = []
        stderr_thread = self._drain_stderr(self._gst_process, stderr_chunks)

        produced = self._read_gst_frames_with_backend(backend)
        if produced:
            return True

        # Kare geldiyse (_pending_backend temizlendi) süreç sonradan ölmüş →
        # bu backend çalıştı, sonraki backend'e düşürme, hata yazma.
        if self._pending_backend is None and self.capture_backend == backend:
            return True

        # Hiç kare üretmeden çöktü: stderr'i topla, tanıyı kaydet.
        if stderr_thread is not None:
            stderr_thread.join(timeout=1)
        detail = b"".join(stderr_chunks).decode("utf-8", "replace").strip()
        # Son anlamlı satır en yararlısı (GStreamer hata zincirinin sonu).
        last_line = detail.splitlines()[-1] if detail else ""
        self.capture_error = f"GStreamer ({backend}) kare üretmedi. {last_line}".strip()
        logger.warning(self.capture_error)
        return False

    @staticmethod
    def _drain_stderr(process, sink: list):
        """Sürecin stderr'ini arka planda oku (pipe deadlock önle). Thread döner."""
        stderr = getattr(process, "stderr", None)
        if stderr is None:
            return None

        def _pump():
            try:
                for chunk in iter(lambda: stderr.read(4096), b""):
                    sink.append(chunk)
            except Exception:
                pass

        thread = threading.Thread(target=_pump, daemon=True)
        thread.start()
        return thread

    def _read_gst_frames_with_backend(self, backend: str) -> bool:
        """`_read_gst_frames` sarmalayıcı: ilk kare gelince backend'i işaretle."""
        self._pending_backend = backend
        return self._read_gst_frames()

    def _read_gst_frames(self) -> bool:
        """Read JPEG frames from GStreamer subprocess stdout."""
        if not self._gst_process or not self._gst_process.stdout:
            return False

        buffer = b""
        MAX_BUFFER = 500000  # 500KB cap to prevent memory bloat
        try:
            while self.is_streaming:
                chunk = self._gst_process.stdout.read(8192)
                if not chunk:
                    # Process died - check return code
                    self._gst_process.poll()
                    return False  # Signal that capture failed
                buffer += chunk
                # Cap buffer to prevent unbounded growth
                if len(buffer) > MAX_BUFFER:
                    buffer = buffer[-MAX_BUFFER // 2 :]
                # Saf parser: tam kareleri ayıkla, yarım kalanı geri besle.
                jpeg_frames, buffer = extract_jpeg_frames(buffer)
                for jpeg in jpeg_frames:
                    with self._frame_lock:
                        self._current_frame = jpeg
                    # İlk gerçek kare: backend'i işaretle, önceki hatayı temizle.
                    if self._pending_backend is not None:
                        self.capture_backend = self._pending_backend
                        self._pending_backend = None
                        self.capture_error = None
                    self._update_native_resolution(jpeg)
            return True
        except Exception:
            return False

    def _fallback_screenshot_loop(self):
        """Universal fallback: capture screen via screenshot tools."""
        if self.has_scrot:
            screenshot_cmd = ["scrot", "-z"]
            backend_label = "scrot"
        elif self.has_import:
            screenshot_cmd = ["import", "-window", "root"]
            backend_label = "import"
        elif self.has_gnome_screenshot:
            screenshot_cmd = ["gnome-screenshot", "-f"]
            backend_label = "gnome-screenshot"
        else:
            # No screenshot tool available - report honestly, do not fake a stream.
            msg = (
                "Ekran yakalama aracı bulunamadı. GStreamer, gnome-screenshot, "
                "ImageMagick (import) veya scrot kurun."
            )
            self.capture_error = msg
            logger.error(msg)
            self.is_streaming = False
            return

        tmp_path = f"/tmp/pardus_screen_{os.getpid()}.jpg"
        tmp_write_path = tmp_path + ".tmp"

        while self.is_streaming:
            try:
                env = os.environ.copy()
                env["CANBERRA_DRIVER"] = "null"  # Silence shutter sounds

                cmd = screenshot_cmd + [tmp_write_path]
                subprocess.run(cmd, timeout=3, capture_output=True, env=env)

                if os.path.exists(tmp_write_path) and os.path.getsize(tmp_write_path) > 100:
                    os.replace(tmp_write_path, tmp_path)
                    with open(tmp_path, "rb") as f:
                        frame = f.read()
                    with self._frame_lock:
                        self._current_frame = frame
                    # İlk kare: fallback backend'i işaretle (dürüst /info).
                    if self.capture_backend is None:
                        self.capture_backend = backend_label
                    self._update_native_resolution(frame)
            except Exception:
                pass
            # Kare aralığı config'den (1/fps); hardcoded 0.04 değil.
            time.sleep(self._config.frame_interval)

    def _update_native_resolution(self, jpeg: bytes) -> None:
        """Native modda ilk kareden gerçek çözünürlüğü oku → dürüst /info.

        Ölçekli modda config etiketi zaten doğru; dokunma. Bir kez çözüldükten
        sonra (unknown değilse) tekrar decode etme — sıcak yolda gereksiz iş.
        """
        if not self._config.is_native_resolution:
            return
        if self.capture_resolution != "unknown":
            return
        dims = parse_jpeg_dimensions(jpeg)
        if dims is not None:
            self.capture_resolution = f"{dims[0]}x{dims[1]}"

    def get_current_frame(self) -> Optional[bytes]:
        with self._frame_lock:
            return self._current_frame

    def stop_server(self):
        # 1. Signal all loops to stop
        self._streaming_event.clear()

        # 2. Stop GStreamer process first (unblocks capture thread)
        if self._gst_process:
            try:
                self._gst_process.terminate()
                self._gst_process.wait(timeout=2)
            except Exception:
                try:
                    self._gst_process.kill()
                except Exception:
                    pass
            self._gst_process = None

        # Join capture thread to ensure clean shutdown
        if self._capture_thread and self._capture_thread.is_alive():
            try:
                self._capture_thread.join(timeout=2)
            except Exception:
                pass
        self._capture_thread = None

        # Stop HTTP server
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass

        # Clean temp file
        tmp_path = f"/tmp/pardus_screen_{os.getpid()}.jpg"
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        # TLS geçici sertifika/anahtar dosyalarını sil (0600 izinli temp).
        for tls_path in (self._tls_cert_path, self._tls_key_path):
            if tls_path and os.path.exists(tls_path):
                try:
                    os.remove(tls_path)
                except OSError:
                    pass
        self._tls_cert_path = None
        self._tls_key_path = None
