"""Tests for the TUI application."""

from __future__ import annotations

import pytest
from textual.widgets import DataTable, Input, Static

from azure_assessor.app import (
    AzureAssessorApp,
    DetailScreen,
    _detail_fields_availability,
    _detail_fields_cost,
    _detail_fields_image,
    _detail_fields_pricing,
    _detail_fields_quota,
    _detail_fields_recommendation,
)
from azure_assessor.models import (
    ImageInfo,
    PriceInfo,
    QuotaInfo,
    ServiceCostEstimate,
    SkuAvailability,
    SkuRecommendation,
    VmSku,
)


class TestDetailFields:
    """Unit tests for the detail field extraction functions."""

    def test_availability_fields(self, sample_availability):
        title, fields = _detail_fields_availability(sample_availability)
        assert "Standard_D4s_v3" in title
        labels = [f[0] for f in fields]
        assert "SKU Name" in labels
        assert "Region" in labels
        assert "Available" in labels
        assert "Zones" in labels
        assert "Restrictions" in labels
        vals = dict(fields)
        assert vals["Available"] == "Yes"
        assert "1" in vals["Zones"]

    def test_availability_fields_unavailable(self, sample_unavailable_sku):
        title, fields = _detail_fields_availability(sample_unavailable_sku)
        vals = dict(fields)
        assert vals["Available"] == "No"
        assert "NotAvailableForSubscription" in vals["Restrictions"]

    def test_quota_fields(self, sample_quota):
        title, fields = _detail_fields_quota(sample_quota)
        assert "Standard DSv3" in title
        vals = dict(fields)
        assert vals["Current Usage"] == "24"
        assert vals["Limit"] == "100"
        assert vals["Available"] == "76"
        assert vals["Usage %"] == "24.0%"
        assert vals["Unit"] == "Count"

    def test_pricing_fields_both(self, sample_price, sample_spot_price):
        title, fields = _detail_fields_pricing(sample_price, sample_spot_price)
        assert "Standard_D4s_v3" in title
        labels = [f[0] for f in fields]
        assert "Retail Price" in labels
        assert "Spot Retail Price" in labels
        vals = dict(fields)
        assert "$0.1920" in vals["Retail Price"]
        assert "$0.0380" in vals["Spot Retail Price"]

    def test_pricing_fields_consumption_only(self, sample_price):
        title, fields = _detail_fields_pricing(sample_price, None)
        labels = [f[0] for f in fields]
        assert "Retail Price" in labels
        assert "Spot Retail Price" not in labels

    def test_pricing_fields_none(self):
        title, fields = _detail_fields_pricing(None, None)
        assert "N/A" in title
        assert fields[0][0] == "Info"

    def test_recommendation_fields(self, sample_sku_d4s_v3, sample_price, sample_availability):
        rec = SkuRecommendation(
            sku=sample_sku_d4s_v3,
            compatibility_score=0.85,
            price=sample_price,
            reasons=["Same family", "Same vCPUs"],
            availability=sample_availability,
        )
        title, fields = _detail_fields_recommendation(rec)
        assert "Standard_D4s_v3" in title
        vals = dict(fields)
        assert vals["vCPUs"] == "4"
        assert vals["Memory (GB)"] == "16.0"
        assert "85.0%" in vals["Compatibility Score"]
        assert "Same family" in vals["Reasons"]
        assert vals["Available"] == "Yes"

    def test_recommendation_fields_gpu(self, sample_sku_nc6):
        rec = SkuRecommendation(
            sku=sample_sku_nc6,
            compatibility_score=0.5,
            reasons=["GPU workload"],
        )
        title, fields = _detail_fields_recommendation(rec)
        vals = dict(fields)
        assert vals["GPU Count"] == "1"
        assert vals["GPU Type"] == "K80"

    def test_image_fields(self, sample_image):
        title, fields = _detail_fields_image(sample_image)
        assert "Canonical" in title
        vals = dict(fields)
        assert vals["Publisher"] == "Canonical"
        assert vals["Architecture"] == "x64"
        assert vals["Hyper-V Generation"] == "V2"
        assert len(fields) == 7

    def test_cost_fields(self, sample_cost_estimates):
        est = sample_cost_estimates[0]  # Virtual Machines
        title, fields = _detail_fields_cost(est)
        assert "Virtual Machines" in title
        vals = dict(fields)
        assert vals["Service"] == "Virtual Machines"
        assert "$140.16" in vals["Monthly Cost"]
        assert "$27.74" in vals["Spot Monthly"]
        assert "Baseline VM cost" in vals["Notes"]

    def test_cost_fields_no_spot(self, sample_cost_estimates):
        est = sample_cost_estimates[1]  # Container Apps, no spot
        title, fields = _detail_fields_cost(est)
        vals = dict(fields)
        assert vals["Spot Monthly"] == "N/A"


class TestDetailScreen:
    """Async TUI tests for the DetailScreen modal."""

    @pytest.mark.asyncio
    async def test_detail_screen_renders(self):
        app = AzureAssessorApp()
        async with app.run_test() as pilot:
            fields = [("Name", "Test"), ("Value", "123")]
            app.push_screen(DetailScreen("Test Detail", fields))
            await pilot.pause()
            await pilot.pause()
            # Check that static widgets with field content exist on the active screen
            statics = app.screen.query(".detail-field")
            assert len(statics) == 2

    @pytest.mark.asyncio
    async def test_detail_screen_close_button(self):
        app = AzureAssessorApp()
        async with app.run_test() as pilot:
            fields = [("Name", "Test")]
            app.push_screen(DetailScreen("Test Detail", fields))
            await pilot.pause()
            await pilot.click("#btn-detail-close")
            await pilot.pause()
            # Modal should be dismissed, no detail-field widgets
            assert len(app.query(".detail-field")) == 0

    @pytest.mark.asyncio
    async def test_detail_screen_escape(self):
        app = AzureAssessorApp()
        async with app.run_test() as pilot:
            fields = [("Name", "Test")]
            app.push_screen(DetailScreen("Test Detail", fields))
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.query(".detail-field")) == 0

    @pytest.mark.asyncio
    async def test_clear_clears_row_data(self):
        app = AzureAssessorApp()
        async with app.run_test() as pilot:
            # Add some fake row data
            app._row_data["fake-key"] = "fake-value"
            assert len(app._row_data) == 1
            await pilot.click("#btn-clear")
            await pilot.pause()
            assert len(app._row_data) == 0

    @pytest.mark.asyncio
    async def test_tables_have_row_cursor(self):
        app = AzureAssessorApp()
        async with app.run_test() as pilot:
            for tid in ["#table-avail", "#table-quota", "#table-pricing",
                        "#table-alt", "#table-images", "#table-costs"]:
                table = app.query_one(tid, DataTable)
                assert table.cursor_type == "row"


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
