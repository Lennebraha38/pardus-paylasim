"""
Metadata Cleaner Engine for Pardus Güvenli Paylaşım.
Scans and strips sensitive metadata from images, PDFs, Microsoft Office & LibreOffice documents.
"""

import logging
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from typing import List, Optional

from pardus_paylasim.i18n import _

logger = logging.getLogger(__name__)


@dataclass
class PrivacyRiskItem:
    category: str  # e.g., 'GPS', 'Cihaz Bilgisi', 'Yazar/Kurum', 'Zaman Damgası'
    key: str  # e.g., 'GPS Latitude', 'Author', 'Camera Model'
    value: str  # e.g., '39.9207° N, 32.8541° E', 'Ahmet Yılmaz', 'iPhone 15 Pro'
    severity: str  # 'KRİTİK', 'YÜKSEK', 'ORTA', 'DÜŞÜK'
    description: str


@dataclass
class CleaningResult:
    original_path: str
    cleaned_path: str
    success: bool
    risks_found: List[PrivacyRiskItem] = field(default_factory=list)
    risks_removed_count: int = 0
    engine_used: str = "Pardus Native Redactor"
    message: str = ""


class MetadataCleaner:
    """Scans and removes sensitive metadata from various file types."""

    RISK_KEYWORDS = {
        "gps": ("GPS", "KRİTİK", "Konum bilgisi paylaşım güvenliği riski oluşturur."),
        "latitude": ("GPS", "KRİTİK", "Hassas coğrafi enlem bilgisi."),
        "longitude": ("GPS", "KRİTİK", "Hassas coğrafi boylam bilgisi."),
        "author": ("Yazar/Kurum", "YÜKSEK", "Kişisel veya kurumsal isim bilgisi."),
        "creator": ("Yazar/Kurum", "YÜKSEK", "Belgeyi oluşturan yazılım/kişi bilgisi."),
        "company": ("Yazar/Kurum", "ORTA", "Kurum veya organizasyon adı."),
        "lastmodifiedby": ("Yazar/Kurum", "YÜKSEK", "Son düzenleyen kullanıcı adı."),
        "camera": ("Cihaz Bilgisi", "ORTA", "Kamera veya telefon donanım modeli."),
        "make": ("Cihaz Bilgisi", "ORTA", "Cihaz üretici markası."),
        "model": ("Cihaz Bilgisi", "ORTA", "Donanım model bilgisi."),
        "serialnumber": ("Cihaz Bilgisi", "YÜKSEK", "Donanım seri numarası."),
        "software": ("Yazılım", "DÜŞÜK", "Kullanılan düzenleme yazılımı sürümü."),
        "createdate": ("Zaman Damgası", "ORTA", "Oluşturulma tarihi ve saati."),
        "modifydate": ("Zaman Damgası", "ORTA", "Son değiştirilme tarihi ve saati."),
    }

    def __init__(self):
        self.has_mat2 = self._check_command("mat2")
        self.has_exiftool = self._check_command("exiftool")

    def _check_command(self, cmd: str) -> bool:
        return shutil.which(cmd) is not None

    def scan_file(self, file_path: str) -> List[PrivacyRiskItem]:
        """Scans a file for metadata risks."""
        if not os.path.exists(file_path):
            return []

        ext = os.path.splitext(file_path)[1].lower()
        risks: List[PrivacyRiskItem] = []

        if ext in [".jpg", ".jpeg", ".png", ".heic", ".tiff"]:
            risks.extend(self._scan_image(file_path))
        elif ext in [".pdf"]:
            risks.extend(self._scan_pdf(file_path))
        elif ext in [".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"]:
            risks.extend(self._scan_office_zip(file_path))
        else:
            risks.extend(self._scan_generic(file_path))

        return risks

    def _scan_image(self, file_path: str) -> List[PrivacyRiskItem]:
        risks = []
        if self.has_exiftool:
            try:
                res = subprocess.run(
                    ["exiftool", "-json", file_path],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    import json

                    data = json.loads(res.stdout)
                    if data and isinstance(data, list):
                        meta = data[0]
                        for k, v in meta.items():
                            lower_k = k.lower()
                            for rkey, (cat, sev, desc) in self.RISK_KEYWORDS.items():
                                if rkey in lower_k and str(v).strip():
                                    risks.append(
                                        PrivacyRiskItem(
                                            category=cat,
                                            key=k,
                                            value=str(v),
                                            severity=sev,
                                            description=desc,
                                        )
                                    )
            except Exception:
                pass

        if not risks:
            # Fallback simple binary scan for GPS or EXIF strings
            try:
                with open(file_path, "rb") as f:
                    content = f.read(100000)
                    import re

                    if (
                        re.search(b"Exif\x00\x00", content)
                        or b"GPSInfo" in content
                        or b"http://ns.adobe.com/exif/1.0/" in content
                    ):
                        risks.append(
                            PrivacyRiskItem(
                                category="GPS/EXIF",
                                key="EXIF Meta Etiketi",
                                value=_("Gömülü EXIF / GPS Verileri Algılandı"),
                                severity="YÜKSEK",
                                description=_(
                                    "Fotoğraf içerisinde konum veya cihaz meta bilgisi bulunmaktadır."
                                ),
                            )
                        )
            except Exception:
                pass
        return risks

    def _scan_pdf(self, file_path: str) -> List[PrivacyRiskItem]:
        risks = []
        try:
            with open(file_path, "rb") as f:
                header = f.read(4096).decode("latin-1", errors="ignore")
                f.seek(max(0, os.path.getsize(file_path) - 8192))
                trailer = f.read().decode("latin-1", errors="ignore")
                content = header + trailer
                for key in [
                    "/Author",
                    "/Creator",
                    "/Producer",
                    "/CreationDate",
                    "/ModDate",
                    "/Title",
                ]:
                    if key in content:
                        idx = content.find(key)
                        val_sample = content[idx : idx + 80].split("\n")[0]
                        risks.append(
                            PrivacyRiskItem(
                                category="PDF Meta",
                                key=key.lstrip("/"),
                                value=val_sample[:50],
                                severity="ORTA",
                                description=_(
                                    "PDF başlık alanında hassas belge ve yazar bilgisi var."
                                ),
                            )
                        )
        except Exception:
            pass
        return risks

    def _scan_office_zip(self, file_path: str) -> List[PrivacyRiskItem]:
        risks = []
        try:
            if zipfile.is_zipfile(file_path):
                with zipfile.ZipFile(file_path, "r") as zf:
                    for name in zf.namelist():
                        if "core.xml" in name or "app.xml" in name or "meta.xml" in name:
                            raw = zf.read(name)
                            try:
                                root = ET.fromstring(raw)
                                for elem in root.iter():
                                    tag = elem.tag.split("}")[-1].lower()
                                    text = (elem.text or "").strip()
                                    if text and tag in [
                                        "creator",
                                        "lastmodifiedby",
                                        "company",
                                        "initials",
                                        "author",
                                    ]:
                                        risks.append(
                                            PrivacyRiskItem(
                                                category="Ofis Belgesi Meta",
                                                key=tag.capitalize(),
                                                value=text,
                                                severity="YÜKSEK",
                                                description=_(
                                                    "Ofis belgesi düzenleyici ve kurumsal bilgisi içeriyor."
                                                ),
                                            )
                                        )
                            except Exception:
                                pass
        except Exception:
            pass
        return risks

    def _scan_generic(self, file_path: str) -> List[PrivacyRiskItem]:
        return []

    def clean_file(self, file_path: str, output_path: Optional[str] = None) -> CleaningResult:
        """Cleans file and writes to output_path (defaults to <name>_temiz.<ext>)."""
        if not os.path.exists(file_path):
            return CleaningResult(
                original_path=file_path,
                cleaned_path="",
                success=False,
                message=_("Dosya bulunamadı."),
            )

        risks = self.scan_file(file_path)
        base, ext = os.path.splitext(file_path)
        if not output_path:
            output_path = f"{base}_temiz{ext}"

        # 1. Try MAT2
        if self.has_mat2:
            try:
                res = subprocess.run(
                    ["mat2", "--no-sandbox", file_path],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                # MAT2 may produce either file.cleaned.ext or file.ext.cleaned
                # depending on version. Check both locations.
                mat2_cleaned_options = [
                    f"{base}.cleaned{ext}",  # file.cleaned.pdf
                    f"{file_path}.cleaned",  # file.pdf.cleaned
                ]
                mat2_cleaned = None
                for candidate in mat2_cleaned_options:
                    if os.path.exists(candidate):
                        mat2_cleaned = candidate
                        break

                if mat2_cleaned:
                    shutil.move(mat2_cleaned, output_path)
                    return CleaningResult(
                        original_path=file_path,
                        cleaned_path=output_path,
                        success=True,
                        risks_found=risks,
                        risks_removed_count=len(risks) if risks else 1,
                        engine_used="MAT2 (Metadata Anonymisation Toolkit 2)",
                        message=_("Tüm meta veriler MAT2 ile başarıyla temizlendi."),
                    )
            except Exception as e:
                # MAT2 failed – log and fall through to the next engine.
                logger.error("MAT2 hatası: %s", e)

        # 2. Try ExifTool for images
        if self.has_exiftool and ext in [".jpg", ".jpeg", ".png", ".tiff"]:
            try:
                shutil.copy2(file_path, output_path)
                res = subprocess.run(
                    ["exiftool", "-all=", "-overwrite_original", output_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                # Clean up ExifTool backup file if it exists
                backup_path = f"{output_path}_original"
                if os.path.exists(backup_path):
                    try:
                        os.remove(backup_path)
                    except Exception:
                        pass
                if res.returncode == 0:
                    return CleaningResult(
                        original_path=file_path,
                        cleaned_path=output_path,
                        success=True,
                        risks_found=risks,
                        risks_removed_count=len(risks) if risks else 1,
                        engine_used="ExifTool Engine",
                        message=_("EXIF ve GPS meta verileri ExifTool ile sıfırlandı."),
                    )
            except Exception as e:
                # ExifTool failed – log and fall through to the native fallback.
                logger.error("ExifTool hatası: %s", e)

        # 3. Fallback Native Redactor
        return self._clean_native_fallback(file_path, output_path, risks, ext)

    def _clean_native_fallback(
        self, file_path: str, output_path: str, risks: List[PrivacyRiskItem], ext: str
    ) -> CleaningResult:
        try:
            if ext in [".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"]:
                # Prevent corruption when src and dst are the same
                if os.path.abspath(file_path) == os.path.abspath(output_path):
                    # Use temp file as intermediate
                    import tempfile

                    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
                    os.close(tmp_fd)
                    cleaned_zip = self._clean_office_zip_native(file_path, tmp_path)
                    if cleaned_zip:
                        shutil.move(tmp_path, output_path)
                else:
                    cleaned_zip = self._clean_office_zip_native(file_path, output_path)
                if cleaned_zip:
                    return CleaningResult(
                        original_path=file_path,
                        cleaned_path=output_path,
                        success=True,
                        risks_found=risks,
                        risks_removed_count=len(risks) if risks else 1,
                        engine_used="Pardus Ofis XML Temizleyici",
                        message=_(
                            "Ofis belgesi meta verileri (author, company, XML props) temizlendi."
                        ),
                    )
            # Default copy + sanitize
            # HIGH SECURITY FIX: Do not pretend to clean files we don't support natively.
            if len(risks) > 0:
                return CleaningResult(
                    original_path=file_path,
                    cleaned_path="",
                    success=False,
                    risks_found=risks,
                    message=_(
                        "Gerekli araçlar (MAT2/ExifTool) kurulu değil. Bu dosya türü için yerleşik temizleyici desteklenmiyor. Dosya temizlenmedi."
                    ),
                )

            # If no risks were found in the first place, just copy
            shutil.copy2(file_path, output_path)
            return CleaningResult(
                original_path=file_path,
                cleaned_path=output_path,
                success=True,
                risks_found=risks,
                risks_removed_count=0,
                engine_used="Pardus Güvenli Kopya Motoru",
                message=_("Bilinen risk bulunmadı. Dosya kopyalandı."),
            )
        except Exception as e:
            return CleaningResult(
                original_path=file_path,
                cleaned_path="",
                success=False,
                risks_found=risks,
                message=_("Temizleme hatası: {error}").format(error=str(e)),
            )

    def _clean_office_zip_native(self, src_path: str, dst_path: str) -> bool:
        try:
            with zipfile.ZipFile(src_path, "r") as zin, zipfile.ZipFile(dst_path, "w") as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename in ["docProps/core.xml", "docProps/app.xml", "meta.xml"]:
                        # Replace content with sanitized XML shell
                        if item.filename == "meta.xml":
                            data = b'<?xml version="1.0" encoding="UTF-8"?><office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"></office:document-meta>'
                        else:
                            data = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"></cp:coreProperties>'
                    zout.writestr(item, data)
            return True
        except Exception:
            return False
