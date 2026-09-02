"""
Klavye kısayolu sekme-eşleme (#22) testleri.

`MainWindow._tab_name_for_index` saf statik yöntemdir: Ctrl+1..5 numarasını
sekme adına çevirir. GTK örneği gerektirmez, headless koşar.
"""

import unittest

from pardus_paylasim.window import MainWindow


class TestTabNameForIndex(unittest.TestCase):
    def test_first_index_maps_to_privacy(self):
        # Ctrl+1 → ilk sekme.
        self.assertEqual(MainWindow._tab_name_for_index(1), "privacy")

    def test_last_index_maps_to_settings(self):
        # Ctrl+5 → son sekme.
        self.assertEqual(MainWindow._tab_name_for_index(5), "settings")

    def test_all_indices_match_tab_order(self):
        # 1..N sırası TAB_NAMES ile birebir örtüşmeli.
        for i, name in enumerate(MainWindow.TAB_NAMES, start=1):
            self.assertEqual(MainWindow._tab_name_for_index(i), name)

    def test_zero_returns_none(self):
        self.assertIsNone(MainWindow._tab_name_for_index(0))

    def test_out_of_range_returns_none(self):
        # Sekme sayısından fazla → None (bağlanmamış kısayol).
        self.assertIsNone(MainWindow._tab_name_for_index(len(MainWindow.TAB_NAMES) + 1))

    def test_negative_returns_none(self):
        self.assertIsNone(MainWindow._tab_name_for_index(-1))

    def test_non_int_returns_none(self):
        # Tür güvenliği: sayı olmayan girdi istisna atmamalı.
        self.assertIsNone(MainWindow._tab_name_for_index("1"))
        self.assertIsNone(MainWindow._tab_name_for_index(None))


if __name__ == "__main__":
    unittest.main()
