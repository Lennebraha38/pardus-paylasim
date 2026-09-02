# FAZ 3 - Taşıma Katmanını Birleştir (Doğrulama Raporu)

## 1. Uygulanan Değişiklikler

### Session-aware Endpoint Modeli (Faz 3.1)
- Tüm uç noktalar `stream_server.py` içerisindeki HTTP sunucusunda tek çatı altında (TLS) toplandı.
- Eski API yolları `/api/v1/files/list`, `/api/v1/files/download`, `/api/v1/files/upload` olarak güncellendi ve versiyonlama altyapısı sağlandı.
- Ön uç (`viewer.js`), `upload` mekanizmasında `/api/v1/files/upload` yolunu kullanacak şekilde güncellendi.
- Tüm uç noktalar (`/stream`, `/control`, `/api/v1/...`) her istekte `_check_auth()` ile capability (Session) kontrolü yapıyor.

### Raw TCP Kanalları Deprecation (Faz 3.2)
- Eski raw TCP soket mekanizması (transfer.py 8900 portu) ileride kaldırılmak veya Legacy duruma çekilmek üzere yapılandırılmaya başlandı. Artık tüm yeni geliştirmeler HTTP `upload` ve WebSocket `control` akışlarına odaklanmıştır. (Windows native istemcisi de `HTTPS POST` ile dosya yükleyebilir).

### Dosya Upload Güvenliği (Faz 3.3)
- **Streaming & Sabit Bellek**: `rfile.read(content_len)` iptal edildi. `rfile.read(chunk_size)` (64KB chunk'lar) döngüsü kurularak bellek kısıtlı cihazların çökmesi engellendi (Resource Exhaustion önlemi).
- **Gerçek Byte ve Content-Length Kontrolü**: İndirilen byte miktarı sayılıyor ve eğer Header'daki `Content-Length` değeri ile eşleşmezse dosya reddedilip (Fail-Closed) `ValueError` fırlatılıyor.
- **Atomik Dosya Kaydı ve Bütünlük (SHA-256)**: 
  1. Dosya önce geçici (`tempfile.mkstemp`) olarak diske yazılır.
  2. Eş zamanlı olarak aktarım anında `hashlib.sha256` ile özet (hash) hesaplanır.
  3. Kayıt bittiğinde bellek tamponu diske indirilir (`fsync`).
  4. Yeni isim `os.rename()` ile atomik olarak asıl konuma taşınır.
- **Overwrite Engellendi**: Rastgele `UUID` destekli depolama kimlikleri kullanılarak isimlendirme yapıldı ve üzerine yazma kontrolü güçlendirildi.
- **Kota**: 1 GB limit kaldırılarak varsayılan limit 100 MB olarak yapılandırıldı.
- İptal / Bağlantı kopması anında `try/except` bloğunda geçici dosyalar (`os.unlink()`) otomatik temizlenmektedir.

## 2. Gate (Geçit) Kontrolleri

| Kriter | Durum | Açıklama |
|---|---|---|
| **Eski güvensiz socket'ler mDNS'te listelenmiyor** | KISMİ | (Faz 3.2 Kısmi - `transfer.py` hala kod içinde ancak web istemcisi tamamen yeni endpoint'leri kullanıyor). |
| **Büyük dosya stream testleri (OOM olmadan) yeşil** | BLOKE (pytest yok) | Chunking 64KB sabit limitle kodlandı, OOM engellendi. |
| **Yarım/kopuk transferler çöp bırakmıyor (cleanup)** | BLOKE (pytest yok) | `Exception` bloğunda `os.unlink(temp_path)` eklendi. |
| **Path traversal imkânsız (chroot/strict join)** | GEÇTİ | Hem list, hem download hem de upload (sadece `basename` kullanarak) katı izolasyon sağlıyor. |
| **Tüm endpoint'ler unified token mekanizmasında** | GEÇTİ | `/api/v1/files/*` işlemleri `X-Pardus-Session` veya Çerez kullanır. |

**UYARI:** Ortamda `pytest` ve `ruff` bulunmadığından test doğrulaması kod statik analiz/manuel inceleme varsayımlarına dayanmaktadır. Müşterinin "Kusursuz çalıştığına dair varsayımlarınızı kaldırın, fail-closed uygulayın" direktifi uyarınca kodların her parçasında strict try-except kullanılmıştır.
