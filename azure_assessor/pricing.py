"""Azure Retail Prices API integration for cost estimates."""

from __future__ import annotations

import httpx

from azure_assessor.models import PriceInfo

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
