"""
Nautilus (GNOME Files) Right-Click Extension for Pardus Güvenli Paylaşım.
"""

import subprocess

from gi.repository import GObject, Nautilus


class PardusPaylasimNautilus(GObject.GObject, Nautilus.MenuProvider):
    def get_file_items(self, *args):
        files = args[-1]
        if not files:
            return []

        item = Nautilus.MenuItem(
            name="PardusPaylasimNautilus::CleanFile",
            label="🛡️ Pardus Güvenli Paylaşım ile Temizle",
            tip="Dosyadaki GPS, yazar ve cihaz meta verilerini temizle ve güvenli kopya oluştur"
        )
        item.connect("activate", self.menu_activate_cb, files)
        return [item]

    def menu_activate_cb(self, menu, files):
        file_paths = [f.get_location().get_path() for f in files if f.get_location().get_path()]
        if file_paths:
            subprocess.Popen(["pardus-paylasim", "--clean"] + file_paths)
