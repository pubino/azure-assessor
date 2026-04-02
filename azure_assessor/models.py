"""Data models for Azure Assessor."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VmSku:
    """Represents a VM SKU with its capabilities."""

    name: str
    family: str
    size: str
    tier: str
    vcpus: int
    memory_gb: float
    max_data_disks: int
    os_disk_size_gb: int
    max_nics: int
    accelerated_networking: bool
    gpu_count: int = 0
    gpu_type: str = ""
    capabilities: dict[str, str] = field(default_factory=dict)


@dataclass
class SkuAvailability:
    """VM SKU availability in a region/zone."""

    sku_name: str
    region: str
    zones: list[str] = field(default_factory=list)
    restrictions: list[str] = field(default_factory=list)
    available: bool = True


@dataclass
class QuotaInfo:
    """Quota usage for a VM family in a region."""

    family: str
    region: str
    current_usage: int
    limit: int
    unit: str = "Count"

    @property
    def available(self) -> int:
        return max(0, self.limit - self.current_usage)

    @property
    def usage_percent(self) -> float:
        if self.limit == 0:
            return 0.0
        return (self.current_usage / self.limit) * 100


@dataclass
class PriceInfo:
    """Pricing information for a VM SKU."""

    sku_name: str
    region: str
    retail_price: float
    unit_price: float
    currency: str = "USD"
    unit_of_measure: str = "1 Hour"
    price_type: str = "Consumption"
    is_spot: bool = False
    meter_name: str = ""
    product_name: str = ""


@dataclass
class ImageInfo:
    """OS image information."""

    publisher: str
    offer: str
    sku: str
    version: str
    architecture: str = "x64"
    os_type: str = "Linux"
    hyper_v_generation: str = "V2"


@dataclass
class SkuRecommendation:
    """Alternative SKU recommendation with compatibility score."""

    sku: VmSku
    compatibility_score: float  # 0.0 - 1.0
    price: PriceInfo | None = None
    reasons: list[str] = field(default_factory=list)
    availability: SkuAvailability | None = None


@dataclass
class AssessmentResult:
    """Complete assessment result for export."""

    target_sku: str
    region: str
    availability: SkuAvailability | None = None
    quota: QuotaInfo | None = None
    pricing: PriceInfo | None = None
    spot_pricing: PriceInfo | None = None
    alternatives: list[SkuRecommendation] = field(default_factory=list)
    compatible_images: list[ImageInfo] = field(default_factory=list)
    timestamp: str = ""
