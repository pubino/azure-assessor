"""Tests for the TUI application."""

from __future__ import annotations

import pytest
from textual.widgets import DataTable, Input

from azure_assessor.app import AzureAssessorApp


class TestAppCreation:
    def test_app_instantiates(self):
        app = AzureAssessorApp()
        assert app is not None
        assert app.TITLE == "Azure VM Assessor"

    def test_app_with_mock_clients(self):
        from unittest.mock import MagicMock
        mock_azure = MagicMock()
        mock_pricing = MagicMock()
        app = AzureAssessorApp(
            azure_client=mock_azure,
            pricing_client=mock_pricing,
        )
        assert app._azure_client is mock_azure
        assert app._pricing_client is mock_pricing


class TestAppCompose:
    @pytest.mark.asyncio
    async def test_app_mounts(self):
        app = AzureAssessorApp()
        async with app.run_test() as pilot:
            # Verify key widgets exist
            assert app.query_one("#region-input", Input) is not None
            assert app.query_one("#sku-input", Input) is not None
            assert app.query_one("#image-input", Input) is not None
            assert app.query_one("#table-avail", DataTable) is not None
            assert app.query_one("#table-quota", DataTable) is not None
            assert app.query_one("#table-pricing", DataTable) is not None
            assert app.query_one("#table-alt", DataTable) is not None
            assert app.query_one("#table-images", DataTable) is not None

    @pytest.mark.asyncio
    async def test_assess_requires_region(self):
        app = AzureAssessorApp()
        async with app.run_test() as pilot:
            # Click assess without entering region
            await pilot.click("#btn-assess")
            # Should show error notification (no crash)

    @pytest.mark.asyncio
    async def test_assess_requires_sku(self):
        app = AzureAssessorApp()
        async with app.run_test() as pilot:
            # Enter region but no SKU
            region_input = app.query_one("#region-input", Input)
            region_input.value = "eastus"
            await pilot.click("#btn-assess")
            # Should show error notification (no crash)

    @pytest.mark.asyncio
    async def test_export_no_results(self):
        app = AzureAssessorApp()
        async with app.run_test() as pilot:
            await pilot.click("#btn-export")
            # Should show warning (no results to export)

    @pytest.mark.asyncio
    async def test_clear_results(self):
        app = AzureAssessorApp()
        async with app.run_test() as pilot:
            await pilot.click("#btn-clear")
            table = app.query_one("#table-avail", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    async def test_keybindings_exist(self):
        app = AzureAssessorApp()
        async with app.run_test() as pilot:
            binding_keys = {b.key for b in app.BINDINGS}
            assert "q" in binding_keys
            assert "a" in binding_keys
            assert "e" in binding_keys
            assert "r" in binding_keys
