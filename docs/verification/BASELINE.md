# Pardus Paylaşım - Kanıt Matrisi (BASELINE)

## 1. Sistem Durumu (Faz 0)
Bu belge, sistemin başlangıç anındaki doğrulama eksikliklerini ve mevcut güvenlik borcunu belgelemektedir. Projenin önceki aşamalarında geliştirildiği iddia edilen tüm özellikler "Kanıt Temelli Denetim" kurallarına göre değerlendirilmiştir.

### 1.1 Python Ortamı
- **Durum:** UNVERIFIED
- **Not:** Sistemde `python` komutu Inkscape'in Python'una (C:\Program Files\Inkscape\bin\python.exe) yönlendirilmiş durumda. `pip`, `ruff` ve `pytest` modülleri bulunamadı. Bu nedenle, testler ve linting adımları çalıştırılamadı.

### 1.2 Özellik Durumları

| Özellik | Dosya/Modül | Durum | Açıklama |
| --- | --- | --- | --- |
| **Ekran Paylaşımı (MJPEG/WebRTC)** | `screen/stream_server.py`, `screen/webrtc_server.py` | `UNVERIFIED`, `EXPERIMENTAL`, `BROKEN` | MJPEG prototipi güvensiz HTTP üzerinden çalışıyor. WebRTC kodları ise deneysel, bağlantı ve şifreleme kanıtları (TLS/DTLS) denetlenmedi. |
| **Keşif (mDNS / Rendezvous)** | `discovery/mdns_discovery.py`, `discovery/rendezvous_client.py` | `UNVERIFIED` | mDNS üzerinden keşif yapılıyor, fakat spoofing koruması yok. Kimlik doğrulama kanıtları eksik. |
| **Pano Senkronizasyonu (Clipboard)** | `discovery/clipboard_sync.py`, `agent/clipboard_adapter.py` | `UNVERIFIED`, `BROKEN` | Veri şifreleme ve yetkilendirme kanıtları yok (Plaintext aktarım şüphesi). |
| **Dosya Aktarımı (Transfer)** | `discovery/transfer.py`, `screen/fs_server.py` | `UNVERIFIED`, `BROKEN` | Path traversal, sembolik link ve rastgele dosya okuma/yazma zafiyetleri denetlenmedi. Yetkisiz erişim riski. |
| **Klavye/Fare Kontrolü (Input Injection)** | `screen/input_inject.py`, `screen/control_server.py` | `UNVERIFIED`, `BROKEN` | Güvensiz HTTP protokolü (ws://) üzerinden kontrol. PIN onayı/yetkilendirme yeterli değil. |
| **Windows/Pardus Ajan Mimarisi** | `agent/agent.py`, `pardus_paylasim_agent/*` | `UNVERIFIED`, `EXPERIMENTAL` | Kodlar eklenmiş ancak Windows üzerinde çalışan bir hizmet olarak kararlılığı (tray, notification vb.) tam test edilmemiş. |

### 1.3 Baseline Dosyaları (work/baseline/)
Aşağıdaki dosyalar sistemin başlangıç anındaki durumu kaydetmek için oluşturulmuştur:
- `git-status.txt`: Modifiye edilen ve takip edilmeyen dosyaların listesi.
- `git-diff.patch`: Kod üzerindeki son değişiklikler.
- `file-hashes.sha256`: (Kısmi çalıştı/yol hataları mevcut) Dosyaların SHA256 özetleri.
- `pytest-result.txt`: Modül bulunamadı hatası (Python ortamı eksikliği).
- `ruff-result.txt`: Modül bulunamadı hatası.
- `pip-check-result.txt`: Modül bulunamadı hatası.

## 2. Sonuç ve Geçiş
Hiçbir kodun güvenilir bir ortamda, CI ve güvenlik taramasından geçerek çalıştığı **kanıtlara dayanmamaktadır**. Her şey UNVERIFIED olarak işaretlenmiştir. Faz 0 tamamlanmış olup, güvenlik iyileştirmelerine (Faz 1) geçilmesi gerekmektedir.
