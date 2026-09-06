# Yol Haritası (Roadmap)

## v1.0 — Mevcut (2026-09)

- mDNS keşfi, PIN korumalı P2P transfer (AES-256-GCM, streaming)
- Mesh relay (3 hop, parça SHA-256), WebRTC data channel,
  SQLite asenkron kuyruk
- GTK4/Adw 6 sekmeli arayüz, CLI, i18n (tr/en)
- ~550 test, benchmarklar, güvenlik denetimi

## v1.1 — Tamamlananlar (2026-09)

- [x] WebRTC çerçeve parçalama (64 KB üstü kareler; 200 KB ~19 ms)
- [x] Kaldığı yerden devam eden dosya transferi (resume, 0x03 modu)
- [x] Bütünlük doğrulamalı normal mod (SHA-256, 0x04 modu)
- [x] Hız/ETA göstergesi (ilerleme çubuğuna bağlı)

## v1.1 — Kalan (hedef: +1 ay)
- [ ] Mesh otomatik yol seçimi (en düşük gecikmeli relay)
- [ ] `pip-licenses` CI kapısı + `debian/copyright` tamamlama
- [ ] pytest-benchmark ile regresyon takibi (CI'da eşik)
- [ ] Kullanıcı anketi sonuçlarının ürüne işlenmesi

## v1.2 — Birlikte Çalışabilirlik (hedef: +3 ay)

- [ ] LocalSend protokolü ile dosya alışverişi
- [ ] KDE Connect bildirim köprüsü
- [ ] Wayland uzaktan kontrol (xdg-desktop-portal RemoteDesktop)
- [ ] Ek dil: Almanca, Arapça

## v2.0 — Vizyon (hedef: +6 ay)

- [ ] Uçtan uca şifreli grup paylaşımı
- [ ] Bağımsız güvenlik denetimi (penetrasyon testi)
