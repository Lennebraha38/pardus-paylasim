"""
Çoklu dosya + klasör transferi ve güvenli alt-yol (safe_target_path) testleri.
"""

import os
import tempfile
import time
import unittest

from pardus_paylasim.discovery.transfer import (
    FileReceiverServer,
    FileSender,
    safe_target_path,
)

_PORT_MULTI = 8971
_PORT_FOLDER = 8972


def _wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


class TestSafeTargetPath(unittest.TestCase):
    """safe_target_path birim testleri (soket yok)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _in_root(self, path):
        real_root = os.path.realpath(self.root)
        return os.path.realpath(path).startswith(real_root)

    def test_plain_name(self):
        p = safe_target_path(self.root, "belge.txt")
        self.assertTrue(self._in_root(p))
        self.assertEqual(os.path.basename(p), "belge.txt")

    def test_subpath_allowed(self):
        # Klasör yapısı korunmalı.
        p = safe_target_path(self.root, "klasor/alt/dosya.txt")
        self.assertTrue(self._in_root(p))
        self.assertIn("klasor", p)
        self.assertIn("alt", p)

    def test_parent_traversal_blocked(self):
        # '..' bileşenleri elenir; sonuç download_dir içinde KALMALI (aşım yok).
        # 'tmp' bir alt klasör adı olarak kalabilir; kritik olan kök-içi olması.
        p = safe_target_path(self.root, "../../../../tmp/evil.bin")
        self.assertTrue(self._in_root(p))
        # Mutlak /tmp hedefi asla oluşmamalı; sonuç kök-içi kalmalı.
        self.assertTrue(os.path.realpath(p).startswith(os.path.realpath(self.root)))

    def test_absolute_path_blocked(self):
        p = safe_target_path(self.root, "/etc/passwd")
        self.assertTrue(self._in_root(p))

    def test_windows_backslash_and_drive(self):
        p = safe_target_path(self.root, "..\\..\\Windows\\evil.dll")
        self.assertTrue(self._in_root(p))

    def test_empty_name_fallback(self):
        p = safe_target_path(self.root, "../../")
        self.assertTrue(self._in_root(p))


class TestMultiAndFolderTransfer(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.download_dir = os.path.join(self._tmp.name, "downloads")
        os.makedirs(self.download_dir, exist_ok=True)
        self.src_dir = os.path.join(self._tmp.name, "src")
        os.makedirs(self.src_dir, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_send_multiple_files(self):
        from pardus_paylasim.screen import tls_util

        cert, key, _ = tls_util.generate_self_signed_cert()
        server_ctx = tls_util.build_server_context(cert, key)
        client_ctx = tls_util.build_client_context(cert)

        received = []
        server = FileReceiverServer(self.download_dir, port=_PORT_MULTI, ssl_context=server_ctx)
        server.on_file_received = lambda p: received.append(p)
        server.on_file_request = lambda name, size, ip: True
        server.start()
        try:
            paths = []
            for i in range(3):
                fp = os.path.join(self.src_dir, f"dosya{i}.txt")
                with open(fp, "wb") as f:
                    f.write(f"icerik {i}".encode())
                paths.append(fp)

            sender = FileSender("127.0.0.1", _PORT_MULTI)
            sender.ssl_context = client_ctx
            sender.send_files(paths)
            self.assertTrue(_wait_for(lambda: len(received) == 3))
            for i in range(3):
                self.assertTrue(os.path.exists(os.path.join(self.download_dir, f"dosya{i}.txt")))
        finally:
            server.stop()

    def test_send_folder_preserves_structure(self):
        from pardus_paylasim.screen import tls_util

        cert, key, _ = tls_util.generate_self_signed_cert()
        server_ctx = tls_util.build_server_context(cert, key)
        client_ctx = tls_util.build_client_context(cert)

        received = []
        server = FileReceiverServer(self.download_dir, port=_PORT_FOLDER, ssl_context=server_ctx)
        server.on_file_received = lambda p: received.append(p)
        server.on_file_request = lambda name, size, ip: True
        server.start()
        try:
            # Kaynak yapı: proje/ana.txt, proje/alt/ic.txt
            proj = os.path.join(self.src_dir, "proje")
            os.makedirs(os.path.join(proj, "alt"), exist_ok=True)
            with open(os.path.join(proj, "ana.txt"), "wb") as f:
                f.write(b"ana")
            with open(os.path.join(proj, "alt", "ic.txt"), "wb") as f:
                f.write(b"ic")

            sender = FileSender("127.0.0.1", _PORT_FOLDER)
            sender.ssl_context = client_ctx
            sender.send_folder(proj)
            self.assertTrue(_wait_for(lambda: len(received) == 2))

            # Alıcıda yapı korunmalı: downloads/proje/ana.txt + proje/alt/ic.txt
            self.assertTrue(os.path.exists(os.path.join(self.download_dir, "proje", "ana.txt")))
            self.assertTrue(
                os.path.exists(os.path.join(self.download_dir, "proje", "alt", "ic.txt"))
            )
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
