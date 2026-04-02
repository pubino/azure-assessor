"""Tests for the pricing module with mocked HTTP responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from azure_assessor.pricing import PricingClient


def _make_price_response(items: list[dict], next_page: str | None = None) -> dict:
    return {
        "Items": items,
        "NextPageLink": next_page,
        "Count": len(items),
    }


def _make_price_item(
    sku_name: str = "Standard_D4s_v3",
    region: str = "eastus",
    retail_price: float = 0.192,
    meter_name: str = "D4s v3",
    product_name: str = "Virtual Machines DSv3 Series",
    is_spot: bool = False,
) -> dict:
    return {
        "armSkuName": sku_name,
        "armRegionName": region,
        "retailPrice": retail_price,
        "unitPrice": retail_price,
        "currencyCode": "USD",
        "unitOfMeasure": "1 Hour",
        "type": "Consumption",
        "meterName": f"{meter_name} Spot" if is_spot else meter_name,
        "productName": product_name,
    }


@pytest.fixture
def mock_pricing_client():
    """Create a PricingClient with mocked HTTP client."""
    with patch("azure_assessor.pricing.httpx.Client") as mock_http:
        client = PricingClient()
        client._client = mock_http.return_value
        yield client, mock_http.return_value


class TestGetVmPrices:
    def test_basic_pricing(self, mock_pricing_client):
        client, mock_http = mock_pricing_client
        response_data = _make_price_response([
            _make_price_item(),
        ])
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_data
        mock_resp.raise_for_status = MagicMock()
        mock_http.get.return_value = mock_resp

        prices = client.get_vm_prices("Standard_D4s_v3", "eastus")
        assert len(prices) >= 1
        assert prices[0].sku_name == "Standard_D4s_v3"
        assert prices[0].retail_price == 0.192

    def test_spot_pricing(self, mock_pricing_client):
        client, mock_http = mock_pricing_client

        # First call returns consumption, second returns spot
        consumption_resp = MagicMock()
        consumption_resp.json.return_value = _make_price_response([
            _make_price_item(),
        ])
        consumption_resp.raise_for_status = MagicMock()

        spot_resp = MagicMock()
        spot_resp.json.return_value = _make_price_response([
            _make_price_item(retail_price=0.038, is_spot=True),
        ])
        spot_resp.raise_for_status = MagicMock()

        mock_http.get.side_effect = [consumption_resp, spot_resp]

        prices = client.get_vm_prices("Standard_D4s_v3", "eastus")
        consumption = [p for p in prices if not p.is_spot]
        spot = [p for p in prices if p.is_spot]
        assert len(consumption) >= 1
        assert len(spot) >= 1
        assert spot[0].retail_price == 0.038

    def test_pagination(self, mock_pricing_client):
        client, mock_http = mock_pricing_client

        page1 = _make_price_response(
            [_make_price_item(retail_price=0.192)],
            next_page="https://prices.azure.com/api/retail/prices?page=2",
        )
        page2 = _make_price_response(
            [_make_price_item(retail_price=0.384, meter_name="D8s v3")],
        )

        resp1 = MagicMock()
        resp1.json.return_value = page1
        resp1.raise_for_status = MagicMock()

        resp2 = MagicMock()
        resp2.json.return_value = page2
        resp2.raise_for_status = MagicMock()

        # spot call returns empty
        spot_resp = MagicMock()
        spot_resp.json.return_value = _make_price_response([])
        spot_resp.raise_for_status = MagicMock()

        mock_http.get.side_effect = [resp1, resp2, spot_resp]

        prices = client.get_vm_prices("Standard_D4s_v3", "eastus")
        assert len(prices) >= 2

    def test_empty_results(self, mock_pricing_client):
        client, mock_http = mock_pricing_client
        empty_resp = MagicMock()
        empty_resp.json.return_value = _make_price_response([])
        empty_resp.raise_for_status = MagicMock()
        mock_http.get.return_value = empty_resp

        prices = client.get_vm_prices("Standard_NonExistent", "eastus")
        assert prices == []


class TestGetSpotPrice:
    def test_spot_price_found(self, mock_pricing_client):
        client, mock_http = mock_pricing_client
        resp = MagicMock()
        resp.json.return_value = _make_price_response([
            _make_price_item(retail_price=0.038, is_spot=True),
        ])
        resp.raise_for_status = MagicMock()
        mock_http.get.return_value = resp

        result = client.get_spot_price("Standard_D4s_v3", "eastus")
        assert result is not None
        assert result.retail_price == 0.038

    def test_spot_price_not_found(self, mock_pricing_client):
        client, mock_http = mock_pricing_client
        resp = MagicMock()
        resp.json.return_value = _make_price_response([])
        resp.raise_for_status = MagicMock()
        mock_http.get.return_value = resp

        result = client.get_spot_price("Standard_D4s_v3", "eastus")
        assert result is None


class TestContextManager:
    def test_context_manager(self, mock_pricing_client):
        client, mock_http = mock_pricing_client
        with client:
            pass
        mock_http.close.assert_called_once()
