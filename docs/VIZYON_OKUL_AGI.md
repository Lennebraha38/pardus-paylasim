# Vizyon: Okul Ağı ("Veri Merkezi Gibi Sınıflar")

> Dürüstlük notu: Bu belge yol haritasıdır, tamamlanmış iş değil.
> "Yapıldı" gibi okunabilecek cümle yoktur; her madde durum etiketlidir.

## Hedef

Okuldaki akıllı tahtaların birbirine bağlı, öğretmenin tek noktadan
dosya dağıtıp ekran izleyebildiği, arızanın erken görüldüğü bir ağ.

## Mevcut mimariyle UYUMLU olanlar (P2P, sunucusuz)

| İhtiyaç | Mevcut karşılık | Durum |
|---------|-----------------|-------|
| Öğretmen → tüm tahtalara dosya | Çoklu cihaza gönderim | ✅ var |
| Ekran izleme | Ekran paylaşımı + web viewer | ✅ var |
| Cihaz envanteri | mDNS keşif + parmak izi kimlik | ✅ var |
| Bağlantı kopması | Resume + retry + async kuyruk | ✅ var |
| Yavaşlık fark etme | TransferHealth uyarıları | ✅ var (bu sürüm) |
| Sınıf sınavı | neural-system quiz motoru | 🔶 taşınabilir (büyük iş) |

## Mimari GERÇEKLER (bilinmesi şart)

1. **Bu uygulama P2P'dir, merkezi değildir.** "Veri merkezi"ndeki gibi
   tek konsoldan 50 tahtayı yönetmek için bir **orkestratör rolü**
   gerekir (öğretmen cihazı = geçici merkez). Protokol buna engel
   değildir (çoklu gönderim + keşif var), ama yönetim UI'sı yoktur.
2. **Ölçek sınırı ölçülmedi.** 2 cihazda doğrulandı; 30 tahtalı sınıfta
   mDNS fırtınası, Wi-Fi darboğazı, pil tüketimi **saha testi ister**.
   Laboratuvar iddiası laboratuvarsız verilmez.
3. **Sınav = yeni etki alanı.** Quiz motoru taşınabilir ama soru
   dağıtımı + cevap toplama + kopya önleme + puanlama UI'sı ayrı
   projedir; "birleştirme" tek commit değildir.
4. **MDM değildir.** Uzaktan kilitleme/silme/kiosk gibi cihaz yönetimi
   bu uygulamanın kapsamı dışındadır (ayrı yetkilendirme modeli ister).

## Önerilen fazlar

- **Faz 1 (mevcut):** P2P paylaşım sağlamlığı — tamamlanmak üzere.
- **Faz 2 — Sınıf Modu:** öğretmen rolü + tahta listesi + tek tuşla
  dosya dağıtımı + toplu ekran küçük resimleri (web viewer üstünden).
- **Faz 3 — Sınav:** quiz motoru taşıma + pilot sınıf (GERÇEK okulda).
- **Faz 4 — İzleme:** tahta sağlık panosu (disk/CPU + aktarım anomalileri).

## Yapamayacaklarım (açıkça)

- Donanım olmadan 30 cihazlı yük testi yapamam.
- Okul pilotu ayarlayamam; bu, sahada insan ister.
- "Devrim" iddiasını kanıtsız yazmam; yukarıdaki fazlar bitmeden
  bu kelime kullanılmayacak.
