"""
Transfer ilerleme yardımcıları: hız + ETA + insan-okur biçimleme.

Saf (yan-etkisiz) fonksiyonlar; GTK/soket bağımlılığı yok. Böylece headless
pytest ortamında da koşar. Gönderim/alım döngüleri aktarılan bayt + geçen
süreyi buraya verir, UI katmanı dönen değerleri gösterir.
"""

from typing import NamedTuple


class TransferStats(NamedTuple):
    """Bir aktarım anının anlık istatistikleri.

    Attributes:
        rate_bps: Anlık hız (bayt/saniye). Süre 0 ise 0.0.
        eta_seconds: Kalan tahmini süre (saniye). Hesaplanamıyorsa None.
        percent: Tamamlanma oranı, 0.0–1.0 arası.
    """

    rate_bps: float
    eta_seconds: "float | None"
    percent: float


def compute_stats(
    transferred: int,
    total: int,
    elapsed: float,
) -> TransferStats:
    """Aktarılan bayt + geçen süreden hız, ETA ve oran hesaplar.

    Args:
        transferred: Şu ana dek aktarılan bayt sayısı.
        total: Toplam bayt sayısı (0 ise oran/ETA belirsiz).
        elapsed: Aktarım başından bu yana geçen süre (saniye).

    Returns:
        TransferStats. Negatif/tutarsız girdiler güvenli değerlere kırpılır;
        istisna atmaz (UI döngüsünde çağrılır, gürültü istemez).
    """
    # Girdi temizliği: negatif değerler mantıksız, 0'a çek.
    transferred = max(0, transferred)
    total = max(0, total)
    elapsed = max(0.0, elapsed)

    # Oran: total yoksa (bilinmeyen boyut) 0 kabul; aşımı 1.0'a kırp.
    if total > 0:
        percent = min(1.0, transferred / total)
    else:
        percent = 0.0

    # Hız: süre henüz 0 ise anlamlı hız yok.
    rate_bps = transferred / elapsed if elapsed > 0 else 0.0

    # ETA: kalan baytı anlık hıza böl. Hız 0 veya boyut bilinmiyorsa None.
    eta_seconds: "float | None"
    if total > 0 and rate_bps > 0:
        remaining = max(0, total - transferred)
        eta_seconds = remaining / rate_bps
    else:
        eta_seconds = None

    return TransferStats(rate_bps=rate_bps, eta_seconds=eta_seconds, percent=percent)


def human_size(num_bytes: float) -> str:
    """Bayt sayısını insan-okur birime çevirir (ör. '4.2 MB').

    İkili (1024) taban kullanır; Pardus/GNOME dosya yöneticileriyle tutarlı
    büyüklük hissi verir.
    """
    num_bytes = max(0.0, float(num_bytes))
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    idx = 0
    while num_bytes >= 1024.0 and idx < len(units) - 1:
        num_bytes /= 1024.0
        idx += 1
    # Bayt için ondalık gereksiz; üst birimlerde tek ondalık hane yeter.
    if idx == 0:
        return f"{int(num_bytes)} {units[idx]}"
    return f"{num_bytes:.1f} {units[idx]}"


def human_rate(rate_bps: float) -> str:
    """Hızı insan-okur biçime çevirir (ör. '4.2 MB/s')."""
    return f"{human_size(rate_bps)}/s"


def human_eta(eta_seconds: "float | None") -> str:
    """Kalan süreyi kısa biçime çevirir (ör. '~1 dk 5 sn', '~12 sn').

    None ise '—' döner (hesaplanamadı). i18n: çağıran taraf gerekirse _() ile
    sarabilir; burada birim ekleri sabit (sn/dk/sa) tutulur.
    """
    if eta_seconds is None:
        return "—"
    total = int(max(0, round(eta_seconds)))
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours > 0:
        return f"~{hours} sa {minutes} dk"
    if minutes > 0:
        return f"~{minutes} dk {seconds} sn"
    return f"~{seconds} sn"


def format_progress_line(stats: TransferStats) -> str:
    """UI altyazısı için tek-satır özet üretir.

    Örn: '%42 · 4.2 MB/s · ~12 sn'. Saf metin; GLib.idle_add ile bir
    Gtk.Label'a verilebilir.
    """
    pct = int(round(stats.percent * 100))
    return f"%{pct} · {human_rate(stats.rate_bps)} · {human_eta(stats.eta_seconds)}"
