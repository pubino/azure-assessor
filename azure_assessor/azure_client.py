"""Azure SDK wrapper for VM SKU availability, quotas, and image compatibility."""

from __future__ import annotations

from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.subscription import SubscriptionClient

from azure_assessor.models import (
    ImageInfo,
    QuotaInfo,
    SkuAvailability,
    VmSku,
)


class AzureClient:
    """Wrapper around Azure SDK for VM-related queries."""

    def __init__(self, subscription_id: str | None = None) -> None:
        self.credential = DefaultAzureCredential()
        self.subscription_id = subscription_id or self._get_default_subscription()
        self.compute_client = ComputeManagementClient(
            self.credential, self.subscription_id
        )

    def _get_default_subscription(self) -> str:
        # Fast path: read from az cli config (no network call)
        import subprocess

        try:
            result = subprocess.run(
                ["az", "account", "show", "--query", "id", "-o", "tsv"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback: enumerate via SDK
        sub_client = SubscriptionClient(self.credential)
        for sub in sub_client.subscriptions.list():
            if sub.state == "Enabled":
                return sub.subscription_id
        raise RuntimeError("No enabled Azure subscription found")

    def list_regions(self) -> list[str]:
        """List available Azure regions for the subscription."""
        sub_client = SubscriptionClient(self.credential)
        locations = sub_client.subscriptions.list_locations(self.subscription_id)
        return sorted([loc.name for loc in locations if loc.name])

    def list_vm_skus(self, region: str) -> list[VmSku]:
        """List all VM SKUs available in a region."""
        skus = []
        resource_skus = self.compute_client.resource_skus.list(
            filter=f"location eq '{region}'"
        )
        for sku in resource_skus:
            if sku.resource_type != "virtualMachines":
                continue
            caps = {c.name: c.value for c in (sku.capabilities or [])}
            skus.append(
                VmSku(
                    name=sku.name,
                    family=sku.family or "",
                    size=sku.size or "",
                    tier=sku.tier or "Standard",
                    vcpus=int(caps.get("vCPUs", 0)),
                    memory_gb=float(caps.get("MemoryGB", 0)),
                    max_data_disks=int(caps.get("MaxDataDiskCount", 0)),
                    os_disk_size_gb=int(caps.get("OSVhdSizeMB", 0)) // 1024,
                    max_nics=int(caps.get("MaxNetworkInterfaces", 0)),
                    accelerated_networking=caps.get("AcceleratedNetworkingEnabled", "False") == "True",
                    gpu_count=int(caps.get("GPUs", 0)),
                    gpu_type=caps.get("GPUType", ""),
                    capabilities=caps,
                )
            )
        return skus

    def check_sku_availability(self, region: str, sku_name: str | None = None) -> list[SkuAvailability]:
        """Check VM SKU availability including zone and restriction info."""
        results = []
        resource_skus = self.compute_client.resource_skus.list(
            filter=f"location eq '{region}'"
        )
        for sku in resource_skus:
            if sku.resource_type != "virtualMachines":
                continue
            if sku_name and sku.name != sku_name:
                continue

            zones = []
            restrictions = []
            available = True

            for loc_info in (sku.location_info or []):
                if loc_info.location and loc_info.location.lower() == region.lower():
                    zones = [z for z in (loc_info.zones or [])]

            for restriction in (sku.restrictions or []):
                reason = restriction.reason_code or "Unknown"
                restrictions.append(reason)
                if reason == "NotAvailableForSubscription":
                    available = False

            results.append(
                SkuAvailability(
                    sku_name=sku.name,
                    region=region,
                    zones=zones,
                    restrictions=restrictions,
                    available=available,
                )
            )
        return results

    def get_quotas(self, region: str) -> list[QuotaInfo]:
        """Get compute quota usage for a region."""
        quotas = []
        usages = self.compute_client.usage.list(region)
        for usage in usages:
            if not usage.name or not usage.name.value:
                continue
            quotas.append(
                QuotaInfo(
                    family=usage.name.localized_value or usage.name.value,
                    region=region,
                    current_usage=usage.current_value or 0,
                    limit=usage.limit or 0,
                    unit=usage.unit or "Count",
                )
            )
        return quotas

    def list_vm_images(
        self, region: str, publisher: str, offer: str, sku: str
    ) -> list[ImageInfo]:
        """List available VM images for a publisher/offer/sku combination."""
        images = []
        try:
            result = self.compute_client.virtual_machine_images.list(
                location=region,
                publisher_name=publisher,
                offer=offer,
                skus=sku,
            )
            for img in result:
                detail = self.compute_client.virtual_machine_images.get(
                    location=region,
                    publisher_name=publisher,
                    offer=offer,
                    skus=sku,
                    version=img.name,
                )
                os_disk = detail.os_disk_image
                images.append(
                    ImageInfo(
                        publisher=publisher,
                        offer=offer,
                        sku=sku,
                        version=img.name,
                        architecture=getattr(detail, "architecture", "x64") or "x64",
                        os_type=os_disk.operating_system if os_disk else "Linux",
                        hyper_v_generation=getattr(detail, "hyper_v_generation", "V2") or "V2",
                    )
                )
        except Exception:
            pass
        return images

    def check_image_sku_compatibility(
        self, sku: VmSku, image: ImageInfo
    ) -> tuple[bool, list[str]]:
        """Check if a VM SKU is compatible with a given image."""
        issues = []
        caps = sku.capabilities

        # Check HyperV generation
        supported_gens = caps.get("HyperVGenerations", "V1,V2")
        if image.hyper_v_generation not in supported_gens.split(","):
            issues.append(
                f"SKU supports {supported_gens} but image requires {image.hyper_v_generation}"
            )

        # Check architecture
        sku_arch = caps.get("CpuArchitectureType", "x64")
        if image.architecture != sku_arch:
            issues.append(
                f"SKU architecture is {sku_arch} but image requires {image.architecture}"
            )

        # Check trusted launch
        if caps.get("TrustedLaunchDisabled", "False") == "True":
            issues.append("SKU does not support Trusted Launch")

        return len(issues) == 0, issues
