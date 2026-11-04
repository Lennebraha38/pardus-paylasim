"""gettext yerelleştirme ve rendezvous onay (consent) testleri."""

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pardus_paylasim import i18n  # noqa: E402
from pardus_paylasim.discovery import rendezvous_client as rc  # noqa: E402

LOCALE_DIR = REPO_ROOT / "src" / "pardus_paylasim" / "locale"


class TestI18n(unittest.TestCase):
    def tearDown(self):
        # Diğer testleri etkilememek için kaynak (Türkçe) kataloğa dön.
        i18n.setup_i18n(localedir=str(REPO_ROOT / "locale"))

    def test_catalog_files_exist(self):
        self.assertTrue(
            (LOCALE_DIR / "en" / "LC_MESSAGES" / "pardus-paylasim.mo").exists()
        )
        self.assertTrue(
            (LOCALE_DIR / "en" / "LC_MESSAGES" / "pardus-paylasim.po").exists()
        )

    def test_english_translation(self):
        with patch.dict(os.environ, {"LANGUAGE": "en"}):
            i18n.setup_i18n(localedir=str(LOCALE_DIR))
            self.assertEqual(i18n._("Başlat"), "Start")
            self.assertEqual(i18n._("Dosya bulunamadı."), "File not found.")
            # Katalogda olmayan metin kaynak dilde döner (fallback).
            self.assertEqual(i18n._("Katalogda yok"), "Katalogda yok")

    def test_turkish_fallback_without_catalog(self):
        i18n.setup_i18n(localedir=str(REPO_ROOT / "locale"))
        self.assertEqual(i18n._("Başlat"), "Başlat")


class _FakeWS:
    """`websockets.connect` yerine geçen sahte bağlantı."""

    def __init__(self, messages, on_last=None):
        self.messages = list(messages)
        self.sent = []
        self.on_last = on_last

    async def send(self, payload):
        self.sent.append(payload)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        msg = self.messages.pop(0)
        if not self.messages and self.on_last:
            self.on_last()
        return msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _run_offer(consent=None):
    """Bir `offer` mesajı işleyen istemciyi çalıştır, gönderilenleri döndür."""
    client = rc.RendezvousClient("ws://127.0.0.1:1")
    if consent is not None:
        client.set_consent_callback(consent)
    offer = json.dumps(
        {
            "type": "offer",
            "sender_id": "peer-x",
            "sdp": "v=0",
            "offer_type": "offer",
            "monitor_index": 0,
        }
    )
    fake = _FakeWS([offer], on_last=lambda: setattr(client, "running", False))

    def fake_connect(*args, **kwargs):
        return fake

    async def run():
        with patch.object(rc.websockets, "connect", fake_connect):
            await client.connect()

    asyncio.run(run())
    return fake.sent


class TestRendezvousConsent(unittest.TestCase):
    def test_default_deny_without_callback(self):
        sent = _run_offer()
        self.assertTrue(sent)
        payload = json.loads(sent[-1])
        self.assertEqual(payload["type"], "reject")
        self.assertEqual(payload["target_id"], "peer-x")

    def test_callback_false_rejects(self):
        calls = []

        def consent(sender_id, offer_type):
            calls.append((sender_id, offer_type))
            return False

        sent = _run_offer(consent)
        self.assertEqual(calls, [("peer-x", "offer")])
        self.assertEqual(json.loads(sent[-1])["type"], "reject")

    def test_callback_exception_rejects(self):
        def consent(sender_id, offer_type):
            raise RuntimeError("onay hatası")

        sent = _run_offer(consent)
        self.assertEqual(json.loads(sent[-1])["type"], "reject")

    def test_callback_true_attempts_answer(self):
        def consent(sender_id, offer_type):
            return True

        class _Desc:
            sdp = "v=0"
            type = "answer"

        class _FakeManager:
            async def handle_offer(self, sdp, offer_type, monitor_index):
                return _Desc()

        fake_module = type(sys)("pardus_paylasim.screen.webrtc_server")
        fake_module.webrtc_manager = _FakeManager()
        sent = _run_offer_with_module(consent, fake_module)
        self.assertEqual(json.loads(sent[-1])["type"], "answer")
        self.assertEqual(json.loads(sent[-1])["target_id"], "peer-x")


def _run_offer_with_module(consent, fake_module):
    client = rc.RendezvousClient("ws://127.0.0.1:1")
    client.set_consent_callback(consent)
    offer = json.dumps(
        {
            "type": "offer",
            "sender_id": "peer-x",
            "sdp": "v=0",
            "offer_type": "offer",
            "monitor_index": 0,
        }
    )
    fake = _FakeWS([offer], on_last=lambda: setattr(client, "running", False))

    def fake_connect(*args, **kwargs):
        return fake

    async def run():
        with patch.object(rc.websockets, "connect", fake_connect), patch.dict(
            sys.modules, {"pardus_paylasim.screen.webrtc_server": fake_module}
        ):
            await client.connect()

    asyncio.run(run())
    return fake.sent


if __name__ == "__main__":
    unittest.main()
