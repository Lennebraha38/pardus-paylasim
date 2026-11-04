"""Mesh ağı HMAC kimlik doğrulama testleri.

Kapsam:
- `MeshProtocol.pack_fragment` / `unpack_fragment` roundtrip
- Paylaşılan anahtar ile imzalama, yanlış anahtar ve kurcalanmış paket reddi
- `load_mesh_key` ortam değişkeni davranışı (hex / parola / tanımsız)
"""

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pardus_paylasim.discovery.mesh.mesh_network import (  # noqa: E402
    AUTH_TAG_LEN,
    FRAG_DATA,
    MeshProtocol,
    load_mesh_key,
)

KEY = b"k" * 32
OTHER_KEY = b"x" * 32


class TestMeshProtocolAuth(unittest.TestCase):
    def _pack(self, auth_key=None):
        return MeshProtocol.pack_fragment(
            FRAG_DATA,
            "transfer-1",
            3,
            10,
            b"merhaba dunya",
            "peer-a",
            0,
            "a" * 32,
            auth_key=auth_key,
        )

    def test_roundtrip_without_auth(self):
        raw = self._pack()
        frag = MeshProtocol.unpack_fragment(raw)
        self.assertIsNotNone(frag)
        self.assertEqual(frag["type"], FRAG_DATA)
        self.assertEqual(frag["chunk_index"], 3)
        self.assertEqual(frag["total_chunks"], 10)
        self.assertEqual(frag["data"], b"merhaba dunya")
        self.assertEqual(frag["source_peer_id"], "peer-a")
        self.assertEqual(frag["hop_count"], 0)
        # Anahtarsız paket imza taşımaz.
        self.assertEqual(len(raw), 4 + 90 + len(b"merhaba dunya"))

    def test_roundtrip_with_auth_appends_tag(self):
        raw = self._pack(KEY)
        self.assertEqual(
            len(raw), 4 + 90 + len(b"merhaba dunya") + AUTH_TAG_LEN
        )
        frag = MeshProtocol.unpack_fragment(raw, auth_key=KEY)
        self.assertIsNotNone(frag)
        self.assertEqual(frag["data"], b"merhaba dunya")

    def test_wrong_key_rejected(self):
        raw = self._pack(KEY)
        self.assertIsNone(MeshProtocol.unpack_fragment(raw, auth_key=OTHER_KEY))

    def test_tampered_payload_rejected(self):
        raw = bytearray(self._pack(KEY))
        # Gövdedeki bir baytı değiştir (imza artık tutmaz).
        raw[20] ^= 0xFF
        self.assertIsNone(MeshProtocol.unpack_fragment(bytes(raw), auth_key=KEY))

    def test_tampered_tag_rejected(self):
        raw = bytearray(self._pack(KEY))
        raw[-1] ^= 0xFF
        self.assertIsNone(MeshProtocol.unpack_fragment(bytes(raw), auth_key=KEY))

    def test_truncated_signed_packet_rejected(self):
        raw = self._pack(KEY)
        self.assertIsNone(
            MeshProtocol.unpack_fragment(raw[: 4 + 90], auth_key=KEY)
        )

    def test_signed_packet_rejected_when_key_expected_but_absent(self):
        raw = self._pack()  # imzasız
        # Anahtar bekleyen taraf imzasız paketi kabul etmemeli.
        self.assertIsNone(MeshProtocol.unpack_fragment(raw, auth_key=KEY))

    def test_bad_magic_rejected(self):
        raw = b"XXXX" + self._pack()[4:]
        self.assertIsNone(MeshProtocol.unpack_fragment(raw))
        self.assertIsNone(MeshProtocol.unpack_fragment(raw, auth_key=KEY))


class TestLoadMeshKey(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop("PARDUS_MESH_KEY", None)

    def tearDown(self):
        os.environ.pop("PARDUS_MESH_KEY", None)
        if self._old is not None:
            os.environ["PARDUS_MESH_KEY"] = self._old

    def test_unset_returns_none(self):
        self.assertIsNone(load_mesh_key())

    def test_empty_returns_none(self):
        os.environ["PARDUS_MESH_KEY"] = "   "
        self.assertIsNone(load_mesh_key())

    def test_hex_64_chars(self):
        os.environ["PARDUS_MESH_KEY"] = "ab" * 32
        self.assertEqual(load_mesh_key(), bytes.fromhex("ab" * 32))

    def test_passphrase_hashed(self):
        import hashlib

        os.environ["PARDUS_MESH_KEY"] = "cok-gizli-parola"
        self.assertEqual(
            load_mesh_key(),
            hashlib.sha256(b"cok-gizli-parola").digest(),
        )

    def test_invalid_hex_falls_back_to_passphrase_hash(self):
        import hashlib

        # 64 karakter ama hex değil → parola olarak özetlenir.
        value = "z" * 64
        os.environ["PARDUS_MESH_KEY"] = value
        self.assertEqual(load_mesh_key(), hashlib.sha256(value.encode()).digest())


if __name__ == "__main__":
    unittest.main()
