# Güvenlik Denetim Raporu

> Yöntem: AST/regex tabanlı statik tarama (bandit/safety çevrimdışı
> ortamda kurulamadığı için eşdeğer kontroller manuel uygulandı).
> Tarih: 2026-09-06 · Kapsam: `src/` altındaki tüm Python dosyaları.

## Tarama Sonuçları

| Kontrol | Sonuç | Durum |
|---------|-------|-------|
| `pickle.loads` / `eval` / `exec` | 0 bulgu | ✅ Temiz |
| `shell=True` | 0 bulgu | ✅ Temiz |
| Hardcoded parola/API anahtarı | 0 bulgu | ✅ Temiz |
| Güvensiz `yaml.load` / `mktemp` | 0 bulgu | ✅ Temiz |
| `random` ile güvenlik değeri üretimi | 2 bulgu → **düzeltildi** | ✅ `secrets` kullanıldı |
| SHA-1 kullanımı | 1 bulgu → yanlış alarm | ✅ RFC6455 zorunluluğu |
| `CERT_NONE` / `verify=False` | 5 bulgu → 4 yanlış alarm, 1 kabul | ⚠️ Açıklama aşağıda |

## Düzeltilen Bulgular

1. **`window.py` — transfer PIN'i `random.randint` ile üretiliyordu.**
   Mersenne Twister tahmin edilebilir olduğu için
   `secrets.randbelow(900000) + 100000` olarak değiştirildi.
2. **`pardus_paylasim_server/router.py` — cihaz kimliği `random`
   ile üretiliyordu.** `secrets.randbelow` olarak değiştirildi.

## Yanlış Alarm Gerekçeleri

- **`control_server.py:91` SHA-1:** WebSocket el sıkışması
  (`Sec-WebSocket-Accept`) RFC6455 §4.2.2 gereğidir; güvenlik
  amaçlı hash değildir.
- **`tls_util.py` istemci bağlamı:** `CERT_REQUIRED` + SHA-256
  fingerprint pinning + `minimum_version = TLSv1_2`. `check_hostname =
  False` yalnızca self-signed/TOFU modelinde pinning'e bırakıldığı
  için kapalıdır; kimlik pinning ile doğrulanır.
- **`tls_util.py` probe bağlamı (`CERT_NONE`):** Yalnızca karşı tarafın
  sertifika parmak izini okumak için açılan geçici bağlantıdır; veri
  taşınmaz, pinning kararı bu iz üzerinden verilir.
- **`router.py` sunucu bağlamı:** Sunucu soketinde istemci sertifikası
  istememek (`CERT_NONE` varsayılanı) normaldir; istemci kimliği
  PIN + oturum token ile sağlanır.

## Güvenlik Mimarisi Özeti

- **Fail-closed TLS:** Sertifika doğrulanamazsa bağlantı kurulmaz.
- **AES-256-GCM:** PIN → PBKDF2 (200.000 iterasyon) ile anahtar türetme.
- **Parça bütünlüğü:** Mesh transferinde her 64 KB parça SHA-256 ile.
- **Oturum token'ları:** `secrets.token_urlsafe`, süre sonu (TTL) ve
  mesaj başına doğrulama (`secrets.compare_digest`).
- **Path traversal koruması:** `realpath` ile dizin aşımı engeli.
- **Yerel AI:** Hassas veri cihazdan çıkmaz; buluta aktarım yok.
- **Audit log:** Güvenlik olayları JSONL olarak kaydedilir.
