"""Resume (0x03) + hash'li normal mod (0x04) + istatistik testleri.

TLS gerektirmez: alıcı tarafı socketpair üzerinden, gönderici tarafı
düz TCP loopback sahte-eş ile test edilir (fail-closed alıcı
değiştirilmeden).
"""

import hashlib
import json
import os
import socket
import struct
import tempfile
import threading
import time
import unittest

from pardus_paylasim.discovery import net_util
from pardus_paylasim.discovery.transfer import (
    MODE_HASHED,
    MODE_NORMAL,
    MODE_RESUME,
    FileReceiverServer,
    FileSender,
)


def _wait_for(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


class TestReceiverHashMode(unittest.TestCase):
    """0x04: doğru hash kabul, yanlış hash ret + kalıntı temizliği."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dl = os.path.join(self._tmp.name, "dl")
        os.makedirs(self.dl)
        self.server = FileReceiverServer(self.dl, port=8911)
        self.server.on_file_request = lambda n, s, ip: True

    def tearDown(self):
        self._tmp.cleanup()

    def _send_hashed(self, payload: bytes, digest: bytes, name="a.bin"):
        srv_end, cli_end = socket.socketpair()
        srv_end.settimeout(10)
        cli_end.settimeout(10)
        errors = []

        def serve():
            try:
                self.server._handle_client(srv_end)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        try:
            cli_end.sendall(MODE_HASHED)
            nb = name.encode()
            cli_end.sendall(struct.pack("!I", len(nb)) + nb)
            cli_end.sendall(struct.pack("!Q", len(payload)))
            cli_end.sendall(payload)
            cli_end.sendall(digest)
            ack = net_util.recv_exact(cli_end, 1)
            return ack
        finally:
            cli_end.close()
            t.join(timeout=10)

    def test_hash_ok_accepted(self):
        payload = os.urandom(100 * 1024)
        ack = self._send_hashed(payload, hashlib.sha256(payload).digest())
        self.assertEqual(ack, b"\x01")
        self.assertTrue(_wait_for(
            lambda: os.path.exists(os.path.join(self.dl, "a.bin"))))
        with open(os.path.join(self.dl, "a.bin"), "rb") as f:
            self.assertEqual(f.read(), payload)

    def test_hash_mismatch_rejected_and_cleaned(self):
        payload = os.urandom(50 * 1024)
        ack = self._send_hashed(payload, b"\x00" * 32, name="b.bin")
        self.assertEqual(ack, b"\x00")
        time.sleep(0.3)
        leftovers = os.listdir(self.dl)
        self.assertEqual(leftovers, [], leftovers)


class TestReceiverResume(unittest.TestCase):
    """0x03: yarım .part + sidecar'dan devam, bayt-bayt doğruluk."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dl = os.path.join(self._tmp.name, "dl")
        os.makedirs(self.dl)
        self.server = FileReceiverServer(self.dl, port=8912)
        self.server.on_file_request = lambda n, s, ip: True
        self.received = []
        self.server.on_file_received = self.received.append

    def tearDown(self):
        self._tmp.cleanup()

    def test_resume_from_partial(self):
        data = os.urandom(200 * 1024)
        mtime_ns = 123456789
        # Yarım kalmış aktarımı önden hazırla: ilk 80KB + sidecar.
        with open(os.path.join(self.dl, "f.bin.part"), "wb") as f:
            f.write(data[:80 * 1024])
        with open(os.path.join(self.dl, "f.bin.part.json"), "w") as f:
            json.dump({"size": len(data), "mtime_ns": mtime_ns,
                       "received": 80 * 1024}, f)

        srv_end, cli_end = socket.socketpair()
        srv_end.settimeout(15)
        cli_end.settimeout(15)
        t = threading.Thread(target=self.server._handle_client,
                             args=(srv_end,), daemon=True)
        t.start()
        try:
            nb = b"f.bin"
            cli_end.sendall(MODE_RESUME)
            cli_end.sendall(struct.pack("!I", len(nb)) + nb)
            cli_end.sendall(struct.pack("!Q", len(data)))
            cli_end.sendall(struct.pack("!Q", mtime_ns))
            off = struct.unpack("!Q", net_util.recv_exact(cli_end, 8))[0]
            self.assertEqual(off, 80 * 1024)
            cli_end.sendall(data[off:])
            ack = net_util.recv_exact(cli_end, 1)
            self.assertEqual(ack, b"\x01")
        finally:
            cli_end.close()
            t.join(timeout=15)

        self.assertTrue(_wait_for(lambda: len(self.received) == 1))
        with open(self.received[0], "rb") as f:
            self.assertEqual(f.read(), data)
        # Sidecar temizlenmeli, .part taşınmalı.
        self.assertFalse(os.path.exists(os.path.join(self.dl, "f.bin.part.json")))
        self.assertFalse(os.path.exists(os.path.join(self.dl, "f.bin.part")))

    def test_abort_then_resume_no_duplication(self):
        """Bağlantı kopunca sidecar güncellenmeli; devamında bayt tekrarı olmamalı.

        Gerçek loopback TCP üzerinden (bu sandbox çekirdeğinde socketpair
        tampon tuhaflığı gözlendi).

        NOT: kopuş 64KB sınırında yapılır; alıcı yalnızca tamamlanan
        çerçeveleri sayar (kısmi çerçeve tamponu atılır, en fazla 64KB
        yeniden indirilir — bozulma olmaz, sadece tekrar indirme).
        """
        data = os.urandom(300 * 1024)
        mtime_ns = 777
        cut = 64 * 1024  # tam bir çerçeve: deterministik kopma noktası

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(5)
        srv.settimeout(15)
        port = srv.getsockname()[1]

        def serve_twice():
            for _ in range(2):
                try:
                    conn, _ = srv.accept()
                except OSError:
                    return
                conn.settimeout(15)
                try:
                    self.server._handle_client(conn)
                except Exception:  # noqa: BLE001 - hata yolu testin konusu
                    pass

        server_thread = threading.Thread(target=serve_twice, daemon=True)
        server_thread.start()

        def one_attempt(send_up_to):
            cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            cli.settimeout(15)
            try:
                cli.connect(("127.0.0.1", port))
                nb = b"h.bin"
                cli.sendall(MODE_RESUME)
                cli.sendall(struct.pack("!I", len(nb)) + nb)
                cli.sendall(struct.pack("!Q", len(data)))
                cli.sendall(struct.pack("!Q", mtime_ns))
                off = struct.unpack("!Q", net_util.recv_exact(cli, 8))[0]
                cli.sendall(data[off:send_up_to])
                # Kop: ACK beklemeden kapat. Verinin ulaşması için kısa bekle.
                time.sleep(0.5)
            finally:
                cli.close()
            return off

        try:
            off1 = one_attempt(cut)
            self.assertEqual(off1, 0)
            # Sidecar diskteki gerçek konumu yansıtmalı.
            part = os.path.join(self.dl, "h.bin.part")
            side = part + ".json"

            def sidecar_matches():
                try:
                    on_disk = os.path.getsize(part)
                    with open(side, encoding="utf-8") as f:
                        recorded = json.load(f)["received"]
                    return on_disk == cut and recorded == on_disk
                except (OSError, ValueError):
                    return False

            self.assertTrue(_wait_for(sidecar_matches, timeout=10),
                            "sidecar kopma noktasını yansıtmadı")

            off2 = one_attempt(len(data) + 1)  # kalanın tamamı
            self.assertEqual(off2, cut)
            self.assertTrue(_wait_for(lambda: len(self.received) == 1))
            with open(self.received[0], "rb") as f:
                self.assertEqual(f.read(), data)
        finally:
            try:
                srv.close()
            except OSError:
                pass
            server_thread.join(timeout=10)

    def test_resume_fresh_when_no_part(self):
        data = os.urandom(10 * 1024)
        srv_end, cli_end = socket.socketpair()
        srv_end.settimeout(15)
        cli_end.settimeout(15)
        t = threading.Thread(target=self.server._handle_client,
                             args=(srv_end,), daemon=True)
        t.start()
        try:
            nb = b"g.bin"
            cli_end.sendall(MODE_RESUME)
            cli_end.sendall(struct.pack("!I", len(nb)) + nb)
            cli_end.sendall(struct.pack("!Q", len(data)))
            cli_end.sendall(struct.pack("!Q", 999))
            off = struct.unpack("!Q", net_util.recv_exact(cli_end, 8))[0]
            self.assertEqual(off, 0)
            cli_end.sendall(data)
            self.assertEqual(net_util.recv_exact(cli_end, 1), b"\x01")
        finally:
            cli_end.close()
            t.join(timeout=15)
        self.assertTrue(_wait_for(
            lambda: os.path.exists(os.path.join(self.dl, "g.bin"))))


class TestSenderResumeAndHash(unittest.TestCase):
    """Gönderici: sahte-eş karşısında resume/hash/istatistik."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self._tmp.name, "src.bin")
        self.data = os.urandom(150 * 1024)
        with open(self.src, "wb") as f:
            f.write(self.data)

    def tearDown(self):
        self._tmp.cleanup()

    def _loopback(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        srv.settimeout(15)
        return srv, srv.getsockname()[1]

    def test_sender_resume_honors_offset(self):
        srv, port = self._loopback()
        seen = {}

        def peer():
            conn, _ = srv.accept()
            conn.settimeout(15)
            try:
                seen["mode"] = net_util.recv_exact(conn, 1)
                nlen = struct.unpack("!I", net_util.recv_exact(conn, 4))[0]
                seen["name"] = net_util.recv_exact(conn, nlen)
                seen["size"] = struct.unpack("!Q", net_util.recv_exact(conn, 8))[0]
                seen["mtime"] = struct.unpack("!Q", net_util.recv_exact(conn, 8))[0]
                conn.sendall(struct.pack("!Q", 50 * 1024))
                body = net_util.recv_exact(conn, len(self.data) - 50 * 1024)
                seen["body"] = body
                conn.sendall(b"\x01")
            finally:
                conn.close()
                srv.close()

        t = threading.Thread(target=peer, daemon=True)
        t.start()
        sender = FileSender("127.0.0.1", port)
        stats = []
        sender.send_file(self.src, resume=True,
                         stats_callback=lambda s, tot, el: stats.append((s, tot)))
        t.join(timeout=15)
        self.assertEqual(seen["mode"], MODE_RESUME)
        self.assertEqual(seen["size"], len(self.data))
        self.assertEqual(seen["body"], self.data[50 * 1024:])
        self.assertTrue(stats)
        self.assertEqual(stats[-1][0], len(self.data))
        self.assertEqual(stats[-1][1], len(self.data))

    def test_sender_hashed_mode_sends_digest(self):
        srv, port = self._loopback()
        seen = {}

        def peer():
            conn, _ = srv.accept()
            conn.settimeout(15)
            try:
                seen["mode"] = net_util.recv_exact(conn, 1)
                nlen = struct.unpack("!I", net_util.recv_exact(conn, 4))[0]
                net_util.recv_exact(conn, nlen)
                size = struct.unpack("!Q", net_util.recv_exact(conn, 8))[0]
                seen["body"] = net_util.recv_exact(conn, size)
                seen["digest"] = net_util.recv_exact(conn, 32)
                conn.sendall(b"\x01")
            finally:
                conn.close()
                srv.close()

        t = threading.Thread(target=peer, daemon=True)
        t.start()
        sender = FileSender("127.0.0.1", port)
        sender.send_file(self.src, verify_hash=True)
        t.join(timeout=15)
        self.assertEqual(seen["mode"], MODE_HASHED)
        self.assertEqual(seen["body"], self.data)
        self.assertEqual(seen["digest"], hashlib.sha256(self.data).digest())

    def test_sender_stats_callback_monotonic(self):
        srv, port = self._loopback()

        def peer():
            conn, _ = srv.accept()
            conn.settimeout(15)
            try:
                mode = net_util.recv_exact(conn, 1)
                assert mode == MODE_NORMAL
                nlen = struct.unpack("!I", net_util.recv_exact(conn, 4))[0]
                net_util.recv_exact(conn, nlen)
                size = struct.unpack("!Q", net_util.recv_exact(conn, 8))[0]
                net_util.recv_exact(conn, size)
                conn.sendall(b"\x01")
            finally:
                conn.close()
                srv.close()

        t = threading.Thread(target=peer, daemon=True)
        t.start()
        sender = FileSender("127.0.0.1", port)
        calls = []
        sender.send_file(self.src, stats_callback=lambda s, tot, el: calls.append((s, tot, el)))
        t.join(timeout=15)
        self.assertTrue(len(calls) >= 2)
        sent_values = [c[0] for c in calls]
        self.assertEqual(sent_values, sorted(sent_values))
        self.assertEqual(calls[-1][0], len(self.data))
        self.assertEqual(calls[-1][1], len(self.data))
        self.assertTrue(all(c[2] >= 0 for c in calls))

    def test_resume_and_secret_rejected(self):
        sender = FileSender("127.0.0.1", 1)
        with self.assertRaises(Exception):
            sender.send_file(self.src, secret_pin="123456", resume=True)


class TestSidecarHelpers(unittest.TestCase):
    def test_sidecar_roundtrip_and_invalid(self):
        with tempfile.TemporaryDirectory() as dl:
            server = FileReceiverServer(dl, port=8913)
            part, side = server._resume_paths("../../etc/x.bin")
            # Traversal engellenmeli: yollar download_dir içinde.
            self.assertTrue(os.path.realpath(part).startswith(os.path.realpath(dl)))
            server._write_sidecar(side, 100, 7, 40)
            self.assertEqual(server._read_sidecar(side, 100, 7), 40)
            # Boyut/mtime uyuşmazsa 0.
            self.assertEqual(server._read_sidecar(side, 101, 7), 0)
            self.assertEqual(server._read_sidecar(side, 100, 8), 0)
            self.assertEqual(server._read_sidecar(side + ".yok", 100, 7), 0)


if __name__ == "__main__":
    unittest.main()
