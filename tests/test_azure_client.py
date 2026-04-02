"""Tests for the Azure client module with mocked Azure SDK."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from azure_assessor.azure_client import AzureClient
from azure_assessor.models import ImageInfo


def _make_resource_sku(
    name: str,
    family: str = "standardDSv3Family",
    location: str = "eastus",
    zones: list[str] | None = None,
    restrictions: list | None = None,
    capabilities: dict[str, str] | None = None,
):
    """Helper to create a mock ResourceSku object."""
    caps = capabilities or {
        "vCPUs": "4",
        "MemoryGB": "16",
        "MaxDataDiskCount": "8",
        "OSVhdSizeMB": "1047552",
        "MaxNetworkInterfaces": "2",
        "AcceleratedNetworkingEnabled": "True",
    }
    cap_list = [SimpleNamespace(name=k, value=v) for k, v in caps.items()]

    loc_info = [
        SimpleNamespace(
            location=location,
            zones=zones or ["1", "2", "3"],
        )
    ]

    restriction_list = []
    if restrictions:
        for r in restrictions:
            restriction_list.append(SimpleNamespace(reason_code=r))

    return SimpleNamespace(
        name=name,
        resource_type="virtualMachines",
        family=family,
        size=name.replace("Standard_", ""),
        tier="Standard",
        capabilities=cap_list,
        location_info=loc_info,
        restrictions=restriction_list,
    )


def _make_usage(name_value: str, localized: str, current: int, limit: int):
    """Helper to create a mock Usage object."""
    return SimpleNamespace(
        name=SimpleNamespace(value=name_value, localized_value=localized),
        current_value=current,
        limit=limit,
        unit="Count",
    )


@pytest.fixture
def mock_azure_client():
    """Create an AzureClient with mocked Azure SDK clients."""
    with (
        patch("azure_assessor.azure_client.DefaultAzureCredential"),
        patch("azure_assessor.azure_client.ComputeManagementClient") as mock_compute,
        patch("azure_assessor.azure_client.SubscriptionClient") as mock_sub,
    ):
        # Mock subscription
        mock_sub_instance = mock_sub.return_value
        mock_sub_list = MagicMock()
        mock_sub_list.__iter__ = MagicMock(
            return_value=iter(
                [SimpleNamespace(subscription_id="test-sub-id", state="Enabled")]
            )
        )
        mock_sub_instance.subscriptions.list.return_value = mock_sub_list

        client = AzureClient()
        client.compute_client = mock_compute.return_value
        yield client


class TestListVmSkus:
    def test_list_returns_vm_skus(self, mock_azure_client):
        skus = [
            _make_resource_sku("Standard_D4s_v3"),
            _make_resource_sku("Standard_D8s_v3", capabilities={
                "vCPUs": "8", "MemoryGB": "32", "MaxDataDiskCount": "16",
                "OSVhdSizeMB": "1047552", "MaxNetworkInterfaces": "4",
                "AcceleratedNetworkingEnabled": "True",
            }),
        ]
        mock_azure_client.compute_client.resource_skus.list.return_value = skus

        result = mock_azure_client.list_vm_skus("eastus")
        assert len(result) == 2
        assert result[0].name == "Standard_D4s_v3"
        assert result[0].vcpus == 4
        assert result[1].name == "Standard_D8s_v3"
        assert result[1].vcpus == 8

    def test_filters_non_vm_resources(self, mock_azure_client):
        vm_sku = _make_resource_sku("Standard_D4s_v3")
        disk_sku = SimpleNamespace(
            name="Premium_LRS",
            resource_type="disks",
            family="",
            size="",
            tier="Premium",
            capabilities=[],
            location_info=[],
            restrictions=[],
        )
        mock_azure_client.compute_client.resource_skus.list.return_value = [vm_sku, disk_sku]

        result = mock_azure_client.list_vm_skus("eastus")
        assert len(result) == 1
        assert result[0].name == "Standard_D4s_v3"


class TestCheckSkuAvailability:
    def test_available_sku(self, mock_azure_client):
        skus = [_make_resource_sku("Standard_D4s_v3")]
        mock_azure_client.compute_client.resource_skus.list.return_value = skus

        result = mock_azure_client.check_sku_availability("eastus", "Standard_D4s_v3")
        assert len(result) == 1
        assert result[0].available is True
        assert result[0].zones == ["1", "2", "3"]

    def test_restricted_sku(self, mock_azure_client):
        skus = [
            _make_resource_sku(
                "Standard_M128s",
                family="standardMSFamily",
                restrictions=["NotAvailableForSubscription"],
            )
        ]
        mock_azure_client.compute_client.resource_skus.list.return_value = skus

        result = mock_azure_client.check_sku_availability("eastus", "Standard_M128s")
        assert len(result) == 1
        assert result[0].available is False
        assert "NotAvailableForSubscription" in result[0].restrictions

    def test_filter_by_sku_name(self, mock_azure_client):
        skus = [
            _make_resource_sku("Standard_D4s_v3"),
            _make_resource_sku("Standard_D8s_v3"),
        ]
        mock_azure_client.compute_client.resource_skus.list.return_value = skus

        result = mock_azure_client.check_sku_availability("eastus", "Standard_D4s_v3")
        assert len(result) == 1
        assert result[0].sku_name == "Standard_D4s_v3"

    def test_all_skus_when_no_filter(self, mock_azure_client):
        skus = [
            _make_resource_sku("Standard_D4s_v3"),
            _make_resource_sku("Standard_D8s_v3"),
        ]
        mock_azure_client.compute_client.resource_skus.list.return_value = skus

        result = mock_azure_client.check_sku_availability("eastus")
        assert len(result) == 2


class TestGetQuotas:
    def test_get_quotas(self, mock_azure_client):
        usages = [
            _make_usage("standardDSv3Family", "Standard DSv3 Family vCPUs", 24, 100),
            _make_usage("standardESv5Family", "Standard ESv5 Family vCPUs", 0, 50),
        ]
        mock_azure_client.compute_client.usage.list.return_value = usages

        result = mock_azure_client.get_quotas("eastus")
        assert len(result) == 2
        assert result[0].family == "Standard DSv3 Family vCPUs"
        assert result[0].current_usage == 24
        assert result[0].limit == 100
        assert result[0].available == 76


class TestImageSkuCompatibility:
    def test_compatible_image(self, mock_azure_client, sample_sku_d4s_v3, sample_image):
        compatible, issues = mock_azure_client.check_image_sku_compatibility(
            sample_sku_d4s_v3, sample_image
        )
        assert compatible is True
        assert issues == []

    def test_incompatible_architecture(self, mock_azure_client, sample_sku_d4s_v3, sample_image_arm):
        compatible, issues = mock_azure_client.check_image_sku_compatibility(
            sample_sku_d4s_v3, sample_image_arm
        )
        assert compatible is False
        assert any("architecture" in issue.lower() for issue in issues)

    def test_incompatible_hyperv_gen(self, mock_azure_client, sample_sku_d4s_v3):
        # SKU that only supports V1
        sku = sample_sku_d4s_v3
        sku.capabilities["HyperVGenerations"] = "V1"
        image = ImageInfo(
            publisher="test", offer="test", sku="test", version="1.0",
            architecture="x64", os_type="Linux", hyper_v_generation="V2",
        )
        compatible, issues = mock_azure_client.check_image_sku_compatibility(sku, image)
        assert compatible is False
        assert any("V2" in issue for issue in issues)
