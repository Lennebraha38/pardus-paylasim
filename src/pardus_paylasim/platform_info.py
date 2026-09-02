"""
Platform/oturum tespiti — çapraz-platform (Pardus ↔ Windows) yardımcı katman.

Bu modül OS ve oturum tipine dair kararları TEK yerde toplar. Proje genelinde
dağınık `sys.platform`/`os.environ` dalları yerine buradaki fonksiyonlar
çağrılır. Böylece mDNS TXT (gerçek OS), ekran yakalama (temp yolu, oturum-aware
backend seçimi), girdi enjeksiyonu (backend tercihi) ve config/history (yollar)
tutarlı davranır.

Saf ve yan-etkisizdir: GTK/soket gerektirmez, headless koşar. Tüm ortam okuması
try/except ile sarılıdır — eksik değişken hata değil "unknown"/fallback verir.
"""

import logging
import os
import platform
import sys
import tempfile

logger = logging.getLogger(__name__)

# Oturum tipi sabitleri (mDNS TXT, backend seçimi ve /info için ortak sözlük).
SESSION_WAYLAND = "wayland"
SESSION_X11 = "x11"
SESSION_WINDOWS = "windows"
SESSION_UNKNOWN = "unknown"


def is_windows() -> bool:
    """Windows üstünde mi? (companion agent + pynput/win32 backend seçimi için.)"""
    return os.name == "nt" or sys.platform.startswith("win")


def is_linux() -> bool:
    """Linux üstünde mi? (Pardus dahil; XTEST/ydotool/GStreamer yolları için.)"""
    return sys.platform.startswith("linux")


def session_type() -> str:
    """
    Oturum tipini döndür: 'wayland' | 'x11' | 'windows' | 'unknown'.

    Linux'ta önce `XDG_SESSION_TYPE`, sonra `WAYLAND_DISPLAY`/`DISPLAY`
    varlığına bakar. Windows'ta her zaman 'windows'. Tespit edilemezse
    'unknown' (çağıran taraf güvenli fallback seçsin).
    """
    if is_windows():
        return SESSION_WINDOWS

    if is_linux():
        # XDG_SESSION_TYPE en güvenilir sinyal (login manager set eder).
        xdg = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
        if xdg == "wayland":
            return SESSION_WAYLAND
        if xdg in ("x11", "tty"):
            # tty (SSH/headless) ekran yoksa X11'e düşürme; DISPLAY'e bak.
            if xdg == "x11":
                return SESSION_X11

        # XDG belirsiz → değişkenlerden çıkar.
        if os.environ.get("WAYLAND_DISPLAY"):
            return SESSION_WAYLAND
        if os.environ.get("DISPLAY"):
            return SESSION_X11

    return SESSION_UNKNOWN


def is_wayland() -> bool:
    """Wayland oturumu mu? (PipeWire yakalama + ydotool enjeksiyon ima eder.)"""
    return session_type() == SESSION_WAYLAND


def is_x11() -> bool:
    """X11 oturumu mu? (ximagesrc yakalama + XTEST enjeksiyon ima eder.)"""
    return session_type() == SESSION_X11


def current_os_label() -> str:
    """
    İnsan-okunur OS etiketi (mDNS TXT `os` alanı için).

    Linux'ta `/etc/os-release` PRETTY_NAME okunur ("Pardus 25 GNU/Linux").
    Windows'ta "Windows <sürüm>". Okunamazsa `platform.system()` +
    `platform.release()` fallback.
    """
    if is_linux():
        label = _read_os_release_pretty_name()
        if label:
            return label

    if is_windows():
        release = platform.release() or ""
        return f"Windows {release}".strip()

    # Bilinmeyen/diğer (macOS, BSD...) → jenerik.
    system = platform.system() or "Unknown"
    release = platform.release() or ""
    return f"{system} {release}".strip()


def temp_dir() -> str:
    """Geçici dizin (TLS temp cert, yakalama ara dosyaları). OS-nötr."""
    return tempfile.gettempdir()


def downloads_dir() -> str:
    """
    Kullanıcı indirilenler dizini (transfer varsayılan hedefi).

    Windows'ta `%USERPROFILE%\\Downloads`. Linux'ta Pardus varsayılanı
    `~/İndirilenler`; yoksa XDG `~/Downloads`. Dizin yoksa da yol döner
    (çağıran taraf oluşturur) — bu fonksiyon I/O yapmaz.
    """
    home = os.path.expanduser("~")

    if is_windows():
        return os.path.join(home, "Downloads")

    # Pardus TR yerelleştirmesi "İndirilenler" kullanır; varsa onu tercih et.
    pardus_downloads = os.path.join(home, "İndirilenler")
    if os.path.isdir(pardus_downloads):
        return pardus_downloads

    return os.path.join(home, "Downloads")


def _read_os_release_pretty_name() -> str:
    """
    `/etc/os-release` içinden PRETTY_NAME çek. Bulunamazsa "" döner.

    Basit satır ayrıştırma (yalnız stdlib, harici dep yok). Tırnaklar
    soyulur. Okuma hatası logla + "" dön (çağıran fallback'e geçer).
    """
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    value = line.split("=", 1)[1].strip()
                    # Çevreleyen çift/tek tırnakları soy.
                    return value.strip('"').strip("'")
    except OSError as exc:
        logger.debug("os-release okunamadı: %s", exc)
    return ""
