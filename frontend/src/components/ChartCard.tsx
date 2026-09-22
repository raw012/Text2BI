import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import {
  Activity,
  BriefcaseBusiness,
  Clock3,
  Gauge,
  UserMinus,
  UserPlus,
  Users,
} from "lucide-react";
import { api } from "../lib/api";
import type { ChartData, DashboardComponent } from "../types";

interface Props {
  component: DashboardComponent;
  datasetId: number;
  primary: string;
  accent: string;
  filters: Record<string, string>;
}

const compact = new Intl.NumberFormat("en", {
  notation: "compact",
  maximumFractionDigits: 1,
});

function semanticIcon(title: string) {
  const value = title.toLowerCase();
  if (value.includes("termination") || value.includes("离职")) return UserMinus;
  if (value.includes("hire") || value.includes("招聘")) return UserPlus;
  if (value.includes("tenure") || value.includes("service") || value.includes("工龄")) return Clock3;
  if (value.includes("rate") || value.includes("ratio") || value.includes("率")) return Gauge;
  if (value.includes("department") || value.includes("position")) return BriefcaseBusiness;
  if (value.includes("headcount") || value.includes("employee") || value.includes("员工")) return Users;
  return Activity;
}

function formatValue(value: number, unit?: unknown) {
  const formatted = compact.format(value);
  if (unit === "%") return `${formatted}%`;
  if (unit === "years") return `${formatted} yrs`;
  return formatted;
}

export function ChartCard({
  component,
  datasetId,
  primary,
  accent,
  filters,
}: Props) {
  const [data, setData] = useState<ChartData>({});
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    if (component.type === "kpi") {
      setData(
        component.computation_status === "computed"
        && component.computed_value !== undefined
        && component.computed_value !== null
          ? { value: component.computed_value }
          : {},
      );
      return;
    }
    const fixedFilters = component.formula?.numerator.filters || {};
    const queryFilters = {
      ...filters,
      ...Object.fromEntries(
        Object.entries(fixedFilters).map(([field, value]) => [
          `${component.query.table_id}.${field}`,
          String(value),
        ]),
      ),
    };
    api.query(datasetId, component.query, queryFilters)
      .then(setData)
      .catch(() => {
        setData({});
        setFailed(true);
      });
  }, [component, datasetId, filters]);

  const option = useMemo(() => {
    const categories = data.categories || [];
    const values = data.values || [];
    const common = {
      animationDuration: 500,
      color: [accent, primary, "#7C8791", "#B8C0C7", "#9ACCE0", "#486575"],
      tooltip: {
        trigger: "axis",
        borderWidth: 0,
        backgroundColor: "#111519",
        textStyle: { color: "#fff", fontSize: 11 },
      },
      grid: { left: 10, right: 14, top: 26, bottom: 8, containLabel: true },
    };
    if (component.type === "pie") {
      return {
        ...common,
        tooltip: { trigger: "item" },
        legend: {
          bottom: 0,
          icon: "circle",
          itemWidth: 7,
          textStyle: { color: "#687079", fontSize: 10 },
        },
        series: [{
          type: "pie",
          radius: ["48%", "72%"],
          center: ["50%", "43%"],
          label: { show: false },
          data: categories.map((name, index) => ({ name, value: values[index] })),
        }],
      };
    }
    const line = component.type === "line" || component.type === "area";
    return {
      ...common,
      xAxis: {
        type: "category",
        data: categories,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#DCE1E5" } },
        axisLabel: {
          color: "#687079",
          fontSize: 9,
          interval: 0,
          rotate: categories.some((item) => item.length > 10) ? 18 : 0,
        },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#EEF1F3" } },
        axisLabel: { color: "#8A9298", fontSize: 9 },
        axisLine: { show: false },
      },
      series: [{
        data: values,
        type: line ? "line" : "bar",
        smooth: true,
        barMaxWidth: 34,
        showSymbol: false,
        areaStyle: component.type === "area" ? { opacity: 0.12 } : undefined,
        lineStyle: { width: 2.5 },
        itemStyle: { borderRadius: line ? 0 : [3, 3, 0, 0] },
      }],
    };
  }, [accent, component.type, data, primary]);

  if (component.type === "kpi") {
    const Icon = semanticIcon(component.title);
    const value = data.value;
    return (
      <article className="kpi-card">
        <i />
        <div className="kpi-title">
          <p>{component.title}</p>
          <Icon size={22} />
        </div>
        <strong>{value === undefined ? "—" : formatValue(value, component.style.unit)}</strong>
        <span>
          {value === undefined
            ? component.computation_message || "Insufficient source data for this KPI"
            : component.subtitle || "Calculated from validated source data"}
        </span>
      </article>
    );
  }

  return (
    <article
      className="chart-panel"
      style={{ gridColumn: `span ${Math.max(4, Math.min(12, component.layout.w))}` }}
    >
      <header>
        <div>
          <p>ANALYTICAL VIEW</p>
          <h3>{component.title}</h3>
        </div>
        <span>{component.query.aggregation.replace("_", " ")}</span>
      </header>
      {failed ? (
        <div className="chart-empty">This chart could not be calculated.</div>
      ) : (
        <ReactECharts option={option} style={{ height: 235 }} opts={{ renderer: "svg" }} />
      )}
    </article>
  );
}
