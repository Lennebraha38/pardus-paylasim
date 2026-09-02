"""
`screen.control_protocol` testleri — tel codec.

Kapsam: her mesaj tipi round-trip (encode→decode aynı kalsın); bozuk/geçersiz
girdi reddi (bilinmeyen tip/sürüm, sayı-olmayan koord, geçersiz tuş/düğme);
güvenlik cap'leri (payload boyut, koordinat kırpma, kaydırma kırpma, mods
canonical). Yalnız stdlib — headless.
"""

from __future__ import annotations

import json
import unittest

from pardus_paylasim.screen.control_protocol import (
    KEY_CODES,
    MAX_MESSAGE_BYTES,
    PROTOCOL_VERSION,
    SCROLL_MAX,
    ButtonEvent,
    GrantEvent,
    KeyEvent,
    MoveEvent,
    PingEvent,
    PongEvent,
    ProtocolError,
    RevokeEvent,
    ScrollEvent,
    decode,
    encode,
)


class TestRoundTrip(unittest.TestCase):
    """encode→decode her mesaj tipini kayıpsız korumalı."""

    def _round(self, msg):
        return decode(encode(msg))

    def test_move_round_trip(self):
        # Arrange
        msg = MoveEvent(x=0.73, y=0.41)
        # Act
        out = self._round(msg)
        # Assert
        self.assertEqual(out, msg)

    def test_move_with_sid_round_trip(self):
        msg = MoveEvent(x=0.1, y=0.2, sid="tok-abc")
        self.assertEqual(self._round(msg), msg)

    def test_button_round_trip(self):
        msg = ButtonEvent(button="left", down=True, x=0.5, y=0.5, sid="s1")
        self.assertEqual(self._round(msg), msg)

    def test_button_up_round_trip(self):
        msg = ButtonEvent(button="right", down=False, x=0.9, y=0.05)
        self.assertEqual(self._round(msg), msg)

    def test_scroll_round_trip(self):
        msg = ScrollEvent(dx=0.0, dy=-3.0)
        self.assertEqual(self._round(msg), msg)

    def test_key_round_trip(self):
        msg = KeyEvent(code="KEY_A", down=True, mods=("ctrl",))
        self.assertEqual(self._round(msg), msg)

    def test_key_multi_mod_canonical(self):
        # Arrange — sırasız/tekrarlı mods
        msg = KeyEvent(code="KEY_C", down=True, mods=("shift", "ctrl"))
        # Act
        out = self._round(msg)
        # Assert — canonical sıralı
        self.assertEqual(out.mods, ("ctrl", "shift"))

    def test_grant_round_trip(self):
        msg = GrantEvent(session="tok-xyz", allow=True)
        self.assertEqual(self._round(msg), msg)

    def test_grant_deny_round_trip(self):
        msg = GrantEvent(session="", allow=False)
        self.assertEqual(self._round(msg), msg)

    def test_revoke_round_trip(self):
        self.assertEqual(self._round(RevokeEvent()), RevokeEvent())

    def test_ping_pong_round_trip(self):
        self.assertEqual(self._round(PingEvent()), PingEvent())
        self.assertEqual(self._round(PongEvent()), PongEvent())

    def test_encode_includes_version(self):
        # Arrange / Act
        obj = json.loads(encode(PingEvent()))
        # Assert
        self.assertEqual(obj["v"], PROTOCOL_VERSION)


class TestMalformedRejected(unittest.TestCase):
    """Yapısal bozuk girdi ProtocolError vermeli (sessiz kabul asla)."""

    def test_invalid_json(self):
        with self.assertRaises(ProtocolError):
            decode("{not json")

    def test_non_object_json(self):
        with self.assertRaises(ProtocolError):
            decode("[1,2,3]")

    def test_unknown_type(self):
        with self.assertRaises(ProtocolError):
            decode('{"t":"explode","v":1}')

    def test_missing_type(self):
        with self.assertRaises(ProtocolError):
            decode('{"v":1,"x":0.5}')

    def test_unsupported_version(self):
        with self.assertRaises(ProtocolError):
            decode('{"t":"ping","v":99}')

    def test_move_non_numeric_coord(self):
        with self.assertRaises(ProtocolError):
            decode('{"t":"move","x":"foo","y":0.5,"v":1}')

    def test_move_bool_coord_rejected(self):
        # bool int alt-tipi — koordinatta kaza engellenmeli
        with self.assertRaises(ProtocolError):
            decode('{"t":"move","x":true,"y":0.5,"v":1}')

    def test_move_missing_coord(self):
        with self.assertRaises(ProtocolError):
            decode('{"t":"move","x":0.5,"v":1}')

    def test_button_invalid_name(self):
        with self.assertRaises(ProtocolError):
            decode('{"t":"btn","b":"scroll","down":true,"x":0.5,"y":0.5,"v":1}')

    def test_button_non_bool_down(self):
        with self.assertRaises(ProtocolError):
            decode('{"t":"btn","b":"left","down":1,"x":0.5,"y":0.5,"v":1}')

    def test_key_invalid_code(self):
        with self.assertRaises(ProtocolError):
            decode('{"t":"key","code":"KEY_PWNED","down":true,"v":1}')

    def test_key_invalid_modifier(self):
        with self.assertRaises(ProtocolError):
            decode('{"t":"key","code":"KEY_A","down":true,"mods":["super"],"v":1}')

    def test_key_mods_not_list(self):
        with self.assertRaises(ProtocolError):
            decode('{"t":"key","code":"KEY_A","down":true,"mods":"ctrl","v":1}')

    def test_grant_non_string_session(self):
        with self.assertRaises(ProtocolError):
            decode('{"t":"grant","session":123,"allow":true,"v":1}')

    def test_sid_non_string(self):
        with self.assertRaises(ProtocolError):
            decode('{"t":"move","x":0.5,"y":0.5,"sid":123,"v":1}')


class TestSecurityCaps(unittest.TestCase):
    """Güvenlik sınırları: payload boyut, koord/scroll kırpma."""

    def test_oversize_message_rejected(self):
        # Arrange — MAX_MESSAGE_BYTES üstü ham girdi
        raw = '{"t":"move","x":0.5,"y":0.5,"pad":"' + "A" * MAX_MESSAGE_BYTES + '"}'
        # Act / Assert
        with self.assertRaises(ProtocolError):
            decode(raw)

    def test_coord_over_one_clamped(self):
        # Arrange — 1.0 üstü koordinat
        out = decode('{"t":"move","x":1.7,"y":-0.3,"v":1}')
        # Assert — [0,1]'e kırpıldı, reddedilmedi (fail-safe)
        self.assertEqual(out.x, 1.0)
        self.assertEqual(out.y, 0.0)

    def test_scroll_clamped(self):
        # Arrange
        out = decode('{"t":"scroll","dx":9999,"dy":-9999,"v":1}')
        # Assert
        self.assertEqual(out.dx, SCROLL_MAX)
        self.assertEqual(out.dy, -SCROLL_MAX)

    def test_bytes_input_decoded(self):
        # Arrange — bytes girdi (soket wire)
        raw = encode(MoveEvent(x=0.5, y=0.5)).encode("utf-8")
        # Act
        out = decode(raw)
        # Assert
        self.assertIsInstance(out, MoveEvent)

    def test_non_utf8_bytes_rejected(self):
        with self.assertRaises(ProtocolError):
            decode(b"\xff\xfe\x00")


class TestKeyCodeTable(unittest.TestCase):
    """Layout-bağımsız enum tablosu beklenen tuşları içermeli."""

    def test_common_keys_present(self):
        for code in ("KEY_A", "KEY_9", "KEY_F1", "KEY_ENTER", "KEY_LEFTCTRL"):
            self.assertIn(code, KEY_CODES)

    def test_vt_switch_keys_still_encodable(self):
        # KEY_F1..F12 tel'de geçerli; tehlikeli-kombo filtresi enjeksiyon
        # katmanında (C4), protokol katmanında değil.
        self.assertIn("KEY_F1", KEY_CODES)


if __name__ == "__main__":
    unittest.main()
