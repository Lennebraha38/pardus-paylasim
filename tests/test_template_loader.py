"""
Pardus Paylaşım — Bildirimsel Arayüz Şablonu (GtkBuilder UI) Testleri.
"""

import os
import xml.etree.ElementTree as ET

from pardus_paylasim.ui.template_loader import TemplateLoader


def test_ui_xml_validity():
    """Tüm data/ui altındaki XML dosyalarının geçerli XML formatında olduğunu doğrular."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ui_dir = os.path.join(repo_root, "data", "ui")

    assert os.path.isdir(ui_dir), "data/ui dizini mevcut olmalı"

    ui_files = [f for f in os.listdir(ui_dir) if f.endswith(".ui")]
    assert len(ui_files) >= 2, "En az main_window.ui ve classroom_tab.ui bulunmalı"

    for f in ui_files:
        path = os.path.join(ui_dir, f)
        tree = ET.parse(path)  # noqa: S314 - yerel statik ui dosyası
        root = tree.getroot()
        assert root.tag == "interface", f"{f} root etiketi <interface> olmalı"


def test_template_loader_search_paths():
    paths = TemplateLoader.get_ui_search_paths()
    assert len(paths) >= 2
    assert any("data" in p and "ui" in p for p in paths)


def test_template_loader_load_missing():
    # Var olmayan şablon None dönmeli, istisna fırlatmamalı
    res = TemplateLoader.load_template("non_existent_tab")
    assert res is None
