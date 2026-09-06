# Jüri Sunum Notu (1 sayfa)

## Ne işe yarar?

Pardus Paylaşım; yerel ağda **dosya transferi, ekran paylaşımı ve pano
senkronizasyonu** yapan, gizlilik odaklı bir masaüstü uygulamasıdır
(GTK4, Türkçe/İngilizce, CLI + GUI).

## Teknik olarak ne var?

- **Mesh ağı (8920):** 64 KB parçalı P2P transfer, 3 hop relay, parça
  başına SHA-256 doğrulama.
- **WebRTC data channel (8921):** sıralı, zlib sıkıştırmalı mesaj kanalı;
  SDP/ICE sinyali JSON ile.
- **Asenkron kuyruk (SQLite):** çevrimdışı cihaza gönderim, hash dedup,
  olay geçmişi; kalıcı bağlantı + WAL (~0,7 ms/yazma).
- **Güvenlik:** AES-256-GCM (PBKDF2 200K), fail-closed TLS 1.2+,
  fingerprint pinning, `secrets` ile PIN/jeton üretimi.
- **Pano maskeleme:** TCKN (Mod-10), IBAN (Mod-97), kredi kartı (Luhn),
  e-posta, telefon — kural tabanlı, cihazda çalışır.

## Bilinçli olarak ne çıkarıldı?

Deneysel **yerel yapay zeka modülü geri çekildi** (`CHANGELOG → Removed`).
Gerekçe: ONNX tarafı iskelet aşamasındaydı; doğrulanmamış bir iddiayı
üründe tutmak yerine klasik maskeleme + Mesh/WebRTC/Async'e
odaklanıldı. Arayüzdeki iddialı başlıklar da tarafsız adlarla
değiştirildi ("Yenilikler" → "Mesh Ağı").

## Kanıtlar

| İddia | Kanıt |
|-------|-------|
| Transfer çalışıyor | `tests/test_mesh_e2e.py` — 200 KB, gerçek TCP, PASS |
| Hızlı | `docs/BENCHMARKS.md` — maskeleme p50 0,028 ms, mesh 3 µs |
| Güvenli | `docs/SECURITY_AUDIT.md` — 2 bulgu düzeltildi |
| Testli | ~500 test, `tests/smoke_test.sh` 6/6 |
| Lisans uyumu | `docs/LICENSES.md` — GPL-3.0 ile çelişki yok |
| Sürdürülebilir | `docs/ROADMAP.md` — v1.1/v1.2/v2.0 |

## Bilinen sınırlar (saklanmıyor)

- WebRTC tek mesaj limiti 64 KB (v1.1: çerçeve parçalama).
- GUI ekran görüntüleri GTK4 iş istasyonunda alınmalı (bu rapor
  başsız ortam + Termux:X11 doğrulamasıyla üretildi).
- Kullanıcı anketi formu hazır (`docs/KULLANICI_ANKETI.md`),
  5 kullanıcıyla uygulama bekliyor.
