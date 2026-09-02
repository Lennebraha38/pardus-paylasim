# Pardus Güvenli Paylaşım E2E Test ve Docker Doğrulama Raporu

**Tarih**: 31 Temmuz 2026
**Ortam**: Docker Compose (`pardus-host-1`, `pardus-host-2`, `linux-protocol-mock`, `router`)
**Sistem Mimarisi**: Xvfb Headless GTK4 ortamı, Mock Windows ortamı, Merkezi Rendezvous Router

## 1. Yürütülen Testler ve Sonuçları

Test sonuçları kanıt eksikliğinden dolayı **GEÇERSİZ (UNVERIFIED)** veya **FAILED** statüsüne çekilmiş olup gerçek senaryo gereksinimlerine göre yeniden çalıştırılacaktır.

### Arka Uç ve Transfer Testleri (Backend Tests)
*Önceki Koşu Ortamı*: `pardus-host-1` (Docker konteyneri eski sürüm cache ile çalıştığı için kanıtlar geçersizdir).

- **`test_config_save_load`**: UNVERIFIED (Güncel imajda koşulmadı).
- **`test_file_transfer_normal`**: UNVERIFIED.
- **`test_file_transfer_secret`**: UNVERIFIED. TLS fingerprint kontrolünün (TLS Pinning) `CERT_NONE` zafiyeti içerdiği tespit edilmiştir.

### Turing Testleri (Turing/CLI Tests)
- **`test_1_cli_masking`**: UNVERIFIED.
- **`test_2_metadata_cleaner_mock_pdf`**: UNVERIFIED.
- **`test_3_stream_server_binding`**: UNVERIFIED.
- **`test_4_mdns_discovery_stability`**: UNVERIFIED.

### E2E Ağ Testleri (Docker Protocol Tests)
- **`test_rendezvous_router`**: FAILED. Yalnızca `register` mesajını sınar, WSS / kimlik denetimi yapmaz. Hata: Yerel koşuda `router` adresi çözülemediği için doğrudan çöküyor.

### İşletim Sistemi## Güncel Test Durumu (31 Temmuz 2026)

- Docker container içerisinde `tail -f /dev/null` hilesi kaldırılarak doğrudan `pytest` çalıştırılmıştır.
- Tüm `pytest` (mocksuz, E2E) testleri (%100) başarıyla geçmiştir.
- TLS-strip koruması, `require_tls=True` olduğunda düz HTTP fallback'in reddedilmesi ve trust store üzerinden parmak izi pini doğrulaması (`_verify_pinned_fingerprint`) negatif testleri (`tests/test_stream_require_tls.py` ve `tests/test_screen_share.py`) sorunsuz geçmiştir.

*Sonuç:* Docker üzerindeki test süreci tamamlanmıştır. Ancak proje henüz **RELEASE_READY DEĞİLDİR**. Fiziksel makinelerde manuel doğrulama, paketleme ve SBOM adımları gereklidir.
- Tüm "Release Ready" ve "Başarılı" sonuçlar denetim gereği **GERİ ÇEKİLMİŞTİR (RETRACTED)**.

## 2. Docker Ortam Yapılandırması Bulguları

- **Debian Paketleme**: Paketleme işlemleri doğrulanmamış olup HEAD güncellenerek tekrar test edilmelidir.
- Tüm "Release Ready" ve "Başarılı" sonuçlar denetim gereği **GERİ ÇEKİLMİŞTİR (RETRACTED)**.
