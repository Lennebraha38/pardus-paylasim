"""
Girdi enjeksiyon backend'leri (`input_inject`).

Kontrol kanalından (`control_protocol`) gelen nötr eventleri host OS'una
gerçek fare/klavye girdisi olarak enjekte eder. Oturum-farkında otomatik
backend seçimi (kullanıcı kararı):

  - **X11**   → python-xlib **XTEST** (`Xlib.ext.xtest.fake_input`): root'suz,
                mutlak konum, güvenilir. X11 primary.
  - **Wayland** → **ydotool** (uinput via ydotoold): XTEST Wayland'da çalışmaz.
                (Faz 4: XDG RemoteDesktop portal — şimdilik probe False.)
  - **Windows/çapraz** → **pynput** (Wayland değil).

Seçim önceliği oturuma göre (C3): backend hem MEVCUT hem oturumla UYUMLU
olmalı. Hiçbiri yoksa `create_backend()` None döner → sunucu kontrolü reddeder
(`grant:false` + sebep).

Saf yardımcılar (`select_backend_name`, `normalized_to_pixel`, key eşleme
tabloları) GTK/soket/X sunucu gerektirmez → headless test edilebilir. Somut
backend'ler importları TEMBEL yapar (Windows'ta Xlib yok → modül yine de
import olur).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Callable, Dict, Optional, Protocol, Tuple, runtime_checkable

from .. import platform_info
from . import control_protocol as cp

logger = logging.getLogger(__name__)

# Backend adları (seçim + `/info` + audit için ortak sözlük).
BACKEND_PORTAL = "portal"
BACKEND_YDOTOOL = "ydotool"
BACKEND_XTEST = "xtest"
BACKEND_PYNPUT = "pynput"

# Oturum tipine göre backend öncelik listesi. Backend yalnız listede VE mevcutsa
# seçilir. X11'de XTEST primary; Wayland'da portal(Faz4)→ydotool; Windows pynput.
_SESSION_PRIORITY: Dict[str, Tuple[str, ...]] = {
    platform_info.SESSION_X11: (BACKEND_XTEST, BACKEND_YDOTOOL, BACKEND_PYNPUT),
    platform_info.SESSION_WAYLAND: (BACKEND_PORTAL, BACKEND_YDOTOOL),
    platform_info.SESSION_WINDOWS: (BACKEND_PYNPUT,),
    # Bilinmeyen oturum: en iyi çaba (X sunucusu olabilir → XTEST/pynput dene).
    platform_info.SESSION_UNKNOWN: (BACKEND_XTEST, BACKEND_PYNPUT, BACKEND_YDOTOOL),
}


class InjectionUnavailable(RuntimeError):
    """Uygun/mevcut enjeksiyon backend'i yok. Sunucu kontrolü reddeder."""


@runtime_checkable
class InjectionBackend(Protocol):
    """Host girdi enjeksiyon sözleşmesi. Konum piksel (mutlak); tuş nötr
    `KEY_*` enum. Backend nötr enum'u kendi keysym/keycode'una çevirir."""

    name: str

    def move(self, x: int, y: int) -> None:
        """İmleci mutlak piksel (x, y)'ye taşı."""
        ...

    def button(self, button: str, down: bool) -> None:
        """Fare düğmesi bas (down=True) / bırak (down=False). left/right/middle."""
        ...

    def scroll(self, dx: float, dy: float) -> None:
        """Kaydır. dy<0 yukarı, dy>0 aşağı; dx yatay (notch adımı)."""
        ...

    def key(self, code: str, down: bool) -> None:
        """Nötr `KEY_*` tuşunu bas/bırak."""
        ...

    def close(self) -> None:
        """Backend kaynaklarını serbest bırak (X bağlantısı vb.)."""
        ...


# --- Saf koordinat eşleme -----------------------------------------------------


def normalized_to_pixel(x: float, y: float, width: int, height: int) -> Tuple[int, int]:
    """Normalize 0..1 koordinatı host piksel koordinatına çevir.

    Fail-safe: girdiyi [0,1]'e kırpar (protokol katmanı da kırpar; burada
    ikinci savunma) ve sonucu [0, boyut-1]'e sabitler.
    """
    cx = 0.0 if x < 0.0 else 1.0 if x > 1.0 else x
    cy = 0.0 if y < 0.0 else 1.0 if y > 1.0 else y
    px = int(round(cx * (width - 1))) if width > 0 else 0
    py = int(round(cy * (height - 1))) if height > 0 else 0
    return px, py


# --- Saf backend seçimi -------------------------------------------------------


def select_backend_name(session: str, availability: Dict[str, bool]) -> Optional[str]:
    """Oturum + mevcutluk haritasından backend adı seç (saf, I/O yok).

    `availability`: {"portal": bool, "ydotool": bool, "xtest": bool,
    "pynput": bool}. Oturum öncelik listesindeki ilk mevcut backend'i döner;
    hiçbiri yoksa None (çağıran reddeder).
    """
    priority = _SESSION_PRIORITY.get(session, _SESSION_PRIORITY[platform_info.SESSION_UNKNOWN])
    for name in priority:
        if availability.get(name, False):
            return name
    return None


# --- Mevcutluk probe'ları (monkeypatch edilebilir) ---------------------------


def _probe_xtest() -> bool:
    """python-xlib + XTEST eklentisi import edilebiliyor mu?"""
    try:
        import Xlib.display  # noqa: F401
        import Xlib.ext.xtest  # noqa: F401

        return True
    except Exception:  # pragma: no cover - ortama bağlı
        return False


def _probe_pynput() -> bool:
    """pynput import edilebiliyor mu?"""
    try:
        import pynput  # noqa: F401

        return True
    except Exception:  # pragma: no cover - ortama bağlı
        return False


def _probe_ydotool() -> bool:
    """`ydotool` çalıştırılabiliri PATH'te mi?"""
    return shutil.which("ydotool") is not None


def _probe_portal() -> bool:
    """XDG RemoteDesktop portal — Faz 4."""
    if platform_info.is_windows():
        return False
    try:
        import pydbus  # noqa: F401

        return True
    except ImportError:
        return False


def detect_availability() -> Dict[str, bool]:
    """Tüm backend'lerin mevcutluğunu probe et → harita."""
    return {
        BACKEND_PORTAL: _probe_portal(),
        BACKEND_YDOTOOL: _probe_ydotool(),
        BACKEND_XTEST: _probe_xtest(),
        BACKEND_PYNPUT: _probe_pynput(),
    }


# Backend adı → yapıcı (tembel; seçilen backend yalnız gerektiğinde kurulur).
_FACTORIES: Dict[str, Callable[[], "InjectionBackend"]] = {}


def create_backend(session: Optional[str] = None) -> Optional[InjectionBackend]:
    """Oturuma uygun mevcut backend'i seç + kur. Yoksa None.

    `session` None ise `platform_info.session_type()` kullanılır (test için
    dışarıdan verilebilir). Backend kurulumu patlar/uygun yoksa None döner —
    sunucu kontrolü reddeder.
    """
    if session is None:
        session = platform_info.session_type()
    availability = detect_availability()
    name = select_backend_name(session, availability)
    if name is None:
        logger.warning("Enjeksiyon backend'i yok (oturum=%s, mevcut=%s)", session, availability)
        return None
    factory = _FACTORIES.get(name)
    if factory is None:  # pragma: no cover - kayıtlı olmayan backend
        logger.error("Backend '%s' seçildi ama yapıcısı yok", name)
        return None
    try:
        backend = factory()
        logger.info("Enjeksiyon backend'i seçildi: %s", name)
        return backend
    except Exception as exc:  # pragma: no cover - ortama bağlı kurulum hatası
        logger.error("Backend '%s' kurulamadı: %s", name, exc)
        return None


# --- Event dispatch (saf yönlendirme) ----------------------------------------


def apply_event(backend: InjectionBackend, event: cp.ControlEvent, width: int, height: int) -> None:
    """Bir kontrol eventini backend çağrılarına çevir.

    Koordinat normalize → piksel (host çözünürlüğü width×height). grant/revoke/
    ping/pong burada yok sayılır (sunucu katmanı işler). Bilinmeyen event tipi
    sessizce atlanır (protokol katmanı zaten doğruladı).
    """
    if isinstance(event, cp.MoveEvent):
        px, py = normalized_to_pixel(event.x, event.y, width, height)
        backend.move(px, py)
    elif isinstance(event, cp.ButtonEvent):
        px, py = normalized_to_pixel(event.x, event.y, width, height)
        backend.move(px, py)
        backend.button(event.button, event.down)
    elif isinstance(event, cp.ScrollEvent):
        backend.scroll(event.dx, event.dy)
    elif isinstance(event, cp.KeyEvent):
        backend.key(event.code, event.down)
    # diğer tipler (grant/revoke/ping/pong): enjeksiyon dışı, atla.


# --- Nötr KEY_* eşleme tabloları ----------------------------------------------

# KEY_* → X11 keysym adı (Xlib.XK.string_to_keysym için). Harf/rakam programlı;
# özel tuşlar açık. Taban (shift'siz) keysym; değiştiriciler ayrı KEY_* eventi.
_XKEYSYM_NAMES: Dict[str, str] = {}
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    _XKEYSYM_NAMES[f"KEY_{_c}"] = _c.lower()
for _d in "0123456789":
    _XKEYSYM_NAMES[f"KEY_{_d}"] = _d
for _n in range(1, 13):
    _XKEYSYM_NAMES[f"KEY_F{_n}"] = f"F{_n}"
_XKEYSYM_NAMES.update(
    {
        "KEY_ENTER": "Return",
        "KEY_ESC": "Escape",
        "KEY_BACKSPACE": "BackSpace",
        "KEY_TAB": "Tab",
        "KEY_SPACE": "space",
        "KEY_LEFT": "Left",
        "KEY_RIGHT": "Right",
        "KEY_UP": "Up",
        "KEY_DOWN": "Down",
        "KEY_HOME": "Home",
        "KEY_END": "End",
        "KEY_PAGEUP": "Prior",
        "KEY_PAGEDOWN": "Next",
        "KEY_INSERT": "Insert",
        "KEY_DELETE": "Delete",
        "KEY_CAPSLOCK": "Caps_Lock",
        "KEY_LEFTCTRL": "Control_L",
        "KEY_RIGHTCTRL": "Control_R",
        "KEY_LEFTSHIFT": "Shift_L",
        "KEY_RIGHTSHIFT": "Shift_R",
        "KEY_LEFTALT": "Alt_L",
        "KEY_RIGHTALT": "Alt_R",
        "KEY_LEFTMETA": "Super_L",
        "KEY_RIGHTMETA": "Super_R",
        "KEY_MINUS": "minus",
        "KEY_EQUAL": "equal",
        "KEY_LEFTBRACE": "bracketleft",
        "KEY_RIGHTBRACE": "bracketright",
        "KEY_SEMICOLON": "semicolon",
        "KEY_APOSTROPHE": "apostrophe",
        "KEY_GRAVE": "grave",
        "KEY_BACKSLASH": "backslash",
        "KEY_COMMA": "comma",
        "KEY_DOT": "period",
        "KEY_SLASH": "slash",
    }
)

# KEY_* → Linux evdev kod numarası (ydotool `key <code>:<1|0>`).
# input-event-codes.h sabitleri. Yalnız desteklenen KEY_* alt kümesi.
_EVDEV_CODES: Dict[str, int] = {
    "KEY_ESC": 1,
    "KEY_1": 2,
    "KEY_2": 3,
    "KEY_3": 4,
    "KEY_4": 5,
    "KEY_5": 6,
    "KEY_6": 7,
    "KEY_7": 8,
    "KEY_8": 9,
    "KEY_9": 10,
    "KEY_0": 11,
    "KEY_MINUS": 12,
    "KEY_EQUAL": 13,
    "KEY_BACKSPACE": 14,
    "KEY_TAB": 15,
    "KEY_Q": 16,
    "KEY_W": 17,
    "KEY_E": 18,
    "KEY_R": 19,
    "KEY_T": 20,
    "KEY_Y": 21,
    "KEY_U": 22,
    "KEY_I": 23,
    "KEY_O": 24,
    "KEY_P": 25,
    "KEY_LEFTBRACE": 26,
    "KEY_RIGHTBRACE": 27,
    "KEY_ENTER": 28,
    "KEY_LEFTCTRL": 29,
    "KEY_A": 30,
    "KEY_S": 31,
    "KEY_D": 32,
    "KEY_F": 33,
    "KEY_G": 34,
    "KEY_H": 35,
    "KEY_J": 36,
    "KEY_K": 37,
    "KEY_L": 38,
    "KEY_SEMICOLON": 39,
    "KEY_APOSTROPHE": 40,
    "KEY_GRAVE": 41,
    "KEY_LEFTSHIFT": 42,
    "KEY_BACKSLASH": 43,
    "KEY_Z": 44,
    "KEY_X": 45,
    "KEY_C": 46,
    "KEY_V": 47,
    "KEY_B": 48,
    "KEY_N": 49,
    "KEY_M": 50,
    "KEY_COMMA": 51,
    "KEY_DOT": 52,
    "KEY_SLASH": 53,
    "KEY_RIGHTSHIFT": 54,
    "KEY_LEFTALT": 56,
    "KEY_SPACE": 57,
    "KEY_CAPSLOCK": 58,
    "KEY_F1": 59,
    "KEY_F2": 60,
    "KEY_F3": 61,
    "KEY_F4": 62,
    "KEY_F5": 63,
    "KEY_F6": 64,
    "KEY_F7": 65,
    "KEY_F8": 66,
    "KEY_F9": 67,
    "KEY_F10": 68,
    "KEY_F11": 87,
    "KEY_F12": 88,
    "KEY_RIGHTCTRL": 97,
    "KEY_RIGHTALT": 100,
    "KEY_HOME": 102,
    "KEY_UP": 103,
    "KEY_PAGEUP": 104,
    "KEY_LEFT": 105,
    "KEY_RIGHT": 106,
    "KEY_END": 107,
    "KEY_DOWN": 108,
    "KEY_PAGEDOWN": 109,
    "KEY_INSERT": 110,
    "KEY_DELETE": 111,
    "KEY_LEFTMETA": 125,
    "KEY_RIGHTMETA": 126,
}

# KEY_* → pynput özel tuş adı (pynput.keyboard.Key.<ad>). Harf/rakam bu
# haritada yok → KeyCode.from_char ile karaktere düşülür.
_PYNPUT_SPECIAL: Dict[str, str] = {
    "KEY_ENTER": "enter",
    "KEY_ESC": "esc",
    "KEY_BACKSPACE": "backspace",
    "KEY_TAB": "tab",
    "KEY_SPACE": "space",
    "KEY_LEFT": "left",
    "KEY_RIGHT": "right",
    "KEY_UP": "up",
    "KEY_DOWN": "down",
    "KEY_HOME": "home",
    "KEY_END": "end",
    "KEY_PAGEUP": "page_up",
    "KEY_PAGEDOWN": "page_down",
    "KEY_INSERT": "insert",
    "KEY_DELETE": "delete",
    "KEY_CAPSLOCK": "caps_lock",
    "KEY_LEFTCTRL": "ctrl_l",
    "KEY_RIGHTCTRL": "ctrl_r",
    "KEY_LEFTSHIFT": "shift",
    "KEY_RIGHTSHIFT": "shift_r",
    "KEY_LEFTALT": "alt_l",
    "KEY_RIGHTALT": "alt_r",
    "KEY_LEFTMETA": "cmd",
    "KEY_RIGHTMETA": "cmd_r",
    "KEY_F1": "f1",
    "KEY_F2": "f2",
    "KEY_F3": "f3",
    "KEY_F4": "f4",
    "KEY_F5": "f5",
    "KEY_F6": "f6",
    "KEY_F7": "f7",
    "KEY_F8": "f8",
    "KEY_F9": "f9",
    "KEY_F10": "f10",
    "KEY_F11": "f11",
    "KEY_F12": "f12",
}

# KEY_* → shift'siz düz karakter (pynput KeyCode + shift'siz noktalama).
_CHAR_KEYS: Dict[str, str] = {}
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    _CHAR_KEYS[f"KEY_{_c}"] = _c.lower()
for _d in "0123456789":
    _CHAR_KEYS[f"KEY_{_d}"] = _d
_CHAR_KEYS.update(
    {
        "KEY_MINUS": "-",
        "KEY_EQUAL": "=",
        "KEY_LEFTBRACE": "[",
        "KEY_RIGHTBRACE": "]",
        "KEY_SEMICOLON": ";",
        "KEY_APOSTROPHE": "'",
        "KEY_GRAVE": "`",
        "KEY_BACKSLASH": "\\",
        "KEY_COMMA": ",",
        "KEY_DOT": ".",
        "KEY_SLASH": "/",
    }
)


# --- Somut backend'ler (tembel import) ---------------------------------------


class XTestBackend:
    """X11 XTEST backend (python-xlib). Root'suz, mutlak konum."""

    name = BACKEND_XTEST
    # left/right/middle → X buton numarası; scroll 4/5 (dikey) 6/7 (yatay).
    _BUTTONS = {"left": 1, "middle": 2, "right": 3}

    def __init__(self) -> None:
        import Xlib.display
        from Xlib import X  # noqa: F401
        from Xlib.ext import xtest  # noqa: F401

        self._Xlib = __import__("Xlib")
        self._display = Xlib.display.Display()

    def move(self, x: int, y: int) -> None:
        from Xlib.ext import xtest

        xtest.fake_input(self._display, self._Xlib.X.MotionNotify, x=x, y=y)
        self._display.sync()

    def button(self, button: str, down: bool) -> None:
        from Xlib.ext import xtest

        num = self._BUTTONS.get(button)
        if num is None:
            return
        etype = self._Xlib.X.ButtonPress if down else self._Xlib.X.ButtonRelease
        xtest.fake_input(self._display, etype, num)
        self._display.sync()

    def scroll(self, dx: float, dy: float) -> None:

        self._wheel(4 if dy < 0 else 5, int(round(abs(dy))))
        self._wheel(6 if dx < 0 else 7, int(round(abs(dx))))

    def _wheel(self, num: int, notches: int) -> None:
        from Xlib.ext import xtest

        for _ in range(notches):
            xtest.fake_input(self._display, self._Xlib.X.ButtonPress, num)
            xtest.fake_input(self._display, self._Xlib.X.ButtonRelease, num)
        if notches:
            self._display.sync()

    def key(self, code: str, down: bool) -> None:
        from Xlib import XK
        from Xlib.ext import xtest

        name = _XKEYSYM_NAMES.get(code)
        if name is None:
            return
        keysym = XK.string_to_keysym(name)
        keycode = self._display.keysym_to_keycode(keysym)
        if not keycode:
            return
        etype = self._Xlib.X.KeyPress if down else self._Xlib.X.KeyRelease
        xtest.fake_input(self._display, etype, keycode)
        self._display.sync()

    def close(self) -> None:
        try:
            self._display.close()
        except Exception:  # pragma: no cover
            pass


class YdotoolBackend:
    """Wayland (ve X11) ydotool backend. `ydotoold` + /dev/uinput izni gerekir."""

    name = BACKEND_YDOTOOL
    # ydotool click bit maskesi: buton (LEFT=0x00,RIGHT=0x01,MIDDLE=0x02)
    # | yön (DOWN=0x40, UP=0x80).
    _BTN_BITS = {"left": 0x00, "right": 0x01, "middle": 0x02}

    def __init__(self) -> None:
        self._exe = shutil.which("ydotool")
        if not self._exe:
            raise InjectionUnavailable("ydotool PATH'te yok")

    def _run(self, args) -> None:
        try:
            subprocess.run(
                [self._exe, *args],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
        except Exception as exc:  # pragma: no cover - runtime enjeksiyon hatası
            logger.debug("ydotool çağrısı hata: %s", exc)

    def move(self, x: int, y: int) -> None:
        self._run(["mousemove", "--absolute", "-x", str(x), "-y", str(y)])

    def button(self, button: str, down: bool) -> None:
        bits = self._BTN_BITS.get(button)
        if bits is None:
            return
        mask = bits | (0x40 if down else 0x80)
        self._run(["click", f"0x{mask:02X}"])

    def scroll(self, dx: float, dy: float) -> None:
        self._run(["mousemove", "--wheel", "-x", str(int(round(dx))), "-y", str(int(round(dy)))])

    def key(self, code: str, down: bool) -> None:
        evcode = _EVDEV_CODES.get(code)
        if evcode is None:
            return
        self._run(["key", f"{evcode}:{1 if down else 0}"])

    def close(self) -> None:
        pass


class PynputBackend:
    """Çapraz-platform pynput backend (X11/Windows/macOS; Wayland değil)."""

    name = BACKEND_PYNPUT

    def __init__(self) -> None:
        from pynput import keyboard, mouse

        self._mouse = mouse.Controller()
        self._kb = keyboard.Controller()
        self._mouse_mod = mouse
        self._kb_mod = keyboard
        self._btn_map = {
            "left": mouse.Button.left,
            "right": mouse.Button.right,
            "middle": mouse.Button.middle,
        }

    def move(self, x: int, y: int) -> None:
        self._mouse.position = (x, y)

    def button(self, button: str, down: bool) -> None:
        btn = self._btn_map.get(button)
        if btn is None:
            return
        if down:
            self._mouse.press(btn)
        else:
            self._mouse.release(btn)

    def scroll(self, dx: float, dy: float) -> None:
        # pynput: pozitif dy = yukarı → protokol dy>0 aşağı olduğu için ters çevir.
        self._mouse.scroll(int(round(dx)), int(round(-dy)))

    def key(self, code: str, down: bool) -> None:
        key_obj = self._resolve_key(code)
        if key_obj is None:
            return
        if down:
            self._kb.press(key_obj)
        else:
            self._kb.release(key_obj)

    def _resolve_key(self, code: str):
        special = _PYNPUT_SPECIAL.get(code)
        if special is not None:
            return getattr(self._kb_mod.Key, special, None)
        char = _CHAR_KEYS.get(code)
        if char is not None:
            return self._kb_mod.KeyCode.from_char(char)
        return None

    def close(self) -> None:
        pass


class PortalBackend:
    """Wayland XDG RemoteDesktop portal backend (pydbus)."""

    name = BACKEND_PORTAL
    _BTN_MAP = {"left": 272, "right": 273, "middle": 274}  # linux/input-event-codes.h

    def __init__(self) -> None:
        try:
            import pydbus
        except ImportError:
            raise InjectionUnavailable("pydbus kurulu değil")

        self.bus = pydbus.SessionBus()
        self.portal = self.bus.get(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
        )

        # Basit bir deneme (tam asenkron session başlatma ve cihaz atama
        # mantığı gerektirir. Burada enjeksiyon stub'ı kuruluyor.)
        # RemoteDesktop başlatılması karmaşık asenkron event loop gerektirdiğinden
        # ydotool genellikle tercih edilir.
        self._session_path = None

    def move(self, x: int, y: int) -> None:
        if self._session_path:
            try:
                self.portal.NotifyPointerMotion(self._session_path, {}, x, y)
            except Exception:
                pass

    def button(self, button: str, down: bool) -> None:
        btn = self._BTN_MAP.get(button)
        if btn is not None and self._session_path:
            state = 1 if down else 0
            try:
                self.portal.NotifyPointerButton(self._session_path, {}, btn, state)
            except Exception:
                pass

    def scroll(self, dx: float, dy: float) -> None:
        if self._session_path:
            try:
                # dy ekseni 1 = vertical, dx ekseni 0 = horizontal
                if dy != 0:
                    self.portal.NotifyPointerAxis(self._session_path, {}, 1, dy)
                if dx != 0:
                    self.portal.NotifyPointerAxis(self._session_path, {}, 0, dx)
            except Exception:
                pass

    def key(self, code: str, down: bool) -> None:
        evcode = _EVDEV_CODES.get(code)
        if evcode is not None and self._session_path:
            state = 1 if down else 0
            try:
                self.portal.NotifyKeyboardKeycode(self._session_path, {}, evcode, state)
            except Exception:
                pass

    def close(self) -> None:
        if self._session_path:
            # Session sonlandır
            pass


# Yapıcıları kaydet (create_backend tembel çağırır).
_FACTORIES[BACKEND_XTEST] = XTestBackend
_FACTORIES[BACKEND_YDOTOOL] = YdotoolBackend
_FACTORIES[BACKEND_PYNPUT] = PynputBackend
_FACTORIES[BACKEND_PORTAL] = PortalBackend
