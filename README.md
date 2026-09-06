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
| **Mesh Ağı** | Parça-parça (64KB) P2P transfer, 3 hop'a kadar relay, SHA-256 parça doğrulama |
| **WebRTC Data Channel** | SCTP benzeri güvenilir kanal, zlib sıkıştırma, sıralı mesaj |
| **Asenkron Transfer** 🆕 | Çevrimdışı cihazlara kuyruk, hash dedup, SQLite tabanlı geçmiş |
| **Ekran Yayını** | GStreamer/PipeWire ile düşük gecikmeli MJPEG streaming |
| **Pano Senkronizasyonu** | Cihazlar arası hassas veri maskeleme |
| **Metadata Temizleme** | EXIF, PDF ve ofis belgelerinden gizli verileri silme |
| **Uzaktan Kontrol** | AnyDesk tarzı WebSocket tabanlı uzaktan kontrol |
| **TLS/SSL** | Fail-closed güvenlik modeli, self-signed sertifika |
| **i18n** | Türkçe ve İngilizce destek |

## 🏗️ Mimari

```
┌─────────────────────────────────────────────────────────┐
│                    GTK4/Adw GUI (6 sekme)               │
│  Gizlilik │ Keşif │ Ekran │ Pano │ Ayarlar │ 🌐Mesh Ağı │
└──────┬──────────┬──────────┬──────────┬─────────┬────────┘
       │          │          │          │         │
┌──────▼──┐ ┌─────▼────┐ ┌───▼────┐ ┌───▼────┐ ┌──▼──────────────┐
│ Cleaner │ │Discovery │ │ Screen │ │Clipbrd │ │ Mesh Ağı       │
│ EXIF/PDF│ │ mDNS     │ │ MJPEG  │ │Masker  │ │ • Mesh (8920)  │
│ Office  │ │ P2P:8900 │ │ :52345 │ │:8901   │ │ • WebRTC(8921) │
│         │ │ Mesh     │ │ WebRTC │ │        │ │ • Async(SQLite)│
│         │ │ Async    │ │ :8921  │ │        │ │                │
└─────────┴─┴──────────┴─┴────────┴─┴────────┴─┴───────────────┘
       │          │          │          │
       └──────────┴──────────┴──────────┘
                  TLS (fail-closed)
              AES-256-GCM + PBKDF2/200K
```

**Portlar:** Dosya `8900` · Pano `8901` · Mesh `8920` · WebRTC `8921` · Ekran `52345`

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
docker build -f Containerfile -t pardus-paylasim .
docker run --rm -it pardus-paylasim
```

### Flatpak

```bash
flatpak-builder --user --install build-dir flatpak/tr.org.pardus.paylasim.yml
flatpak run tr.org.pardus.paylasim
```

## 📁 Proje Yapısı

```
pardus-paylasim/
├── src/
│   ├── pardus_paylasim/           # Ana uygulama
│   │   ├── app.py                 # Entry point (GTK4/Adw + CLI)
│   │   ├── config.py              # GSettings + JSON fallback
│   │   ├── window.py              # Ana pencere (6 sekme)
│   │   ├── discovery/             # mDNS, dosya transferi
│   │   │   ├── mesh/              # 🆕 P2P mesh ağı (8920)
│   │   │   └── async_transfer/    # 🆕 Çevrimdışı kuyruk (SQLite)
│   │   ├── screen/                # Ekran yayınlama ve kontrol
│   │   │   └── webrtc/            # 🆕 Data channel (8921)
│   │   ├── clipboard/             # Pano maskeleme
│   │   ├── cleaner/               # Metadata temizleme
│   │   └── auth/                  # Güvenlik ve audit log
│   ├── pardus_paylasim_agent/     # Arka plan agentı
│   └── pardus_paylasim_server/    # HTTP sunucu
├── tests/                         # 40+ test dosyası
├── data/                          # Web viewer ve statik varlıklar
├── docs/                          # Teknik dokümanlar
├── scripts/                       # Build ve kurulum betikleri
└── tools/                         # Yardımcı araçlar
```

## 📖 Kullanıcı Kılavuzu

### GUI Sekmeleri

| # | Sekme | Ne İşe Yarar |
|---|-------|--------------|
| 1 | 🛡️ Gizlilik | Dosya seç → metadata tara → temizle |
| 2 | 🔍 Keşif | Ağdaki cihazları bul → dosya gönder/al (istersen göndermeden metadata temizlenir) |
| 3 | 🖥️ Ekran | Ekranını paylaş veya karşı tarafı izle; uygulamasız cihaz tarayıcıdan dosya alıp gönderebilir |
| 4 | 📋 Pano | Hassas veriyi maskele, cihazlara senkronize et |
| 5 | ⚙️ Ayarlar | Cihaz adı, klasör, mDNS görünürlüğü, parmak izi, güvenilir cihazlar |
| 6 | 🌐 Mesh Ağı | Mesh başlat/durdur (otomatik eş keşfi), eş ekle, WebRTC durumu, asenkron kuyruk |

### 🌐 Mesh Ağı Sekmesi — Adım Adım

1. **Mesh Ağı:** "Başlat" → durum "Çalışıyor" olur; aynı ağdaki eşler mDNS ile otomatik bulunur (yoksa "Eş Ekle"ye IP:port yazılır).
2. **WebRTC:** Ekran paylaşımı oturum durumunu gösterir.
3. **Asenkron:** "Yenile" → bekleyen çevrimdışı transfer sayısı görünür.

### 🔧 Kullanım

#### CLI

```bash
# Dosya temizleme
pardus-paylasim --clean dosya1.jpg dosya2.pdf

# Maskeleme (TCKN, IBAN, kredi kartı, e-posta, telefon)
pardus-paylasim --mask "TCKN: 10000000146"

# Mesh ağı durumu
pardus-paylasim --mesh-status

# Bekleyen asenkron transferler
pardus-paylasim --async-list

# Çıktı ile temizleme
pardus-paylasim --clean foto.jpg --out temiz_foto.jpg
```

#### GUI

```bash
pardus-paylasim
```

#### Python API (Mesh, WebRTC, Asenkron Transfer)

```python
# 1. Mesh — parça-parça transfer
from pardus_paylasim.discovery.mesh.mesh_network import MeshNode
node = MeshNode(peer_id="benim-id", local_ip="192.168.1.10")
node.start()   # 8920 portunda dinler
node.stop()

# 2. WebRTC — SDP teklifi oluştur
from pardus_paylasim.screen.webrtc.data_channel import SDPMessage, WebRTCScreenNode
teklif = SDPMessage.create_offer("oturum-1", {"codecs": ["jpeg"]})
node = WebRTCScreenNode(peer_id="ben", port=8921)
node.start()

# 3. Asenkron — çevrimdışı kuyruk
from pardus_paylasim.discovery.async_transfer.manager import AsyncTransferManager
mgr = AsyncTransferManager(device_id="ben", device_name="Ofis PC")
tid = mgr.queue_offline("/home/kullanici/rapor.pdf", receiver_id="ev-pc", receiver_name="Ev")
bekleyen = mgr.check_pending_for("ev-pc")  # karşı taraf çevrimiçi olunca
```

## 🧪 Testler

```bash
# Hızlı testler (önerilen: ağ gerektirmez)
pytest tests/test_ui_integration.py tests/test_accessibility.py -v

# 4 yeni modül (doğrudan, pytest'siz de çalışır)
python3 tests/test_innovations_simple.py
pytest tests/test_innovations.py -v

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

# Performans ölçümleri (pytest gerektirmez)
python3 tests/benchmarks.py

# Uçtan uca mesh transferi (gerçek TCP, Docker gerektirmez)
python3 tests/test_mesh_e2e.py
```

> **Not:** `pytest.ini` kaldırıldı; tüm pytest ayarı `pyproject.toml`
> içindeki `[tool.pytest.ini_options]` bölümündedir.

## 📈 Kanıtlar

| Belge | İçerik |
|-------|--------|
| [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md) | Ölçülen gecikme tablosu (maskeleme 0,04 ms, mesh 3 µs) + rakip özellik matrisi |
| [`docs/DEMO.md`](docs/DEMO.md) | Gerçek CLI çıktıları (4 komut) + E2E mesh kaydı |
| [`docs/SECURITY_AUDIT.md`](docs/SECURITY_AUDIT.md) | Statik tarama: 2 bulgu düzeltildi (`secrets`), yanlış alarmlar gerekçelendirildi |
| [`docs/LICENSES.md`](docs/LICENSES.md) | Bağımlılık lisans uyumu (GPL-3.0 ile çelişki yok) |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | v1.1 / v1.2 / v2.0 hedefleri |
| [`docs/KULLANICI_ANKETI.md`](docs/KULLANICI_ANKETI.md) | 5 senaryoluk kullanıcı test formu |

## 🔒 Güvenlik

- **Fail-Closed Modeli:** TLS olmadan sunucu başlatılmaz
- **AES-256-GCM:** PIN tabanlı PBKDF2 (200K iterasyon) ile şifreleme
- **Streaming I/O:** Dosyalar parça-parça aktarılır, bellek kullanımı dosya boyutundan bağımsız
- **Parça Doğrulama:** Mesh transferinde her parça SHA-256 ile doğrulanır
- **Path Traversal Koruması:** `realpath` ile dizin aşımı engeli
- **TCKN Doğrulama:** Mod-10 kriptografik algoritması
- **IBAN Doğrulama:** Mod-97 algoritması
- **Kredi Kartı:** Luhn algoritması
- **Yerel AI:** Hassas veri tespiti cihazda yapılır, buluta veri gitmez
- **Audit Logging:** Tüm güvenlik olayları JSONL formatında kaydedilir

## 🛠️ Sorun Giderme

| Sorun | Çözüm |
|-------|-------|
| `pytest: configfile pytest.ini (WARNING: ignoring ...)` | Eski sürümden kalma `pytest.ini` dosyasını silin; ayar `pyproject.toml`'dadır |
| `ModuleNotFoundError: pardus_paylasim` | Kök dizindeki `conftest.py` `src/` yolunu ekler; `pip install -e .` veya `PYTHONPATH=src` kullanın |
| Port çakışması (8920/8921/8900) | Başka örnek çalışıyor olabilir; `stop()` çağrıldığından emin olun veya portu değiştirin |
| Testler takılıyor | Soket açan testler `try/finally` ile kapatılmalı; `MeshNode.stop()` / `DataChannel.close()` çağrılmalı |
| IBAN tespit edilmiyor | Test IBAN'ının Mod-97'si `1` olmalı (örn. `TR96 3456 7890 1234 5678 9012 34`) |
| GTK4 bulunamadı | CLI modu otomatik açılır; GUI için `gir1.2-gtk-4.0 gir1.2-adw-1` kurun |

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
