# Azure VM Assessor

Interactive terminal UI for Azure VM SKU assessment, pricing lookup, and fleet planning. Built with [Textual](https://textual.textualize.io/) and the Azure SDK.

## Features

- **VM Availability Checks** — See which VM SKUs are available in specific regions and availability zones, with restriction detection to avoid failed deployments
- **Quota & Capacity Insights** — View current vCPU quota usage and remaining capacity per VM family per region, color-coded by utilization level
- **Automated Pricing Lookup** — Fetch hourly pricing from the Azure Retail Prices API, including spot pricing for cost optimization
- **Alternative SKU Recommendations** — When a desired SKU is unavailable or for comparison, get ranked alternatives scored on vCPU count, memory, VM family, GPU, networking, and disk capabilities
- **Image Compatibility Validation** — Check whether a VM SKU supports a specific OS image by validating HyperV generation, CPU architecture, and Trusted Launch requirements
- **Export** — Save results to Excel (multi-sheet with formatting), CSV, or JSON for reporting and pipeline integration

## Requirements

- Python 3.10+
- An Azure subscription with credentials configured via [`DefaultAzureCredential`](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential) (Azure CLI login, environment variables, managed identity, etc.)

## Installation

```bash
# Clone the repo
git clone https://github.com/pubino/azure-assessor.git
cd azure-assessor

# Create a virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

For development (includes pytest and test dependencies):

```bash
pip install ".[dev]"
```

## Quick Start

1. **Authenticate with Azure:**

   ```bash
   az login
   ```

2. **Launch the TUI:**

   ```bash
   azure-assessor
   ```

   Or run as a module:

   ```bash
   python -m azure_assessor
   ```

## Usage

### TUI Interface

The application opens with an input panel at the top and tabbed result tables below.

**Input fields:**

| Field | Description | Example |
|-------|-------------|---------|
| Region | Azure region name | `eastus`, `westus2`, `westeurope` |
| SKU | VM SKU name to assess | `Standard_D4s_v3`, `Standard_E8s_v5` |
| Image | OS image reference (optional) | `Canonical:0001-com-ubuntu-server-jammy:22_04-lts` |

**Buttons:**

| Button | Action |
|--------|--------|
| Assess | Run a full assessment for the given SKU and region |
| Check Quota | Load all quota usage for the specified region |
| Export | Open the export dialog to save results |
| Clear | Clear all result tables |

**Keyboard shortcuts:**

| Key | Action |
|-----|--------|
| `a` | Assess SKU |
| `e` | Export results |
| `r` | Refresh (re-run assessment) |
| `d` | Toggle dark/light mode |
| `q` | Quit |

### Result Tabs

- **Availability** — SKU name, region, whether it's available, supported zones, and any restrictions
- **Quotas** — VM family, current usage, limit, available capacity, and usage percentage (green < 70%, yellow 70-90%, red > 90%)
- **Pricing** — Hourly retail price, spot price, currency, and product name
- **Alternatives** — Recommended substitute SKUs with compatibility scores (green > 80%, yellow 50-80%, red < 50%), specs, and reasoning
- **Image Compat** — Compatible OS images with publisher, offer, SKU, version, architecture, and HyperV generation

### Export

Press `e` or click **Export** to open the export dialog. Choose a format and file path:

- **Excel (.xlsx)** — Multi-sheet workbook with Summary, Alternatives, and Compatible Images sheets, styled with colored headers and auto-sized columns
- **CSV (.csv)** — Flat summary of all assessment results
- **JSON (.json)** — Full nested data including all alternatives and image details

If no file path is entered, a timestamped default name is generated.

### Programmatic Use

The modules can be used independently without the TUI:

```python
from azure_assessor.azure_client import AzureClient
from azure_assessor.pricing import PricingClient
from azure_assessor.advisor import SkuAdvisor
from azure_assessor.export import export_json, export_csv, export_excel

# Query Azure
client = AzureClient()  # uses DefaultAzureCredential
skus = client.list_vm_skus("eastus")
availability = client.check_sku_availability("eastus", "Standard_D4s_v3")
quotas = client.get_quotas("eastus")

# Look up pricing (no Azure auth needed)
with PricingClient() as pricing:
    prices = pricing.get_vm_prices("Standard_D4s_v3", "eastus")
    spot = pricing.get_spot_price("Standard_D4s_v3", "eastus")

# Get alternative recommendations
advisor = SkuAdvisor()
target = next(s for s in skus if s.name == "Standard_D4s_v3")
alternatives = advisor.find_alternatives(target, skus, max_results=5)

# Check image compatibility
image_info = client.list_vm_images(
    "eastus", "Canonical", "0001-com-ubuntu-server-jammy", "22_04-lts"
)
compatible, issues = client.check_image_sku_compatibility(target, image_info[0])

# Export
from pathlib import Path
from azure_assessor.models import AssessmentResult

result = AssessmentResult(
    target_sku="Standard_D4s_v3",
    region="eastus",
    availability=availability[0],
    pricing=prices[0] if prices else None,
)
export_excel([result], Path("report.xlsx"))
export_json([result], Path("report.json"))
```

## Project Structure

```
azure_assessor/
    __init__.py          # Package metadata
    __main__.py          # CLI entry point
    app.py               # Textual TUI application
    azure_client.py      # Azure SDK wrapper (SKUs, quotas, images)
    pricing.py           # Azure Retail Prices API client
    advisor.py           # Alternative SKU recommendation engine
    export.py            # Excel/CSV/JSON export
    models.py            # Data models (dataclasses)
tests/
    conftest.py          # Shared fixtures and mock data
    test_advisor.py      # SKU advisor tests
    test_app.py          # TUI application tests
    test_azure_client.py # Azure client tests (mocked SDK)
    test_export.py       # Export format tests
    test_models.py       # Data model tests
    test_pricing.py      # Pricing client tests (mocked HTTP)
Dockerfile               # Container image for packaging/testing
docker-compose.yml       # Containerized test runner
```

## Testing

All tests use mocks and do not require Azure credentials.

```bash
# Run tests locally
pytest -v

# Run with coverage
pytest --cov=azure_assessor --cov-report=term-missing

# Run tests in Docker
docker-compose run test
```

## License

MIT
