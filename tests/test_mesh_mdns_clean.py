"""Mesh mDNS keşfi + gönderim-öncesi temizlik testleri (soket/ağ yok)."""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))


class TestMdnsHelpers(unittest.TestCase):
    def test_service_name_safe(self):
        from pardus_paylasim.discovery.mesh.mdns import build_service_name
        name = build_service_name("abc123")
        self.assertIn("abc123", name)
        self.assertTrue(name.endswith("._pardus-mesh._tcp.local."))
        evil = build_service_name("a/b c.d")
        self.assertNotIn(" ", evil)
        self.assertNotIn("/", evil)

    def test_txt_roundtrip(self):
        from pardus_paylasim.discovery.mesh.mdns import decode_peer_id, encode_txt
        self.assertEqual(decode_peer_id(encode_txt("es-42")), "es-42")
        self.assertEqual(decode_peer_id(None), "")
        self.assertEqual(decode_peer_id({}), "")
        self.assertEqual(decode_peer_id({"peer_id": "plain"}), "plain")

    def test_listener_ignores_self_and_reports_peer(self):
        from pardus_paylasim.discovery.mesh import mdns as M
        import socket

        seen = []
        lost = []
        listener = M._MeshListener(
            None, "ben", lambda ip, port, pid: seen.append((ip, port, pid)),
            lambda pid: lost.append(pid),
        )

        class FakeInfo:
            name = "pardus-mesh-sender._pardus-mesh._tcp.local."
            addresses = [socket.inet_aton("192.168.1.20")]
            port = 8920
            properties = {b"peer_id": b"sender"}

        listener._report(FakeInfo())
        self.assertEqual(seen, [("192.168.1.20", 8920, "sender")])

        class FakeSelf(FakeInfo):
            properties = {b"peer_id": b"ben"}

        listener._report(FakeSelf())
        self.assertEqual(len(seen), 1)  # kendi kaydımız elendi

        listener.remove_service(None, "", FakeInfo.name)
        self.assertEqual(lost, ["sender"])

    def test_discovery_degrades_without_zeroconf(self):
        from pardus_paylasim.discovery.mesh import mdns as M
        if M.HAS_ZEROCONF:
            self.skipTest("zeroconf kurulu; degrade yolu test edilemez")
        d = M.MeshDiscovery("ben", "127.0.0.1", 8920)
        self.assertFalse(d.start())
        self.assertFalse(d.running)
        d.stop()  # çökmemeli

    def test_node_discovery_lifecycle_no_zeroconf(self):
        from pardus_paylasim.discovery.mesh import mdns as M
        from pardus_paylasim.discovery.mesh.mesh_network import MeshNode
        if M.HAS_ZEROCONF:
            self.skipTest("zeroconf kurulu")
        node = MeshNode("ben", "127.0.0.1", mesh_port=0)
        try:
            node.start()
            self.assertTrue(node._running)
            self.assertFalse(node.start_discovery())
            self.assertFalse(node.discovery_running)
        finally:
            node.stop()


class TestPrepareSendFile(unittest.TestCase):
    def test_passthrough_when_disabled(self):
        from pardus_paylasim.cleaner.metadata_cleaner import prepare_send_file
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "a.txt")
            with open(src, "w") as f:
                f.write("merhaba")
            send_path, cleanup = prepare_send_file(src, False, tmp)
            self.assertEqual(send_path, src)
            self.assertIsNone(cleanup)

    def test_cleaned_copy_or_original(self):
        from pardus_paylasim.cleaner.metadata_cleaner import prepare_send_file
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "not.txt")
            with open(src, "w") as f:
                f.write("TCKN: 10000000146")
            send_path, cleanup = prepare_send_file(src, True, tmp)
            # Orijinal asla değişmemeli.
            with open(src) as f:
                self.assertIn("10000000146", f.read())
            if cleanup is not None:
                self.assertTrue(os.path.exists(send_path))
                self.assertNotEqual(send_path, src)
                os.unlink(cleanup)
                self.assertFalse(os.path.exists(send_path))
            else:
                # Temizleyici desteklemiyorsa orijinal yol döner.
                self.assertEqual(send_path, src)

    def test_missing_source_falls_back(self):
        from pardus_paylasim.cleaner.metadata_cleaner import prepare_send_file
        with tempfile.TemporaryDirectory() as tmp:
            send_path, cleanup = prepare_send_file(
                os.path.join(tmp, "yok.txt"), True, tmp)
            self.assertTrue(send_path.endswith("yok.txt"))
            self.assertIsNone(cleanup)


if __name__ == "__main__":
    unittest.main()
