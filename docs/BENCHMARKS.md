# Performans Ölçümleri (Benchmarks)

> Ölçüm ortamı: tek makine (loopback), Python 3.14, `tests/benchmarks.py`
> ile `time.perf_counter()` kullanılarak alınmıştır.
> Tekrar üretmek için: `python3 tests/benchmarks.py`
>
> Tarih: 2026-09-06 · Ham veriler: `docs/BENCH_RAW.txt`

## Gecikme (Latency) Tablosu

| Senaryo | p50 | p95 | Ortalama | İşlem/s |
|---------|-----|-----|----------|---------|
| AI tespiti — kısa metin (~200 karakter) | 0,038 ms | 0,057 ms | 0,043 ms | ~23.000 |
| AI tespiti — uzun rapor (~10 KB) | 1,48 ms | 2,01 ms | 1,54 ms | ~650 |
| AI tespiti — temiz metin (negatif vaka) | 0,016 ms | 0,016 ms | 0,016 ms | ~62.000 |
| AI maskeleme (mask_with_ai) | 0,041 ms | 0,042 ms | 0,042 ms | ~24.000 |
| Mesh parça paketleme (64 KB) | 0,003 ms | 0,003 ms | 0,003 ms | ~364.000 |
| Mesh parça açma + doğrulama (64 KB) | 0,003 ms | 0,003 ms | 0,003 ms | ~349.000 |
| SQLite kuyruğa yazma (WAL, kalıcı bağlantı) | 0,66 ms | 1,50 ms | 0,79 ms | ~1.270 |
| WebRTC kanal kuyruğuna yazma (30 KB) | 0,001 ms | 0,002 ms | 0,003 ms | ~365.000 |

## Yorum

- **Pano senkronizasyonu gerçek zamanlıdır:** tipik bir pano metni
  0,05 ms altında taranır; kullanıcı yazarken bile hissedilmez.
- **Mesh ek yükü ihmal edilebilir:** 64 KB parçanın paketlenmesi
  3 µs sürer; darboğaz ağ hızıdır, protokol değildir.
- **SQLite optimizasyonu (v1.0):** her yazışta bağlantı açmak yerine
  tek kalıcı bağlantı + WAL modu kullanılıyor; kuyruk yazma
  **~37× hızlandı** (p50: 24,3 ms → 0,66 ms).

## Bilinen Sınırlar

- WebRTC data channel tek mesaj limiti **64 KB**'tır; daha büyük
  ekran kareleri gönderilmeden önce parçalanmalıdır (yol haritası: v1.1).
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
| Çevrimdışı hassas veri tespiti (yerel AI) | ✅ | ❌ | ❌ | ❌ |
| Metadata temizleme (EXIF/PDF/Office) | ✅ | ❌ | ❌ | ❌ |
| Mesh relay (dolaylı P2P) | ✅ | ❌ | ❌ | ❌ (sunucu) |
| Çevrimdışı kuyruk (asenkron transfer) | ✅ | ❌ | ❌ | ❌ |
| Türkçe arayüz | ✅ | ✅ | ✅ | ✅ |
| Pardus/DEB + Flatpak paketi | ✅ | ✅ | ✅ | ✅ |

**Fark:** Rakipler dosya paylaşımında güçlüdür; bu proje **gizlilik
katmanını** (tespit + maskeleme + temizleme + çevrimdışı kuyruk)
aynı çatı altında toplar.
