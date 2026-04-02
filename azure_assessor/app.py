"""Interactive TUI application using Textual."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    LoadingIndicator,
    OptionList,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from azure_assessor.advisor import SkuAdvisor
from azure_assessor.export import export_csv, export_excel, export_json
from azure_assessor.models import (
    AssessmentResult,
    PriceInfo,
    QuotaInfo,
    SkuAvailability,
    SkuRecommendation,
    VmSku,
)

STYLE_CSS = """
Screen {
    background: $surface;
}

#main-container {
    height: 100%;
}

.section-title {
    color: $accent;
    text-style: bold;
    margin: 0 0 0 1;
    height: 1;
}

#input-panel {
    height: auto;
    padding: 0 1;
    background: $surface-darken-1;
    border: round $primary;
    margin: 1 1 0 1;
}

#input-panel Label {
    width: 8;
    height: 1;
    content-align: right middle;
    margin: 1 1 0 0;
}

.input-row {
    height: 3;
}

.input-row Input {
    width: 1fr;
}

.button-row {
    height: 3;
    align: center middle;
}

.button-row Button {
    margin: 0 1;
}

#results-panel {
    height: 1fr;
    margin: 0 1 0 1;
}

DataTable {
    height: 1fr;
}

#loading-container {
    align: center middle;
    height: 100%;
    display: none;
}

#loading-container.visible {
    display: block;
}

ExportScreen {
    align: center middle;
}

#export-dialog {
    width: 60;
    height: 18;
    padding: 1 2;
    background: $surface;
    border: round $primary;
}

#export-dialog Label {
    margin: 1 0;
}

#export-dialog Input {
    margin: 0 0 1 0;
}

.export-buttons {
    height: 3;
    align: center middle;
    margin: 1 0;
}
"""


class ExportScreen(ModalScreen[str | None]):
    """Modal screen for export options."""

    def compose(self) -> ComposeResult:
        with Container(id="export-dialog"):
            yield Label("Export Results", classes="section-title")
            yield Label("File path:")
            yield Input(placeholder="e.g., results.xlsx", id="export-path")
            yield Label("Format:")
            yield Select(
                [
                    ("Excel (.xlsx)", "excel"),
                    ("CSV (.csv)", "csv"),
                    ("JSON (.json)", "json"),
                ],
                value="excel",
                id="export-format",
            )
            with Horizontal(classes="export-buttons"):
                yield Button("Export", variant="primary", id="btn-export-confirm")
                yield Button("Cancel", variant="default", id="btn-export-cancel")

    @on(Button.Pressed, "#btn-export-confirm")
    def do_export(self) -> None:
        path_input = self.query_one("#export-path", Input)
        fmt_select = self.query_one("#export-format", Select)
        path = path_input.value.strip()
        fmt = fmt_select.value
        if not path:
            ext_map = {"excel": ".xlsx", "csv": ".csv", "json": ".json"}
            path = f"azure_assessment_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}{ext_map.get(fmt, '.json')}"
        self.dismiss(f"{fmt}:{path}")

    @on(Button.Pressed, "#btn-export-cancel")
    def cancel_export(self) -> None:
        self.dismiss(None)


class AzureAssessorApp(App):
    """Azure VM Assessor TUI Application."""

    TITLE = "Azure VM Assessor"
    SUB_TITLE = "VM SKU Assessment & Fleet Planning"
    CSS = STYLE_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("a", "assess", "Assess SKU"),
        Binding("e", "export", "Export"),
        Binding("r", "refresh", "Refresh"),
        Binding("d", "toggle_dark", "Toggle Dark"),
    ]

    def __init__(self, azure_client=None, pricing_client=None) -> None:
        super().__init__()
        self._azure_client = azure_client
        self._pricing_client = pricing_client
        self._advisor = SkuAdvisor()
        self._results: list[AssessmentResult] = []
        self._current_skus: list[VmSku] = []
        self._init_error: str | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="main-container"):
            with Container(id="input-panel"):
                with Horizontal(classes="input-row"):
                    yield Label("Region:")
                    yield Input(placeholder="eastus", id="region-input")
                with Horizontal(classes="input-row"):
                    yield Label("SKU:")
                    yield Input(placeholder="Standard_D4s_v3", id="sku-input")
                with Horizontal(classes="input-row"):
                    yield Label("Image:")
                    yield Input(placeholder="publisher:offer:sku (optional)", id="image-input")
                with Horizontal(classes="button-row"):
                    yield Button("Assess", variant="primary", id="btn-assess")
                    yield Button("Quota", variant="warning", id="btn-quota")
                    yield Button("Export", variant="success", id="btn-export")
                    yield Button("Clear", variant="error", id="btn-clear")

            with Container(id="loading-container"):
                yield LoadingIndicator()
                yield Label("Querying Azure...", id="loading-label")

            with TabbedContent(id="results-panel"):
                with TabPane("Availability", id="tab-avail"):
                    yield DataTable(id="table-avail")
                with TabPane("Quotas", id="tab-quota"):
                    yield DataTable(id="table-quota")
                with TabPane("Pricing", id="tab-pricing"):
                    yield DataTable(id="table-pricing")
                with TabPane("Alternatives", id="tab-alt"):
                    yield DataTable(id="table-alt")
                with TabPane("Image Compat", id="tab-images"):
                    yield DataTable(id="table-images")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize data tables and kick off Azure client init."""
        if self._pricing_client is None:
            from azure_assessor.pricing import PricingClient
            self._pricing_client = PricingClient()

        if self._azure_client is None:
            self._init_azure_client()

        avail_table = self.query_one("#table-avail", DataTable)
        avail_table.add_columns("SKU", "Region", "Available", "Zones", "Restrictions")

        quota_table = self.query_one("#table-quota", DataTable)
        quota_table.add_columns("Family", "Region", "Usage", "Limit", "Available", "Usage %")

        pricing_table = self.query_one("#table-pricing", DataTable)
        pricing_table.add_columns("SKU", "Region", "Price/Hr", "Spot Price/Hr", "Currency", "Product")

        alt_table = self.query_one("#table-alt", DataTable)
        alt_table.add_columns("SKU", "Score", "vCPUs", "Memory (GB)", "Family", "Price/Hr", "Reasons")

        img_table = self.query_one("#table-images", DataTable)
        img_table.add_columns("Publisher", "Offer", "SKU", "Version", "OS", "Arch", "HyperV Gen", "Compatible")

    @work(thread=True)
    def _init_azure_client(self) -> None:
        """Initialize Azure client in a background thread."""
        try:
            from azure_assessor.azure_client import AzureClient
            client = AzureClient()
            self._azure_client = client
            self.call_from_thread(
                self.notify,
                f"Connected to Azure (subscription {client.subscription_id[:8]}...)",
                severity="information",
            )
        except Exception as e:
            self._init_error = str(e)
            self.call_from_thread(
                self.notify, f"Azure connection failed: {e}", severity="error"
            )

    @on(Button.Pressed, "#btn-assess")
    def on_assess_pressed(self) -> None:
        self.action_assess()

    @on(Button.Pressed, "#btn-quota")
    def on_quota_pressed(self) -> None:
        self._run_quota_check()

    @on(Button.Pressed, "#btn-export")
    def on_export_pressed(self) -> None:
        self.action_export()

    @on(Button.Pressed, "#btn-clear")
    def on_clear_pressed(self) -> None:
        self._clear_results()

    def action_assess(self) -> None:
        region = self.query_one("#region-input", Input).value.strip()
        sku = self.query_one("#sku-input", Input).value.strip()
        if not region:
            self.notify("Please enter a region", severity="error")
            return
        if not sku:
            self.notify("Please enter a SKU name", severity="error")
            return
        self._run_assessment(region, sku)

    def action_export(self) -> None:
        if not self._results:
            self.notify("No results to export", severity="warning")
            return
        self.push_screen(ExportScreen(), self._handle_export)

    def action_refresh(self) -> None:
        self.action_assess()

    def _handle_export(self, result: str | None) -> None:
        if not result:
            return
        fmt, path_str = result.split(":", 1)
        path = Path(path_str)
        try:
            if fmt == "excel":
                export_excel(self._results, path)
            elif fmt == "csv":
                export_csv(self._results, path)
            elif fmt == "json":
                export_json(self._results, path)
            self.notify(f"Exported to {path}", severity="information")
        except Exception as e:
            self.notify(f"Export failed: {e}", severity="error")

    @work(thread=True)
    def _run_assessment(self, region: str, sku_name: str) -> None:
        """Run full SKU assessment in background thread."""
        self.call_from_thread(self._show_loading, True)

        try:
            if not self._azure_client:
                self.call_from_thread(
                    self.notify,
                    "Azure client not configured. Set up credentials first.",
                    severity="error",
                )
                return

            client = self._azure_client
            result = AssessmentResult(
                target_sku=sku_name,
                region=region,
                timestamp=datetime.now(tz=timezone.utc).isoformat(),
            )

            # Check availability
            avail_list = client.check_sku_availability(region, sku_name)
            if avail_list:
                result.availability = avail_list[0]

            # Get quotas
            quotas = client.get_quotas(region)
            # Find matching quota for the SKU family
            all_skus = client.list_vm_skus(region)
            self._current_skus = all_skus
            target_sku_obj = next((s for s in all_skus if s.name == sku_name), None)
            if target_sku_obj:
                matching_quota = next(
                    (q for q in quotas if target_sku_obj.family.lower() in q.family.lower()),
                    None,
                )
                result.quota = matching_quota

            # Get pricing
            if self._pricing_client:
                prices = self._pricing_client.get_vm_prices(sku_name, region)
                consumption = [p for p in prices if not p.is_spot]
                spot = [p for p in prices if p.is_spot]
                if consumption:
                    result.pricing = consumption[0]
                if spot:
                    result.spot_pricing = spot[0]

            # Find alternatives if target is unavailable or for comparison
            if target_sku_obj:
                avail_map = {a.sku_name: a for a in client.check_sku_availability(region)}
                result.alternatives = self._advisor.find_alternatives(
                    target_sku_obj,
                    [s for s in all_skus if s.name != sku_name],
                    availability_map=avail_map,
                    max_results=10,
                )

            # Check image compatibility
            image_input = self.call_from_thread(self._get_image_input)
            if image_input and target_sku_obj:
                parts = image_input.split(":")
                if len(parts) == 3:
                    images = client.list_vm_images(region, parts[0], parts[1], parts[2])
                    for img in images:
                        compatible, _ = client.check_image_sku_compatibility(target_sku_obj, img)
                        if compatible:
                            result.compatible_images.append(img)

            self._results.append(result)
            self.call_from_thread(self._update_tables, result)
            self.call_from_thread(
                self.notify, f"Assessment complete for {sku_name} in {region}"
            )

        except Exception as e:
            self.call_from_thread(
                self.notify, f"Assessment failed: {e}", severity="error"
            )
        finally:
            self.call_from_thread(self._show_loading, False)

    @work(thread=True)
    def _run_quota_check(self) -> None:
        """Run quota check for a region."""
        region = self.call_from_thread(
            lambda: self.query_one("#region-input", Input).value.strip()
        )
        if not region:
            self.call_from_thread(
                self.notify, "Please enter a region", severity="error"
            )
            return
        self.call_from_thread(self._show_loading, True)
        try:
            if not self._azure_client:
                self.call_from_thread(
                    self.notify,
                    "Azure client not configured",
                    severity="error",
                )
                return
            quotas = self._azure_client.get_quotas(region)
            self.call_from_thread(self._update_quota_table, quotas)
            self.call_from_thread(
                self.notify, f"Loaded {len(quotas)} quota entries for {region}"
            )
        except Exception as e:
            self.call_from_thread(
                self.notify, f"Quota check failed: {e}", severity="error"
            )
        finally:
            self.call_from_thread(self._show_loading, False)

    def _get_image_input(self) -> str:
        return self.query_one("#image-input", Input).value.strip()

    def _show_loading(self, show: bool) -> None:
        try:
            container = self.query_one("#loading-container")
            if show:
                container.add_class("visible")
            else:
                container.remove_class("visible")
        except NoMatches:
            pass

    def _clear_results(self) -> None:
        self._results.clear()
        for table_id in ["#table-avail", "#table-quota", "#table-pricing", "#table-alt", "#table-images"]:
            try:
                table = self.query_one(table_id, DataTable)
                table.clear()
            except NoMatches:
                pass
        self.notify("Results cleared")

    def _update_tables(self, result: AssessmentResult) -> None:
        """Update all data tables with assessment results."""
        # Availability table
        if result.availability:
            avail = result.availability
            table = self.query_one("#table-avail", DataTable)
            status = "[green]Yes[/]" if avail.available else "[red]No[/]"
            table.add_row(
                avail.sku_name,
                avail.region,
                status,
                ", ".join(avail.zones) or "N/A",
                ", ".join(avail.restrictions) or "None",
            )

        # Pricing table
        pricing_table = self.query_one("#table-pricing", DataTable)
        price_str = f"${result.pricing.retail_price:.4f}" if result.pricing else "N/A"
        spot_str = f"${result.spot_pricing.retail_price:.4f}" if result.spot_pricing else "N/A"
        product = result.pricing.product_name if result.pricing else "N/A"
        pricing_table.add_row(
            result.target_sku, result.region, price_str, spot_str,
            result.pricing.currency if result.pricing else "USD", product,
        )

        # Alternatives table
        alt_table = self.query_one("#table-alt", DataTable)
        for alt in result.alternatives:
            score = alt.compatibility_score
            if score >= 0.8:
                score_str = f"[green]{score:.1%}[/]"
            elif score >= 0.5:
                score_str = f"[yellow]{score:.1%}[/]"
            else:
                score_str = f"[red]{score:.1%}[/]"

            price_val = f"${alt.price.retail_price:.4f}" if alt.price else "N/A"
            alt_table.add_row(
                alt.sku.name, score_str,
                str(alt.sku.vcpus), f"{alt.sku.memory_gb:.1f}",
                alt.sku.family, price_val,
                "; ".join(alt.reasons[:3]),
            )

        # Images table
        img_table = self.query_one("#table-images", DataTable)
        for img in result.compatible_images:
            img_table.add_row(
                img.publisher, img.offer, img.sku, img.version,
                img.os_type, img.architecture, img.hyper_v_generation,
                "[green]Yes[/]",
            )

    def _update_quota_table(self, quotas: list[QuotaInfo]) -> None:
        """Update the quota table."""
        table = self.query_one("#table-quota", DataTable)
        table.clear()
        for q in quotas:
            pct = q.usage_percent
            if pct >= 90:
                pct_str = f"[red]{pct:.1f}%[/]"
            elif pct >= 70:
                pct_str = f"[yellow]{pct:.1f}%[/]"
            else:
                pct_str = f"[green]{pct:.1f}%[/]"

            table.add_row(
                q.family, q.region,
                str(q.current_usage), str(q.limit),
                str(q.available), pct_str,
            )
