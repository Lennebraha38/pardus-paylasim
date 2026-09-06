"""Aktarım sağlığı testleri: retry + anomali + TransferHealth (soket yok)."""

import os
import sys
import time
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))


class TestRetry(unittest.TestCase):
    def test_flaky_succeeds(self):
        from pardus_paylasim.discovery.health import retry
        calls = {"n": 0}

        @retry(max_attempts=3, initial_delay=0.01, exceptions=(OSError,))
        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise OSError("gecici")
            return "ok"

        self.assertEqual(flaky(), "ok")
        self.assertEqual(calls["n"], 3)

    def test_give_up_reraises_last(self):
        from pardus_paylasim.discovery.health import retry

        @retry(max_attempts=2, initial_delay=0.01, exceptions=(OSError,))
        def dead():
            raise OSError("kalici")

        with self.assertRaises(OSError):
            dead()

    def test_other_exceptions_not_caught(self):
        from pardus_paylasim.discovery.health import retry

        @retry(max_attempts=3, initial_delay=0.01, exceptions=(OSError,))
        def boom():
            raise ValueError("farkli")

        with self.assertRaises(ValueError):
            boom()

    def test_on_retry_called(self):
        from pardus_paylasim.discovery.health import retry
        seen = []

        @retry(max_attempts=2, initial_delay=0.01, exceptions=(OSError,),
               on_retry=lambda a, e, d: seen.append(a))
        def flaky():
            if not seen:
                raise OSError("x")
            return 1

        self.assertEqual(flaky(), 1)
        self.assertEqual(seen, [1])


class TestAnomalyDetector(unittest.TestCase):
    def test_spike_detected_after_baseline(self):
        from pardus_paylasim.discovery.health import AnomalyDetector
        # Not: 5'li pencerede tekil sıçrama |z|=2'yi geçemez (matematik);
        # eşik 1.5 ile ani çöküş yakalanır.
        det = AnomalyDetector(zscore_threshold=1.5, window_size=5)
        for _ in range(5):
            self.assertIsNone(det.ingest("transfer_Bps", 100.0))
        a = det.ingest("transfer_Bps", 100.0)
        a = det.ingest("transfer_Bps", 5.0)
        self.assertIsNotNone(a)
        self.assertIn(a.severity, ("low", "medium", "high", "critical"))

    def test_stable_series_quiet(self):
        from pardus_paylasim.discovery.health import AnomalyDetector
        det = AnomalyDetector(window_size=5)
        for _ in range(10):
            self.assertIsNone(det.ingest("transfer_Bps", 100.0))

    def test_baseline_excludes_current(self):
        from pardus_paylasim.discovery.health import AnomalyDetector
        det = AnomalyDetector(window_size=5)
        for _ in range(5):
            det.ingest("m", 100.0)
        mean, n = det.baseline_mean("m")
        self.assertEqual(mean, 100.0)
        self.assertEqual(n, 4)  # son örnek hariç
        det.ingest("m", 0.0)
        mean2, _ = det.baseline_mean("m")
        self.assertEqual(mean2, 100.0)  # güncel 0 ortalamayı çekmemeli


class TestTransferHealth(unittest.TestCase):
    def test_steady_no_warning(self):
        from pardus_paylasim.discovery.health import TransferHealth
        th = TransferHealth(window_size=5)
        for i in range(8):
            self.assertIsNone(th.check(100 * (i + 1), 100000, float(i + 1)))

    def test_slowdown_warns_once_then_recovers(self):
        from pardus_paylasim.discovery.health import TransferHealth
        th = TransferHealth(window_size=5)
        for i in range(6):
            th.check(100 * (i + 1), 100000, float(i + 1))
        w = th.check(640, 100000, 7.0)
        self.assertIsNotNone(w)
        self.assertIn("düştü", w)
        self.assertEqual(th.active_warning, w)
        # Aynı yavaşlıkta tekrar uyarı yok (tek seferlik).
        self.assertIsNone(th.check(680, 100000, 8.0))
        # Toparlanma bayrağı indirir.
        th.check(1780, 100000, 9.0)
        self.assertIsNone(th.active_warning)

    def test_stall_warns_and_clears_on_progress(self):
        from pardus_paylasim.discovery.health import TransferHealth
        th = TransferHealth(stall_after_s=5.0, window_size=5)
        th.check(100, 100000, 1.0)
        w = th.check(100, 100000, 7.0)
        self.assertIsNotNone(w)
        self.assertIn("duraksad", w)
        th.check(200, 100000, 8.0)
        self.assertIsNone(th.active_warning)

    def test_finished_transfer_quiet(self):
        from pardus_paylasim.discovery.health import TransferHealth
        th = TransferHealth(window_size=5)
        self.assertIsNone(th.check(100000, 100000, 10.0))
        self.assertIsNone(th.check(0, 0, 0.0))


if __name__ == "__main__":
    unittest.main()
