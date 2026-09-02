"""
İlerleme/hız/ETA yardımcı (#23) testleri.

`progress` modülü saf ve yan-etkisizdir: GTK/soket gerektirmez, headless koşar.
"""

import unittest

from pardus_paylasim.progress import (
    TransferStats,
    compute_stats,
    format_progress_line,
    human_eta,
    human_rate,
    human_size,
)


class TestComputeStats(unittest.TestCase):
    def test_half_done_percent(self):
        # 50 / 100 bayt → %50.
        stats = compute_stats(50, 100, elapsed=1.0)
        self.assertAlmostEqual(stats.percent, 0.5)

    def test_rate_is_bytes_over_elapsed(self):
        # 1000 bayt / 2 sn → 500 B/s.
        stats = compute_stats(1000, 2000, elapsed=2.0)
        self.assertAlmostEqual(stats.rate_bps, 500.0)

    def test_eta_from_remaining_and_rate(self):
        # 500/1000 bayt, 500 B/s → kalan 500 bayt / 500 = 1 sn.
        stats = compute_stats(500, 1000, elapsed=1.0)
        self.assertAlmostEqual(stats.eta_seconds, 1.0)

    def test_zero_elapsed_gives_zero_rate_and_no_eta(self):
        # Süre 0 → hız hesaplanamaz, ETA yok (istisna atmamalı).
        stats = compute_stats(10, 100, elapsed=0.0)
        self.assertEqual(stats.rate_bps, 0.0)
        self.assertIsNone(stats.eta_seconds)

    def test_unknown_total_gives_zero_percent_and_no_eta(self):
        # Toplam bilinmiyorsa (0) oran 0, ETA None; hız yine ölçülebilir.
        stats = compute_stats(2048, 0, elapsed=1.0)
        self.assertEqual(stats.percent, 0.0)
        self.assertIsNone(stats.eta_seconds)
        self.assertAlmostEqual(stats.rate_bps, 2048.0)

    def test_percent_clamped_to_one(self):
        # Aktarılan toplamı aşarsa oran 1.0'ı geçmemeli.
        stats = compute_stats(150, 100, elapsed=1.0)
        self.assertEqual(stats.percent, 1.0)

    def test_negative_inputs_are_clamped(self):
        # Negatif girdi güvenli 0'a çekilir; çökme yok.
        stats = compute_stats(-10, -100, elapsed=-5.0)
        self.assertEqual(stats.percent, 0.0)
        self.assertEqual(stats.rate_bps, 0.0)
        self.assertIsNone(stats.eta_seconds)

    def test_returns_namedtuple(self):
        self.assertIsInstance(compute_stats(1, 2, 1.0), TransferStats)


class TestHumanSize(unittest.TestCase):
    def test_bytes_no_decimal(self):
        self.assertEqual(human_size(512), "512 B")

    def test_kilobytes(self):
        self.assertEqual(human_size(1024), "1.0 KB")

    def test_megabytes(self):
        self.assertEqual(human_size(1024 * 1024 * 4.2), "4.2 MB")

    def test_negative_clamped_to_zero(self):
        self.assertEqual(human_size(-99), "0 B")


class TestHumanRate(unittest.TestCase):
    def test_appends_per_second(self):
        self.assertEqual(human_rate(1024), "1.0 KB/s")


class TestHumanEta(unittest.TestCase):
    def test_none_is_dash(self):
        self.assertEqual(human_eta(None), "—")

    def test_seconds_only(self):
        self.assertEqual(human_eta(12.0), "~12 sn")

    def test_minutes_and_seconds(self):
        self.assertEqual(human_eta(65.0), "~1 dk 5 sn")

    def test_hours_and_minutes(self):
        self.assertEqual(human_eta(3720.0), "~1 sa 2 dk")

    def test_negative_clamped(self):
        self.assertEqual(human_eta(-5.0), "~0 sn")


class TestFormatProgressLine(unittest.TestCase):
    def test_line_has_percent_rate_eta(self):
        # %50 · 500 B/s · ~1 sn biçimini üretmeli.
        stats = compute_stats(500, 1000, elapsed=1.0)
        line = format_progress_line(stats)
        self.assertIn("%50", line)
        self.assertIn("/s", line)
        self.assertIn("~1 sn", line)


if __name__ == "__main__":
    unittest.main()
