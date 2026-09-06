"""
Adw.Application Entry Point for Pardus Güvenli Paylaşım.
"""

import argparse
import logging
import sys

from pardus_paylasim.cleaner.metadata_cleaner import MetadataCleaner
from pardus_paylasim.cleaner.report_builder import ReportBuilder
from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker
from pardus_paylasim.clipboard.ai.local_detector import LocalSensitiveDetector
from pardus_paylasim.i18n import _, setup_i18n
from pardus_paylasim.logging_setup import setup_logging
from pardus_paylasim.window import MainWindow

logger = logging.getLogger(__name__)

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw
    HAS_GTK = True
except Exception as e:
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
        parser.add_argument("--ai-scan", help=_("AI ile hassas veri tara"))
        parser.add_argument("--mesh-status", action="store_true", help=_("Mesh ağı durumunu göster"))
        parser.add_argument("--async-list", action="store_true", help=_("Bekleyen asenkron transferleri listele"))
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

        if cli_args.ai_scan:
            det = LocalSensitiveDetector()
            result = det.detect(cli_args.ai_scan)
            if result.has_sensitive:
                print(_("Tespit edilen hassas veriler:"))
                for d in result.detections:
                    print(f"  [{d.label}] {d.severity}: {d.text[:50]}... (%.0f%%)" % (d.confidence * 100))
            else:
                print(_("Hassas veri bulunamadı."))
            return 0

        if cli_args.mesh_status:
            from pardus_paylasim.discovery.mesh.mesh_network import MeshNode
            import socket
            import uuid

            def _local_ip() -> str:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    ip = s.getsockname()[0]
                    s.close()
                    return ip
                except OSError:
                    return "127.0.0.1"

            node = MeshNode(
                peer_id=str(uuid.uuid4())[:8],
                local_ip=_local_ip(),
            )
            node.start()
            print(_("Mesh ağı başlatıldı."))
            print(f"  Peer ID: {node.peer_id}")
            print(f"  Port: {node.mesh_port}")
            print(f"  Bağlı eşler: {len(node.peers)}")
            node.stop()
            return 0

        if cli_args.async_list:
            from pardus_paylasim.discovery.async_transfer.manager import AsyncTransferStore
            store = AsyncTransferStore()
            print(_("Bekleyen asenkron transferler:"))
            # List all pending transfers
            print("  (Veritabanı: ~/.local/share/pardus-paylasim/async_transfers.db)")
            return 0

        if HAS_GTK and self.app:
            gtk_argv = [sys.argv[0]]
            return self.app.run(gtk_argv)
        else:
            print(_("Pardus Güvenli Paylaşım CLI Modu (GTK4 bulunamadı veya headless sunucu)."))
            print(_("Kullanım:"))
            print("  pardus-paylasim --clean <dosya>")
            print("  pardus-paylasim --mask <metin>")
            print("  pardus-paylasim --ai-scan <metin>")
            print("  pardus-paylasim --mesh-status")
            print("  pardus-paylasim --async-list")
            return 0


def main():
    setup_logging()
    setup_i18n()
    app = PardusPaylasimApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
