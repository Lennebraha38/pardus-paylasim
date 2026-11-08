"""
Pardus Paylaşım — GTK4 / Libadwaita Bildirimsel Şablon Yükleyicisi (GtkBuilder).
XML arayüz şablonlarını yükler ve Python bileşenleri ile bağlar.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    HAS_GTK = True
except Exception:
    Gtk = None  # type: ignore[assignment]
    HAS_GTK = False


class TemplateLoader:
    """GTK4 GtkBuilder XML arayüz şablonlarını arar ve yükler."""

    @staticmethod
    def get_ui_search_paths() -> list[str]:
        """Yerel geliştirme dizini ve kurulu sistem yollarını listeler."""
        here = os.path.dirname(os.path.abspath(__file__))
        repo_data_ui = os.path.abspath(os.path.join(here, "..", "..", "..", "data", "ui"))
        system_data_ui = "/usr/share/pardus-paylasim/ui"
        return [repo_data_ui, system_data_ui]

    @classmethod
    def load_template(cls, template_name: str) -> Any | None:
        """Belirtilen isimdeki .ui şablonunu yükleyip Gtk.Builder nesnesi döner."""
        if not HAS_GTK or Gtk is None:
            return None

        filename = template_name if template_name.endswith(".ui") else f"{template_name}.ui"
        for search_dir in cls.get_ui_search_paths():
            candidate = os.path.join(search_dir, filename)
            if os.path.isfile(candidate):
                try:
                    builder = Gtk.Builder.new_from_file(candidate)
                    return builder
                except Exception:
                    logger.debug("Gtk.Builder şablon okuma hatası: %s", candidate, exc_info=True)

        return None
