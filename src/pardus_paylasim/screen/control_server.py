"""
Uzaktan kontrol kanalı sunucusu (`control_server`).

Mevcut TLS-pinlenmiş MJPEG HTTP sunucusu (port 52345) üstünde WebSocket
`/control` uç noktası açar. `http.server` WebSocket bilmez → RFC6455 upgrade
elle yapılır: `101 Switching Protocols` sonrası soket ele geçirilir (hijack),
istemci→sunucu maskeli çerçeveler çözülür.

Güven modeli (Faz 1 — MVP; katı consent 1.4'te sertleşir):
- **Host toggle (default KAPALI, oturum-only):** açık değilse geçerli PIN'le
  bile `/control` upgrade reddedilir.
- **PIN doğrulama:** upgrade öncesi `X-Pardus-PIN` header doğrulanır
  (`ScreenPairingManager.verify_pin`) — görüntüleme yoluyla aynı eşleşme.
- **Per-oturum token:** grant edilince istemci IP'sine bağlı token üretilir;
  istemci her mesajda `sid` olarak taşır, sunucu **her mesajda** doğrular
  (yalnız upgrade'de değil) → ele geçirilmiş soket revoke sonrası enjekte edemez.
- **Enjeksiyon reddi:** uygun backend yoksa (`input_inject.create_backend`
  None) kontrol reddedilir (`grant allow=False`).

Saf/headless-test edilebilir parçalar (soket/GTK gerektirmez): handshake
accept-key hesabı, çerçeve maskele/çöz, çerçeve kur/oku (BytesIO ile).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import struct
import threading
import time
from typing import Dict, Optional, Tuple

from pardus_paylasim import platform_info
from pardus_paylasim.discovery.history import (
    STATUS_CONTROL_START,
    STATUS_CONTROL_STOP,
    TransferHistory,
)
from pardus_paylasim.screen import control_protocol as cp
from pardus_paylasim.screen import input_inject

logger = logging.getLogger(__name__)

# RFC6455 sabit GUID: Sec-WebSocket-Accept hesabında client key'e eklenir.
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# WebSocket opcode'ları (RFC6455 §5.2).
OP_CONT = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

# Kapatma kodları (RFC6455 §7.4.1).
CLOSE_NORMAL = 1000
CLOSE_PROTOCOL_ERR = 1002
CLOSE_UNSUPPORTED = 1003
CLOSE_TOO_BIG = 1009

# Çerçeve payload üst sınırı: protokol mesaj tavanıyla aynı (güvenlik). Kontrol
# mesajları küçük; bu tavan dev/uydurma payload'u daha çözmeden reddeder.
_MAX_FRAME_PAYLOAD = cp.MAX_MESSAGE_BYTES

# Olay hız tavanı (~mesaj/saniye). Ele geçirilmiş/kötü istemcinin enjeksiyon
# taşmasını bağlar; aşan mesajlar sessizce düşürülür (kanal kapanmaz).
_RATE_LIMIT_PER_SEC = 500

# Backend/oturum ekran çözünürlüğü çözülemezse güvenli varsayılan (piksel).
_FALLBACK_SCREEN_W = 1920
_FALLBACK_SCREEN_H = 1080

# Tehlikeli sanal-terminal (VT) geçiş tuşları: Ctrl+Alt+F1..F12 host'u başka bir
# TTY'ye atar (grafik oturumu arka plana düşer, uzak istemci kör kalır). Bu
# kombinasyonlar opt-in olmadan bloklanır (C4 — kapsam limiti).
_VT_SWITCH_KEYS = frozenset(f"KEY_F{i}" for i in range(1, 13))


# --- Saf WebSocket yardımcıları (headless test edilebilir) --------------------


def compute_accept_key(client_key: str) -> str:
    """`Sec-WebSocket-Accept` başlık değerini hesapla (RFC6455 §4.2.2).

    base64( SHA-1( client_key + WS_GUID ) ). İstemci `Sec-WebSocket-Key`
    başlığını verir; sunucu bu sabit dönüşümle yanıtlar → istemci gerçekten
    WebSocket handshake beklediğini doğrular.
    """
    digest = hashlib.sha1((client_key + _WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def build_handshake_response(accept_key: str) -> bytes:
    """`101 Switching Protocols` handshake yanıtını (ham baytlar) kur."""
    return (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept_key}\r\n"
        "\r\n"
    ).encode("ascii")


def mask_payload(payload: bytes, mask: bytes) -> bytes:
    """XOR maskeleme/çözme (simetrik — aynı işlem her iki yön için).

    İstemci→sunucu çerçeveleri RFC6455 gereği maskelidir; aynı 4-baytlık
    anahtarla XOR uygulayınca hem maskele hem çöz işi görür.
    """
    return bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


def build_frame(opcode: int, payload: bytes = b"") -> bytes:
    """Sunucu→istemci WebSocket çerçevesi kur (FIN=1, MASK=0).

    Sunucu çerçeveleri maskelenMEZ (RFC6455 §5.1). Payload uzunluğu 7-bit /
    16-bit / 64-bit genişletilmiş formda kodlanır.
    """
    b0 = 0x80 | (opcode & 0x0F)  # FIN=1 + opcode
    length = len(payload)
    if length < 126:
        header = struct.pack("!BB", b0, length)
    elif length < 65536:
        header = struct.pack("!BBH", b0, 126, length)
    else:
        header = struct.pack("!BBQ", b0, 127, length)
    return header + payload


def encode_text_frame(text: str) -> bytes:
    """Metin (JSON) çerçevesi kur (sunucu→istemci, maskesiz)."""
    return build_frame(OP_TEXT, text.encode("utf-8"))


def encode_close_frame(code: int = CLOSE_NORMAL, reason: str = "") -> bytes:
    """Kapatma çerçevesi kur (2-bayt kod + opsiyonel gerekçe)."""
    return build_frame(OP_CLOSE, struct.pack("!H", code) + reason.encode("utf-8"))


def build_client_frame(opcode: int, payload: bytes = b"", mask: Optional[bytes] = None) -> bytes:
    """İstemci→sunucu WebSocket çerçevesi kur (FIN=1, MASK=1).

    İstemci çerçeveleri RFC6455 §5.1 gereği MASKELİ olmalı: uzunluk baytının en
    yüksek biti (0x80) set edilir, 4-baytlık maske eklenir, payload `mask_payload`
    ile XOR'lanır. `mask` verilmezse kriptografik rastgele üretilir (her çerçeve
    ayrı maske — RFC önerisi). Saf: soket/GTK gerektirmez → BytesIO ile test.
    """
    if mask is None:
        mask = secrets.token_bytes(4)
    b0 = 0x80 | (opcode & 0x0F)  # FIN=1 + opcode
    length = len(payload)
    if length < 126:
        header = struct.pack("!BB", b0, 0x80 | length)
    elif length < 65536:
        header = struct.pack("!BBH", b0, 0x80 | 126, length)
    else:
        header = struct.pack("!BBQ", b0, 0x80 | 127, length)
    return header + mask + mask_payload(payload, mask)


def encode_client_text_frame(text: str, mask: Optional[bytes] = None) -> bytes:
    """Maskeli metin (JSON) çerçevesi kur (istemci→sunucu)."""
    return build_client_frame(OP_TEXT, text.encode("utf-8"), mask)


def read_server_frame(reader) -> Tuple[int, bytes]:
    """Sunucu→istemci WebSocket çerçevesi oku → (opcode, payload).

    `read_client_frame`'in karşıtı: sunucu çerçeveleri RFC6455 §5.1 gereği
    maskesiz OLMALI → maskeli çerçeve protokol ihlali (istemci maske çözmeyi
    beklemez). Payload maskesiz doğrudan döner. `_MAX_FRAME_PAYLOAD` tavanı
    burada da uygulanır (kötü/dev sunucu payload'una karşı). Saf: `reader`
    yalnız `read(n)` gerektirir → BytesIO ile test edilebilir.
    """
    b0, b1 = struct.unpack("!BB", _read_exact(reader, 2))
    opcode = b0 & 0x0F
    masked = bool(b1 & 0x80)
    length = b1 & 0x7F

    if masked:
        # Sunucu çerçevesi maskeli gelemez (§5.1).
        raise FrameError("sunucu çerçevesi maskesiz olmalı")

    if length == 126:
        (length,) = struct.unpack("!H", _read_exact(reader, 2))
    elif length == 127:
        (length,) = struct.unpack("!Q", _read_exact(reader, 8))

    if length > _MAX_FRAME_PAYLOAD:
        raise FrameError(f"çerçeve çok büyük: {length} > {_MAX_FRAME_PAYLOAD}")

    payload = _read_exact(reader, length) if length else b""
    return opcode, payload


class FrameError(Exception):
    """WebSocket çerçeve protokolü ihlali (maskesiz istemci çerçevesi, aşırı
    boy, EOF). Sunucu bunu yakalar → kanalı uygun close koduyla kapatır."""


def _read_exact(reader, n: int) -> bytes:
    """`reader`'dan tam `n` bayt oku; erken EOF → FrameError.

    Soket makefile BufferedReader ya da BytesIO (test) ile çalışır. Kısa
    okumalara karşı döngüyle tam `n` toplanır.
    """
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = reader.read(remaining)
        if not chunk:
            raise FrameError("erken EOF (bağlantı kapandı)")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_client_frame(reader) -> Tuple[int, bytes]:
    """İstemci→sunucu WebSocket çerçevesi oku → (opcode, çözülmüş payload).

    İstemci çerçeveleri RFC6455 §5.1 gereği maskeli OLMALI → maskesiz çerçeve
    protokol ihlali. Payload `_MAX_FRAME_PAYLOAD`'ı aşarsa reddedilir (güvenlik).
    Saf: `reader` yalnız `read(n)` gerektirir → BytesIO ile test edilebilir.
    """
    b0, b1 = struct.unpack("!BB", _read_exact(reader, 2))
    opcode = b0 & 0x0F
    masked = bool(b1 & 0x80)
    length = b1 & 0x7F

    if not masked:
        # İstemci çerçevesi maskesiz gelemez (§5.1). Enjeksiyona ham veri geçmesin.
        raise FrameError("istemci çerçevesi maskeli olmalı")

    if length == 126:
        (length,) = struct.unpack("!H", _read_exact(reader, 2))
    elif length == 127:
        (length,) = struct.unpack("!Q", _read_exact(reader, 8))

    if length > _MAX_FRAME_PAYLOAD:
        raise FrameError(f"çerçeve çok büyük: {length} > {_MAX_FRAME_PAYLOAD}")

    mask = _read_exact(reader, 4)
    payload = _read_exact(reader, length) if length else b""
    return opcode, mask_payload(payload, mask)


# --- Ekran çözünürlüğü çözücü -------------------------------------------------


def resolve_screen_size() -> Tuple[int, int]:
    """Host ekran çözünürlüğünü (piksel) çöz; başarısızsa güvenli varsayılan.

    Normalize 0..1 koordinat gerçek piksele çarpılacağı için host ekran boyutu
    gerekir (akış karesinin ölçekli boyutu DEĞİL). X11'de Xlib ekranını sorgular;
    Xlib yoksa/Wayland'da başarısızsa `_FALLBACK_SCREEN_*`. Tembel import →
    Windows/Xlib'siz ortamda modül yine yüklenir.
    """
    try:
        import Xlib.display

        screen = Xlib.display.Display().screen()
        width = int(screen.width_in_pixels)
        height = int(screen.height_in_pixels)
        if width > 0 and height > 0:
            return width, height
    except Exception as exc:  # pragma: no cover - ortama bağlı
        logger.debug("Ekran boyutu Xlib ile çözülemedi: %s", exc)
    return _FALLBACK_SCREEN_W, _FALLBACK_SCREEN_H


# --- Tehlikeli tuş filtresi (saf — headless test edilebilir) ------------------


def is_dangerous_key(event) -> bool:
    """Olay VT-geçiş (Ctrl+Alt+F1..F12) tuş kombinasyonu mu?

    Yalnız `KeyEvent` için anlamlı; başka olay türleri her zaman False. VT geçişi
    host'u başka TTY'ye atıp uzak istemciyi kör bırakır → opt-in olmadan
    bloklanır. `mods` hem "ctrl" hem "alt" içerir VE `code` bir F-tuşudur. Saf:
    modül dışı bağımlılık yok → doğrudan unit-test edilir.
    """
    if not isinstance(event, cp.KeyEvent):
        return False
    if event.code not in _VT_SWITCH_KEYS:
        return False
    mods = set(event.mods or ())
    return "ctrl" in mods and "alt" in mods


# --- Consent / oturum token defteri (minimal — 1.4 sertleştirir) --------------


class ControlConsent:
    """Host tarafı uzaktan kontrol izin durumu (thread-safe, granüler izinler dahil)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._allowed: bool = False
        self._granted_permissions = {"mouse": True, "keyboard": True, "clipboard": True}
        # client_ip -> token (yalnız o token o IP'den input sürebilir).
        self._tokens: Dict[str, str] = {}

    def is_allowed(self) -> bool:
        """Host kontrole izin verdi mi? (upgrade ön-koşulu)."""
        with self._lock:
            return self._allowed

    def set_allowed(self, value: bool) -> None:
        with self._lock:
            self._allowed = bool(value)
            if not self._allowed:
                self._tokens.clear()

    def check_permission(self, perm: str) -> bool:
        with self._lock:
            return self._allowed and self._granted_permissions.get(perm, False)

    def set_permissions(self, mouse: bool, keyboard: bool, clipboard: bool) -> None:
        with self._lock:
            self._granted_permissions["mouse"] = bool(mouse)
            self._granted_permissions["keyboard"] = bool(keyboard)
            self._granted_permissions["clipboard"] = bool(clipboard)

    def grant(self, session_token: str) -> Optional[str]:
        """İlgili session token'ına bağlı yeni kontrol token'ı (sid) üret. Toggle kapalıysa None."""
        with self._lock:
            if not self._allowed:
                return None
            sid = secrets.token_urlsafe(24)
            self._tokens[session_token] = sid
            return sid

    def revoke(self, session_token: str) -> None:
        """Tek istemcinin kontrol token'ını iptal et."""
        with self._lock:
            self._tokens.pop(session_token, None)

    def validate(self, session_token: str, sid: Optional[str]) -> bool:
        """Mesaj token'ını doğrula: toggle açık, oturum kayıtlı, token eşleşiyor.

        Sabit-zamanlı karşılaştırma (`secrets.compare_digest`) — token tahmin
        zamanlama yan-kanalını kapatır. Eksik/yanlış token → False (mesaj düşer).
        """
        if not sid or not session_token:
            return False
        with self._lock:
            if not self._allowed:
                return False
            expected = self._tokens.get(session_token)
        if expected is None:
            return False
        return secrets.compare_digest(expected, sid)


# --- Kontrol kanalı sunucusu --------------------------------------------------


class ControlChannelServer:
    """`/control` WebSocket upgrade'ini yönetir ve enjeksiyona dispatch eder.

    Sahibi `ScreenStreamServer`'dır (PIN eşleştirme + consent durumu oradan).
    `MJPEGHandler.do_GET`'teki `path == "/control"` dalı `handle_upgrade`'i
    çağırır.
    """

    def __init__(self, stream_server, history: Optional[TransferHistory] = None) -> None:
        self._server = stream_server
        self.consent = ControlConsent()
        # Kontrol oturumu denetim günlüğü (start/stop). Enjekte edilebilir (test).
        self._history = history or TransferHistory()
        # Tehlikeli tuşlara (VT geçiş Ctrl+Alt+F*) izin: default KAPALI (opt-in).
        self._allow_dangerous_keys = False

    # --- Dış API (UI entegrasyonu 1.8'de kullanır) ---
    def set_control_allowed(self, value: bool) -> None:
        """Host "Kontrole İzin Ver" anahtarını ayarla."""
        self.consent.set_allowed(value)

    def is_control_allowed(self) -> bool:
        return self.consent.is_allowed()

    def set_allow_dangerous_keys(self, value: bool) -> None:
        """VT-geçiş tuşlarına (Ctrl+Alt+F*) izin ver/reddet (opt-in)."""
        self._allow_dangerous_keys = bool(value)

    def is_dangerous_keys_allowed(self) -> bool:
        return self._allow_dangerous_keys

    def available_backend_name(self) -> Optional[str]:
        """Enjekte etmeden, bu oturumda seçilecek backend adını döndür (probe).

        `/info` bunu yayar → istemci kontrol İSTEMEDEN önce kontrolün mümkün
        olup olmadığını (ve hangi backend'le) bilir. Yan etki yok: yalnız
        mevcutluk probe'u + saf öncelik seçimi; backend kurulmaz, grant verilmez.
        Hiçbiri yoksa None (kontrol reddedilecek).
        """
        try:
            availability = input_inject.detect_availability()
            return input_inject.select_backend_name(platform_info.session_type(), availability)
        except Exception as e:  # pragma: no cover - ortama bağlı
            return None

    # --- Upgrade ---
    def handle_upgrade(self, handler) -> None:
        """`/control` GET isteğini WebSocket'e yükselt ve mesaj döngüsünü sür.

        Ön-koşullar (biri düşerse düz HTTP hatası, upgrade yok):
        1. Host toggle açık (`consent.is_allowed`).
        2. PIN doğrulandı (`handler._check_auth` → X-Pardus-PIN header).
        3. `Sec-WebSocket-Key` başlığı var.
        Sonra 101 yanıtı yazılır, soket ele geçirilir, token üretilir ve
        istemciye grant gönderilir.
        """
        client_ip = handler.client_address[0]

        # 1) Method GET
        if handler.command != "GET":
            self._reject(handler, 405, "BAD_METHOD", "Yalnızca GET metodu desteklenir.")
            return

        # 2) RFC 6455 Handshake Check
        upgrade = handler.headers.get("Upgrade", "").lower()
        if upgrade != "websocket":
            self._reject(handler, 400, "BAD_UPGRADE", "Upgrade başlığı websocket olmalıdır.")
            return

        connection = handler.headers.get("Connection", "").lower()
        if "upgrade" not in connection.split(",") and "upgrade" not in connection:
            self._reject(handler, 400, "BAD_CONNECTION", "Connection başlığı upgrade içermelidir.")
            return

        version = handler.headers.get("Sec-WebSocket-Version")
        if version != "13":
            self._reject(handler, 400, "BAD_VERSION", "Sec-WebSocket-Version 13 olmalıdır.")
            return

        # 3) Origin Check (Faz 4.1)
        origin = handler.headers.get("Origin")
        if origin and origin not in self._server.allowed_web_origins:
            self._reject(handler, 403, "BAD_ORIGIN", "Origin allowlist'te yok.")
            return

        # 4) Host kontrole izin vermedi → geçerli PIN'le bile reddet.
        if not self.consent.is_allowed():
            self._reject(handler, 403, "CONTROL_DISABLED", "Uzaktan kontrol host tarafında kapalı.")
            return

        # 5) PIN doğrula (görüntülemeyle aynı eşleşme; session token veya X-Pardus-Session).
        if not handler._check_auth():
            self._reject(handler, 403, "INVALID_PIN", "Kontrol için geçerli PIN gerekli.")
            return

        # 6) Sec-WebSocket-Key başlığı
        client_key = handler.headers.get("Sec-WebSocket-Key")
        if not client_key:
            self._reject(handler, 400, "BAD_KEY", "Sec-WebSocket-Key başlığı eksik.")
            return

        cookie_header = handler.headers.get("Cookie", "")
        session_token = None
        if "pardus_session=" in cookie_header:
            for part in cookie_header.split(";"):
                part = part.strip()
                if part.startswith("pardus_session="):
                    session_token = part[len("pardus_session=") :]
                    break
        if not session_token:
            session_token = handler.headers.get("X-Pardus-Session", "")

        # Scope (Kapsam Yalıtımı) kontrolü
        session_details = self._server.session_mgr.get_session_details(session_token)
        if not session_details or "control" not in session_details.get("capabilities", []):
            logger.warning("Kontrol reddedildi: İstemci scope yetkisi yetersiz.")
            self._reject(
                handler, 403, "FORBIDDEN_SCOPE", "Bu oturum sadece izleme yetkisine sahiptir."
            )
            return

        # Handshake yanıtını yaz → bu noktadan sonra soket WebSocket.
        accept = compute_accept_key(client_key.strip())
        try:
            handler.wfile.write(build_handshake_response(accept))
            handler.wfile.flush()
        except OSError as exc:
            logger.debug("Handshake yazılamadı: %s", exc)
            return

        # Enjeksiyon backend'i (X11→XTEST, Wayland→ydotool, ...). Yoksa reddet.
        backend = input_inject.create_backend()
        if backend is None:
            logger.warning("Kontrol reddedildi: uygun enjeksiyon backend'i yok.")
            self._audit(client_ip, STATUS_CONTROL_STOP, "no_backend")
            self._send(handler, cp.encode(cp.GrantEvent(session="", allow=False)))
            self._send_raw(handler, encode_close_frame(CLOSE_NORMAL))
            return

        # Oturum token'ı üret (oturum kimliğine bağlı) ve istemciye grant gönder.
        token = self.consent.grant(session_token)
        if token is None:  # yarış: toggle upgrade ile grant arası kapandı
            backend.close()
            self._audit(client_ip, STATUS_CONTROL_STOP, "disabled")
            self._send(handler, cp.encode(cp.GrantEvent(session="", allow=False)))
            self._send_raw(handler, encode_close_frame(CLOSE_NORMAL))
            return

        logger.info("Kontrol oturumu başladı: %s (backend=%s)", client_ip, backend.name)
        # Denetim: kontrol yetkisi verildi (C4 — kontrol asla sessiz kalmaz).
        self._audit(client_ip, STATUS_CONTROL_START, backend.name)
        self._send(handler, cp.encode(cp.GrantEvent(session=token, allow=True)))
        try:
            self._serve(handler, client_ip, session_token, backend)
        finally:
            self.consent.revoke(session_token)
            try:
                backend.close()
            except Exception as e:  # pragma: no cover
                pass
            # Denetim: kontrol oturumu bitti (normal kapanış/kill-switch/kopma).
            self._audit(client_ip, STATUS_CONTROL_STOP, "ended")
            logger.info("Kontrol oturumu bitti: %s", client_ip)

    # --- Mesaj döngüsü ---
    def _serve(self, handler, client_ip: str, token: str, backend) -> None:
        """Çerçeveleri oku → doğrula → enjekte et. Hız tavanı uygulanır.

        Her mesajda: (a) toggle hâlâ açık mı, (b) token geçerli mi (per-mesaj
        doğrulama). Herhangi biri düşerse mesaj enjekte edilMEZ; toggle kapanmışsa
        revoke gönderilip kanal kapatılır (kill-switch anlık düşer).
        """
        width, height = resolve_screen_size()
        reader = handler.rfile

        window_start = time.monotonic()
        count = 0

        while True:
            try:
                opcode, payload = read_client_frame(reader)
            except FrameError as exc:
                logger.debug("Çerçeve okunamadı, kanal kapanıyor: %s", exc)
                break

            if opcode == OP_CLOSE:
                break
            if opcode == OP_PING:
                self._send_raw(handler, build_frame(OP_PONG, payload))
                continue
            if opcode == OP_PONG:
                continue
            if opcode != OP_TEXT:
                # İkili/parça (continuation) desteklenmiyor: kontrol JSON metindir.
                self._send_raw(handler, encode_close_frame(CLOSE_UNSUPPORTED))
                break

            # Toggle kapandıysa (kill-switch) anında revoke + kapat.
            if not self.consent.is_allowed():
                self._send(handler, cp.encode(cp.RevokeEvent()))
                self._send_raw(handler, encode_close_frame(CLOSE_NORMAL))
                break

            # Hız tavanı: pencere başına sayaç; aşarsa mesajı düşür (kanal yaşar).
            now = time.monotonic()
            if now - window_start >= 1.0:
                window_start = now
                count = 0
            count += 1
            if count > _RATE_LIMIT_PER_SEC:
                continue

            try:
                event = cp.decode(payload)
            except cp.ProtocolError as exc:
                # Bozuk/geçersiz mesaj → düşür (asla ham veriyi enjekte etme).
                logger.debug("Geçersiz kontrol mesajı düştü: %s", exc)
                continue

            # Per-mesaj token doğrulama: grant sonrası tek geçerli token.
            sid = getattr(event, "sid", None)
            if not self.consent.validate(client_ip, sid):
                logger.debug("Token doğrulanamadı, mesaj düştü: %s", client_ip)
                continue

            # Tehlikeli tuş filtresi: VT geçiş (Ctrl+Alt+F*) opt-in olmadan bloklu.
            if not self._allow_dangerous_keys and is_dangerous_key(event):
                logger.warning("Tehlikeli tuş bloklandı (VT geçiş): %s", client_ip)
                continue

            # Token'ın scope yetkisini denetle (sadece view ise input olayı drop edilir)
            session_details = self._server.sessions.get_session_details(token)
            caps = session_details.get("capabilities", []) if session_details else []

            if isinstance(event, cp.ClipboardEvent):
                if "control" not in caps:
                    logger.warning(
                        "Olay reddedildi: token 'control' yetkisine sahip değil (clipboard)"
                    )
                    continue
                if not self.consent.check_permission("clipboard"):
                    continue
                try:
                    import pyperclip

                    pyperclip.copy(event.text)
                    self._last_clipboard = event.text
                except Exception as exc:
                    logger.debug("Pano eşitleme hatası: %s", exc)
                continue

            if isinstance(event, (cp.MouseMoveEvent, cp.MouseButtonEvent, cp.MouseScrollEvent)):
                if "control" not in caps:
                    logger.warning("Olay reddedildi: token 'control' yetkisine sahip değil (mouse)")
                    continue
                if not self.consent.check_permission("mouse"):
                    continue

            if isinstance(event, cp.KeyEvent):
                if "control" not in caps:
                    logger.warning(
                        "Olay reddedildi: token 'control' yetkisine sahip değil (keyboard)"
                    )
                    continue
                if not self.consent.check_permission("keyboard"):
                    continue

            try:
                input_inject.apply_event(backend, event, width, height)
            except Exception as exc:
                logger.debug("Backend injection error for event %s: %s", type(event), exc)
            # Polling host panosu (saniyede bir defadan fazla yormamak için basit kısıt)
            if self.consent.check_permission("clipboard"):
                try:
                    import pyperclip

                    current_clipboard = pyperclip.paste()
                    if not hasattr(self, "_last_clipboard"):
                        self._last_clipboard = current_clipboard
                    elif current_clipboard and current_clipboard != self._last_clipboard:
                        self._last_clipboard = current_clipboard
                        self._send(handler, cp.encode(cp.ClipboardEvent(text=current_clipboard)))
                except Exception as e:
                    pass

    # --- Denetim (audit) ---
    def _audit(self, client_ip: str, status: str, detail: str) -> None:
        """Kontrol oturumu denetim kaydı yaz; hata kanalı bozmasın (yut+logla)."""
        try:
            self._history.add_control(peer=client_ip, status=status, detail=detail)
        except Exception as exc:  # pragma: no cover - günlük yazımı kritik değil
            logger.debug("Kontrol denetim kaydı yazılamadı: %s", exc)

    # --- Düşük seviyeli yazma yardımcıları ---
    def _send(self, handler, text: str) -> None:
        """Metin (JSON) çerçevesi gönder; soket hatası sessiz (kanal kapanır)."""
        self._send_raw(handler, encode_text_frame(text))

    def _send_raw(self, handler, frame: bytes) -> None:
        try:
            handler.wfile.write(frame)
            handler.wfile.flush()
        except OSError as exc:  # pragma: no cover - istemci koptu
            logger.debug("Çerçeve gönderilemedi: %s", exc)

    def _reject(self, handler, status: int, code: str, message: str) -> None:
        """Upgrade öncesi düz HTTP JSON hatası (WebSocket'e geçmeden reddet)."""
        try:
            handler._send_json(f'{{"error":"{code}","message":"{message}"}}', status)
        except OSError as exc:  # pragma: no cover
            logger.debug("Red yanıtı yazılamadı: %s", exc)
