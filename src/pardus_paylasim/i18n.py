"""gettext tabanlı yerelleştirme altyapısı (TR + EN).

`_()` her yerde çağrılabilir. Katalog bulunamazsa `fallback=True` sayesinde
kaynak (Türkçe) string aynen döner — Windows/dev ortamı bozulmaz.
"""

import gettext as _gettext
import os

DOMAIN = "pardus-paylasim"

# Kurulu sistemde /usr/share/locale; geliştirmede paket-içi veya proje kökü
_PKG_LOCALE = os.path.join(os.path.dirname(__file__), "locale")
_ROOT_LOCALE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "locale")
_SYS_LOCALE = "/usr/share/locale"

_translation = None


def _pick_localedir() -> str:
    if os.path.isdir(_PKG_LOCALE):
        return _PKG_LOCALE
    if os.path.isdir(_ROOT_LOCALE):
        return _ROOT_LOCALE
    return _SYS_LOCALE


def setup_i18n(localedir: str | None = None) -> None:
    """Çeviri katalogunu yükle. LANG/LC_MESSAGES env değişkenlerini onurlandırır."""
    global _translation
    localedir = localedir or _pick_localedir()
    _translation = _gettext.translation(DOMAIN, localedir=localedir, fallback=True)


def gettext(message: str) -> str:
    if _translation is None:
        setup_i18n()
    return _translation.gettext(message)


# Kısa takma ad — modüller `from .i18n import _` ile kullanır.
_ = gettext
