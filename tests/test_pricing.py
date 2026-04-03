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


def _make_container_apps_items() -> list[dict]:
    return [
        {
            "armSkuName": "",
            "armRegionName": "eastus",
            "retailPrice": 0.000024,
            "unitPrice": 0.000024,
            "currencyCode": "USD",
            "unitOfMeasure": "1 Second",
            "type": "Consumption",
            "meterName": "vCPU Duration",
            "productName": "Azure Container Apps",
        },
        {
            "armSkuName": "",
            "armRegionName": "eastus",
            "retailPrice": 0.000003,
            "unitPrice": 0.000003,
            "currencyCode": "USD",
            "unitOfMeasure": "1 GiB Second",
            "type": "Consumption",
            "meterName": "Memory Duration",
            "productName": "Azure Container Apps",
        },
    ]


def _make_aks_items() -> list[dict]:
    return [
        {
            "armSkuName": "",
            "armRegionName": "eastus",
            "retailPrice": 0.10,
            "unitPrice": 0.10,
            "currencyCode": "USD",
            "unitOfMeasure": "1 Hour",
            "type": "Consumption",
            "meterName": "Standard",
            "productName": "Azure Kubernetes Service",
        },
    ]


def _make_app_service_items() -> list[dict]:
    return [
        {
            "armSkuName": "",
            "armRegionName": "eastus",
            "retailPrice": 0.10,
            "unitPrice": 0.10,
            "currencyCode": "USD",
            "unitOfMeasure": "1 Hour",
            "type": "Consumption",
            "meterName": "B1",
            "productName": "Azure App Service Basic Plan",
        },
        {
            "armSkuName": "",
            "armRegionName": "eastus",
            "retailPrice": 0.20,
            "unitPrice": 0.20,
            "currencyCode": "USD",
            "unitOfMeasure": "1 Hour",
            "type": "Consumption",
            "meterName": "P2v3",
            "productName": "Azure App Service Premium v3 Plan",
        },
    ]


class TestGetContainerAppsPrice:
    def test_returns_estimate(self, mock_pricing_client):
        client, mock_http = mock_pricing_client
        resp = MagicMock()
        resp.json.return_value = _make_price_response(_make_container_apps_items())
        resp.raise_for_status = MagicMock()
        mock_http.get.return_value = resp

        result = client.get_container_apps_price("eastus", vcpus=4, memory_gb=16.0)
        assert result is not None
        assert result.service_name == "Container Apps"
        assert result.tier == "Consumption"
        assert result.monthly_cost > 0
        assert result.vcpus == 4
        assert result.memory_gb == 16.0

    def test_returns_none_on_empty(self, mock_pricing_client):
        client, mock_http = mock_pricing_client
        resp = MagicMock()
        resp.json.return_value = _make_price_response([])
        resp.raise_for_status = MagicMock()
        mock_http.get.return_value = resp

        result = client.get_container_apps_price("eastus", vcpus=4, memory_gb=16.0)
        assert result is None


class TestGetAksPrice:
    def test_returns_estimate_with_mgmt_fee(self, mock_pricing_client):
        client, mock_http = mock_pricing_client

        aks_resp = MagicMock()
        aks_resp.json.return_value = _make_price_response(_make_aks_items())
        aks_resp.raise_for_status = MagicMock()

        vm_resp = MagicMock()
        vm_resp.json.return_value = _make_price_response([_make_price_item()])
        vm_resp.raise_for_status = MagicMock()

        spot_resp = MagicMock()
        spot_resp.json.return_value = _make_price_response([
            _make_price_item(retail_price=0.038, is_spot=True),
        ])
        spot_resp.raise_for_status = MagicMock()

        mock_http.get.side_effect = [aks_resp, vm_resp, spot_resp]

        result = client.get_aks_price("eastus", "Standard_D4s_v3")
        assert result is not None
        assert result.service_name == "AKS"
        assert "Standard" in result.tier
        # Monthly = (0.10 mgmt + 0.192 vm) * 730
        expected = round((0.10 + 0.192) * 730, 2)
        assert result.monthly_cost == expected
        assert result.spot_monthly is not None

    def test_free_tier_no_mgmt_fee(self, mock_pricing_client):
        client, mock_http = mock_pricing_client

        aks_resp = MagicMock()
        aks_resp.json.return_value = _make_price_response([])
        aks_resp.raise_for_status = MagicMock()

        vm_resp = MagicMock()
        vm_resp.json.return_value = _make_price_response([_make_price_item()])
        vm_resp.raise_for_status = MagicMock()

        spot_resp = MagicMock()
        spot_resp.json.return_value = _make_price_response([])
        spot_resp.raise_for_status = MagicMock()

        mock_http.get.side_effect = [aks_resp, vm_resp, spot_resp]

        result = client.get_aks_price("eastus", "Standard_D4s_v3")
        assert result is not None
        assert "Free" in result.tier
        expected = round(0.192 * 730, 2)
        assert result.monthly_cost == expected
        assert result.spot_monthly is None


class TestGetAppServicePrice:
    def test_returns_matching_plan(self, mock_pricing_client):
        client, mock_http = mock_pricing_client
        resp = MagicMock()
        resp.json.return_value = _make_price_response(_make_app_service_items())
        resp.raise_for_status = MagicMock()
        mock_http.get.return_value = resp

        result = client.get_app_service_price("eastus", vcpus=4, memory_gb=16.0)
        assert result is not None
        assert result.service_name == "App Service"
        assert result.tier == "P2v3"
        assert result.monthly_cost == round(0.20 * 730, 2)

    def test_picks_cheapest_matching(self, mock_pricing_client):
        client, mock_http = mock_pricing_client
        resp = MagicMock()
        resp.json.return_value = _make_price_response(_make_app_service_items())
        resp.raise_for_status = MagicMock()
        mock_http.get.return_value = resp

        # Requesting 1 vCPU, 1 GB — B1 (1 vCPU, 1.75 GB) should match at $0.10/hr
        result = client.get_app_service_price("eastus", vcpus=1, memory_gb=1.0)
        assert result is not None
        assert result.tier == "B1"
        assert result.monthly_cost == round(0.10 * 730, 2)

    def test_returns_none_when_no_match(self, mock_pricing_client):
        client, mock_http = mock_pricing_client
        resp = MagicMock()
        resp.json.return_value = _make_price_response([])
        resp.raise_for_status = MagicMock()
        mock_http.get.return_value = resp

        result = client.get_app_service_price("eastus", vcpus=4, memory_gb=16.0)
        assert result is None


class TestEstimateMonthlyCosts:
    def test_returns_all_services(self, mock_pricing_client):
        client, mock_http = mock_pricing_client

        # VM consumption
        vm_consumption_resp = MagicMock()
        vm_consumption_resp.json.return_value = _make_price_response([_make_price_item()])
        vm_consumption_resp.raise_for_status = MagicMock()

        # VM spot (empty)
        vm_spot_resp = MagicMock()
        vm_spot_resp.json.return_value = _make_price_response([])
        vm_spot_resp.raise_for_status = MagicMock()

        # Container Apps
        ca_resp = MagicMock()
        ca_resp.json.return_value = _make_price_response(_make_container_apps_items())
        ca_resp.raise_for_status = MagicMock()

        # AKS management
        aks_resp = MagicMock()
        aks_resp.json.return_value = _make_price_response(_make_aks_items())
        aks_resp.raise_for_status = MagicMock()

        # AKS node VM consumption
        aks_vm_resp = MagicMock()
        aks_vm_resp.json.return_value = _make_price_response([_make_price_item()])
        aks_vm_resp.raise_for_status = MagicMock()

        # AKS node VM spot
        aks_spot_resp = MagicMock()
        aks_spot_resp.json.return_value = _make_price_response([])
        aks_spot_resp.raise_for_status = MagicMock()

        # App Service
        app_resp = MagicMock()
        app_resp.json.return_value = _make_price_response(_make_app_service_items())
        app_resp.raise_for_status = MagicMock()

        mock_http.get.side_effect = [
            vm_consumption_resp, vm_spot_resp,  # estimate_monthly_costs -> get_vm_prices
            ca_resp,                             # get_container_apps_price
            aks_resp, aks_vm_resp, aks_spot_resp, # get_aks_price
            app_resp,                             # get_app_service_price
        ]

        results = client.estimate_monthly_costs(
            "Standard_D4s_v3", "eastus", vcpus=4, memory_gb=16.0,
        )
        service_names = [r.service_name for r in results]
        assert "Virtual Machines" in service_names
        assert "Container Apps" in service_names
        assert "AKS" in service_names
        assert "App Service" in service_names

    def test_handles_no_pricing(self, mock_pricing_client):
        client, mock_http = mock_pricing_client
        empty_resp = MagicMock()
        empty_resp.json.return_value = _make_price_response([])
        empty_resp.raise_for_status = MagicMock()
        mock_http.get.return_value = empty_resp

        results = client.estimate_monthly_costs(
            "Standard_NonExistent", "westus99", vcpus=4, memory_gb=16.0,
        )
        assert results == []
