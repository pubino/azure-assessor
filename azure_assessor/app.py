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
    Checkbox,
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
    ExportComponents,
    ImageInfo,
    PriceInfo,
    QuotaInfo,
    ServiceCostEstimate,
    SkuAvailability,
    SkuRecommendation,
    VmSku,
)
from azure_assessor.pricing import DATABASE_PRESETS, DISK_TIER_LADDERS

DISK_TYPES = list(DISK_TIER_LADDERS.keys()) + ["Premium SSD v2"]

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

.addons-status {
    height: 1;
    color: $text-muted;
    margin: 0 1 0 1;
}

.addons-status.active {
    color: $success;
    text-style: bold;
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
    width: 64;
    height: 90%;
    max-height: 40;
    padding: 1 2;
    background: $surface;
    border: round $primary;
}

#export-dialog Label {
    margin: 1 0 0 0;
}

#export-dialog Input {
    margin: 0 0 1 0;
}

#export-body {
    height: 1fr;
}

#export-body Checkbox {
    width: 100%;
    margin: 0 0 0 0;
}

.export-buttons {
    height: 3;
    align: center middle;
    margin: 1 0 0 0;
    dock: bottom;
}

DetailScreen {
    align: center middle;
}

#detail-dialog {
    width: 70;
    height: 80%;
    max-height: 40;
    padding: 1 2;
    background: $surface;
    border: round $accent;
}

#detail-dialog Label.section-title {
    margin: 0 0 1 0;
}

#detail-body {
    height: 1fr;
}

#detail-body .detail-field {
    margin: 0 0 0 1;
}

.detail-buttons {
    height: 3;
    align: center middle;
    dock: bottom;
}

AddonsScreen {
    align: center middle;
}

#addons-dialog {
    width: 70;
    height: 28;
    padding: 1 2;
    background: $surface;
    border: round $accent;
}

#addons-dialog Label {
    margin: 1 0 0 0;
}

#addons-dialog Input, #addons-dialog Select {
    margin: 0 0 0 0;
}

.addons-buttons {
    height: 3;
    align: center middle;
    margin: 1 0;
}
"""


def _detail_fields_availability(obj: SkuAvailability) -> tuple[str, list[tuple[str, str]]]:
    return (
        f"Availability — {obj.sku_name}",
        [
            ("SKU Name", obj.sku_name),
            ("Region", obj.region),
            ("Available", "Yes" if obj.available else "No"),
            ("Zones", ", ".join(obj.zones) if obj.zones else "None"),
            ("Restrictions", ", ".join(obj.restrictions) if obj.restrictions else "None"),
        ],
    )


def _detail_fields_quota(obj: QuotaInfo) -> tuple[str, list[tuple[str, str]]]:
    return (
        f"Quota — {obj.family}",
        [
            ("Family", obj.family),
            ("Region", obj.region),
            ("Current Usage", str(obj.current_usage)),
            ("Limit", str(obj.limit)),
            ("Available", str(obj.available)),
            ("Usage %", f"{obj.usage_percent:.1f}%"),
            ("Unit", obj.unit),
        ],
    )


def _detail_fields_pricing(
    consumption: PriceInfo | None, spot: PriceInfo | None,
) -> tuple[str, list[tuple[str, str]]]:
    sku = (consumption or spot).sku_name if (consumption or spot) else "N/A"
    fields: list[tuple[str, str]] = []
    if consumption:
        fields += [
            ("SKU Name", consumption.sku_name),
            ("Region", consumption.region),
            ("Retail Price", f"${consumption.retail_price:.4f}"),
            ("Unit Price", f"${consumption.unit_price:.4f}"),
            ("Currency", consumption.currency),
            ("Unit of Measure", consumption.unit_of_measure),
            ("Price Type", consumption.price_type),
            ("Meter Name", consumption.meter_name or "N/A"),
            ("Product Name", consumption.product_name or "N/A"),
        ]
    if spot:
        fields += [
            ("Spot Retail Price", f"${spot.retail_price:.4f}"),
            ("Spot Unit Price", f"${spot.unit_price:.4f}"),
            ("Spot Meter Name", spot.meter_name or "N/A"),
        ]
    if not fields:
        fields.append(("Info", "No pricing data available"))
    return (f"Pricing — {sku}", fields)


def _detail_fields_recommendation(obj: SkuRecommendation) -> tuple[str, list[tuple[str, str]]]:
    fields: list[tuple[str, str]] = [
        ("SKU Name", obj.sku.name),
        ("Family", obj.sku.family),
        ("Size", obj.sku.size),
        ("Tier", obj.sku.tier),
        ("vCPUs", str(obj.sku.vcpus)),
        ("Memory (GB)", f"{obj.sku.memory_gb:.1f}"),
        ("Max Data Disks", str(obj.sku.max_data_disks)),
        ("OS Disk Size (GB)", str(obj.sku.os_disk_size_gb)),
        ("Max NICs", str(obj.sku.max_nics)),
        ("Accelerated Net", "Yes" if obj.sku.accelerated_networking else "No"),
        ("Compatibility Score", f"{obj.compatibility_score:.1%}"),
        ("Price/Hr", f"${obj.price.retail_price:.4f}" if obj.price else "N/A"),
        ("Reasons", "; ".join(obj.reasons) if obj.reasons else "None"),
    ]
    if obj.availability:
        fields.append(("Available", "Yes" if obj.availability.available else "No"))
    if obj.sku.gpu_count:
        fields.append(("GPU Count", str(obj.sku.gpu_count)))
        fields.append(("GPU Type", obj.sku.gpu_type or "N/A"))
    if obj.sku.capabilities:
        caps = ", ".join(f"{k}={v}" for k, v in sorted(obj.sku.capabilities.items()))
        fields.append(("Capabilities", caps))
    return (f"Alternative — {obj.sku.name}", fields)


def _detail_fields_image(obj: ImageInfo) -> tuple[str, list[tuple[str, str]]]:
    return (
        f"Image — {obj.publisher}:{obj.offer}:{obj.sku}",
        [
            ("Publisher", obj.publisher),
            ("Offer", obj.offer),
            ("SKU", obj.sku),
            ("Version", obj.version),
            ("OS Type", obj.os_type),
            ("Architecture", obj.architecture),
            ("Hyper-V Generation", obj.hyper_v_generation),
        ],
    )


def _detail_fields_cost(obj: ServiceCostEstimate) -> tuple[str, list[tuple[str, str]]]:
    fields: list[tuple[str, str]] = [
        ("Service", obj.service_name),
        ("Tier / Plan", obj.tier),
        ("vCPUs", str(obj.vcpus) if obj.vcpus else "N/A"),
        ("Memory (GB)", f"{obj.memory_gb:.1f}" if obj.memory_gb else "N/A"),
        ("Storage (GB)", str(obj.storage_gb) if obj.storage_gb else "N/A"),
        ("Hourly Cost", f"${obj.hourly_cost:.4f}"),
        ("Monthly Cost", f"${obj.monthly_cost:,.2f}"),
        ("Spot Monthly", f"${obj.spot_monthly:,.2f}" if obj.spot_monthly is not None else "N/A"),
        ("Currency", obj.currency),
        ("Notes", "; ".join(obj.notes) if obj.notes else "None"),
    ]
    return (f"Cost — {obj.service_name}", fields)


class ExportScreen(ModalScreen[dict | None]):
    """Modal screen for export options.

    Returns a dict with keys ``format``, ``path``, and ``components`` (an
    ``ExportComponents``), or ``None`` if cancelled.
    """

    def compose(self) -> ComposeResult:
        with Container(id="export-dialog"):
            yield Label("Export Results", classes="section-title")
            with VerticalScroll(id="export-body"):
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
                yield Label("Include components:")
                yield Checkbox("Summary", value=True, id="export-comp-summary")
                yield Checkbox("Alternatives", value=True, id="export-comp-alternatives")
                yield Checkbox("Compatible Images", value=True, id="export-comp-images")
                yield Checkbox("Cost Comparison", value=True, id="export-comp-costs")
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

        components = ExportComponents(
            summary=self.query_one("#export-comp-summary", Checkbox).value,
            alternatives=self.query_one("#export-comp-alternatives", Checkbox).value,
            compatible_images=self.query_one("#export-comp-images", Checkbox).value,
            cost_comparison=self.query_one("#export-comp-costs", Checkbox).value,
        )
        self.dismiss({"format": fmt, "path": path, "components": components})

    @on(Button.Pressed, "#btn-export-cancel")
    def cancel_export(self) -> None:
        self.dismiss(None)


class AddonsScreen(ModalScreen[dict | None]):
    """Modal for configuring storage and database add-ons."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, current: dict[str, object] | None = None) -> None:
        super().__init__()
        self._current = current or {}

    def compose(self) -> ComposeResult:
        with Container(id="addons-dialog"):
            yield Label("Cost Add-ons", classes="section-title")

            yield Label("Storage type:")
            storage_options: list[tuple[str, str]] = [("None", "none")] + [
                (t, t) for t in DISK_TYPES
            ]
            yield Select(
                storage_options,
                value=self._current.get("storage_type") or "none",
                id="addon-storage-type",
            )

            yield Label("Storage size (GB):")
            yield Input(
                value=str(self._current.get("storage_gb") or ""),
                placeholder="e.g., 128",
                id="addon-storage-gb",
            )

            yield Label("Database tier:")
            db_options: list[tuple[str, str]] = [("None", "none")]
            for kind, tiers in DATABASE_PRESETS.items():
                for tier in tiers:
                    db_options.append((f"{kind} — {tier}", f"{kind}|{tier}"))
            current_db = "none"
            if self._current.get("database_kind") and self._current.get("database_tier"):
                current_db = f"{self._current['database_kind']}|{self._current['database_tier']}"
            yield Select(db_options, value=current_db, id="addon-database")

            with Horizontal(classes="addons-buttons"):
                yield Button("Apply", variant="primary", id="btn-addons-apply")
                yield Button("Clear", variant="warning", id="btn-addons-clear")
                yield Button("Cancel", variant="default", id="btn-addons-cancel")

    @on(Button.Pressed, "#btn-addons-apply")
    def _apply(self) -> None:
        storage_type_val = self.query_one("#addon-storage-type", Select).value
        storage_gb_str = self.query_one("#addon-storage-gb", Input).value.strip()
        db_val = self.query_one("#addon-database", Select).value

        storage_type: str | None = None
        storage_gb = 0
        if storage_type_val and storage_type_val != "none":
            try:
                storage_gb = int(storage_gb_str)
            except ValueError:
                storage_gb = 0
            if storage_gb > 0:
                storage_type = str(storage_type_val)

        database_kind: str | None = None
        database_tier: str | None = None
        if db_val and db_val != "none" and isinstance(db_val, str) and "|" in db_val:
            database_kind, database_tier = db_val.split("|", 1)

        self.dismiss({
            "storage_type": storage_type,
            "storage_gb": storage_gb,
            "database_kind": database_kind,
            "database_tier": database_tier,
        })

    @on(Button.Pressed, "#btn-addons-clear")
    def _clear(self) -> None:
        self.dismiss({
            "storage_type": None,
            "storage_gb": 0,
            "database_kind": None,
            "database_tier": None,
        })

    @on(Button.Pressed, "#btn-addons-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class DetailScreen(ModalScreen[None]):
    """Modal screen showing detail fields for a selected row."""

    BINDINGS = [Binding("escape", "dismiss_detail", "Close")]

    def __init__(self, title: str, fields: list[tuple[str, str]]) -> None:
        super().__init__()
        self._title = title
        self._fields = fields

    def compose(self) -> ComposeResult:
        with Container(id="detail-dialog"):
            yield Label(self._title, classes="section-title")
            with VerticalScroll(id="detail-body"):
                for label, value in self._fields:
                    yield Static(f"[bold]{label}:[/] {value}", classes="detail-field")
            with Horizontal(classes="detail-buttons"):
                yield Button("Close", variant="primary", id="btn-detail-close")

    @on(Button.Pressed, "#btn-detail-close")
    def close_detail(self) -> None:
        self.dismiss(None)

    def action_dismiss_detail(self) -> None:
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
        Binding("o", "addons", "Add-ons"),
    ]

    def __init__(self, azure_client=None, pricing_client=None) -> None:
        super().__init__()
        self._azure_client = azure_client
        self._pricing_client = pricing_client
        self._advisor = SkuAdvisor()
        self._results: list[AssessmentResult] = []
        self._current_skus: list[VmSku] = []
        self._init_error: str | None = None
        self._row_data: dict[object, object] = {}
        self._addons: dict[str, object] = {
            "storage_type": None,
            "storage_gb": 0,
            "database_kind": None,
            "database_tier": None,
        }

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
                    yield Button("Add-ons", variant="default", id="btn-addons")
                    yield Button("Export", variant="success", id="btn-export")
                    yield Button("Clear", variant="error", id="btn-clear")
                yield Static("Add-ons: none", id="addons-status", classes="addons-status")

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
                with TabPane("Cost Compare", id="tab-costs"):
                    yield DataTable(id="table-costs")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize data tables and kick off Azure client init."""
        if self._pricing_client is None:
            from azure_assessor.pricing import PricingClient
            self._pricing_client = PricingClient()

        if self._azure_client is None:
            self._init_azure_client()

        avail_table = self.query_one("#table-avail", DataTable)
        avail_table.cursor_type = "row"
        avail_table.add_columns("SKU", "Region", "Available", "Zones", "Restrictions")

        quota_table = self.query_one("#table-quota", DataTable)
        quota_table.cursor_type = "row"
        quota_table.add_columns("Family", "Region", "Usage", "Limit", "Available", "Usage %")

        pricing_table = self.query_one("#table-pricing", DataTable)
        pricing_table.cursor_type = "row"
        pricing_table.add_columns("SKU", "Region", "Price/Hr", "Spot Price/Hr", "Currency", "Product")

        alt_table = self.query_one("#table-alt", DataTable)
        alt_table.cursor_type = "row"
        alt_table.add_columns("SKU", "Score", "vCPUs", "Memory (GB)", "Family", "Price/Hr", "Reasons")

        img_table = self.query_one("#table-images", DataTable)
        img_table.cursor_type = "row"
        img_table.add_columns("Publisher", "Offer", "SKU", "Version", "OS", "Arch", "HyperV Gen", "Compatible")

        cost_table = self.query_one("#table-costs", DataTable)
        cost_table.cursor_type = "row"
        cost_table.add_columns(
            "Service", "Tier/Plan", "vCPUs", "Memory (GB)",
            "Monthly Cost", "Spot Monthly", "vs VM", "Notes",
        )

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

    @on(Button.Pressed, "#btn-addons")
    def on_addons_pressed(self) -> None:
        self.action_addons()

    def action_addons(self) -> None:
        self.push_screen(AddonsScreen(dict(self._addons)), self._handle_addons)

    def _handle_addons(self, result: dict | None) -> None:
        if result is None:
            return
        self._addons = result
        self._refresh_addons_indicator()
        if result.get("storage_type") or result.get("database_kind"):
            self.notify(f"Add-ons set: {self._addons_summary()}")
        else:
            self.notify("Add-ons cleared")

    def _addons_summary(self) -> str:
        parts: list[str] = []
        if self._addons.get("storage_type"):
            parts.append(f"{self._addons['storage_type']} {self._addons['storage_gb']} GB")
        if self._addons.get("database_kind"):
            parts.append(f"{self._addons['database_kind']} / {self._addons['database_tier']}")
        return " · ".join(parts) if parts else "none"

    def _refresh_addons_indicator(self) -> None:
        try:
            status = self.query_one("#addons-status", Static)
        except NoMatches:
            return
        summary = self._addons_summary()
        status.update(f"Add-ons: {summary}")
        if summary == "none":
            status.remove_class("active")
        else:
            status.add_class("active")

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

    def _handle_export(self, result: dict | None) -> None:
        if not result:
            return
        fmt = result["format"]
        path = Path(result["path"])
        components: ExportComponents = result["components"]
        if not components.any_selected():
            self.notify("Select at least one component to export", severity="warning")
            return
        try:
            if fmt == "excel":
                export_excel(self._results, path, components)
            elif fmt == "csv":
                export_csv(self._results, path, components)
            elif fmt == "json":
                export_json(self._results, path, components)
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

            # Cost comparison across services
            if self._pricing_client and target_sku_obj:
                try:
                    result.cost_comparison = self._pricing_client.estimate_monthly_costs(
                        sku_name, region,
                        vcpus=target_sku_obj.vcpus,
                        memory_gb=target_sku_obj.memory_gb,
                        storage_type=self._addons.get("storage_type"),  # type: ignore[arg-type]
                        storage_gb=int(self._addons.get("storage_gb") or 0),
                        database_kind=self._addons.get("database_kind"),  # type: ignore[arg-type]
                        database_tier=self._addons.get("database_tier"),  # type: ignore[arg-type]
                    )
                except Exception:
                    pass  # non-critical, don't block assessment

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
        self._row_data.clear()
        for table_id in ["#table-avail", "#table-quota", "#table-pricing", "#table-alt", "#table-images", "#table-costs"]:
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
            rk = table.add_row(
                avail.sku_name,
                avail.region,
                status,
                ", ".join(avail.zones) or "N/A",
                ", ".join(avail.restrictions) or "None",
            )
            self._row_data[rk] = avail

        # Pricing table
        pricing_table = self.query_one("#table-pricing", DataTable)
        price_str = f"${result.pricing.retail_price:.4f}" if result.pricing else "N/A"
        spot_str = f"${result.spot_pricing.retail_price:.4f}" if result.spot_pricing else "N/A"
        product = result.pricing.product_name if result.pricing else "N/A"
        rk = pricing_table.add_row(
            result.target_sku, result.region, price_str, spot_str,
            result.pricing.currency if result.pricing else "USD", product,
        )
        self._row_data[rk] = (result.pricing, result.spot_pricing)

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
            rk = alt_table.add_row(
                alt.sku.name, score_str,
                str(alt.sku.vcpus), f"{alt.sku.memory_gb:.1f}",
                alt.sku.family, price_val,
                "; ".join(alt.reasons[:3]),
            )
            self._row_data[rk] = alt

        # Images table
        img_table = self.query_one("#table-images", DataTable)
        for img in result.compatible_images:
            rk = img_table.add_row(
                img.publisher, img.offer, img.sku, img.version,
                img.os_type, img.architecture, img.hyper_v_generation,
                "[green]Yes[/]",
            )
            self._row_data[rk] = img

        # Cost comparison table
        cost_table = self.query_one("#table-costs", DataTable)
        vm_monthly = None
        for est in result.cost_comparison:
            if est.service_name == "Virtual Machines":
                vm_monthly = est.monthly_cost
                break

        for est in result.cost_comparison:
            spot_str = f"${est.spot_monthly:,.2f}" if est.spot_monthly is not None else "N/A"
            if vm_monthly and est.service_name != "Virtual Machines" and vm_monthly > 0:
                diff_pct = ((est.monthly_cost - vm_monthly) / vm_monthly) * 100
                if diff_pct < 0:
                    vs_vm = f"[green]{diff_pct:+.1f}%[/]"
                else:
                    vs_vm = f"[red]+{diff_pct:.1f}%[/]"
            else:
                vs_vm = "baseline" if est.service_name == "Virtual Machines" else "N/A"

            rk = cost_table.add_row(
                est.service_name,
                est.tier,
                str(est.vcpus) if est.vcpus else "—",
                f"{est.memory_gb:.1f}" if est.memory_gb else "—",
                f"${est.monthly_cost:,.2f}",
                spot_str,
                vs_vm,
                "; ".join(est.notes[:2]),
            )
            self._row_data[rk] = est

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

            rk = table.add_row(
                q.family, q.region,
                str(q.current_usage), str(q.limit),
                str(q.available), pct_str,
            )
            self._row_data[rk] = q

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Show detail modal when a row is selected."""
        obj = self._row_data.get(event.row_key)
        if obj is None:
            return

        table_id = event.data_table.id
        title: str
        fields: list[tuple[str, str]]

        if table_id == "table-avail" and isinstance(obj, SkuAvailability):
            title, fields = _detail_fields_availability(obj)
        elif table_id == "table-quota" and isinstance(obj, QuotaInfo):
            title, fields = _detail_fields_quota(obj)
        elif table_id == "table-pricing" and isinstance(obj, tuple):
            title, fields = _detail_fields_pricing(obj[0], obj[1])
        elif table_id == "table-alt" and isinstance(obj, SkuRecommendation):
            title, fields = _detail_fields_recommendation(obj)
        elif table_id == "table-images" and isinstance(obj, ImageInfo):
            title, fields = _detail_fields_image(obj)
        elif table_id == "table-costs" and isinstance(obj, ServiceCostEstimate):
            title, fields = _detail_fields_cost(obj)
        else:
            return

        self.push_screen(DetailScreen(title, fields))
