# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- README.md with comprehensive project documentation
- CHANGELOG.md for tracking changes
- Framed, authenticated streaming encryption for large secret transfers
- Flatpak manifest for universal Linux packaging
- Containerfile for Docker builds
- Accessibility (a11y) test suite
- Additional E2E tests for screen sharing and transfer workflows
- **Mesh Network** (`discovery/mesh/mesh_network.py`): P2P parça-parça dosya transferi. Cihazlar doğrudan erişilemediğinde mesh ağı üzerinden relay yapılır. 64KB chunk, SHA-256 hash doğrulama, 3 hop relay limit.
- **WebRTC Data Channel** (`screen/webrtc/data_channel.py`): SCTP benzeri güvenilir veri kanalı. JSON SDP/ICE sinyali, zlib sıkıştırma, sıralı mesaj gönderimi.
- **Async Transfer Manager** (`discovery/async_transfer/manager.py`): SQLite destekli asenkron transfer. Çevrimdışı cihazlara gönderim kuyruğu, hash tabanlı dedup, olay geçmişi.
- **Resume** (0x03 modu): yarım `.part` + sidecar ile kaldığı yerden devam; boyut/mtime uyuşmazsa sıfırdan başlar.
- **Bütünlük doğrulamalı normal mod** (0x04): gövde sonu SHA-256; tutmazsa ret + temp temizliği.
- **Hız/ETA**: `stats_callback` + ilerleme çubuğuna bağlı `% · MB/s · ETA` satırı.
- **Mesh mDNS keşfi** (`discovery/mesh/mdns.py`): `_pardus-mesh._tcp` duyuru + tarama; eşler otomatik eklenir/düşer, zeroconf yoksa sessiz degrade.
- **Gönderim-öncesi temizlik**: Keşif sekmesinde seçenek (varsayılan açık); orijinal korunur, temiz kopya gönderilir.
- **Parmak izi + güvenilir cihazlar**: kalıcı cihaz sertifikası (SHA-256 kimlik), QR'da `fp` alanı, Ayarlar'da parmak izi + güven listesi + oto-kabul anahtarı (varsayılan kapalı), `--fingerprint` CLI.
- **mDNS parmak izi akışı**: keşif TXT'de `fp`, listede 🔒 rozeti, detayda parmak izi, satırdan Güven butonu, ele cihaz ekleme.
- **WebRTC parçalama**: 64 KB üstü kareler otomatik bölünür/birleşir (16 MB üst sınır).

### Changed
- Logging: replaced f-string logger calls with %-formatting (security best practice)
- Typing: completed type annotations across all modules
- CI/CD: fixed GitHub Actions workflow path (workflows/workflows → workflows)
- Normal transfer mode: streaming disk I/O (temp file, bounded memory)
- IBAN regex: fixed 26-digit validation pattern (was only 18 digits)

### Fixed
- Workflow YAML path nesting issue in `.github/workflows/`
- Resume: kopma anında sidecar güncelleniyor (bayt tekrarı/bozulma giderildi); sidecar atomik yazılıyor
- Mesh sekmesi: port doluyken "Çalışıyor" yalanı giderildi; dolu port uygulamayı öldürmüyor
- Asenkron sayaç/CLI artık gerçek bekleyen sayısını gösteriyor (`count_pending`/`get_all_pending`)
- `_peer_ip()`: UNIX/socketpair soketlerde çökme giderildi

### Removed
- **Local AI Sensitive Detection** (`clipboard/ai/`): Deneysel modül geri çekildi; hassas veri koruması klasik maskeleme (`clipboard/sensitive_masker.py`: TCKN, IBAN, kredi kartı, e-posta, telefon) ile devam ediyor. İlgili `--ai-scan` CLI komutu ve arayüz bölümü kaldırıldı; "Yenilikler" sekmesi "Mesh Ağı" adıyla sadeleştirildi.

## [1.0.0] - 2025-09-01

### Added
- mDNS/Zeroconf device discovery (`_pardus-share._tcp.local.`)
- P2P file transfer with AES-256-GCM encryption (PIN-based PBKDF2)
- Screen sharing via GStreamer/PipeWire with MJPEG HTTP streaming
- Clipboard sync with sensitive data masking (TCKN, credit card, IBAN)
- Metadata cleaner for images, PDFs, and Office documents
- Remote control via WebSocket (AnyDesk-style)
- TLS/SSL with ephemeral self-signed certificates
- GTK4/Libadwaita GUI with 5-tab interface
- CLI mode for headless operations
- i18n support (Turkish + English)
- Docker integration tests
- Debian package build system

[Unreleased]: https://github.com/Lennebraha38/pardus-paylasim/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Lennebraha38/pardus-paylasim/releases/tag/v1.0.0
