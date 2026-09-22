import unittest

import pandas as pd

from app.agent_tools.dashboard import render_dashboard
from app.schemas import (
    ComponentSchema,
    DashboardSchema,
    FilterSchema,
    FormulaOperand,
    KPIFormulaSpec,
    LayoutSchema,
    QuerySchema,
)


class DashboardIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tables = {
            "employees": pd.DataFrame(
                [
                    {"Employee ID": 1, "Gender": "Female", "Status": "Active", "Age": 30},
                    {"Employee ID": 2, "Gender": "Male", "Status": "Active", "Age": 40},
                    {"Employee ID": 3, "Gender": "Male", "Status": "Inactive", "Age": 50},
                ]
            )
        }

    def dashboard(self):
        active_count = KPIFormulaSpec(
            kind="aggregate",
            numerator=FormulaOperand(
                table_id="employees",
                field="Employee ID",
                aggregation="count",
                filters={"Status": "Active"},
            ),
        )
        missing_growth = KPIFormulaSpec(
            kind="period_growth",
            numerator=FormulaOperand(
                table_id="employees",
                field="Age",
                aggregation="avg",
            ),
            time_table_id="employees",
            time_field="Snapshot Time",
            time_granularity="month",
            comparison="mom",
            multiplier=100,
        )
        return DashboardSchema(
            title="Workforce dashboard",
            description="Validated workforce view",
            dataset_id=1,
            theme={
                "primary": "#111111",
                "accent": "#00ADEF",
                "surface": "#FFFFFF",
                "text": "#111827",
            },
            filters=[
                FilterSchema(
                    id="gender",
                    table_id="employees",
                    field="Gender",
                    label="Gender (employees)",
                    type="select",
                )
            ],
            components=[
                ComponentSchema(
                    id="missing-growth",
                    type="kpi",
                    title="Month-over-Month Age Growth",
                    query=QuerySchema(
                        table_id="employees",
                        metric="Age",
                        aggregation="avg",
                    ),
                    formula=missing_growth,
                    computed_value=None,
                    computation_status="insufficient_data",
                    computation_message="The matching previous period is missing.",
                    layout=LayoutSchema(x=0, y=0, w=4, h=2),
                ),
                ComponentSchema(
                    id="headcount-gender",
                    type="bar",
                    title="Active Headcount by Gender",
                    query=QuerySchema(
                        table_id="employees",
                        group_by="Gender",
                        metric="Employee ID",
                        aggregation="count",
                    ),
                    formula=active_count,
                    layout=LayoutSchema(x=0, y=2, w=6, h=5),
                ),
            ],
        )

    def test_missing_growth_never_falls_back_to_average(self):
        rendered, artifact = render_dashboard(self.dashboard(), self.tables)
        self.assertNotIn("missing-growth", artifact.component_data)
        self.assertNotIn(
            "missing-growth",
            {component.id for component in rendered.components},
        )

    def test_chart_inherits_formula_filters(self):
        _, artifact = render_dashboard(self.dashboard(), self.tables)
        result = artifact.component_data["headcount-gender"]
        self.assertEqual(sum(result["values"]), 2)

    def test_export_is_self_contained_and_filterable(self):
        rendered, artifact = render_dashboard(self.dashboard(), self.tables)
        self.assertNotIn("cdn.jsdelivr", artifact.html)
        self.assertIn('createElement("select")', artifact.html)
        self.assertIn('"tables":', artifact.html)
        self.assertIn('id="insights"', artifact.html)
        self.assertEqual(rendered.filters[0].label, "Gender")


if __name__ == "__main__":
    unittest.main()
