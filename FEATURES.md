# Pardus Güvenli Paylaşım - Proje Yetenekleri (Features)

Bu belge, **Pardus Güvenli Paylaşım** (Pardus Secure Share) projesinin mevcut yazılım mimarisine, geliştirme standartlarına ve proje prosedürlerine göre sahip olduğu detaylı yetenekleri listelemektedir.

## 1. 🌐 Yerel Ağ Keşfi ve Sıfır Yapılandırma (Zero-Config)
- **mDNS / Zeroconf Entegrasyonu:** Cihazların IP adresine veya manuel bir kuruluma ihtiyaç duymadan yerel ağ (LAN/WLAN) üzerinde birbirlerini otomatik bulmasını sağlar (`_pardus-share._tcp.local`).
- **Dinamik Ağ Takibi:** Ağa katılan veya ayrılan cihazlar anlık olarak (Real-time) kullanıcı arayüzünde güncellenir.
- **Çoklu Arayüz Desteği:** Docker köprü (bridge) ağlarında dahi keşif protokolleri (Alice & Bob testleriyle kanıtlanmış biçimde) kusursuz çalışır.

## 2. 📁 P2P (Uçtan Uca) Dosya Transferi
- **Merkeziyetsiz Mimari:** Transferler doğrudan iki cihaz (Peer-to-Peer) arasında, soket bağlantısı ile gerçekleşir; hiçbir veriniz üçüncü parti bir sunucuya uğramaz.
- **Normal Paylaşım:** Standart hız odaklı uçtan uca dosya aktarımı.
- **Güvenli / Gizli (Secret) Paylaşım:** Transfer öncesinde iki cihaz arasında dinamik bir PIN oluşturulur. Transfer edilen veriler bu PIN kullanılarak kriptografik olarak şifrelenir ve alıcı tarafta şifresi çözülür.

## 3. 🖥️ Ekran Yayınlama (Screen Broadcasting) ve İzleme
- **Akıllı Görüntü Yakalama Algoritması:** Öncelikli olarak `GStreamer` (PipeWire veya X11) ile yüksek performanslı ekran yakalama kullanır. Desteklenmiyorsa fallback (yedek) mekanizması olarak `scrot`, `import` veya `gnome-screenshot` devreye girer.
- **Donanımsal Sessizlik:** Arka plan yakalamalarında oluşabilecek rahatsız edici deklanşör sesleri `CANBERRA_DRIVER=null` çevre değişkeniyle işletim sistemi seviyesinde (OS-level) susturulur.
- **PIN Korumalı HTTP Akışı (Streaming):** Ekranını paylaşan kullanıcıya özel ve tek kullanımlık 6 haneli bir PIN kodu verilir. İstemci (Client) bu PIN kodu olmadan `/stream` uç noktasına (endpoint) erişmeye çalışırsa sistem **HTTP 403 Forbidden** ile bağlantıyı reddeder.
- **Canlı Yayın Monitörü:** Bağlanan cihazlar stream_client aracılığıyla düşük gecikme (low-latency) ile ekran karelerini (frames) render eder.

## 4. 🛡️ Akıllı Pano ve Hassas Veri Koruması (DLP Engine)
İşletim sistemi panosuna (Clipboard) kopyalanan veya aktarılmak istenen metinleri siber güvenlik (Data Loss Prevention) standartlarında denetler:
- **Gelişmiş TCKN Tarama:** Rastgele 11 haneli sayıları değil; **Mod-10 kriptografik sağlama algoritmasını** kullanarak sayının geçerli bir Türkiye Cumhuriyeti Kimlik Numarası olup olmadığını doğrular ve geçerliyse `100*****146` formatında maskeler (False-Positive korumalı).
- **Finansal Veri Maskeleme:** Kredi kartı formatları (Luhn kontrol benzeri) ve IBAN numaraları tespit edilerek yıldızlanır (`TR12 **** **** ... 34`).
- **Kişisel ve Teknik Veri Maskeleme:** Telefon numaraları (Uluslararası format testlerinden geçmiş, çift artı `++` hatalarından arındırılmış tam uyumlu Regex), E-posta adresleri ve gizli API anahtarları (sk-****) uçtan uca maskelenir.

## 5. ⚙️ Dinamik Konfigürasyon ve Ayar Yönetimi
- **GSettings / JSON Fallback:** Pardus/Debian gibi tam teşekküllü Linux dağıtımlarında yerel `Gio.Settings` (GSettings) şemalarını kullanır. GSettings bulunmayan, derlenmemiş veya test (Docker) ortamlarında ise dinamik olarak `~/.config/pardus-paylasim/config.json` singleton dosyasına geri dönüş (fallback) yapar. 
- **Cihaz Özelleştirme:** Kullanıcılar cihaz adını, indirme konumlarını ve Pano koruması (otomatik hassas veri filtreleme) ayarlarını kolayca değiştirebilir.

## 6. 🌍 Uluslararasılaştırma (i18n) ve Yerelleştirme
- **Gettext Mimarisi:** Uygulamanın tüm arayüzü ve hata mesajları `gettext` ile sarmalanmıştır (`_()`).
- **Çoklu Dil Desteği:** Türkçe (`tr`) ve İngilizce (`en`) .po / .mo dosyaları derlenmiş olup, Pardus sisteminin varsayılan dil ayarlarına göre arayüz dilini otomatik ayarlar.

## 7. 🚀 Kalite Güvencesi (QA), CI/CD ve Test Mimarisi
- **Otomatize Pipeline'lar:** GitHub Actions (`build.yml`) ve GitLab CI (`.gitlab-ci.yml`) süreçleri ile her kod değişikliğinde test ve paketleme adımları otomatik tetiklenir.
- **Docker Integration Testleri:** İki sanal Pardus cihazı (Alice ve Bob) bir Docker köprü ağında ayağa kaldırılarak; mDNS keşfi, PIN ile güvenli ekran stream bağlantısı ve soket üzerinden dosya gönderimi otomatize bir Python test mimarisiyle (%100 başarıyla) doğrulanır.
- **Stand-alone Debian Paketleme:** `build_deb.py` modülü ile proje; ikonları, `.desktop` dosyası, dil derlemeleri (`.mo`) ve GSettings şemalarıyla birlikte dağıtıma hazır tek bir `pardus-paylasim.deb` paketi haline saniyeler içinde dönüştürülür.
