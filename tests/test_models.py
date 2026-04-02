"""Tests for data models."""

from azure_assessor.models import (
    AssessmentResult,
    ImageInfo,
    PriceInfo,
    QuotaInfo,
    SkuAvailability,
    SkuRecommendation,
    VmSku,
)


class TestVmSku:
    def test_basic_creation(self, sample_sku_d4s_v3):
        sku = sample_sku_d4s_v3
        assert sku.name == "Standard_D4s_v3"
        assert sku.vcpus == 4
        assert sku.memory_gb == 16.0
        assert sku.accelerated_networking is True
        assert sku.gpu_count == 0

    def test_gpu_sku(self, sample_sku_nc6):
        assert sample_sku_nc6.gpu_count == 1
        assert sample_sku_nc6.gpu_type == "K80"


class TestSkuAvailability:
    def test_available_sku(self, sample_availability):
        assert sample_availability.available is True
        assert sample_availability.zones == ["1", "2", "3"]
        assert sample_availability.restrictions == []

    def test_unavailable_sku(self, sample_unavailable_sku):
        assert sample_unavailable_sku.available is False
        assert "NotAvailableForSubscription" in sample_unavailable_sku.restrictions


class TestQuotaInfo:
    def test_available_quota(self, sample_quota):
        assert sample_quota.available == 76
        assert sample_quota.usage_percent == 24.0

    def test_near_limit_quota(self, sample_quota_near_limit):
        assert sample_quota_near_limit.available == 5
        assert sample_quota_near_limit.usage_percent == 95.0

    def test_zero_limit(self):
        q = QuotaInfo(family="test", region="eastus", current_usage=0, limit=0)
        assert q.available == 0
        assert q.usage_percent == 0.0


class TestPriceInfo:
    def test_consumption_price(self, sample_price):
        assert sample_price.retail_price == 0.192
        assert sample_price.is_spot is False

    def test_spot_price(self, sample_spot_price, sample_price):
        assert sample_spot_price.is_spot is True
        assert sample_spot_price.retail_price < sample_price.retail_price


class TestImageInfo:
    def test_basic_image(self, sample_image):
        assert sample_image.publisher == "Canonical"
        assert sample_image.architecture == "x64"
        assert sample_image.hyper_v_generation == "V2"


class TestAssessmentResult:
    def test_complete_result(self, sample_assessment_result):
        r = sample_assessment_result
        assert r.target_sku == "Standard_D4s_v3"
        assert r.region == "eastus"
        assert r.availability is not None
        assert r.availability.available is True
        assert r.quota is not None
        assert r.pricing is not None
        assert r.spot_pricing is not None
