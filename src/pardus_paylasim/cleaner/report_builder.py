"""
Report Builder for Pardus Güvenli Paylaşım.
Generates Privacy Audit Reports in JSON, Markdown, and Plain Text formats.
"""

import json
import time
from typing import List

from pardus_paylasim.cleaner.metadata_cleaner import CleaningResult
from pardus_paylasim.i18n import _


class ReportBuilder:
    """Generates detailed reports of privacy audit and cleaning sessions."""

    @staticmethod
    def to_json(results: List[CleaningResult]) -> str:
        data = {
            "app": "Pardus Güvenli Paylaşım",
            "version": "1.0.0",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_files": len(results),
            "files": [
                {
                    "original": r.original_path,
                    "cleaned": r.cleaned_path,
                    "success": r.success,
                    "engine": r.engine_used,
                    "message": r.message,
                    "risks": [
                        {
                            "category": risk.category,
                            "key": risk.key,
                            "value": risk.value,
                            "severity": risk.severity,
                            "description": risk.description,
                        }
                        for risk in r.risks_found
                    ],
                }
                for r in results
            ],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    @staticmethod
    def to_markdown(results: List[CleaningResult]) -> str:
        lines = [
            "# 🛡️ Pardus Güvenli Paylaşım - " + _("Gizlilik Raporu"),
            f"**{_('Tarih:')}** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**{_('Toplam İşlenen Dosya:')}** {len(results)}",
            "",
            "## " + _("Dosya Detayları"),
            "",
        ]

        for i, r in enumerate(results, start=1):
            status = "✅ " + _("Temizlendi") if r.success else "❌ " + _("Hata")
            lines.append(f"### {i}. {r.original_path}")
            lines.append(f"- **{_('Durum:')}** {status}")
            lines.append(f"- **{_('Temizlenmiş Kopya:')}** `{r.cleaned_path}`")
            lines.append(f"- **{_('Motor:')}** {r.engine_used}")
            lines.append(f"- **{_('Mesaj:')}** {r.message}")
            if r.risks_found:
                lines.append("- **" + _("Tespit Edilen Gizlilik Riskleri:") + "**")
                for risk in r.risks_found:
                    lines.append(
                        f"  - `[{risk.severity}]` **{risk.category} - {risk.key}**: {risk.value} ({risk.description})"
                    )
            else:
                lines.append(
                    "- **"
                    + _("Gizlilik Riski:")
                    + "** "
                    + _("Temiz (Herhangi bir gizlilik ihlali bulunamadı).")
                )
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def to_txt(results: List[CleaningResult]) -> str:
        lines = [
            "=" * 60,
            " PARDUS GÜVENLİ PAYLAŞIM - " + _("GİZLİLİK VE DETAY RAPORU"),
            f" {_('Tarih:')} {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            "",
        ]
        for r in results:
            lines.append(f"{_('Dosya:')} {r.original_path}")
            lines.append(f"{_('Temiz Kopya:')} {r.cleaned_path}")
            lines.append(f"{_('Motor:')} {r.engine_used}")
            durum = _("BAŞARILI") if r.success else _("BAŞARISIZ")
            lines.append(f"{_('Durum:')} {durum}")
            lines.append(f"{_('Tespit Edilen Risk Sayısı:')} {len(r.risks_found)}")
            for risk in r.risks_found:
                lines.append(f"  - [{risk.severity}] {risk.key}: {risk.value}")
            lines.append("-" * 60)

        return "\n".join(lines)
