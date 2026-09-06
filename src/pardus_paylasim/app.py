"""
Adw.Application Entry Point for Pardus Güvenli Paylaşım.
"""

import argparse
import logging
import sys

from pardus_paylasim.cleaner.metadata_cleaner import MetadataCleaner
from pardus_paylasim.cleaner.report_builder import ReportBuilder
from pardus_paylasim.clipboard.sensitive_masker import SensitiveMasker
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
        parser.add_argument("--mesh-status", action="store_true", help=_("Mesh ağı durumunu göster"))
        parser.add_argument("--async-list", action="store_true", help=_("Bekleyen asenkron transferleri listele"))
        parser.add_argument("--fingerprint", action="store_true", help=_("Bu cihazın parmak izini göster"))
        parser.add_argument("--send", nargs="+", metavar="DOSYA", help=_("Son cihaza dosya gönder"))
        parser.add_argument("--to", metavar="IP:PORT", help=_("Hedef cihaz (varsayılan: son cihaz)"))
        parser.add_argument("--pin", help=_("Secret mod PIN'i (yoksa normal mod)"))
        parser.add_argument("--no-clean", action="store_true", help=_("Gönderim-öncesi temizliği atla"))
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
            try:
                pending = store.get_all_pending()
            finally:
                store.close()
            print(_("Bekleyen asenkron transferler:"))
            if not pending:
                print("  " + _("(yok)"))
            for t in pending:
                print(f"  {t.file_name} ({t.file_size} B) -> {t.receiver_id}")
            return 0

        if cli_args.fingerprint:
            from pardus_paylasim.auth.trust_store import group_fingerprint, own_fingerprint
            fp = own_fingerprint()
            if not fp:
                print(_("Parmak izi üretilemedi (cryptography gerekli)."))
                return 1
            print(group_fingerprint(fp))
            return 0

        if cli_args.send:
            import os
            import tempfile
            import threading
            from pardus_paylasim.cleaner.metadata_cleaner import prepare_send_file
            from pardus_paylasim.discovery.transfer import FileSender
            from pardus_paylasim.progress import compute_stats, format_progress_line

            target = cli_args.to
            if not target:
                from pardus_paylasim.config import AppConfig
                last = AppConfig().get("last_peer") or {}
                if not last.get("address"):
                    print(_("Hedef yok: önce GUI'den gönderim yapın ya da --to IP:PORT verin."))
                    return 1
                target = f"{last['address']}:{last.get('port', 8900)}"
            try:
                address, _sep, port_s = target.rpartition(":")
                port = int(port_s)
                if not address or not 1 <= port <= 65535:
                    raise ValueError
            except ValueError:
                print(_("Geçersiz hedef (ör. 192.168.1.20:8900)."))
                return 1

            secret_pin = cli_args.pin
            is_secret = bool(secret_pin)
            sender = FileSender(address, port)
            cancel_event = threading.Event()
            failed = 0
            for path in cli_args.send:
                if not os.path.isfile(path):
                    print(_("Atlandı (dosya değil): {p}").format(p=path))
                    failed += 1
                    continue
                name = os.path.basename(path)
                send_path, tmp_path = prepare_send_file(
                    path, not cli_args.no_clean, tempfile.gettempdir()
                )
                try:
                    # Her dosya tek satırla özetlenir (çok sık yazılmaz).
                    last_line = {"pct": -1}

                    def on_stats_throttled(sent, total, elapsed, _n=name):
                        import sys
                        s = compute_stats(sent, total, elapsed)
                        pct = int(round(s.percent * 100))
                        if pct != last_line["pct"]:
                            last_line["pct"] = pct
                            sys.stdout.write(f"\r  {_n}: {format_progress_line(s)}   ")
                            sys.stdout.flush()
                    sender.send_file(
                        send_path, secret_pin, stats_callback=on_stats_throttled,
                        rel_name=name, resume=not is_secret,
                        verify_hash=not is_secret, cancel_event=cancel_event,
                    )
                    print(_("OK: {n}").format(n=name))
                except KeyboardInterrupt:
                    print(_("İptal edildi."))
                    return 130
                except Exception as e:
                    print(_("HATA ({n}): {e}").format(n=name, e=e))
                    failed += 1
                finally:
                    if tmp_path:
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass
            return 1 if failed else 0

        if HAS_GTK and self.app:
            gtk_argv = [sys.argv[0]]
            return self.app.run(gtk_argv)
        else:
            print(_("Pardus Güvenli Paylaşım CLI Modu (GTK4 bulunamadı veya headless sunucu)."))
            print(_("Kullanım:"))
            print("  pardus-paylasim --clean <dosya>")
            print("  pardus-paylasim --mask <metin>")
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
