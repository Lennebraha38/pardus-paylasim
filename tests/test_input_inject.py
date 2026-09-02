"""
`input_inject` birim testleri (headless).

Kapsam:
  - Oturum-farkında saf backend seçimi (`select_backend_name`).
  - `create_backend` mevcutluk probe'ları monkeypatch ile → doğru backend
    yapıcısı seçilir, hiçbiri yoksa None.
  - Normalize→piksel koordinat matematiği (letterbox ikinci savunma).
  - `apply_event` bir kontrol eventini backend çağrılarına çevirir
    (FakeInjectionBackend çağrı kaydı).
  - Somut backend'ler mevcut değilken bile modül import olur (tembel import).

Test stili: unittest.TestCase, TR docstring, AAA (Arrange/Act/Assert).
"""

from __future__ import annotations

import unittest

from pardus_paylasim import platform_info
from pardus_paylasim.screen import control_protocol as cp
from pardus_paylasim.screen import input_inject as ii


class FakeInjectionBackend:
    """Çağrıları kaydeden sahte backend (InjectionBackend Protocol uyumlu)."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list = []

    def move(self, x: int, y: int) -> None:
        self.calls.append(("move", x, y))

    def button(self, button: str, down: bool) -> None:
        self.calls.append(("button", button, down))

    def scroll(self, dx: float, dy: float) -> None:
        self.calls.append(("scroll", dx, dy))

    def key(self, code: str, down: bool) -> None:
        self.calls.append(("key", code, down))

    def close(self) -> None:
        self.calls.append(("close",))


class TestSelectBackendName(unittest.TestCase):
    """Oturum + mevcutluk haritasından saf backend seçimi."""

    def test_x11_prefers_xtest(self) -> None:
        # Arrange
        avail = {ii.BACKEND_XTEST: True, ii.BACKEND_PYNPUT: True, ii.BACKEND_YDOTOOL: True}

        # Act
        name = ii.select_backend_name(platform_info.SESSION_X11, avail)

        # Assert
        self.assertEqual(name, ii.BACKEND_XTEST)

    def test_x11_falls_back_to_pynput_when_no_xtest(self) -> None:
        # Arrange
        avail = {ii.BACKEND_PYNPUT: True}

        # Act
        name = ii.select_backend_name(platform_info.SESSION_X11, avail)

        # Assert
        self.assertEqual(name, ii.BACKEND_PYNPUT)

    def test_wayland_prefers_portal_then_ydotool(self) -> None:
        # Arrange: portal Faz4 daima False; ydotool mevcut
        avail = {ii.BACKEND_YDOTOOL: True, ii.BACKEND_XTEST: True}

        # Act
        name = ii.select_backend_name(platform_info.SESSION_WAYLAND, avail)

        # Assert: Wayland'da XTEST çalışmaz → ydotool seçilir, xtest asla
        self.assertEqual(name, ii.BACKEND_YDOTOOL)

    def test_wayland_rejects_xtest_only(self) -> None:
        # Arrange: yalnız XTEST mevcut ama Wayland önceliğinde yok
        avail = {ii.BACKEND_XTEST: True, ii.BACKEND_PYNPUT: True}

        # Act
        name = ii.select_backend_name(platform_info.SESSION_WAYLAND, avail)

        # Assert: Wayland listesi (portal, ydotool) → ikisi de yok → None
        self.assertIsNone(name)

    def test_windows_prefers_pynput(self) -> None:
        # Arrange
        avail = {ii.BACKEND_PYNPUT: True, ii.BACKEND_XTEST: True}

        # Act
        name = ii.select_backend_name(platform_info.SESSION_WINDOWS, avail)

        # Assert
        self.assertEqual(name, ii.BACKEND_PYNPUT)

    def test_none_available_returns_none(self) -> None:
        # Arrange
        avail = {}

        # Act
        name = ii.select_backend_name(platform_info.SESSION_X11, avail)

        # Assert
        self.assertIsNone(name)

    def test_unknown_session_best_effort(self) -> None:
        # Arrange: bilinmeyen oturum → XTEST/pynput/ydotool dener
        avail = {ii.BACKEND_PYNPUT: True}

        # Act
        name = ii.select_backend_name(platform_info.SESSION_UNKNOWN, avail)

        # Assert
        self.assertEqual(name, ii.BACKEND_PYNPUT)


class TestCreateBackend(unittest.TestCase):
    """create_backend probe monkeypatch ile doğru yapıcıyı seçer."""

    def _patch_availability(self, avail: dict) -> None:
        """detect_availability'yi sabit harita ile değiştir."""
        self._orig_detect = ii.detect_availability
        ii.detect_availability = lambda: avail  # type: ignore[assignment]
        self.addCleanup(setattr, ii, "detect_availability", self._orig_detect)

    def _patch_factory(self, name: str, backend: object) -> None:
        """Bir backend yapıcısını sahte ile değiştir."""
        orig = ii._FACTORIES.get(name)
        ii._FACTORIES[name] = lambda: backend  # type: ignore[assignment,return-value]
        if orig is not None:
            self.addCleanup(ii._FACTORIES.__setitem__, name, orig)

    def test_selects_xtest_on_x11(self) -> None:
        # Arrange
        self._patch_availability({ii.BACKEND_XTEST: True})
        fake = FakeInjectionBackend()
        self._patch_factory(ii.BACKEND_XTEST, fake)

        # Act
        backend = ii.create_backend(session=platform_info.SESSION_X11)

        # Assert
        self.assertIs(backend, fake)

    def test_returns_none_when_no_backend(self) -> None:
        # Arrange
        self._patch_availability({})

        # Act
        backend = ii.create_backend(session=platform_info.SESSION_X11)

        # Assert
        self.assertIsNone(backend)

    def test_returns_none_when_factory_raises(self) -> None:
        # Arrange: seçilir ama kurulum patlar → None (kontrol reddedilir)
        self._patch_availability({ii.BACKEND_PYNPUT: True})

        def _boom():
            raise RuntimeError("kurulum hatası")

        orig = ii._FACTORIES.get(ii.BACKEND_PYNPUT)
        ii._FACTORIES[ii.BACKEND_PYNPUT] = _boom  # type: ignore[assignment]
        if orig is not None:
            self.addCleanup(ii._FACTORIES.__setitem__, ii.BACKEND_PYNPUT, orig)

        # Act
        backend = ii.create_backend(session=platform_info.SESSION_WINDOWS)

        # Assert
        self.assertIsNone(backend)


class TestNormalizedToPixel(unittest.TestCase):
    """Normalize 0..1 → host piksel dönüşümü."""

    def test_origin_maps_to_zero(self) -> None:
        # Act
        px, py = ii.normalized_to_pixel(0.0, 0.0, 1920, 1080)

        # Assert
        self.assertEqual((px, py), (0, 0))

    def test_max_maps_to_last_pixel(self) -> None:
        # Act
        px, py = ii.normalized_to_pixel(1.0, 1.0, 1920, 1080)

        # Assert: son piksel indeksi (boyut-1)
        self.assertEqual((px, py), (1919, 1079))

    def test_center(self) -> None:
        # Act
        px, py = ii.normalized_to_pixel(0.5, 0.5, 1920, 1080)

        # Assert
        self.assertEqual((px, py), (960, 540))

    def test_out_of_range_clamped(self) -> None:
        # Act: fail-safe ikinci savunma
        px, py = ii.normalized_to_pixel(1.5, -0.3, 800, 600)

        # Assert
        self.assertEqual((px, py), (799, 0))

    def test_zero_dimension_safe(self) -> None:
        # Act: sıfır boyut → 0 (bölme/negatif index yok)
        px, py = ii.normalized_to_pixel(0.5, 0.5, 0, 0)

        # Assert
        self.assertEqual((px, py), (0, 0))


class TestApplyEvent(unittest.TestCase):
    """apply_event eventi backend çağrılarına çevirir."""

    def test_move_event(self) -> None:
        # Arrange
        be = FakeInjectionBackend()
        ev = cp.MoveEvent(x=0.5, y=0.5)

        # Act
        ii.apply_event(be, ev, 1920, 1080)

        # Assert
        self.assertEqual(be.calls, [("move", 960, 540)])

    def test_button_event_moves_then_presses(self) -> None:
        # Arrange
        be = FakeInjectionBackend()
        ev = cp.ButtonEvent(button="left", down=True, x=0.0, y=0.0)

        # Act
        ii.apply_event(be, ev, 100, 100)

        # Assert: önce konumlan, sonra bas
        self.assertEqual(be.calls, [("move", 0, 0), ("button", "left", True)])

    def test_scroll_event(self) -> None:
        # Arrange
        be = FakeInjectionBackend()
        ev = cp.ScrollEvent(dx=0.0, dy=-3.0)

        # Act
        ii.apply_event(be, ev, 100, 100)

        # Assert
        self.assertEqual(be.calls, [("scroll", 0.0, -3.0)])

    def test_key_event(self) -> None:
        # Arrange
        be = FakeInjectionBackend()
        ev = cp.KeyEvent(code="KEY_A", down=True, mods=("ctrl",))

        # Act
        ii.apply_event(be, ev, 100, 100)

        # Assert: mods enjeksiyon katmanında ayrı KEY_* eventle basılır; key() koda odaklı
        self.assertEqual(be.calls, [("key", "KEY_A", True)])

    def test_grant_event_ignored(self) -> None:
        # Arrange: grant/revoke/ping enjeksiyon dışı
        be = FakeInjectionBackend()
        ev = cp.GrantEvent(session="tok", allow=True)

        # Act
        ii.apply_event(be, ev, 100, 100)

        # Assert
        self.assertEqual(be.calls, [])


class TestKeyTables(unittest.TestCase):
    """Nötr KEY_* eşleme tabloları tutarlı."""

    def test_evdev_codes_cover_letters(self) -> None:
        # Assert: A-Z evdev kod haritasında
        for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            self.assertIn(f"KEY_{c}", ii._EVDEV_CODES)

    def test_evdev_known_values(self) -> None:
        # Assert: input-event-codes.h bilinen değerler
        self.assertEqual(ii._EVDEV_CODES["KEY_ESC"], 1)
        self.assertEqual(ii._EVDEV_CODES["KEY_ENTER"], 28)
        self.assertEqual(ii._EVDEV_CODES["KEY_LEFTCTRL"], 29)
        self.assertEqual(ii._EVDEV_CODES["KEY_A"], 30)
        self.assertEqual(ii._EVDEV_CODES["KEY_SPACE"], 57)

    def test_xkeysym_names_cover_letters(self) -> None:
        # Assert
        self.assertEqual(ii._XKEYSYM_NAMES["KEY_A"], "a")
        self.assertEqual(ii._XKEYSYM_NAMES["KEY_ENTER"], "Return")
        self.assertEqual(ii._XKEYSYM_NAMES["KEY_LEFTCTRL"], "Control_L")

    def test_pynput_special_and_char_disjoint_coverage(self) -> None:
        # Assert: harf char haritasında, özel tuş special haritasında
        self.assertIn("KEY_A", ii._CHAR_KEYS)
        self.assertNotIn("KEY_A", ii._PYNPUT_SPECIAL)
        self.assertIn("KEY_ENTER", ii._PYNPUT_SPECIAL)
        self.assertNotIn("KEY_ENTER", ii._CHAR_KEYS)

    def test_all_supported_keys_have_at_least_one_mapping(self) -> None:
        # Assert: protokolün her KEY_* kodu en az bir backend tablosunda çözülür
        for code in cp.KEY_CODES:
            resolvable = (
                code in ii._XKEYSYM_NAMES
                or code in ii._EVDEV_CODES
                or code in ii._PYNPUT_SPECIAL
                or code in ii._CHAR_KEYS
            )
            self.assertTrue(resolvable, f"{code} hiçbir backend tablosunda yok")


if __name__ == "__main__":
    unittest.main()
