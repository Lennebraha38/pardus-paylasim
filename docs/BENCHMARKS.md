# Performans Ölçümleri (Benchmarks)

> Ölçüm ortamı: tek makine (loopback), Python 3.14, `tests/benchmarks.py`
> ile `time.perf_counter()` kullanılarak alınmıştır.
> Tekrar üretmek için: `python3 tests/benchmarks.py`
>
> Tarih: 2026-09-06 · Ham veriler: `docs/BENCH_RAW.txt`

## Gecikme (Latency) Tablosu

| Senaryo | p50 | p95 | Ortalama | İşlem/s |
|---------|-----|-----|----------|---------|
| Pano maskeleme — tipik metin (~150 karakter) | 0,028 ms | 0,037 ms | 0,029 ms | ~34.500 |
| Mesh parça paketleme (64 KB) | 0,003 ms | 0,003 ms | 0,003 ms | ~371.000 |
| Mesh parça açma + doğrulama (64 KB) | 0,003 ms | 0,004 ms | 0,003 ms | ~335.000 |
| SQLite kuyruğa yazma (WAL, kalıcı bağlantı) | 0,74 ms | 1,38 ms | 0,84 ms | ~1.200 |
| WebRTC kanal kuyruğuna yazma (30 KB) | 0,002 ms | 0,003 ms | 0,002 ms | ~479.000 |
| WebRTC 200 KB çerçeve uçtan uca (parçalı, loopback) | 19,4 ms | 23,8 ms | 18,6 ms | ~54 |

## Yorum

- **Pano maskeleme gerçek zamanlıdır:** tipik bir metin 0,03 ms altında
  taranıp maskelenir; kullanıcı yazarken bile hissedilmez.
- **Mesh ek yükü ihmal edilebilir:** 64 KB parçanın paketlenmesi
  3 µs sürer; darboğaz ağ hızıdır, protokol değildir.
- **SQLite optimizasyonu (v1.0):** her yazışta bağlantı açmak yerine
  tek kalıcı bağlantı + WAL modu kullanılıyor; kuyruk yazma
  **~37× hızlandı** (p50: 24,3 ms → 0,66 ms).

## Bilinen Sınırlar

- WebRTC data channel 64 KB üstü mesajları otomatik parçalar (v1.1);
  200 KB çerçeve loopback'te ~19 ms'de birleşir (~54 kare/s).
  Tek parça üst sınırı 64 KB, mesaj üst sınırı 16 MB'tır.
- Mesh transferinde parça başına SHA-256 doğrulanır; bu, CPU'da
  ~350.000 parça/s hızında çalışır ve pratikte ağı yavaşlatmaz.

## Rakip Karşılaştırması (Özellik Matrisi)

> Hız iddiaları yerine doğrulanabilir özellik farkları listelenmiştir.
> Ölçülen değerler yalnızca bu projeye aittir.

| Özellik | Pardus Paylaşım | KDE Connect | LocalSend | AnyDesk |
|---------|:---:|:---:|:---:|:---:|
| Açık kaynak | ✅ (GPL-3.0) | ✅ (GPL) | ✅ (MIT) | ❌ |
| Hesapsız yerel çalışma | ✅ | ✅ | ✅ | ❌ (ID/sunucu) |
| Uçtan uca şifreleme (AES-256-GCM) | ✅ | ✅ (TLS) | ✅ (TLS) | ✅ |
| Pano hassas veri maskeleme (TCKN/IBAN/kart/e-posta) | ✅ | ❌ | ❌ | ❌ |
| Metadata temizleme (EXIF/PDF/Office) | ✅ | ❌ | ❌ | ❌ |
| Mesh relay (dolaylı P2P) | ✅ | ❌ | ❌ | ❌ (sunucu) |
| Çevrimdışı kuyruk (asenkron transfer) | ✅ | ❌ | ❌ | ❌ |
| Türkçe arayüz | ✅ | ✅ | ✅ | ✅ |
| Pardus/DEB + Flatpak paketi | ✅ | ✅ | ✅ | ✅ |

**Fark:** Rakipler dosya paylaşımında güçlüdür; bu proje **gizlilik
katmanını** (maskeleme + temizleme + çevrimdışı kuyruk)
aynı çatı altında toplar.
