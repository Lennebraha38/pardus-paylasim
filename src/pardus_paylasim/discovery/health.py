"""Aktarım sağlığı: anomali tespiti + yeniden deneme.

`Anomaly`/`AnomalyDetector`, pardus-neural-system `brain/anomaly_detector.py`
dosyasından taşınmıştır (yalnız stdlib; Z-skor + eşik + trend). `retry`
dekoratörü neural-system `core/retry.py` karşılığıdır (yerleşik logging).

`TransferHealth`, hız serisini detektöre besleyip yavaşlama/duraksama
uyarısı üretir; pencere ve CLI'daki hız satırına eklenir.
"""

import functools
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)


@dataclass
class Anomaly:
    anomaly_id: str
    source_node: str
    metric: str
    value: float
    expected_range: tuple
    severity: str  # low, medium, high, critical
    timestamp: float = 0.0
    description: str = ""
    recommended_action: str = ""

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "anomaly_id": self.anomaly_id,
            "source_node": self.source_node,
            "metric": self.metric,
            "value": self.value,
            "expected_range": self.expected_range,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "description": self.description,
            "recommended_action": self.recommended_action,
        }


class AnomalyDetector:
    """Z-skor + eşik + trend ile anomali tespiti (neural-system portu)."""

    def __init__(self, zscore_threshold: float = 3.0, window_size: int = 60,
                 history_size: int = 1000):
        self.zscore_threshold = zscore_threshold
        self.window_size = window_size
        self.history_size = history_size
        self._history: dict = {}
        self._anomalies: list = []
        self.thresholds = {
            "cpu_percent": (0, 90),
            "memory_percent": (0, 85),
            "disk_percent": (0, 90),
            "temperature": (0, 80),
            "ping_ms": (0, 100),
            "load_1min": (0, 4.0),
        }
        self._seq = 0

    def ingest(self, metric: str, value: float, node_id: str = "local"):
        if metric not in self._history:
            self._history[metric] = deque(maxlen=self.history_size)
        self._history[metric].append({
            "value": value, "node_id": node_id, "timestamp": time.time(),
        })
        if len(self._history[metric]) >= self.window_size:
            return self._check_anomaly(metric, value, node_id)
        return None

    def _check_anomaly(self, metric, value, node_id):
        history = list(self._history[metric])
        recent = [h["value"] for h in history[-self.window_size:]]
        zscore = self._calculate_zscore(value, recent)
        in_range = self._check_thresholds(metric, value)
        if abs(zscore) > self.zscore_threshold or not in_range:
            severity = self._calculate_severity(zscore, metric, value)
            anomaly = self._create_anomaly(metric, value, node_id, zscore, severity)
            self._anomalies.append(anomaly)
            return anomaly
        return None

    def _calculate_zscore(self, value, data) -> float:
        if len(data) < 2:
            return 0.0
        mean = sum(data) / len(data)
        variance = sum((x - mean) ** 2 for x in data) / len(data)
        std_dev = math.sqrt(variance)
        if std_dev == 0:
            return 0.0
        return (value - mean) / std_dev

    def _check_thresholds(self, metric, value) -> bool:
        if metric in self.thresholds:
            min_val, max_val = self.thresholds[metric]
            return min_val <= value <= max_val
        return True

    def _calculate_severity(self, zscore, metric, value) -> str:
        abs_zscore = abs(zscore)
        if abs_zscore > 5 or value > 95:
            return "critical"
        elif abs_zscore > 4 or value > 90:
            return "high"
        elif abs_zscore > 3 or value > 85:
            return "medium"
        else:
            return "low"

    def _create_anomaly(self, metric, value, node_id, zscore, severity):
        import uuid

        history = [h["value"] for h in self._history[metric]]
        mean = sum(history) / len(history)
        var = sum((x - mean) ** 2 for x in history) / len(history)
        std_dev = math.sqrt(var)
        return Anomaly(
            anomaly_id=str(uuid.uuid4()),
            source_node=node_id,
            metric=metric,
            value=value,
            expected_range=(max(0, mean - 2 * std_dev), mean + 2 * std_dev),
            severity=severity,
            description=f"{metric} normalin dışında: {value}",
            recommended_action="Durumu manuel kontrol et",
        )

    def get_recent_anomalies(self, limit: int = 10) -> list:
        return [a.to_dict() for a in self._anomalies[-limit:]]

    def baseline_mean(self, metric: str) -> tuple:
        """(ortalama, örnek_sayısı): son örnek HARİÇ tarihçe ortalaması.

        TransferHealth, o anki hızı geçmişe karşılar; güncel değer
        ortalamayı aşağı çekmesin diye hariç tutulur.
        """
        hist = list(self._history.get(metric, []))
        if len(hist) < 2:
            return 0.0, 0
        base = [h["value"] for h in hist[:-1]]
        return sum(base) / len(base), len(base)


def retry(max_attempts: int = 3, initial_delay: float = 0.2,
          backoff_factor: float = 2.0, max_delay: float = 5.0,
          exceptions: Tuple[Type[Exception], ...] = (OSError,),
          on_retry: Optional[Callable] = None):
    """Üstel geri çekilmeli yeniden deneme (neural-system core/retry karşılığı).

    Varsayılanlar LAN için tutumlu tutuldu: en fazla ~0.6 sn ekler.
    Kalıcı hatalarda (reddedilen port) hızlı vazgeçilir.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts:
                        if on_retry:
                            try:
                                on_retry(attempt, e, delay)
                            except Exception:
                                pass
                        logger.debug("%s deneme %d/%d başarısız: %s",
                                     func.__name__, attempt, max_attempts, e)
                        time.sleep(delay)
                        delay = min(delay * backoff_factor, max_delay)
            raise last_exc
        return wrapper
    return decorator


class TransferHealth:
    """Aktarım hızı izleyici: yavaşlama + duraksama uyarısı üretir.

    Her `stats_callback` çağrısında `check(sent, total, elapsed)` çağrılır;
    uyarı metni ya da None döner. Durum bilgisizdir (yan etkisiz) dışında
    son örnek ve uyarı bayrakları.
    """

    METRIC = "transfer_Bps"

    def __init__(self, stall_after_s: float = 5.0, window_size: int = 10):
        self.detector = AnomalyDetector(
            zscore_threshold=3.0, window_size=window_size, history_size=200,
        )
        self._stall_after = stall_after_s
        self._last_sent = 0
        self._last_elapsed = 0.0
        self._last_progress_t = None
        self._stall_warned = False
        self._slow_warned = False
        # O an görünen uyarı (toparlanınca None). UI satıra ekler.
        self.active_warning: Optional[str] = None

    def check(self, sent: int, total: int, elapsed: float) -> Optional[str]:
        if total <= 0 or sent >= total:
            return None
        dt = elapsed - self._last_elapsed
        if dt <= 0:
            return None
        gained = sent - self._last_sent
        self._last_sent, self._last_elapsed = sent, elapsed
        if gained > 0:
            self._last_progress_t = elapsed
            self._stall_warned = False
            if self.active_warning and "duraksad" in self.active_warning:
                self.active_warning = None
        bps = gained / dt
        self.detector.ingest(self.METRIC, bps)
        baseline, n_base = self.detector.baseline_mean(self.METRIC)
        # Yavaşlama: hız, geçmiş ortalamanın yarısının altına düştüyse.
        if (n_base >= 5 and baseline > 0 and not self._slow_warned
                and bps < 0.5 * baseline):
            self._slow_warned = True
            self.active_warning = "⚠️ hız olağandışı düştü"
            return self.active_warning
        if self._slow_warned and bps >= 0.8 * baseline:
            self._slow_warned = False
            self.active_warning = None
        if (self._last_progress_t is not None
                and not self._stall_warned
                and elapsed - self._last_progress_t >= self._stall_after):
            self._stall_warned = True
            self.active_warning = "⚠️ aktarım duraksadı"
            return self.active_warning
        return None
