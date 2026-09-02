import json
import logging
import os
import socket

logger = logging.getLogger(__name__)

# GSettings şeması. Kurulu ve derlenmişse (Pardus/Debian) tercih edilir;
# aksi halde (Windows/dev, şema-yok ortam) JSON singleton'a düşülür.
SCHEMA_ID = "tr.org.pardus.paylasim"

# Python (snake_case) anahtar  ->  GSettings (kebab-case) anahtar eşlemesi.
_SCHEMA_KEYS = {
    "device_name": "device-name",
    "mdns_visible": "mdns-visible",
    "auto_clipboard_protection": "auto-clipboard-protection",
    "download_dir": "download-dir",
    # Ekran akışı parametreleri (StreamConfig.from_app_config tüketir).
    "screen_quality": "screen-quality",
    "framerate": "framerate",
    "resolution": "resolution",
    "port": "port",
    # Web istemci CORS allowlist (virgülle ayrık origin listesi; boş → CORS yok).
    "allow_web_origin": "allow-web-origin",
}

# Boş string dönen string anahtarlar için çalışma-zamanı geri düşüşleri.
_DYNAMIC_DEFAULTS = {
    "device_name": socket.gethostname,
    "download_dir": lambda: os.path.expanduser("~/İndirilenler/PardusPaylasim"),
}


def _try_load_gsettings():
    """Gio.Settings örneği döndür; şema yoksa/derlenmemişse None."""
    try:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
    except Exception:
        return None
    try:
        source = Gio.SettingsSchemaSource.get_default()
        if source is None or source.lookup(SCHEMA_ID, True) is None:
            return None
        return Gio.Settings.new(SCHEMA_ID)
    except (GLib.Error, Exception):
        return None


class AppConfig:
    _instance = None
    _config_path = os.path.expanduser("~/.config/pardus-paylasim/config.json")

    # Statik varsayılanlar (dinamik olanlar _resolve_dynamic ile doldurulur).
    data = {
        "device_name": socket.gethostname(),
        "mdns_visible": True,
        "auto_clipboard_protection": False,
        "download_dir": os.path.expanduser("~/İndirilenler/PardusPaylasim"),
        # Ekran akışı varsayılanları (gschema ile aynı; JSON fallback için).
        "screen_quality": 70,
        "framerate": 25,
        "resolution": "native",
        "port": 52345,
        # CORS allowlist: boş → hiçbir origin echo edilmez ('*' asla).
        "allow_web_origin": "",
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppConfig, cls).__new__(cls)
            cls._instance._settings = _try_load_gsettings()
            cls._instance.load()
        return cls._instance

    @property
    def uses_gsettings(self) -> bool:
        return getattr(self, "_settings", None) is not None

    @staticmethod
    def _resolve_dynamic(key, value):
        """Boş string string-anahtarları çalışma-zamanı varsayılanına çevir."""
        if value == "" and key in _DYNAMIC_DEFAULTS:
            return _DYNAMIC_DEFAULTS[key]()
        return value

    def load(self):
        if self.uses_gsettings:
            self._load_from_gsettings()
        else:
            self._load_from_json()

    def _load_from_gsettings(self):
        for py_key, gs_key in _SCHEMA_KEYS.items():
            try:
                value = self._settings[gs_key]
            except Exception as e:
                logger.error("GSettings okunamadı (%s): %s", gs_key, e)
                continue
            self.data[py_key] = self._resolve_dynamic(py_key, value)

    def _load_from_json(self):
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.data.update(loaded)
            except Exception as e:
                logger.error("Yapılandırma okunamadı: %s", e)

    def save(self):
        # GSettings write-through set() içinde yapılır; JSON ise dosyaya yazar.
        if self.uses_gsettings:
            return
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error("Yapılandırma kaydedilemedi: %s", e)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        if self.uses_gsettings and key in _SCHEMA_KEYS:
            gs_key = _SCHEMA_KEYS[key]
            try:
                self._settings[gs_key] = value
            except Exception as e:
                logger.error("GSettings yazılamadı (%s): %s", gs_key, e)
        else:
            self.save()
