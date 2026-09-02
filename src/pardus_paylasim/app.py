"""
Adw.Application Entry Point for Pardus Güvenli Paylaşım.
"""

import argparse
import sys

from pardus_paylasim.cleaner.metadata_cleaner import MetadataCleaner
from pardus_paylasim.cleaner.report_builder import ReportBuilder
from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker
from pardus_paylasim.i18n import _, setup_i18n
from pardus_paylasim.logging_setup import setup_logging
from pardus_paylasim.window import MainWindow

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw

    HAS_GTK = True
except Exception:
    HAS_GTK = False


class PardusPaylasimApp:
    def __init__(self):
        if HAS_GTK:
            self.app = Adw.Application(application_id="tr.org.pardus.paylasim")
            self.app.connect("activate", self.on_activate)
        else:
            self.app = None

    def on_activate(self, app):
        MainWindow(app)

    def run(self, args=None):
        parser = argparse.ArgumentParser(
            description=_("Pardus Güvenli Paylaşım ve Süreklilik Merkezi")
        )
        parser.add_argument("--clean", nargs="+", help=_("Temizlenecek dosya yol(lar)ı"))
        parser.add_argument("--mask", help=_("Maskelenecek metin"))
        parser.add_argument("--out", help=_("Çıktı dosya yolu"))
        cli_args, extra = parser.parse_known_args(args)

        if cli_args.clean:
            cleaner = MetadataCleaner()
            for path in cli_args.clean:
                res = cleaner.clean_file(path, cli_args.out)
                print(ReportBuilder.to_txt([res]))
            return 0

        if cli_args.mask:
            masked = SensitiveMasker.mask_text(cli_args.mask)
            print(_("Maskelenmiş Metin:") + f"\n{masked}")
            return 0

        if HAS_GTK and self.app:
            # Only pass GTK-specific args, not our custom CLI args
            gtk_argv = [sys.argv[0]]  # Just the program name
            return self.app.run(gtk_argv)
        else:
            print(_("Pardus Güvenli Paylaşım CLI Modu (GTK4 bulunamadı veya headless sunucu)."))
            print(_("Kullanım: pardus-paylasim --clean <dosya> veya --mask <metin>"))
            return 0


def main():
    setup_logging()
    setup_i18n()
    app = PardusPaylasimApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
