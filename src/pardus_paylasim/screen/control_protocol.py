"""
Uzaktan kontrol tel protokolü (`control_protocol`).

AnyDesk-tarzı kontrol kanalının mesaj codec'i. Transport-agnostik: aynı
kodlama native GTK istemcisi, tarayıcı WebSocket'i ve Windows companion
agent'ı tarafından paylaşılır (Faz 1/2/3). Yalnız stdlib (`json`) — GTK,
soket, GStreamer bağı YOK → tümüyle headless test edilebilir.

Tasarım kararları:
- **Versiyonlu zarf** (`v`): ileride kırıcı değişiklik için. Bilinmeyen ana
  sürüm reddedilir (sessiz yanlış-yorum değil).
- **Normalize koordinat 0..1**: istemci host çözünürlüğünü bilmez; host
  gerçek piksele çarpar. Akış-ortası çözünürlük değişiminde sağ kalır.
- **Layout-bağımsız `KEY_*` enum** (evdev input-event-codes adları): istemci
  GDK keyval → nötr enum, host enum → backend keysym. Windows↔Pardus arası
  klavye düzeni farkından bağımsız çalışır.
- **Fail-safe**: sayısal aralık taşması kırpılır (oturumu düşürmez); yapısal
  bozukluk (bilinmeyen tip, sayı-olmayan koord, geçersiz tuş) reddedilir.
- **Güvenlik**: her mesaj opsiyonel `sid` (oturum token) taşıyabilir → sunucu
  her mesajda doğrular (yalnız upgrade'de değil); ham boyut `MAX_MESSAGE_BYTES`
  ile sınırlı; bilinmeyen tip/alan reddedilir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Tuple, Union

# Tel protokol sürümü. `v` alanı eksikse bu varsayılır; farklı ana sürüm gelirse
# reddedilir (geriye-uyumsuz yorumla çökmek yerine açık hata).
PROTOCOL_VERSION = 1

# Mesaj tipleri (zarf `t` alanı).
T_MOVE = "move"
T_BTN = "btn"
T_SCROLL = "scroll"
T_KEY = "key"
T_GRANT = "grant"  # host -> istemci
T_REVOKE = "revoke"  # host -> istemci
T_PING = "ping"
T_PONG = "pong"
T_CLIPBOARD = "clipboard"

_KNOWN_TYPES = frozenset(
    {T_MOVE, T_BTN, T_SCROLL, T_KEY, T_GRANT, T_REVOKE, T_PING, T_PONG, T_CLIPBOARD}
)

# Fare düğmeleri ve klavye değiştiricileri (nötr adlar).
BUTTONS = frozenset({"left", "right", "middle"})
MODIFIERS = frozenset({"ctrl", "shift", "alt", "meta"})

# Ham mesaj bayt üst sınırı (payload cap — güvenlik). Kontrol mesajları küçüktür;
# bu bol bir tavan, dev/uydurma payload'u erkenden reddeder.
MAX_MESSAGE_BYTES = 512

# Kaydırma büyüklüğü sınırı: tek mesajda aşırı kaydırma enjeksiyonunu bağla.
SCROLL_MAX = 100.0


def _build_key_codes() -> frozenset:
    """Desteklenen layout-bağımsız `KEY_*` enum kümesini üret (evdev adları).

    Harf/rakam/fonksiyon tuşları programlı; navigasyon, değiştirici ve
    noktalama açıkça listelenir. Bu adlar hem XTEST (keysym), hem ydotool
    (uinput), hem Windows sanal-tuş eşlemesine tercüme edilebilir.
    """
    codes = set()
    for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        codes.add(f"KEY_{c}")
    for d in "0123456789":
        codes.add(f"KEY_{d}")
    for n in range(1, 13):
        codes.add(f"KEY_F{n}")
    codes.update(
        {
            "KEY_ENTER",
            "KEY_ESC",
            "KEY_BACKSPACE",
            "KEY_TAB",
            "KEY_SPACE",
            "KEY_LEFT",
            "KEY_RIGHT",
            "KEY_UP",
            "KEY_DOWN",
            "KEY_HOME",
            "KEY_END",
            "KEY_PAGEUP",
            "KEY_PAGEDOWN",
            "KEY_INSERT",
            "KEY_DELETE",
            "KEY_CAPSLOCK",
            "KEY_LEFTCTRL",
            "KEY_RIGHTCTRL",
            "KEY_LEFTSHIFT",
            "KEY_RIGHTSHIFT",
            "KEY_LEFTALT",
            "KEY_RIGHTALT",
            "KEY_LEFTMETA",
            "KEY_RIGHTMETA",
            "KEY_MINUS",
            "KEY_EQUAL",
            "KEY_LEFTBRACE",
            "KEY_RIGHTBRACE",
            "KEY_SEMICOLON",
            "KEY_APOSTROPHE",
            "KEY_GRAVE",
            "KEY_BACKSLASH",
            "KEY_COMMA",
            "KEY_DOT",
            "KEY_SLASH",
        }
    )
    return frozenset(codes)


KEY_CODES = _build_key_codes()


class ProtocolError(ValueError):
    """Bozuk/geçersiz kontrol mesajı. Sunucu bunu yakalar → mesajı düşürür
    (ve gerekirse kanalı kapatır), asla ham veriyi enjeksiyona geçirmez."""


# --- Mesaj modelleri (immutable) ---------------------------------------------


@dataclass(frozen=True)
class MoveEvent:
    """Fare hareketi. `x`/`y` normalize 0..1 (host gerçek piksele çarpar)."""

    x: float
    y: float
    sid: Optional[str] = None


@dataclass(frozen=True)
class ButtonEvent:
    """Fare düğmesi bas/bırak. Konum normalize 0..1."""

    button: str
    down: bool
    x: float
    y: float
    sid: Optional[str] = None


@dataclass(frozen=True)
class ScrollEvent:
    """Kaydırma. `dx`/`dy` göreli adım (±SCROLL_MAX ile sınırlı)."""

    dx: float
    dy: float
    sid: Optional[str] = None


@dataclass(frozen=True)
class KeyEvent:
    """Klavye tuşu bas/bırak. `code` layout-bağımsız `KEY_*` enum; `mods`
    aktif değiştiriciler (canonical: sıralı, tekilleştirilmiş)."""

    code: str
    down: bool
    mods: Tuple[str, ...] = ()
    sid: Optional[str] = None


@dataclass(frozen=True)
class GrantEvent:
    """Host → istemci: kontrol izni verildi/reddedildi. `session` = izinli
    oturum token'ı (yalnız `allow=True` iken anlamlı)."""

    session: str
    allow: bool


@dataclass(frozen=True)
class RevokeEvent:
    """Host → istemci: izin geri alındı (kill-switch/kapatma). Token ölür."""


@dataclass(frozen=True)
class PingEvent:
    """Canlılık yoklaması."""


@dataclass(frozen=True)
class PongEvent:
    """Ping yanıtı."""


@dataclass(frozen=True)
class ClipboardEvent:
    """Pano eşitleme (çift yönlü metin)."""

    text: str
    sid: Optional[str] = None


ControlEvent = Union[
    MoveEvent,
    ButtonEvent,
    ScrollEvent,
    KeyEvent,
    GrantEvent,
    RevokeEvent,
    PingEvent,
    PongEvent,
    ClipboardEvent,
]


# --- Yardımcılar --------------------------------------------------------------


def _clamp01(value: float) -> float:
    """Koordinatı [0.0, 1.0]'a kırp (fail-safe). Yuvarlama taşması oturumu
    düşürmesin diye reddetmek yerine kırpılır."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _clamp_scroll(value: float) -> float:
    """Kaydırma adımını ±SCROLL_MAX'a kırp."""
    if value < -SCROLL_MAX:
        return -SCROLL_MAX
    if value > SCROLL_MAX:
        return SCROLL_MAX
    return value


def _as_number(obj: dict, key: str) -> float:
    """Alanı sayı olarak al; yoksa/sayısal değilse ProtocolError."""
    if key not in obj:
        raise ProtocolError(f"eksik alan: {key}")
    val = obj[key]
    # bool int alt-tipidir; koordinat/sayı alanında kaza engelle.
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ProtocolError(f"sayısal olmayan alan: {key}={val!r}")
    return float(val)


def _as_bool(obj: dict, key: str) -> bool:
    if key not in obj:
        raise ProtocolError(f"eksik alan: {key}")
    val = obj[key]
    if not isinstance(val, bool):
        raise ProtocolError(f"bool olmayan alan: {key}={val!r}")
    return val


def _opt_sid(obj: dict) -> Optional[str]:
    """Opsiyonel oturum token'ı (`sid`). Varsa string olmalı."""
    if "sid" not in obj:
        return None
    sid = obj["sid"]
    if not isinstance(sid, str):
        raise ProtocolError("sid string olmalı")
    return sid


def _canonical_mods(raw) -> Tuple[str, ...]:
    """`mods` listesini doğrula → sıralı, tekilleştirilmiş tuple. Bilinmeyen
    değiştirici reddedilir."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ProtocolError("mods liste olmalı")
    seen = set()
    for m in raw:
        if not isinstance(m, str) or m not in MODIFIERS:
            raise ProtocolError(f"geçersiz değiştirici: {m!r}")
        seen.add(m)
    return tuple(sorted(seen))


# --- Kodla / çöz --------------------------------------------------------------


def encode(msg: ControlEvent) -> str:
    """Kontrol mesajını tel JSON string'ine kodla (versiyonlu zarf)."""
    if isinstance(msg, MoveEvent):
        body = {"t": T_MOVE, "x": msg.x, "y": msg.y}
        _attach_sid(body, msg.sid)
    elif isinstance(msg, ButtonEvent):
        body = {"t": T_BTN, "b": msg.button, "down": msg.down, "x": msg.x, "y": msg.y}
        _attach_sid(body, msg.sid)
    elif isinstance(msg, ScrollEvent):
        body = {"t": T_SCROLL, "dx": msg.dx, "dy": msg.dy}
        _attach_sid(body, msg.sid)
    elif isinstance(msg, KeyEvent):
        body = {"t": T_KEY, "code": msg.code, "down": msg.down, "mods": list(msg.mods)}
        _attach_sid(body, msg.sid)
    elif isinstance(msg, GrantEvent):
        body = {"t": T_GRANT, "session": msg.session, "allow": msg.allow}
    elif isinstance(msg, RevokeEvent):
        body = {"t": T_REVOKE}
    elif isinstance(msg, PingEvent):
        body = {"t": T_PING}
    elif isinstance(msg, PongEvent):
        body = {"t": T_PONG}
    elif isinstance(msg, ClipboardEvent):
        body = {"t": T_CLIPBOARD, "text": msg.text}
        _attach_sid(body, msg.sid)
    else:
        raise ProtocolError(f"kodlanamayan mesaj: {type(msg).__name__}")
    body["v"] = PROTOCOL_VERSION
    return json.dumps(body, separators=(",", ":"))


def _attach_sid(body: dict, sid: Optional[str]) -> None:
    """Zarfa oturum token'ı ekle (yalnız verilmişse)."""
    if sid is not None:
        body["sid"] = sid


def decode(raw: Union[str, bytes]) -> ControlEvent:
    """Tel JSON'unu doğrulanmış kontrol mesajına çöz.

    Bozuk/geçersiz/aşırı-boy girdi → ProtocolError (asla sessiz kabul).
    Sayısal aralık taşması kırpılır (fail-safe), yapısal hata reddedilir.
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("UTF-8 olmayan mesaj") from exc
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError(f"mesaj çok büyük: {len(raw)} > {MAX_MESSAGE_BYTES}")
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ProtocolError("geçersiz JSON") from exc
    if not isinstance(obj, dict):
        raise ProtocolError("mesaj JSON nesnesi olmalı")

    version = obj.get("v", PROTOCOL_VERSION)
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"desteklenmeyen sürüm: {version}")

    t = obj.get("t")
    if t not in _KNOWN_TYPES:
        raise ProtocolError(f"bilinmeyen mesaj tipi: {t!r}")

    if t == T_MOVE:
        return MoveEvent(
            x=_clamp01(_as_number(obj, "x")),
            y=_clamp01(_as_number(obj, "y")),
            sid=_opt_sid(obj),
        )
    if t == T_BTN:
        button = obj.get("b")
        if button not in BUTTONS:
            raise ProtocolError(f"geçersiz düğme: {button!r}")
        return ButtonEvent(
            button=button,
            down=_as_bool(obj, "down"),
            x=_clamp01(_as_number(obj, "x")),
            y=_clamp01(_as_number(obj, "y")),
            sid=_opt_sid(obj),
        )
    if t == T_SCROLL:
        return ScrollEvent(
            dx=_clamp_scroll(_as_number(obj, "dx")),
            dy=_clamp_scroll(_as_number(obj, "dy")),
            sid=_opt_sid(obj),
        )
    if t == T_KEY:
        code = obj.get("code")
        if code not in KEY_CODES:
            raise ProtocolError(f"geçersiz tuş kodu: {code!r}")
        return KeyEvent(
            code=code,
            down=_as_bool(obj, "down"),
            mods=_canonical_mods(obj.get("mods")),
            sid=_opt_sid(obj),
        )
    if t == T_GRANT:
        session = obj.get("session")
        if not isinstance(session, str):
            raise ProtocolError("grant.session string olmalı")
        return GrantEvent(session=session, allow=_as_bool(obj, "allow"))
    if t == T_REVOKE:
        return RevokeEvent()
    if t == T_PING:
        return PingEvent()
    if t == T_PONG:
        return PongEvent()
    if t == T_CLIPBOARD:
        text = obj.get("text")
        if not isinstance(text, str):
            raise ProtocolError("clipboard.text string olmalı")
        return ClipboardEvent(text=text, sid=_opt_sid(obj))
    # Buraya ulaşılamaz, _KNOWN_TYPES yukarıda garantili.
    raise ProtocolError(f"bilinmeyen t: {t}")
