# Bağımlılık Lisans Raporu

> Proje lisansı: **GPL-3.0-only** (`pyproject.toml`).
> Aşağıdaki tablo doğrudan bağımlılıkların bilinen lisanslarını listeler.
> Doğrulama: CI'a `pip-licenses --fail-on="GPL"` dışı denetim eklenmesi
> önerilir (çevrimdışı ortamda çalıştırılamadı; tablo paketlerin
> resmi PyPI/bildirim kayıtlarına göre hazırlanmıştır).

## Doğrudan Bağımlılıklar

| Paket | Kullanım | Lisans | GPL-3.0 ile Uyum |
|-------|----------|--------|:---:|
| `cryptography` | AES-GCM, PBKDF2, TLS | Apache-2.0 / BSD (çift) | ✅ |
| `PyGObject` | GTK4/Adw arayüzü | LGPL-2.1+ | ✅ |
| `zeroconf` | mDNS cihaz keşfi | LGPL-2.1 | ✅ |
| `pynput` | Uzaktan kontrol girişi | LGPL-3.0 | ✅ |
| `qrcode` | Eşleştirme QR kodu | BSD-3-Clause | ✅ |
| `websockets` | Sinyalizasyon sunucusu | BSD-3-Clause | ✅ |
| `aiortc` | WebRTC deneyleri | BSD-3-Clause | ✅ |
| `aiohttp` | HTTP sunucu | Apache-2.0 | ✅ |
| `pillow` | Ekran karesi işleme | HPND (PIL Lisansı) | ✅ |
| `numpy` | Görüntü dizileri | BSD-3-Clause | ✅ |
| `pytest`, `pytest-cov` | Test | MIT | ✅ (test) |
| `pytest-asyncio` | Test | Apache-2.0 | ✅ (test) |
| `ruff`, `mypy`, `pre-commit` | Geliştirme | MIT | ✅ (dev) |

## Sonuç

- Çalışma zamanı bağımlılıklarında **GPL ile çelişen lisans yoktur.**
- LGPL kütüphaneler dinamik bağlıdır (Python import); GPL-3.0 ile uyumludur.
- Test/geliştirme bağımlılıkları dağıtım paketine girmez.
- Öneri: `debian/copyright` dosyasına bu tablo işlenmelidir.
