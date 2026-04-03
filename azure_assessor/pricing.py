"""Azure Retail Prices API integration for cost estimates."""

from __future__ import annotations

import httpx

from azure_assessor.models import PriceInfo, ServiceCostEstimate

RETAIL_PRICES_URL = "https://prices.azure.com/api/retail/prices"


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

    def estimate_monthly_costs(
        self,
        sku_name: str,
        region: str,
        vcpus: int,
        memory_gb: float,
        currency: str = "USD",
        hours: float = 730,
    ) -> list[ServiceCostEstimate]:
        """Orchestrate cost estimates across VM, Container Apps, AKS, App Service."""
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

        return estimates
