# FAZ 7 - WAYLAND, X11, WINDOWS VE ÇOKLU MONİTÖR (Doğrulama Raporu)

## Destek Matrisi ve Backend Durumları

Mevcut test ortamı (Windows CI / Headless), gerçek ekran ve giriş aygıtı taklidine tam olarak izin vermediğinden, aşağıdaki hedeflerin tamamı "Fiziksel Test Edilemedi" kuralı gereğince `UNVERIFIED` olarak işaretlenmiştir.

| İşletim Sistemi (Hedef) | View | Control (Input) | File Transfer | Clipboard | Mevcut Backend Mimarisi | Test Durumu |
|---|---|---|---|---|---|---|
| **Pardus 23 (X11)** | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | X11 (MSS) / XTEST | UNVERIFIED |
| **Pardus 23 (Wayland)** | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | XDG Portal / ydotool | UNVERIFIED |
| **Pardus 25 (X11)** | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | X11 (MSS) / XTEST | UNVERIFIED |
| **Pardus 25 (Wayland)** | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | XDG Portal / ydotool | UNVERIFIED |
| **Windows 10/11** | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | GDI/MSS / Pynput | UNVERIFIED |

## Teknik Mimari Beklentileri (Gelecek Doğrulama İçin)
1. **Wayland Portal (XDG RemoteDesktop):**
   - Kod mimarisinde D-Bus, XDG portal ve ydotool yeteneklerinin varlığı varsayılmakta, ancak bu çağrıların "Session Create -> Select -> Start" şeklindeki sinyal onayları Wayland compositor'a bağımlı olduğundan test edilememektedir.
2. **Çoklu Monitör:**
   - `mss.monitors` üzerinden indeks bazlı koordinat ayrıştırması `webrtc_tracks.py` modülüne implement edilmiştir. Koordinat haritalaması, mutlak piksellere göre yapıldığından farklı DPI ölçeklerine sahip ekranlarda fiziki doğrulama gerektirir.
3. **Windows 10/11:**
   - Control: `pynput` kullanılarak native hook'lar aracılığıyla enjeksiyon tasarlandı.
   - View: `mss` GDI aracılığıyla framebuffer okuyabilir.
   - Gerçek Windows izin istemleri (UAC) nedeniyle klavye/fare hook'larının drop olma ihtimali test edilemedi.

**SONUÇ:** Ortamdaki CI koşulları nedeniyle tüm gerçek donanım/Wayland etkileşimleri zorunlu olarak "Fail-Closed" / UNVERIFIED statüsünde bırakılmıştır.
