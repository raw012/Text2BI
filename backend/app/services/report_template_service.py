from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReportTemplate:
    id: str
    name: str
    description: str
    version: str
    is_default: bool = False


REPORT_TEMPLATES = (
    ReportTemplate("generic-executive", "Text2BI Executive", "Neutral, brand-aware executive dashboard for general BI use.", "1.0.0", True),
    ReportTemplate(
        "mercedes-hr-executive",
        "Mercedes HR Executive",
        "Reusable HR dashboard derived from Mercedes_HR_Dashboard.html, with embedded data, filters, KPIs, and charts.",
        "1.0.0",
    ),
)


def list_report_templates() -> list[dict]:
    return [asdict(template) for template in REPORT_TEMPLATES]


def require_report_template(template_id: str) -> ReportTemplate:
    for template in REPORT_TEMPLATES:
        if template.id == template_id:
            return template
    supported = ", ".join(template.id for template in REPORT_TEMPLATES)
    raise ValueError(f"Unknown report template '{template_id}'. Supported: {supported}.")
