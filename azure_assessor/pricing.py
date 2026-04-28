"""Azure Retail Prices API integration for cost estimates."""

from __future__ import annotations

import httpx

from azure_assessor.models import PriceInfo, ServiceCostEstimate

RETAIL_PRICES_URL = "https://prices.azure.com/api/retail/prices"

# Managed disk tier ladders: (tier_name, max_size_gb). Used to map a
# requested size to the smallest tier that contains it.
DISK_TIER_LADDERS: dict[str, list[tuple[str, int]]] = {
    "Premium SSD": [
        ("P1", 4), ("P2", 8), ("P3", 16), ("P4", 32), ("P6", 64),
        ("P10", 128), ("P15", 256), ("P20", 512), ("P30", 1024),
        ("P40", 2048), ("P50", 4096), ("P60", 8192),
        ("P70", 16384), ("P80", 32767),
    ],
    "Standard SSD": [
        ("E1", 4), ("E2", 8), ("E3", 16), ("E4", 32), ("E6", 64),
        ("E10", 128), ("E15", 256), ("E20", 512), ("E30", 1024),
        ("E40", 2048), ("E50", 4096), ("E60", 8192),
        ("E70", 16384), ("E80", 32767),
    ],
    "Standard HDD": [
        ("S4", 32), ("S6", 64), ("S10", 128), ("S15", 256), ("S20", 512),
        ("S30", 1024), ("S40", 2048), ("S50", 4096), ("S60", 8192),
        ("S70", 16384), ("S80", 32767),
    ],
}

# Database preset tiers. Each entry's value is a list of substrings that must
# all appear (case-insensitive) in either skuName, meterName, or productName
# for the price item to match.
DATABASE_PRESETS: dict[str, dict[str, dict[str, str | list[str]]]] = {
    "Azure SQL Database": {
        "Basic (DTU)": {"service": "SQL Database", "match": ["Basic", "DTU"]},
        "S0 Standard (10 DTU)": {"service": "SQL Database", "match": ["Standard", "S0"]},
        "GP Gen5 2 vCore": {"service": "SQL Database", "match": ["General Purpose", "Gen5", "2 vCore"]},
        "GP Gen5 4 vCore": {"service": "SQL Database", "match": ["General Purpose", "Gen5", "4 vCore"]},
    },
    "Azure Database for PostgreSQL": {
        "Burstable B1ms": {"service": "Azure Database for PostgreSQL", "match": ["Burstable", "B1ms"]},
        "Burstable B2s": {"service": "Azure Database for PostgreSQL", "match": ["Burstable", "B2s"]},
        "GP D2s v3": {"service": "Azure Database for PostgreSQL", "match": ["General Purpose", "D2s v3"]},
        "GP D4s v3": {"service": "Azure Database for PostgreSQL", "match": ["General Purpose", "D4s v3"]},
    },
    "Azure Database for MySQL": {
        "Burstable B1ms": {"service": "Azure Database for MySQL", "match": ["Burstable", "B1ms"]},
        "Burstable B2s": {"service": "Azure Database for MySQL", "match": ["Burstable", "B2s"]},
        "GP D2s v3": {"service": "Azure Database for MySQL", "match": ["General Purpose", "D2s v3"]},
        "GP D4s v3": {"service": "Azure Database for MySQL", "match": ["General Purpose", "D4s v3"]},
    },
    "Azure Cosmos DB": {
        "Serverless": {"service": "Azure Cosmos DB", "match": ["Serverless"]},
        "Provisioned 400 RU/s": {"service": "Azure Cosmos DB", "match": ["100 RU/s"]},
    },
}


class PricingClient:
    """Client for Azure Retail Prices API (no authentication required)."""

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=30.0)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PricingClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_vm_prices(
        self,
        sku_name: str,
        region: str,
        currency: str = "USD",
    ) -> list[PriceInfo]:
        """Get all pricing (consumption + spot) for a VM SKU in a region."""
        arm_region = region.lower().replace(" ", "")
        filter_expr = (
            f"armRegionName eq '{arm_region}' "
            f"and armSkuName eq '{sku_name}' "
            f"and serviceFamily eq 'Compute' "
            f"and priceType eq 'Consumption'"
        )
        consumption = self._query_prices(filter_expr, currency)

        # Also get spot prices
        spot_filter = (
            f"armRegionName eq '{arm_region}' "
            f"and armSkuName eq '{sku_name}' "
            f"and serviceFamily eq 'Compute' "
            f"and priceType eq 'Consumption' "
            f"and contains(meterName, 'Spot')"
        )
        spot = self._query_prices(spot_filter, currency)
        for p in spot:
            p.is_spot = True

        return consumption + spot

    def get_spot_price(
        self,
        sku_name: str,
        region: str,
        currency: str = "USD",
    ) -> PriceInfo | None:
        """Get spot pricing for a VM SKU."""
        arm_region = region.lower().replace(" ", "")
        filter_expr = (
            f"armRegionName eq '{arm_region}' "
            f"and armSkuName eq '{sku_name}' "
            f"and serviceFamily eq 'Compute' "
            f"and priceType eq 'Consumption' "
            f"and contains(meterName, 'Spot')"
        )
        results = self._query_prices(filter_expr, currency)
        return results[0] if results else None

    def _query_prices(
        self, filter_expr: str, currency: str = "USD"
    ) -> list[PriceInfo]:
        """Execute a query against the Retail Prices API with pagination."""
        prices: list[PriceInfo] = []
        params: dict[str, str] = {
            "$filter": filter_expr,
            "currencyCode": currency,
        }
        url: str | None = RETAIL_PRICES_URL

        while url:
            resp = self._client.get(url, params=params if url == RETAIL_PRICES_URL else None)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("Items", []):
                is_spot = "Spot" in item.get("meterName", "")
                prices.append(
                    PriceInfo(
                        sku_name=item.get("armSkuName", ""),
                        region=item.get("armRegionName", ""),
                        retail_price=item.get("retailPrice", 0.0),
                        unit_price=item.get("unitPrice", 0.0),
                        currency=item.get("currencyCode", currency),
                        unit_of_measure=item.get("unitOfMeasure", "1 Hour"),
                        price_type=item.get("type", "Consumption"),
                        is_spot=is_spot,
                        meter_name=item.get("meterName", ""),
                        product_name=item.get("productName", ""),
                    )
                )

            url = data.get("NextPageLink")
            params = {}  # pagination URL already has params

        return prices

    # ---- Multi-service cost comparison methods ----

    def get_container_apps_price(
        self,
        region: str,
        vcpus: int,
        memory_gb: float,
        currency: str = "USD",
        hours: float = 730,
    ) -> ServiceCostEstimate | None:
        """Get Container Apps consumption-tier cost for given vCPU/memory.

        Container Apps charges per vCPU-second and per GiB-second.
        We query the Retail Prices API for the vCPU and memory meters.
        """
        arm_region = region.lower().replace(" ", "")
        filter_expr = (
            f"armRegionName eq '{arm_region}' "
            f"and serviceName eq 'Azure Container Apps' "
            f"and priceType eq 'Consumption'"
        )
        prices = self._query_prices(filter_expr, currency)
        if not prices:
            return None

        vcpu_rate = 0.0
        mem_rate = 0.0
        for p in prices:
            meter = p.meter_name.lower()
            if "vcpu" in meter and "spot" not in meter:
                vcpu_rate = p.retail_price
            elif "memory" in meter and "spot" not in meter:
                mem_rate = p.retail_price

        if vcpu_rate == 0.0 and mem_rate == 0.0:
            return None

        # Rates are per vCPU-second and per GiB-second
        seconds = hours * 3600
        monthly = (vcpus * vcpu_rate * seconds) + (memory_gb * mem_rate * seconds)
        hourly = monthly / hours if hours else 0.0

        notes = [f"vCPU rate: ${vcpu_rate}/s", f"Mem rate: ${mem_rate}/GiB-s"]
        return ServiceCostEstimate(
            service_name="Container Apps",
            tier="Consumption",
            monthly_cost=round(monthly, 2),
            hourly_cost=round(hourly, 4),
            currency=currency,
            vcpus=vcpus,
            memory_gb=memory_gb,
            notes=notes,
        )

    def get_aks_price(
        self,
        region: str,
        sku_name: str,
        currency: str = "USD",
        hours: float = 730,
    ) -> ServiceCostEstimate | None:
        """Get AKS cost: management fee + node VM price.

        AKS Free tier has no management fee. Standard/Premium have an hourly fee.
        Node cost is the same as the underlying VM price.
        """
        arm_region = region.lower().replace(" ", "")

        # Get AKS management fee
        aks_filter = (
            f"armRegionName eq '{arm_region}' "
            f"and serviceName eq 'Azure Kubernetes Service' "
            f"and priceType eq 'Consumption'"
        )
        aks_prices = self._query_prices(aks_filter, currency)

        mgmt_hourly = 0.0
        aks_tier = "Free"
        for p in aks_prices:
            meter = p.meter_name.lower()
            if "standard" in meter and "spot" not in meter:
                mgmt_hourly = p.retail_price
                aks_tier = "Standard"
                break

        # Get VM node price (reuse existing logic)
        vm_prices = self.get_vm_prices(sku_name, region, currency)
        vm_consumption = [p for p in vm_prices if not p.is_spot]
        vm_spot = [p for p in vm_prices if p.is_spot]

        if not vm_consumption:
            return None

        node_hourly = vm_consumption[0].retail_price
        total_hourly = mgmt_hourly + node_hourly
        monthly = total_hourly * hours
        spot_monthly = (mgmt_hourly + vm_spot[0].retail_price) * hours if vm_spot else None

        notes = []
        if mgmt_hourly > 0:
            notes.append(f"Mgmt fee: ${mgmt_hourly:.4f}/hr")
        else:
            notes.append("Free tier (no mgmt fee)")
        notes.append(f"Node VM: {sku_name}")

        # Get vcpus/memory from the VM price info if available
        vcpus = 0
        memory_gb = 0.0

        return ServiceCostEstimate(
            service_name="AKS",
            tier=f"{aks_tier} + {sku_name}",
            monthly_cost=round(monthly, 2),
            hourly_cost=round(total_hourly, 4),
            currency=currency,
            vcpus=vcpus,
            memory_gb=memory_gb,
            spot_monthly=round(spot_monthly, 2) if spot_monthly is not None else None,
            notes=notes,
        )

    def get_app_service_price(
        self,
        region: str,
        vcpus: int,
        memory_gb: float,
        currency: str = "USD",
        hours: float = 730,
    ) -> ServiceCostEstimate | None:
        """Get App Service plan cost for the closest matching tier.

        Queries for Premium v3 and Standard tiers and picks the cheapest plan
        that meets the vCPU/memory requirements.
        """
        arm_region = region.lower().replace(" ", "")
        filter_expr = (
            f"armRegionName eq '{arm_region}' "
            f"and serviceName eq 'Azure App Service' "
            f"and priceType eq 'Consumption'"
        )
        prices = self._query_prices(filter_expr, currency)
        if not prices:
            return None

        # Map known App Service plan tiers to vCPU/memory
        plan_specs: dict[str, tuple[int, float]] = {
            "B1": (1, 1.75),
            "B2": (2, 3.5),
            "B3": (4, 7.0),
            "S1": (1, 1.75),
            "S2": (2, 3.5),
            "S3": (4, 7.0),
            "P1v3": (2, 8.0),
            "P2v3": (4, 16.0),
            "P3v3": (8, 32.0),
            "P0v3": (1, 4.0),
            "P1mv3": (2, 16.0),
            "P2mv3": (4, 32.0),
            "P3mv3": (8, 64.0),
            "P4mv3": (16, 128.0),
            "P5mv3": (32, 256.0),
        }

        best: PriceInfo | None = None
        best_plan = ""
        best_vcpus = 0
        best_mem = 0.0

        for p in prices:
            meter = p.meter_name.strip()
            if "spot" in meter.lower():
                continue
            # Match meter name to a known plan
            for plan_name, (plan_vcpus, plan_mem) in plan_specs.items():
                if plan_name.lower() in meter.lower():
                    if plan_vcpus >= vcpus and plan_mem >= memory_gb:
                        if best is None or p.retail_price < best.retail_price:
                            best = p
                            best_plan = plan_name
                            best_vcpus = plan_vcpus
                            best_mem = plan_mem
                    break

        if best is None:
            return None

        monthly = best.retail_price * hours
        return ServiceCostEstimate(
            service_name="App Service",
            tier=best_plan,
            monthly_cost=round(monthly, 2),
            hourly_cost=round(best.retail_price, 4),
            currency=currency,
            vcpus=best_vcpus,
            memory_gb=best_mem,
            notes=[f"Plan: {best_plan}", f"Meter: {best.meter_name}"],
        )

    # ---- Storage and database add-ons ----

    def get_managed_disk_price(
        self,
        region: str,
        disk_type: str,
        size_gb: int,
        currency: str = "USD",
        hours: float = 730,
    ) -> ServiceCostEstimate | None:
        """Estimate monthly cost for a managed disk of a given type and size.

        Tier-based disks (Premium SSD, Standard SSD, Standard HDD) are billed
        at the smallest tier that fits ``size_gb`` (LRS redundancy). Premium
        SSD v2 is billed per provisioned GiB-month for the capacity component
        only (IOPS / throughput surcharges are not included).
        """
        arm_region = region.lower().replace(" ", "")

        if disk_type in DISK_TIER_LADDERS:
            ladder = DISK_TIER_LADDERS[disk_type]
            tier_name = next((name for name, max_sz in ladder if max_sz >= size_gb), None)
            if tier_name is None:
                return None
            filter_expr = (
                f"armRegionName eq '{arm_region}' "
                f"and serviceName eq 'Storage' "
                f"and priceType eq 'Consumption'"
            )
            prices = self._query_prices(filter_expr, currency)
            tier_lower = tier_name.lower()
            best: PriceInfo | None = None
            for p in prices:
                meter = p.meter_name.lower()
                product = p.product_name.lower()
                if disk_type.lower() not in product:
                    continue
                # Match the tier code as a whole token (e.g. "p10" in "P10 LRS Disk").
                tokens = meter.replace("/", " ").split()
                if tier_lower not in tokens:
                    continue
                # Prefer LRS redundancy when multiple meters match the tier.
                if "lrs" in tokens:
                    best = p
                    break
                if best is None:
                    best = p
            if best is None:
                return None
            monthly = best.retail_price
            return ServiceCostEstimate(
                service_name="Managed Disk",
                tier=f"{disk_type} {tier_name}",
                monthly_cost=round(monthly, 2),
                hourly_cost=round(monthly / hours, 6) if hours else 0.0,
                currency=currency,
                storage_gb=size_gb,
                notes=[f"Tier {tier_name} ({disk_type})", f"Provisioned {size_gb} GiB"],
            )

        if disk_type == "Premium SSD v2":
            filter_expr = (
                f"armRegionName eq '{arm_region}' "
                f"and serviceName eq 'Storage' "
                f"and priceType eq 'Consumption'"
            )
            prices = self._query_prices(filter_expr, currency)
            per_gib_month: float | None = None
            chosen_meter = ""
            for p in prices:
                product = p.product_name.lower()
                meter = p.meter_name.lower()
                uom = p.unit_of_measure.lower()
                if "premium ssd v2" not in product:
                    continue
                if "provisioned capacity" in meter or ("gib" in uom and "month" in uom):
                    per_gib_month = p.retail_price
                    chosen_meter = p.meter_name
                    break
            if per_gib_month is None:
                return None
            monthly = per_gib_month * size_gb
            return ServiceCostEstimate(
                service_name="Managed Disk",
                tier=f"Premium SSD v2 {size_gb} GiB",
                monthly_cost=round(monthly, 2),
                hourly_cost=round(monthly / hours, 6) if hours else 0.0,
                currency=currency,
                storage_gb=size_gb,
                notes=[
                    f"Per-GiB rate: ${per_gib_month}/GiB-month",
                    f"Meter: {chosen_meter}",
                    "IOPS / throughput surcharges not included",
                ],
            )

        return None

    def get_database_price(
        self,
        region: str,
        db_kind: str,
        tier_key: str,
        currency: str = "USD",
        hours: float = 730,
    ) -> ServiceCostEstimate | None:
        """Estimate monthly cost for a managed database tier preset.

        ``db_kind`` and ``tier_key`` must come from ``DATABASE_PRESETS`` keys.
        Costs reflect compute only — storage, backup, and egress are excluded.
        """
        presets = DATABASE_PRESETS.get(db_kind)
        if not presets:
            return None
        preset = presets.get(tier_key)
        if not preset:
            return None

        service_name = preset["service"]
        match_terms: list[str] = list(preset["match"])  # type: ignore[arg-type]
        arm_region = region.lower().replace(" ", "")

        filter_expr = (
            f"armRegionName eq '{arm_region}' "
            f"and serviceName eq '{service_name}' "
            f"and priceType eq 'Consumption'"
        )
        prices = self._query_prices(filter_expr, currency)
        if not prices:
            return None

        terms_lower = [t.lower() for t in match_terms]
        candidates: list[PriceInfo] = []
        for p in prices:
            haystack = " ".join([
                p.meter_name.lower(),
                p.product_name.lower(),
                p.sku_name.lower(),
            ])
            if all(term in haystack for term in terms_lower):
                candidates.append(p)

        if not candidates:
            return None

        chosen = min(candidates, key=lambda p: p.retail_price)
        uom = chosen.unit_of_measure.lower()
        if "hour" in uom:
            hourly = chosen.retail_price
            monthly = hourly * hours
        elif "month" in uom:
            monthly = chosen.retail_price
            hourly = monthly / hours if hours else 0.0
        else:
            # Unknown unit: surface it but don't extrapolate.
            hourly = chosen.retail_price
            monthly = chosen.retail_price * hours

        return ServiceCostEstimate(
            service_name=db_kind,
            tier=tier_key,
            monthly_cost=round(monthly, 2),
            hourly_cost=round(hourly, 4),
            currency=currency,
            notes=[
                f"Meter: {chosen.meter_name}",
                f"Unit: {chosen.unit_of_measure}",
                "Compute only; storage and backup not included",
            ],
        )

    def estimate_monthly_costs(
        self,
        sku_name: str,
        region: str,
        vcpus: int,
        memory_gb: float,
        currency: str = "USD",
        hours: float = 730,
        storage_type: str | None = None,
        storage_gb: int = 0,
        database_kind: str | None = None,
        database_tier: str | None = None,
    ) -> list[ServiceCostEstimate]:
        """Orchestrate cost estimates across VM, Container Apps, AKS, App Service.

        When ``storage_type`` and ``storage_gb`` are provided, a Managed Disk
        line item is appended. When ``database_kind`` and ``database_tier`` are
        provided, a database line item is appended.
        """
        estimates: list[ServiceCostEstimate] = []

        # 1. VM cost (baseline)
        vm_prices = self.get_vm_prices(sku_name, region, currency)
        vm_consumption = [p for p in vm_prices if not p.is_spot]
        vm_spot = [p for p in vm_prices if p.is_spot]
        if vm_consumption:
            hourly = vm_consumption[0].retail_price
            spot_monthly = vm_spot[0].retail_price * hours if vm_spot else None
            estimates.append(
                ServiceCostEstimate(
                    service_name="Virtual Machines",
                    tier=sku_name,
                    monthly_cost=round(hourly * hours, 2),
                    hourly_cost=round(hourly, 4),
                    currency=currency,
                    vcpus=vcpus,
                    memory_gb=memory_gb,
                    spot_monthly=round(spot_monthly, 2) if spot_monthly is not None else None,
                    notes=["Baseline VM cost"],
                )
            )

        # 2. Container Apps
        ca = self.get_container_apps_price(region, vcpus, memory_gb, currency, hours)
        if ca:
            estimates.append(ca)

        # 3. AKS
        aks = self.get_aks_price(region, sku_name, currency, hours)
        if aks:
            estimates.append(aks)

        # 4. App Service
        app_svc = self.get_app_service_price(region, vcpus, memory_gb, currency, hours)
        if app_svc:
            estimates.append(app_svc)

        # 5. Optional managed disk add-on
        if storage_type and storage_gb > 0:
            disk = self.get_managed_disk_price(region, storage_type, storage_gb, currency, hours)
            if disk:
                estimates.append(disk)

        # 6. Optional database add-on
        if database_kind and database_tier:
            db = self.get_database_price(region, database_kind, database_tier, currency, hours)
            if db:
                estimates.append(db)

        return estimates
