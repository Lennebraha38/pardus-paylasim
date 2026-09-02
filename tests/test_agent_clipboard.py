"""Faz 3.3: Pano adaptörü testleri."""

from __future__ import annotations

import os

import pytest

from pardus_paylasim_agent.clipboard_adapter import (
    ClipboardAdapter,
    NoOpClipboardAdapter,
    Win32ClipboardAdapter,
    create_clipboard_adapter,
)


class TestClipboardAdapter:
    """Pano backend testleri."""

    @pytest.mark.skipif(os.name != "nt", reason="Yalnız Windows")
    def test_win32_protocol_uyumu(self) -> None:
        adapter = Win32ClipboardAdapter()
        assert isinstance(adapter, ClipboardAdapter)

    def test_noop_protocol_uyumu(self) -> None:
        adapter = NoOpClipboardAdapter()
        assert isinstance(adapter, ClipboardAdapter)

    def test_noop_get_none_doner(self) -> None:
        adapter = NoOpClipboardAdapter()
        assert adapter.get_text() is None

    def test_noop_set_hata_firlatmaz(self) -> None:
        adapter = NoOpClipboardAdapter()
        adapter.set_text("test")  # Hata fırlatmamalı

    def test_create_adapter_gecerli_tip_doner(self) -> None:
        adapter = create_clipboard_adapter()
        assert isinstance(adapter, ClipboardAdapter)
