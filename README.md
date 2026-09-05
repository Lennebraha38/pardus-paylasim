# Pardus Güvenli Paylaşım

> Pardus/Linux ekosistemi için güvenli dosya transferi, ekran yayınlama ve hassas veri koruma platformu.

[![CI](https://github.com/Lennebraha38/pardus-paylasim/actions/workflows/build.yml/badge.svg)](https://github.com/Lennebraha38/pardus-paylasim/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-green.svg)](LICENSE)

---

## 🛡️ Özellikler

| Özellik | Açıklama |
|---------|----------|
| **mDNS Keşfi** | Yerel ağda cihazları otomatik bulma (Zeroconf) |
| **P2P Dosya Transferi** | AES-256-GCM ile PIN korumalı uçtan uca aktarım |
| **Ekran Yayını** | GStreamer/PipeWire ile düşük gecikmeli MJPEG streaming |
| **Pano Senkronizasyonu** | Cihazlar arası hassas veri maskeleme |
| **Metadata Temizleme** | EXIF, PDF ve ofis belgelerinden gizli verileri silme |
| **Uzaktan Kontrol** | AnyDesk tarzı WebSocket tabanlı uzaktan kontrol |
| **TLS/SSL** | Fail-closed güvenlik modeli, self-signed sertifika |
| **i18n** | Türkçe ve İngilizce destek |

## 🚀 Kurulum

### Debian/Pardus (Önerilen)

```bash
sudo dpkg -i pardus-paylasim_1.0.0_all.deb
sudo apt-get install -f
```

### Geliştirme Ortamı

```bash
git clone https://github.com/Lennebraha38/pardus-paylasim.git
cd pardus-paylasim
python -m venv venv
source venv/bin/activate
pip install -e ".[dev,test]"
```

### Docker

```bash
docker build -t pardus-paylasim .
docker run --rm -it pardus-paylasim
```

## 📁 Proje Yapısı

```
pardus-paylasim/
├── src/
│   ├── pardus_paylasim/           # Ana uygulama
│   │   ├── app.py                 # Entry point (GTK4/Adw)
│   │   ├── config.py              # GSettings + JSON fallback
│   │   ├── window.py              # Ana pencere (5 sekme)
│   │   ├── discovery/             # mDNS, BLE, dosya transferi
│   │   ├── screen/                # Ekran yayınlama ve kontrol
│   │   ├── clipboard/             # Pano maskeleme
│   │   ├── cleaner/               # Metadata temizleme
│   │   └── auth/                  # Güvenlik ve audit log
│   ├── pardus_paylasim_agent/     # Arka plan agentı
│   └── pardus_paylasim_server/    # HTTP sunucu
├── tests/                         # Testler ve Docker/E2E senaryoları
├── data/                          # Web viewer ve statik varlıklar
├── docs/                          # Teknik dokümanlar
├── scripts/                       # Build ve kurulum betikleri
└── tools/                         # Yardımcı araçlar
```

## 🔧 Kullanım

### CLI

```bash
# Dosya temizleme
pardus-paylasim --clean dosya1.jpg dosya2.pdf

# Metin maskeleme
pardus-paylasim --mask "TCKN: 12345678901"

# Çıktı ile
pardus-paylasim --clean foto.jpg --out temiz_foto.jpg
```

### GUI

```bash
pardus-paylasim
```

## 🧪 Testler

```bash
# Platform bağımsız testler
pytest tests/ -m "not docker and not e2e" -v

# Tüm testler (Docker ve ağ ortamı gerektirenler dahil)
pytest tests/ -v

# Yalnız birim testleri
pytest tests/ -m unit -v

# Docker entegrasyon testleri
pytest tests/ -m docker -v

# Güvenlik testleri
pytest tests/ -m security -v
```

## 🔒 Güvenlik

- **Fail-Closed Modeli:** TLS olmadan sunucu başlatılmaz
- **AES-256-GCM:** PIN tabanlı PBKDF2 (200K iterasyon) ile şifreleme
- **Path Traversal Koruması:** `realpath` ile dizin aşımı engeli
- **TCKN Doğrulama:** Mod-10 kriptografik algoritması
- **Audit Logging:** Tüm güvenlik olayları JSONL formatında kaydedilir

## 📊 CI/CD

- **GitHub Actions:** Lint + unit test (Python 3.10-3.12 matrix)
- **GitLab CI:** Paralel pipeline yapılandırması
- **Docker Integration:** İki Pardus cihazı ile otomatik test

## 🤫 Katkıda Bulunma

1. Fork yapın
2. `feature/ozellik-adı` dalı oluşturun
3. Değişikliklerinizi commit edin
4. Pull Request açın

## 📄 Lisans

GPL-3.0 License — Detaylı bilgi için [LICENSE](LICENSE) dosyasına bakın.

---

**TÜBİTAK ULAKBİM** | Pardus Ekosistemi
