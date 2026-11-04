"""Çekirdek modüller için davranışsal kapsam testleri.

Kapsam:
- `screen/fs_server.py`: path traversal/sürücü harfi/symlink kaçışı, dizin
  listeleme, dosya indirme (200/404)
- `screen/control_client.py`: koordinat eşleme, WebSocket el sıkışma saf
  yardımcıları, GDK keyval/modifier dönüşümleri
- `screen/trust_store.py`: yükleme/kaydetme, bozuk JSON, fingerprint doğrulama
- `cleaner/metadata_cleaner.py`: PDF/Ofis tarama, fail-closed temizleme
- `cleaner/report_builder.py`: JSON/Markdown/TXT çıktıları
"""

import base64
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pardus_paylasim.cleaner.metadata_cleaner import (  # noqa: E402
    CleaningResult,
    MetadataCleaner,
    PrivacyRiskItem,
)
from pardus_paylasim.cleaner.report_builder import ReportBuilder  # noqa: E402
from pardus_paylasim.screen import control_client, fs_server, trust_store  # noqa: E402
from pardus_paylasim.screen.control_server import compute_accept_key  # noqa: E402


class _FakeHandler:
    """`serve_download` için minimal HTTP handler taklidi."""

    def __init__(self):
        self.wfile = io.BytesIO()
        self.status = None
        self.headers = []
        self.body = None

    def send_response(self, code):
        self.status = code

    def send_header(self, key, value):
        self.headers.append((key, value))

    def end_headers(self):
        pass

    def _send_json(self, payload, status=200):
        self.status = status
        self.body = payload


class TestFsServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = os.path.realpath(self.tmp.name)
        self.patcher = patch.object(
            fs_server, "get_allowed_roots", return_value={"downloads": self.base}
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_resolve_valid_path(self):
        target = os.path.join(self.base, "a.txt")
        Path(target).write_text("x", encoding="utf-8")
        self.assertEqual(
            fs_server.resolve_path("downloads", "a.txt"), os.path.realpath(target)
        )
        # Baştaki ayraçlar temizlenir, kök dizin de geçerlidir.
        self.assertEqual(fs_server.resolve_path("downloads", "/a.txt"), os.path.realpath(target))
        self.assertEqual(fs_server.resolve_path("downloads", ""), self.base)

    def test_unknown_root_rejected(self):
        with self.assertRaises(fs_server.PathTraversalError):
            fs_server.resolve_path("root", "a.txt")

    def test_drive_letter_rejected(self):
        with self.assertRaises(fs_server.PathTraversalError):
            fs_server.resolve_path("downloads", "C:\\Windows\\system32")

    def test_parent_traversal_rejected(self):
        with self.assertRaises(fs_server.PathTraversalError):
            fs_server.resolve_path("downloads", "../etc/passwd")
        with self.assertRaises(fs_server.PathTraversalError):
            fs_server.resolve_path("downloads", "a/../../etc/passwd")

    def test_symlink_escape_rejected(self):
        link = os.path.join(self.base, "escape")
        try:
            os.symlink("/etc", link)
        except OSError:
            self.skipTest("symlink oluşturulamadı")
        with self.assertRaises(fs_server.PathTraversalError):
            fs_server.resolve_path("downloads", "escape/passwd")

    def test_list_directory(self):
        os.makedirs(os.path.join(self.base, "alt"))
        Path(os.path.join(self.base, "b.txt")).write_text("12345", encoding="utf-8")
        payload = json.loads(fs_server.list_directory("downloads", ""))
        self.assertEqual(payload["status"], "ok")
        by_name = {e["name"]: e for e in payload["entries"]}
        self.assertTrue(by_name["alt"]["is_dir"])
        self.assertEqual(by_name["alt"]["size"], 0)
        self.assertFalse(by_name["b.txt"]["is_dir"])
        self.assertEqual(by_name["b.txt"]["size"], 5)

    def test_list_directory_on_file_raises(self):
        target = os.path.join(self.base, "a.txt")
        Path(target).write_text("x", encoding="utf-8")
        with self.assertRaises(ValueError):
            fs_server.list_directory("downloads", "a.txt")

    def test_serve_download_success(self):
        target = os.path.join(self.base, "veri.bin")
        Path(target).write_bytes(b"abcdef")
        handler = _FakeHandler()
        fs_server.serve_download("downloads", "veri.bin", handler)
        self.assertEqual(handler.status, 200)
        headers = dict(handler.headers)
        self.assertEqual(headers["Content-Length"], "6")
        self.assertIn("veri.bin", headers["Content-Disposition"])
        self.assertEqual(handler.wfile.getvalue(), b"abcdef")

    def test_serve_download_missing_returns_404(self):
        handler = _FakeHandler()
        fs_server.serve_download("downloads", "yok.bin", handler)
        self.assertEqual(handler.status, 404)
        self.assertIn("Dosya bulunamadı", handler.body)


class TestControlClientHelpers(unittest.TestCase):
    def test_clamp01(self):
        self.assertEqual(control_client._clamp01(-5.0), 0.0)
        self.assertEqual(control_client._clamp01(0.25), 0.25)
        self.assertEqual(control_client._clamp01(5.0), 1.0)

    def test_map_widget_exact_fit(self):
        x, y = control_client.map_widget_to_normalized(800, 600, 800, 600, 400, 300)
        self.assertAlmostEqual(x, 0.5)
        self.assertAlmostEqual(y, 0.5)
        x, y = control_client.map_widget_to_normalized(800, 600, 800, 600, 0, 0)
        self.assertAlmostEqual(x, 0.0)
        self.assertAlmostEqual(y, 0.0)
        x, y = control_client.map_widget_to_normalized(800, 600, 800, 600, 800, 600)
        self.assertAlmostEqual(x, 1.0)
        self.assertAlmostEqual(y, 1.0)

    def test_map_widget_letterbox(self):
        # 1000x500 widget'a 400x400 kare görüntü: 500x500 çizilir, x'te 250 boşluk.
        x, _ = control_client.map_widget_to_normalized(1000, 500, 400, 400, 250, 250)
        self.assertAlmostEqual(x, 0.0)
        x, _ = control_client.map_widget_to_normalized(1000, 500, 400, 400, 750, 250)
        self.assertAlmostEqual(x, 1.0)
        # Boşluğa taşan fare kenara kırpılır.
        x, _ = control_client.map_widget_to_normalized(1000, 500, 400, 400, 0, 250)
        self.assertAlmostEqual(x, 0.0)
        x, _ = control_client.map_widget_to_normalized(1000, 500, 400, 400, 1000, 250)
        self.assertAlmostEqual(x, 1.0)

    def test_map_widget_invalid_sizes(self):
        self.assertEqual(
            control_client.map_widget_to_normalized(0, 0, 0, 0, 10, 10), (0.0, 0.0)
        )
        self.assertEqual(
            control_client.map_widget_to_normalized(100, 100, -1, 100, 10, 10),
            (0.0, 0.0),
        )

    def test_generate_ws_key(self):
        key = control_client.generate_ws_key()
        self.assertEqual(len(base64.b64decode(key)), 16)
        self.assertNotEqual(key, control_client.generate_ws_key())

    def test_build_handshake_request(self):
        raw = control_client.build_handshake_request(
            "192.168.1.10", 8920, "abc", pin="123456", session_token="tok"
        )
        text = raw.decode("ascii")
        self.assertTrue(text.startswith("GET /control HTTP/1.1\r\n"))
        self.assertIn("Host: 192.168.1.10:8920", text)
        self.assertIn("Upgrade: websocket", text)
        self.assertIn("Sec-WebSocket-Key: abc", text)
        self.assertIn("Sec-WebSocket-Version: 13", text)
        self.assertIn("X-Pardus-PIN: 123456", text)
        self.assertIn("X-Pardus-Session: tok", text)
        self.assertIn("Cookie: pardus_session=tok", text)
        self.assertTrue(text.endswith("\r\n\r\n"))

    def test_build_handshake_request_without_credentials(self):
        text = control_client.build_handshake_request("h", 1, "k").decode("ascii")
        self.assertNotIn("X-Pardus-PIN", text)
        self.assertNotIn("Cookie:", text)

    def test_parse_handshake_response(self):
        raw = (
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\n"
            b"Sec-WebSocket-Accept: ABC\r\n\r\n"
        )
        status, headers = control_client.parse_handshake_response(raw)
        self.assertEqual(status, 101)
        self.assertEqual(headers["upgrade"], "websocket")
        self.assertEqual(headers["sec-websocket-accept"], "ABC")

    def test_parse_handshake_response_malformed(self):
        self.assertEqual(control_client.parse_handshake_response(b"")[0], 0)
        status, headers = control_client.parse_handshake_response(
            b"HTTP/1.1 abc Nope\r\nK: V\r\n\r\n"
        )
        self.assertEqual(status, 0)
        self.assertEqual(headers["k"], "V")

    def test_verify_accept(self):
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        accept = compute_accept_key(key)
        self.assertTrue(control_client.verify_accept(key, accept))
        self.assertFalse(control_client.verify_accept(key, "yanlis"))
        self.assertFalse(control_client.verify_accept(key, ""))

    def test_keyval_to_key_code(self):
        self.assertEqual(control_client.keyval_to_key_code(0x41), "KEY_A")
        self.assertEqual(control_client.keyval_to_key_code(0x61), "KEY_A")
        self.assertEqual(control_client.keyval_to_key_code(0x30), "KEY_0")
        self.assertEqual(control_client.keyval_to_key_code(0xFFBE), "KEY_F1")
        self.assertEqual(control_client.keyval_to_key_code(0xFF0D), "KEY_ENTER")
        self.assertIsNone(control_client.keyval_to_key_code(0x123456))
        # Üretilen tüm kodlar protokol sözlüğünde olmalı.
        from pardus_paylasim.screen import control_protocol as cp

        for keyval in list(control_client._KEYVAL_MAP)[:200]:
            self.assertIn(control_client.keyval_to_key_code(keyval), cp.KEY_CODES)

    def test_gdk_state_to_mods(self):
        self.assertEqual(control_client.gdk_state_to_mods(0), ())
        state = 1 | 4  # shift + ctrl
        self.assertEqual(control_client.gdk_state_to_mods(state), ("ctrl", "shift"))
        self.assertEqual(
            control_client.gdk_state_to_mods(8 | (1 << 26)), ("alt", "meta")
        )
        self.assertEqual(control_client.gdk_state_to_mods(1 << 28), ("meta",))


class TestTrustStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.file = os.path.join(self.dir, "trusted_devices.json")
        self.lock = os.path.join(self.dir, "trusted_devices.json.lock")
        self.patches = [
            patch.object(trust_store, "_config_dir", self.dir),
            patch.object(trust_store, "TRUST_STORE_FILE", self.file),
            patch.object(trust_store, "LOCK_FILE", self.lock),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_missing_store_returns_none(self):
        self.assertIsNone(trust_store.get_trusted_fingerprint("dev"))

    def test_add_and_get_roundtrip(self):
        fp = "ab" * 32
        trust_store.add_trusted_fingerprint("dev", fp)
        self.assertEqual(trust_store.get_trusted_fingerprint("dev"), fp)
        self.assertIsNone(trust_store.get_trusted_fingerprint("baska"))
        with open(self.file, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["dev"]["fingerprint"], fp)
        self.assertIn("timestamp", data["dev"])

    def test_colon_fingerprint_accepted(self):
        fp = ":".join(["AB"] * 32)
        trust_store.add_trusted_fingerprint("dev", fp)
        self.assertEqual(trust_store.get_trusted_fingerprint("dev"), fp)

    def test_invalid_fingerprint_rejected(self):
        for bad in ["", "kisa", "zz" * 32, "ab" * 31]:
            with self.assertRaises(ValueError):
                trust_store.add_trusted_fingerprint("dev", bad)

    def test_corrupt_json_raises(self):
        Path(self.file).write_text("{bozuk", encoding="utf-8")
        with self.assertRaises(trust_store.TrustStoreError):
            trust_store.get_trusted_fingerprint("dev")

    def test_non_dict_root_raises(self):
        Path(self.file).write_text("[1,2,3]", encoding="utf-8")
        with self.assertRaises(trust_store.TrustStoreError):
            trust_store.get_trusted_fingerprint("dev")

    def test_record_without_valid_fingerprint_returns_none(self):
        Path(self.file).write_text(
            json.dumps({"dev": {"fingerprint": "gecersiz"}}), encoding="utf-8"
        )
        self.assertIsNone(trust_store.get_trusted_fingerprint("dev"))


class TestMetadataCleaner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cleaner = MetadataCleaner()

    def tearDown(self):
        self.tmp.cleanup()

    def _path(self, name: str) -> str:
        return os.path.join(self.tmp.name, name)

    def test_missing_file_scan_and_clean(self):
        missing = self._path("yok.pdf")
        self.assertEqual(self.cleaner.scan_file(missing), [])
        result = self.cleaner.clean_file(missing)
        self.assertFalse(result.success)
        self.assertEqual(result.cleaned_path, "")
        self.assertIn("bulunamadı", result.message)

    def test_scan_pdf_metadata(self):
        pdf = self._path("belge.pdf")
        with open(pdf, "wb") as f:
            f.write(
                b"%PDF-1.4\n/Author (Hacker)\n/Creator (Canva)\n"
                b"/CreationDate (D:20260101)\n%%EOF"
            )
        risks = self.cleaner.scan_file(pdf)
        keys = {r.key for r in risks}
        self.assertIn("Author", keys)
        self.assertIn("Creator", keys)
        self.assertTrue(all(r.severity == "ORTA" for r in risks))

    def test_scan_office_zip_metadata(self):
        docx = self._path("belge.docx")
        core = (
            '<?xml version="1.0"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:creator>Ahmet Yilmaz</dc:creator>"
            "<cp:lastModifiedBy>Mehmet</cp:lastModifiedBy>"
            "</cp:coreProperties>"
        )
        with zipfile.ZipFile(docx, "w") as zf:
            zf.writestr("docProps/core.xml", core)
        risks = self.cleaner.scan_file(docx)
        values = {r.value for r in risks}
        self.assertIn("Ahmet Yilmaz", values)
        self.assertIn("Mehmet", values)
        self.assertTrue(all(r.severity == "YÜKSEK" for r in risks))

    def test_scan_office_zip_invalid_xml_is_safe(self):
        docx = self._path("bozuk.docx")
        with zipfile.ZipFile(docx, "w") as zf:
            zf.writestr("docProps/core.xml", "<bozuk><<<")
        # Bozuk XML çökme değil, boş risk listesi üretmeli.
        self.assertEqual(self.cleaner.scan_file(docx), [])

    def test_clean_unsupported_type_fails_closed(self):
        doc = self._path("not.pdf")
        Path(doc).write_text("/Author (Hacker)", encoding="utf-8")
        with patch.object(self.cleaner, "has_mat2", False), patch.object(
            self.cleaner, "has_exiftool", False
        ):
            result = self.cleaner.clean_file(doc, self._path("out.pdf"))
        self.assertFalse(result.success)
        self.assertEqual(result.cleaned_path, "")

    def test_clean_no_risk_copies_file(self):
        txt = self._path("temiz.txt")
        Path(txt).write_text("merhaba", encoding="utf-8")
        out = self._path("kopya.txt")
        with patch.object(self.cleaner, "has_mat2", False), patch.object(
            self.cleaner, "has_exiftool", False
        ):
            result = self.cleaner.clean_file(txt, out)
        self.assertTrue(result.success)
        self.assertTrue(os.path.exists(out))
        self.assertEqual(Path(out).read_text(encoding="utf-8"), "merhaba")


class TestReportBuilder(unittest.TestCase):
    def _results(self):
        risk = PrivacyRiskItem(
            category="GPS",
            key="GPS Latitude",
            value="39.9 N",
            severity="KRİTİK",
            description="Konum",
        )
        return [
            CleaningResult(
                original_path="/tmp/a.jpg",
                cleaned_path="/tmp/a_temiz.jpg",
                success=True,
                risks_found=[risk],
                risks_removed_count=1,
                engine_used="MAT2",
                message="Temizlendi",
            ),
            CleaningResult(
                original_path="/tmp/b.pdf",
                cleaned_path="",
                success=False,
                message="Hata",
            ),
        ]

    def test_to_json(self):
        data = json.loads(ReportBuilder.to_json(self._results()))
        self.assertEqual(data["version"], "1.1.0")
        self.assertEqual(data["total_files"], 2)
        self.assertEqual(data["files"][0]["risks"][0]["key"], "GPS Latitude")
        self.assertFalse(data["files"][1]["success"])

    def test_to_markdown(self):
        text = ReportBuilder.to_markdown(self._results())
        self.assertIn("# 🛡️", text)
        self.assertIn("/tmp/a.jpg", text)
        self.assertIn("GPS Latitude", text)
        self.assertIn("Temizlendi", text)

    def test_to_txt(self):
        text = ReportBuilder.to_txt(self._results())
        self.assertIn("PARDUS GÜVENLİ PAYLAŞIM", text)
        self.assertIn("/tmp/b.pdf", text)
        self.assertIn("BAŞARISIZ", text)


if __name__ == "__main__":
    unittest.main()
