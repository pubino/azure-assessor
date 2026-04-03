"""Shared test fixtures and mock data for Azure Assessor tests."""

from __future__ import annotations

import pytest

from azure_assessor.models import (
    AssessmentResult,
    ImageInfo,
    PriceInfo,
    QuotaInfo,
    ServiceCostEstimate,
    SkuAvailability,
    SkuRecommendation,
    VmSku,
)


@pytest.fixture
def sample_sku_d4s_v3() -> VmSku:
    return VmSku(
        name="Standard_D4s_v3",
        family="standardDSv3Family",
        size="D4s_v3",
        tier="Standard",
        vcpus=4,
        memory_gb=16.0,
        max_data_disks=8,
        os_disk_size_gb=1023,
        max_nics=2,
        accelerated_networking=True,
        capabilities={
            "vCPUs": "4",
            "MemoryGB": "16",
            "MaxDataDiskCount": "8",
            "MaxNetworkInterfaces": "2",
            "AcceleratedNetworkingEnabled": "True",
            "HyperVGenerations": "V1,V2",
            "CpuArchitectureType": "x64",
        },
    )


@pytest.fixture
def sample_sku_d8s_v3() -> VmSku:
    return VmSku(
        name="Standard_D8s_v3",
        family="standardDSv3Family",
        size="D8s_v3",
        tier="Standard",
        vcpus=8,
        memory_gb=32.0,
        max_data_disks=16,
        os_disk_size_gb=1023,
        max_nics=4,
        accelerated_networking=True,
        capabilities={
            "vCPUs": "8",
            "MemoryGB": "32",
            "MaxDataDiskCount": "16",
            "MaxNetworkInterfaces": "4",
            "AcceleratedNetworkingEnabled": "True",
            "HyperVGenerations": "V1,V2",
            "CpuArchitectureType": "x64",
        },
    )


@pytest.fixture
def sample_sku_e4s_v5() -> VmSku:
    return VmSku(
        name="Standard_E4s_v5",
        family="standardESv5Family",
        size="E4s_v5",
        tier="Standard",
        vcpus=4,
        memory_gb=32.0,
        max_data_disks=8,
        os_disk_size_gb=1023,
        max_nics=2,
        accelerated_networking=True,
        capabilities={
            "vCPUs": "4",
            "MemoryGB": "32",
            "MaxDataDiskCount": "8",
            "MaxNetworkInterfaces": "2",
            "AcceleratedNetworkingEnabled": "True",
            "HyperVGenerations": "V1,V2",
            "CpuArchitectureType": "x64",
        },
    )


@pytest.fixture
def sample_sku_nc6() -> VmSku:
    return VmSku(
        name="Standard_NC6",
        family="standardNCFamily",
        size="NC6",
        tier="Standard",
        vcpus=6,
        memory_gb=56.0,
        max_data_disks=24,
        os_disk_size_gb=1023,
        max_nics=2,
        accelerated_networking=False,
        gpu_count=1,
        gpu_type="K80",
        capabilities={
            "vCPUs": "6",
            "MemoryGB": "56",
            "GPUs": "1",
            "GPUType": "K80",
            "HyperVGenerations": "V1",
            "CpuArchitectureType": "x64",
        },
    )


@pytest.fixture
def sample_availability() -> SkuAvailability:
    return SkuAvailability(
        sku_name="Standard_D4s_v3",
        region="eastus",
        zones=["1", "2", "3"],
        restrictions=[],
        available=True,
    )


@pytest.fixture
def sample_unavailable_sku() -> SkuAvailability:
    return SkuAvailability(
        sku_name="Standard_M128s",
        region="eastus",
        zones=[],
        restrictions=["NotAvailableForSubscription"],
        available=False,
    )


@pytest.fixture
def sample_quota() -> QuotaInfo:
    return QuotaInfo(
        family="Standard DSv3 Family vCPUs",
        region="eastus",
        current_usage=24,
        limit=100,
        unit="Count",
    )


@pytest.fixture
def sample_quota_near_limit() -> QuotaInfo:
    return QuotaInfo(
        family="Standard ESv5 Family vCPUs",
        region="eastus",
        current_usage=95,
        limit=100,
        unit="Count",
    )


@pytest.fixture
def sample_price() -> PriceInfo:
    return PriceInfo(
        sku_name="Standard_D4s_v3",
        region="eastus",
        retail_price=0.192,
        unit_price=0.192,
        currency="USD",
        unit_of_measure="1 Hour",
        price_type="Consumption",
        is_spot=False,
        meter_name="D4s v3",
        product_name="Virtual Machines DSv3 Series",
    )


@pytest.fixture
def sample_spot_price() -> PriceInfo:
    return PriceInfo(
        sku_name="Standard_D4s_v3",
        region="eastus",
        retail_price=0.038,
        unit_price=0.038,
        currency="USD",
        unit_of_measure="1 Hour",
        price_type="Consumption",
        is_spot=True,
        meter_name="D4s v3 Spot",
        product_name="Virtual Machines DSv3 Series",
    )


@pytest.fixture
def sample_image() -> ImageInfo:
    return ImageInfo(
        publisher="Canonical",
        offer="0001-com-ubuntu-server-jammy",
        sku="22_04-lts",
        version="22.04.202401010",
        architecture="x64",
        os_type="Linux",
        hyper_v_generation="V2",
    )


@pytest.fixture
def sample_image_arm() -> ImageInfo:
    return ImageInfo(
        publisher="Canonical",
        offer="0001-com-ubuntu-server-jammy",
        sku="22_04-lts-arm64",
        version="22.04.202401010",
        architecture="Arm64",
        os_type="Linux",
        hyper_v_generation="V2",
    )


@pytest.fixture
def sample_cost_estimates() -> list[ServiceCostEstimate]:
    return [
        ServiceCostEstimate(
            service_name="Virtual Machines",
            tier="Standard_D4s_v3",
            monthly_cost=140.16,
            hourly_cost=0.192,
            vcpus=4,
            memory_gb=16.0,
            spot_monthly=27.74,
            notes=["Baseline VM cost"],
        ),
        ServiceCostEstimate(
            service_name="Container Apps",
            tier="Consumption",
            monthly_cost=105.12,
            hourly_cost=0.144,
            vcpus=4,
            memory_gb=16.0,
            notes=["vCPU rate: $0.000012/s", "Mem rate: $0.0000012/GiB-s"],
        ),
        ServiceCostEstimate(
            service_name="AKS",
            tier="Standard + Standard_D4s_v3",
            monthly_cost=147.46,
            hourly_cost=0.202,
            spot_monthly=35.04,
            notes=["Mgmt fee: $0.0100/hr", "Node VM: Standard_D4s_v3"],
        ),
        ServiceCostEstimate(
            service_name="App Service",
            tier="P2v3",
            monthly_cost=175.20,
            hourly_cost=0.240,
            vcpus=4,
            memory_gb=16.0,
            notes=["Plan: P2v3", "Meter: P2 v3"],
        ),
    ]


@pytest.fixture
def sample_assessment_result(
    sample_availability, sample_quota, sample_price, sample_spot_price
) -> AssessmentResult:
    return AssessmentResult(
        target_sku="Standard_D4s_v3",
        region="eastus",
        availability=sample_availability,
        quota=sample_quota,
        pricing=sample_price,
        spot_pricing=sample_spot_price,
        alternatives=[],
        compatible_images=[],
        timestamp="2026-04-02T12:00:00+00:00",
    )
