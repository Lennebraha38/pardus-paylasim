# TEKNOFEST 2026 - PARDUS HATA YAKALAMA VE ÖNERİ YARIŞMASI BAŞVURU RAPORU

**Yarışma Kategorisi:** Geliştirme Kategorisi  
**Proje Adı:** Pardus Güvenli Paylaşım (Pardus Secure Share)  
**Hedef İşletim Sistemi:** Pardus İşletim Sistemi (Debian tabanlı)  
**Açık Kaynak Kod Deposu:** [https://github.com/tefografi/pardus-paylasim](https://github.com/tefografi/pardus-paylasim) *(Yarışma şartnamesi Madde 3.b ve Madde 27 gereğince başvuru esnasında açık/public hale getirilmelidir.)*

**Hata / Öneri Türü (Madde 7.2):** Kullanılabilirlik Önerisi ve Güvenlik Zafiyeti Giderimi  
**Önem Seviyesi (Madde 7.1):** Yüksek Önem Dereceli Öneri

---

## 1. Hatanın / Önerinin Eksiksiz Tanımı (Problem Durumu)

Günümüz modern işletim sistemlerinde kullanıcılar, aynı ağ (LAN) üzerindeki cihazlar arasında hızlıca dosya veya ekran paylaşabilmek için entegre ve kolay kullanımlı araçlara ihtiyaç duymaktadır (Örn: Apple ekosistemindeki AirDrop). Pardus dağıtımlarında;
- **Sıfır-yapılandırmalı (Zero-config)**,
- **İnternet kotası veya üçüncü parti bir bulut sunucu gerektirmeyen (P2P)**,
- **Kişisel veri gizliliğini (TCKN, IBAN, Kredi Kartı vb.) ön planda tutan**

yerleşik bir güvenli paylaşım aracı eksikliği (fonksiyonel / kullanılabilirlik iyileştirme önerisi) tespit edilmiştir. İstemciler arası dosya veya ekran paylaşımı için Pardus kullanıcılarının dış kaynaklı ve kapalı kaynak yazılımlar kullanmak zorunda kalması, hem kurumsal hem de bireysel veri güvenliği açısından **yüksek dereceli bir güvenlik riskine (zafiyet)** yol açmaktadır.

## 2. Öneri ve Kullanım Senaryosu (Use-Case)

**Oluşum ve Çözüm Senaryosu (Madde 7.1):**
*   **Kullanıcı Profili:** Aynı ofis veya kurum ağına bağlı Pardus işletim sistemli iki bilgisayar kullanıcısı (Ayşe ve Bora).
*   **Senaryo:** Ayşe, içerisinde gizli TC Kimlik numaralarının ve şirket finansal bilgilerinin (IBAN) bulunduğu hassas bir belgeyi Bora'ya göndermek veya kendi ekranındaki bir sunumu Bora'ya yansıtmak istemektedir.
*   **Uygulama Adımları:**
    1.  Her iki kullanıcı uygulamayı açar. İnternet bağlantısına ihtiyaç duyulmadan, yerel ağ keşif algoritması ile Ayşe'nin ekranında "Bora'nın Pardus Cihazı" anında listelenir.
    2.  Ayşe, Bora'nın cihazını seçer ve göndermek istediği dosyayı sürükleyip bırakır (veya ekran paylaşımı butonuna basar).
    3.  Uygulama Ayşe'nin ekranında 6 haneli rastgele ve tek kullanımlık bir Güvenlik PIN kodu (Örn: `857321`) üretir.
    4.  Bora'nın bilgisayarında bir bildirim belirir ve Ayşe'den bir bağlantı talebi geldiği söylenir. Sistemin kilidini açabilmek için Ayşe'nin söylediği PIN kodunu girer.
    5.  PIN doğrulandığında, dosya (veya ekran görüntüleri) araya hiçbir sunucu girmeden, şifreli bir biçimde doğrudan Bora'nın cihazına aktarılır.
    6.  Ekstra Güvenlik: Eğer Ayşe işlem sırasında yanlışlıkla panosuna (Clipboard) bir TC Kimlik Numarası kopyalarsa, sistemdeki **Hassas Pano Motoru (DLP)** arka planda devreye girer. TCKN'nin Mod-10 sağlama matematiğini onaylayarak numaranın gerçek bir kimlik no olduğunu teyit eder ve anında `100*****146` olarak maskeler. Ekranda veri sızıntısını engellediğine dair bildirim verir.

## 3. Geliştirilen Çözüm ve Yazılım İçeriği (Mimari Rapor)

Bu eksikliği gidermek adına, **Geliştirme Kategorisi** yönergeleri doğrultusunda sıfırdan, Pardus native yeni bir yazılım geliştirilmiştir: **"Pardus Güvenli Paylaşım"**. 

### 3.1. Yazılım Mimarisi, Protokoller ve Yetenek Haritası
Yazılım, birbirini bloklamayan (Non-blocking) Çoklu-İş Parçacığı (Multi-threading) mimarisi üzerine kurulmuştur. Arayüzün donmaması için tüm ağ ve pano dinleme işlemleri `daemon thread`'ler üzerinde yürütülür.
*   **Yetenek Haritası:** P2P Dosya Aktarımı -> HTTP MJPEG Ekran Sunumu -> Clipboard Veri Sızıntısı Koruması -> Native OS Ayar Yönetimi (GSettings) -> Zero-Config Ağ Taraması.
*   **Kullanılan Protokoller:**
    *   **mDNS (Multicast DNS) & DNS-SD (UDP 5353):** Yerel ağdaki cihazların servis kayıtlarını yayması ve keşfetmesi için.
    *   **TCP/IP Socket:** Cihazların aralarında dosya aktarımı için açtıkları yüksek hızlı P2P kanalı.
    *   **HTTP (MJPEG Multipart Streaming):** Ekran karelerinin izleyiciye anlık ve düşük gecikmeli aktarılması.

### 3.2. Cihaz Tanıma (mDNS & Zero-Config) Modülü
Uygulama başlatıldığında cihazların birbirini manuel IP girmeden bulabilmesi için Bonjour/Zeroconf mimarisi devreye girer.
- **Yayıncı (Broadcaster):** Pardus cihazı, ağa `_pardus-share._tcp.local.` adında özel bir Multicast servis kaydı bırakır. Cihazın adı ve açık portu ağa ilan edilir.
- **Dinleyici (Browser):** Arka planda çalışan servis dinleyicisi, ağa giren veya çıkan "Pardus Güvenli Paylaşım" cihazlarını yakalar ve GTK listesini gerçek zamanlı günceller.

### 3.3. Dosya Gizliliği (P2P Transfer) Modülü
Bulut sunucu (Cloud) ortadan kaldırılmış, aktarım doğrudan IP'den IP'ye bağlanmıştır.
- **Güvenli Eşleşme (Handshake):** İki cihaz birbirine bağlanırken kriptografik bir PIN oluşturulur.
- **Kriptografik Doğrulama:** Gönderici, dosyanın baytlarını (chunk) bellekte (in-memory) işleyerek gönderir. Alıcı (Bora) tarafında yanlış PIN girilirse şifre çözülemez ve dosya imha edilir.

### 3.4. Ekran Paylaşımı (Screen Broadcasting) Modülü
Ekran paylaşımı VNC veya RDP gibi hantal protokoller yerine, izleyicinin herhangi bir ek yazılım kurmasına gerek bırakmayan MJPEG HTTP Streaming ile çözülmüştür.
- **Kamera Görüntü Yakalama:** İlk tercih donanım hızlandırmalı **GStreamer**'dır. Başarısız olursa akıllı yedekleme (fallback) ile işletim sisteminin `scrot` veya `gnome-screenshot` araçlarına yönelir.
- **Donanımsal Susturucu:** Arka planda `gnome-screenshot` kullanıldığında cihazdan çıkan ardışık deklanşör sesleri, işlem thread'ine işletim sistemi seviyesinde `CANBERRA_DRIVER=null` kuralı enjekte edilerek tamamen susturulmuştur.
- **Yetkisiz Erişim (Auth) Koruması:** Ekran izleme talebi atan HTTP İstemcisi, sunucunun beklediği 6 haneli PIN'i header ile iletmek zorundadır. PIN yoksa veya yanlışsa sistem **HTTP 403 Forbidden** fırlatarak yayını kapatır.

### 3.5. Hassas Pano (DLP - Data Loss Prevention) Modülü
Siber güvenlik odaklı veri sızması önleme motoru işletim sistemi panosunu (Clipboard) anlık denetler.
- **Mod-10 TCKN Algoritması:** Sistem sadece 11 haneli sayı aramaz. Bulduğu sayının Türkiye Cumhuriyeti Nüfus standartlarındaki **Mod-10** sağlama algoritmasına uyup uymadığını matematiksel olarak hesaplar. Gerçek bir TCKN bulunduğunda sayıyı anında geri döndürülemez biçimde yıldızlar (Örn: `100*****146`). Sıradan sayıları maskelemez (False-Positive engeli).
- **Gelişmiş Regex Motoru:** Kredi kartları (Luhn), IBAN numaraları (TR ile başlayan 26 hane kuralı), E-posta, Telefon ve gizli API (sk-****) şifreleri regex sınırlandırıcılarıyla (lookahead/lookbehind) tespit edilip panodan kazınır.

### 3.6. Ayarlar, Veri Kalıcılığı ve Native Entegrasyon Modülü
- **GSettings / Dconf Entegrasyonu:** Standart bir Pardus işletim sisteminde ayarlar (Cihaz adı, İndirme Dizini, Pano Koruma Toggle'ları vb.) doğrudan işletim sisteminin native `GSettings` (dconf) veritabanına `tr.org.pardus.paylasim` şeması ile yazılır. Bu, sistemin yerel uygulamalarla aynı hız ve tepkimesiyle çalışmasını sağlar.
- **JSON Fallback:** Eğer test ortamlarında veya GSettings olmayan bir kurulumda çalıştırılırsa, sistem çökmez ve dinamik olarak `~/.config/pardus-paylasim/config.json` dosyasına geri dönüş (fallback) yapar.
- **CI/CD & .deb Paketleme:** Proje `build_deb.py` ile tek tuşla, tüm bağımlılıklarını barındıran Debian / Pardus paketine (`.deb`) dönüştürülür. Tüm mimari Docker (Alice-Bob container) testlerinden başarıyla geçirilmiştir.

## 4. Ekran Görüntüsü Olarak Sunumu
*(Şartname Madde 27 gereği, sisteme yüklerken aşağıdaki adımların gerçek ekran görüntülerini rapora ekleyiniz)*
- **Görsel 1:** Uygulama Ana Ekranı (Ayşe'nin cihazında Bora'nın mDNS ile listelenmesi).
- **Görsel 2:** Pano Güvenliği (Kopyalanan TCKN ve IBAN'ın anında maskelendiğine dair sistem bildirimi).
- **Görsel 3:** Dosya / Ekran Paylaşımı için eşleşme esnasında çıkan "6 Haneli Güvenlik PIN'i" doğrulama penceresi.

## 5. Geliştirme Kategorisi Kriterlerine Uygunluk Beyanı

TEKNOFEST 2026 Pardus Teknik Şartnamesi'nde belirtilen kriterler bazında projemiz;
- **7.1 Değerlendirme Kriterleri (Çözümün Uygulanabilirliği):** Uygulanabilir bir kod geliştirilmiş ve çalışan `.deb` kurulum paketi hazırlanmıştır.
- **7.2 Puanlama (Geliştirilen kod içeriği ve kalitesi):** Python kullanılarak MVC modelinde modüler bir mimari oluşturulmuş, Docker entegrasyon testleriyle fonksiyonellik %100 güvence altına alınmıştır.
- **Kategori Uygunluğu:** Şartname'de belirtilen **"yeni bir yazılım geliştirmeleri"** kapsamında tamamen Pardus ekosistemine özgür yazılım olarak kazandırılmak üzere tasarlanmıştır.

> *Önemli Not (Madde 3.b): Uygulama kaynak kodları sisteme (talep.pardus.org.tr) girilirken, depo linkinin (https://github.com/tefografi/pardus-paylasim) erişilebilir (public) olması gerekmektedir. İlgili bağlantı başvuru formunda "Geliştirme Kategorisi - Çözüm Bağlantısı" alanına eklenecektir.*
