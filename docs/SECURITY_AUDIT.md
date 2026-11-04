# Güvenlik Denetim Raporu

> Yöntem: AST/regex tabanlı statik tarama + Ruff Bandit (S) analizi.
> Tarih: 2026-11-04 · Sürüm: 1.1.0 · Kapsam: `src/` ve `tests/` altındaki tüm Python dosyaları.
> Maintainer: Lennebraha38 <farukhilmi12345@gmail.com>

## Tarama Sonuçları

| Kontrol | Sonuç | Durum |
|---------|-------|-------|
| `pickle.loads` / `eval` / `exec` | 0 bulgu | ✅ Temiz |
| `shell=True` | 0 bulgu | ✅ Temiz |
| Hardcoded parola/API anahtarı | 0 bulgu | ✅ Temiz |
| Güvensiz `yaml.load` / `mktemp` | 0 bulgu | ✅ Temiz |
| `random` ile güvenlik değeri üretimi | 0 bulgu | ✅ `secrets` kullanıldı |
| SHA-1 kullanımı | 1 bulgu → standart gereği | ✅ RFC6455 zorunluluğu |
| `CERT_NONE` / `verify=False` | 0 istismar edilebilir bulgu | ✅ Fail-closed ve TOFU pinning |
| Ruff Bandit (S) Kural İhlalleri | 0 hata | ✅ Tamamen Temiz |

## Güvenlik ve Mimari İyileştirmeleri (v1.1.0)

1. **Birleşik Güven Deposu ve Parmak İzi Doğrulama:**
   `auth/trust_store.py` ile `screen/trust_store.py` standart `fcntl.flock` mekanizmasıyla senkronize edildi; `0o700` dizin ve `0o600` dosya izinleriyle korundu.
2. **Fail-Closed Dosya Kabul ve Dizin Aşımı Engeli:**
   Dosya alımında onay verilmedikçe hiçbir dosya diske yazılmaz (`FileReceiverServer`). Tüm dosya isimleri `realpath` sınırlandırmasından geçer.
3. **Web-Viewer ve CSP Uyumluluğu:**
   Web izleyicide inline script ve style'lar kaldırıldı; Content-Security-Policy (CSP) başlığına tam uyum sağlandı. Dış STUN bağımlılıkları temizlendi.
4. **RFC 5987 UTF-8 Dosya Adı Desteği:**
   `fs_server.py` dosya indirmelerinde Türkçe/UTF-8 karakterleri RFC 5987 standardına uygun olarak kodlar; HTTP başlık çökmeleri önlenmiştir.
5. **DLP ve Hassas Veri Maskeleme:**
   `SensitiveMasker` modülünde TCKN (Mod-10), Kredi Kartı (Luhn standardı), IBAN (Mod-97) ve API anahtarları regex + sağlama algoritmalarıyla maskelenir.
