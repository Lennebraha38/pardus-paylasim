#!/usr/bin/env python3
"""gettext kataloğu üretici (harici `msgfmt` gerektirmez).

Kullanım:
    python3 scripts/i18n_build.py

`src/pardus_paylasim/locale/en/LC_MESSAGES/pardus-paylasim.po` dosyasını
yazar ve aynı dizine `.mo` derler. Çeviri eklemek için `TRANSLATIONS`
sözlüğüne `kaynak Türkçe: English` satırı ekleyip scripti yeniden çalıştırın.
"""

from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "src" / "pardus_paylasim" / "locale" / "en" / "LC_MESSAGES"

TRANSLATIONS: dict[str, str] = {
    # --- Sekmeler / başlıklar -------------------------------------------------
    "Dosya Gizliliği ve Meta Veri Temizleyici": "File Privacy & Metadata Cleaner",
    "Wi-Fi ve Bluetooth Cihaz Tanıma": "Wi-Fi & Bluetooth Device Discovery",
    "Ekran Paylaşımı": "Screen Sharing",
    "Hassas Metin ve Pano Maskeleyici": "Sensitive Text & Clipboard Masker",
    "Mesh Ağı": "Mesh Network",
    "Sınıf": "Classroom",
    "Genel Ayarlar": "General Settings",
    "Keşif": "Discovery",
    "Pardus Paylaşım": "Pardus Share",
    "Pardus Paylaşım'a Hoş Geldiniz": "Welcome to Pardus Share",
    "Pardus Güvenli Paylaşım ve Süreklilik Merkezi": "Pardus Secure Sharing & Continuity Center",
    # --- Düğmeler -------------------------------------------------------------
    "Başlat": "Start",
    "Durdur": "Stop",
    "Gönder": "Send",
    "İptal": "Cancel",
    "Temizle": "Clean",
    "Tara": "Scan",
    "Ekle": "Add",
    "Kaldır": "Remove",
    "Kaydet": "Save",
    "Kapat": "Close",
    "Yenile": "Refresh",
    "Kopyala": "Copy",
    "Onayla": "Approve",
    "Reddet": "Reject",
    "Geri": "Back",
    "İleri": "Next",
    "Aç": "Open",
    "Seç": "Select",
    "Değiştir": "Change",
    "Devam": "Continue",
    "Gözat": "Browse",
    "Yükle": "Upload",
    "İndir": "Download",
    # --- Durumlar -------------------------------------------------------------
    "BAŞARILI": "SUCCESS",
    "BAŞARISIZ": "FAILED",
    "Temiz": "Clean",
    "Temizlendi": "Cleaned",
    "Hazır": "Ready",
    "Bilgi": "Info",
    "Hata": "Error",
    "Uyarı": "Warning",
    "Sonuç": "Result",
    "Durum": "Status",
    "Gönderildi": "Sent",
    "Alındı": "Received",
    "Başlatılmadı": "Not started",
    "Bağlı değil": "Not connected",
    "Bağlantı kesildi.": "Disconnected.",
    "Yayın başlatılmadı": "Broadcast not started",
    "Yayın durduruldu.": "Broadcast stopped.",
    "Çalışıyor (otomatik keşif açık)": "Running (auto-discovery on)",
    "Çalışıyor (manuel eş ekleyin)": "Running (add a peer manually)",
    "Henüz kayıt yok.": "No records yet.",
    "Henüz dosya seçilmedi.": "No file selected yet.",
    "Henüz taranmadı": "Not scanned yet",
    "Henüz yayın yok": "No broadcast yet",
    "Henüz bildirim yok.": "No notifications yet.",
    "Kullanılamıyor": "Unavailable",
    # --- Etiketler ------------------------------------------------------------
    "Ad": "Name",
    "Adres": "Address",
    "Port": "Port",
    "PIN Kodu": "PIN Code",
    "Dosya": "File",
    "Dosya:": "File:",
    "Klasör": "Folder",
    "Klasör Gönder": "Send Folder",
    "Dosya Seç": "Choose File",
    "Dosya Seç ve Dağıt": "Choose & Distribute File",
    "Dosya Paylaşımı": "File Sharing",
    "Dosya Detayları": "File Details",
    "Dosya Dağıtımı": "File Distribution",
    "Sunucu IP Adresi": "Server IP Address",
    "İndirme Konumu": "Download Location",
    "İndirme konumunu değiştir": "Change download location",
    "Güvenilir": "Trusted",
    "Güven": "Trust",
    "Güveni kaldır": "Remove trust",
    "Parmak izi": "Fingerprint",
    "Parmak İzi ve Güven": "Fingerprint & Trust",
    "Bağlı Eşler": "Connected Peers",
    "Bekleyen Transferler": "Pending Transfers",
    "Transfer Geçmişi": "Transfer History",
    "Gizlilik Raporu": "Privacy Report",
    "Gizlilik Riski:": "Privacy Risk:",
    "Tespit Edilen Gizlilik Riskleri:": "Detected Privacy Risks:",
    "Tespit Edilen Risk Sayısı:": "Number of Risks Detected:",
    "Temiz Kopya:": "Clean Copy:",
    "Temizlenmiş Kopya:": "Cleaned Copy:",
    "Motor:": "Engine:",
    "Maskelenecek metin": "Text to mask",
    "Maskelenmiş Metin:": "Masked Text:",
    "Taranacak Metin": "Text to scan",
    "Taranacak Metin:": "Text to scan:",
    "Otomatik Maskele": "Auto-mask",
    "Otomatik Pano Koruması": "Automatic Clipboard Protection",
    "Panodan Yapıştır": "Paste from Clipboard",
    "Panoyu Gönder": "Send Clipboard",
    "Pano Geçmişi (yalnız bu oturum):": "Clipboard History (this session only):",
    "Ekran Yansıt": "Mirror Screen",
    "Ekran Yayınını Başlat": "Start Screen Broadcast",
    "Ekranımı Yayınla (Sunucu)": "Share My Screen (Server)",
    "Uzak Ekrana Bağlan": "Connect to Remote Screen",
    "Uzak Ekrana Bağlan (İstemci)": "Connect to Remote Screen (Client)",
    "Kontrolü İste": "Request Control",
    "Kontrolü Bırak": "Release Control",
    "Kontrolü Durdur": "Stop Control",
    "Uzaktan kontrole izin ver": "Allow remote control",
    "Uzaktan Kontrole İzin Ver": "Allow Remote Control",
    "Sınav": "Exam",
    "Sınav Oluştur": "Create Exam",
    "Sınav Dağıt": "Distribute Exam",
    "Sınav Cevapla": "Answer Exam",
    "Sınıf Adı": "Class Name",
    "Sınıf Rolü": "Class Role",
    "Rol seç": "Choose role",
    "Tahtalar": "Boards",
    "Tahta modu": "Board mode",
    "Duyuru": "Announcement",
    "Mesaj Yayını": "Message Broadcast",
    # --- Mesajlar -------------------------------------------------------------
    "Dosya bulunamadı.": "File not found.",
    "Bilinen risk bulunmadı. Dosya kopyalandı.": "No known risk found. File copied.",
    "Hassas veri tespit edilmedi.": "No sensitive data detected.",
    "Lütfen maskelenecek metni girin.": "Please enter the text to mask.",
    "Lütfen taranacak metni girin.": "Please enter the text to scan.",
    "Lütfen sunucu IP adresini girin.": "Please enter the server IP address.",
    "Geçersiz port numarası.": "Invalid port number.",
    "Geçersiz eşleştirme bağlantısı.": "Invalid pairing link.",
    "Pano boş; gönderilecek metin yok.": "Clipboard is empty; nothing to send.",
    "Pano metni alındı": "Clipboard text received",
    "Parmak izi panoya kopyalandı.": "Fingerprint copied to clipboard.",
    "Parmak izi üretilemedi (cryptography gerekli).": "Could not generate fingerprint (cryptography required).",
    "Tüm meta veriler MAT2 ile başarıyla temizlendi.": "All metadata was successfully removed with MAT2.",
    "Ofis belgesi meta verileri (author, company, XML props) temizlendi.": "Office document metadata (author, company, XML props) removed.",
    "EXIF ve GPS meta verileri ExifTool ile sıfırlandı.": "EXIF and GPS metadata reset with ExifTool.",
    "Gerekli araçlar (MAT2/ExifTool) kurulu değil. Bu dosya türü için yerleşik temizleyici desteklenmiyor. Dosya temizlenmedi.": "Required tools (MAT2/ExifTool) are not installed. The built-in cleaner does not support this file type. File was not cleaned.",
    "Fotoğraf, PDF ve ofis belgelerindeki GPS konumu, yazar adı, cihaz bilgisi gibi gizlilik risklerini tespit edin ve temizleyin.": "Detect and remove privacy risks such as GPS location, author name and device info in photos, PDFs and office documents.",
    "Metin içindeki T.C. Kimlik No, kredi kartı, IBAN, e-posta, \n telefon ve API anahtarı gibi hassas bilgileri otomatik tespit eder ve maskeler.": "Automatically detects and masks sensitive data such as national ID, credit card, IBAN, e-mail, phone and API keys in text.",
    "Parça-parça P2P transfer ve çevrimdışı kuyruk.\nTüm veriler cihazınızda kalır — buluta gönderilmez.": "Chunked P2P transfer and offline queue.\nAll data stays on your device — nothing is sent to the cloud.",
    "Yerel ağda ve Bluetooth üzerinden Pardus cihazlarını keşfedin.": "Discover Pardus devices on the local network and over Bluetooth.",
    "Yerel ağdaki Pardus cihazları arasında güvenli, düşük gecikmeli ekran yayını.": "Secure, low-latency screen broadcast between Pardus devices on the local network.",
    "Dosyayı AES-256 ile şifreleyerek P2P gönder.": "Send the file P2P encrypted with AES-256.",
    "Dosyayı yerel ağ üzerinden hızlıca gönder.": "Send the file quickly over the local network.",
    "Bir klasörü iç yapısını koruyarak gönder.": "Send a folder while preserving its structure.",
    "Göndermeden önce dosya metadata bilgisini temizle": "Clean file metadata before sending",
    "Gönderim-öncesi temizliği atla": "Skip pre-send cleaning",
    "Diğer cihazlar beni bulabilsin (mDNS yayını)": "Let other devices find me (mDNS broadcast)",
    "Ağda görünecek adınız": "Your name on the network",
    "Uygulama bildirimleri": "Application notifications",
    "İptal edildi.": "Cancelled.",
    "İptal ediliyor…": "Cancelling…",
    "Gönderiliyor…": "Sending…",
    "Bağlanıyor...": "Connecting...",
    "Dosyalar taranıyor ve temizleniyor...": "Scanning and cleaning files...",
    "Yayın başlatılıyor...": "Starting broadcast...",
    "Taramayı Durdur": "Stop Scan",
    "Yayını Durdur": "Stop Broadcast",
    "Bağlantıyı Kes": "Disconnect",
}


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def build_po() -> str:
    lines = [
        'msgid ""',
        'msgstr ""',
        '"Project-Id-Version: pardus-paylasim 1.1.0\\n"',
        '"Report-Msgid-Bugs-To: https://github.com/Lennebraha38/pardus-paylasim/issues\\n"',
        '"POT-Creation-Date: 2026-11-04 00:00+0300\\n"',
        '"PO-Revision-Date: 2026-11-04 00:00+0300\\n"',
        '"Language: en\\n"',
        '"MIME-Version: 1.0\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        "",
    ]
    for msgid in sorted(TRANSLATIONS):
        lines.append(f'msgid "{_escape(msgid)}"')
        lines.append(f'msgstr "{_escape(TRANSLATIONS[msgid])}"')
        lines.append("")
    return "\n".join(lines)


def build_mo(po_pairs: dict[str, str]) -> bytes:
    """GNU MO formatı (küçük katalog için yeterli, hash tablosu boş)."""
    messages = {"": "Content-Type: text/plain; charset=UTF-8\nLanguage: en\n"}
    messages.update(po_pairs)
    keys = sorted(messages)
    offsets: list[tuple[int, int, int, int]] = []
    payload = bytearray()
    # Önce string tablosunu oluştur, offsetleri sonra hesapla.
    for key in keys:
        k = key.encode("utf-8") + b"\0"
        v = messages[key].encode("utf-8") + b"\0"
        offsets.append((len(payload), len(k) - 1, len(payload) + len(k), len(v) - 1))
        payload += k + v
    key_table_offset = 28
    value_table_offset = key_table_offset + 8 * len(keys)
    payload_offset = value_table_offset + 8 * len(keys)
    header = struct.pack(
        "<7I", 0x950412DE, 0, len(keys), key_table_offset, value_table_offset, 0, 0
    )
    key_table = b"".join(
        struct.pack("<II", length, payload_offset + start) for start, length, _, _ in offsets
    )
    value_table = b"".join(
        struct.pack("<II", length, payload_offset + start)
        for _, _, start, length in offsets
    )
    return header + key_table + value_table + bytes(payload)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    po_path = OUT_DIR / "pardus-paylasim.po"
    mo_path = OUT_DIR / "pardus-paylasim.mo"
    po_path.write_text(build_po(), encoding="utf-8")
    mo_path.write_bytes(build_mo(TRANSLATIONS))
    print(f"yazıldı: {po_path} ({len(TRANSLATIONS)} çeviri)")
    print(f"yazıldı: {mo_path} ({mo_path.stat().st_size} bayt)")


if __name__ == "__main__":
    main()
