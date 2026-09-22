---
name: design-enterprise-dashboard

description: >-
  Design professional interactive BI dashboards based on business goals,
  company branding, user preferences, and visualization principles.
---

# BI Designer Skill

## Runtime Contract

- LangGraph node: `bi_designer`
- Input: `DataAnalysisSpec`, `BusinessAnalysisSpec`, deterministic
  `KPIResultSet`, user preferences, and optional prior `DashboardSchema`.
- Output: `DashboardSchema` JSON only.
- Every query and filter is table-qualified. KPI cards use calculated values
  and evidence; charts use safe query specifications.
- The designer may change layout, theme, chart choice, filters, and logo
  placement. It must not calculate data, invent KPI values, or emit HTML.


## Purpose


The BI Designer Agent transforms business requirements into
professional dashboard experiences.


The output should be a Dashboard JSON Schema,
not static HTML.


---

# Core Responsibilities


## 1. Brand Identity Understanding


Analyze:


- company name
- industry
- uploaded logo
- preferred colors
- visual style


If logo is provided:


Evaluate:


- logo colors
- logo placement
- background compatibility
- visual balance


Example:


Luxury automotive company:


Preferred style:

- premium
- minimal
- high whitespace


---

## 2. Theme Generation


Generate:


- primary color
- secondary color
- background style
- typography style


Based on:


- company branding
- user preference
- industry


---

## 3. Dashboard Layout Design


Follow enterprise BI principles:


Executive summary:


Top:

- KPI cards


Middle:

- trends
- comparisons


Bottom:

- detailed analysis


Avoid:


- unnecessary charts
- excessive decoration
- poor information hierarchy


---

## 4. Visualization Selection


Select charts based on analytical purpose.


Examples:


Trend:

Line chart


Comparison:

Bar chart


Distribution:

Pie/Donut


Relationship:

Scatter plot


Do not choose charts only for visual appearance.


---

## 5. Filter Design


Determine whether interactive filters are needed.


Examples:


HR dashboard:

- department
- location
- year


Sales dashboard:

- region
- product
- time


---

## 6. Iterative Dashboard Refinement


The agent must support modification requests.


Examples:


User:

"Make it more executive"


Actions:


- simplify layout
- emphasize KPIs
- reduce unnecessary charts


User:

"Change color theme"


Actions:


- regenerate theme
- preserve data logic


Only modify affected components.


---

# Data Integrity Rules


Dashboard can only contain:


- available dataset fields
- validated metrics
- calculated values from tools


Never:

- invent data
- create fake KPI values
- create unsupported insights


---

# Output


Generate:


DashboardSchema


Including:


- theme
- layout
- components
- charts
- filters
- interactions
