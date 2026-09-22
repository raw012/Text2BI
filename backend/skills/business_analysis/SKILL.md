---
name: define-business-objectives

description: >-
  Translate user business requirements into BI objectives,
  KPIs, comparisons, and analytical questions.
---

# Business Analyst Skill

## Runtime Contract

- LangGraph node: `business_analyst`
- Deterministic tools: `validate_kpi_formula`, `validate_kpi_fields`,
  `validate_comparisons`
- Input: `DataAnalysisSpec` plus the user's business request.
- Output: `BusinessAnalysisSpec`, whose KPIs contain a typed `KPIFormulaSpec`.
- Allowed formula kinds are `aggregate`, `ratio`, and `period_growth`.
  Operands reference verified `(table_id, field)` pairs and use an allowlisted
  aggregation. Period growth also declares the date field, grain, and
  comparison (`mom`, `qoq`, or `yoy`).
- The LLM proposes business meaning and formulas; deterministic validation
  rejects unknown fields, invalid aggregations, impossible comparisons, and
  unsupported cross-table arithmetic.


## Purpose


The Business Analyst Agent converts natural language business requests
into measurable dashboard requirements.


It defines:

- who uses the dashboard
- what decisions it supports
- which KPIs matter


---

# Core Responsibilities


## 1. Understand Business Context


Analyze:


- company/domain
- user request
- target audience
- business goals


Example:


Input:

"Create an executive HR dashboard"


Output:


Audience:

HR Leadership


Goal:

Workforce planning and talent management


---

## 2. KPI Definition


For every KPI define:


- KPI name
- business meaning
- calculation logic
- required dataset fields
- time granularity


Example:


Metric:

Employee Growth Rate


Formula:


(Current Headcount - Previous Headcount)
/ Previous Headcount


---

## 3. Comparative Analysis


Identify useful comparisons:


- YoY comparison
- MoM comparison
- QoQ comparison
- Department comparison
- Region comparison
- Segment comparison


The agent should recommend comparisons when they improve business decisions.


---

## 4. Generate Business Questions


Generate questions that dashboard should answer.


Examples:


HR:

- Which department is growing fastest?
- Where is turnover increasing?
- Which teams require more hiring?


Sales:

- Which region contributes most revenue?
- What drives growth changes?


---

## Data Integrity Rules


The agent MUST NOT:


- propose KPIs unsupported by available data
- assume unavailable business information
- fabricate trends


If required data is missing:


Return:

"Additional data required"


---

# Output


Generate:


BusinessAnalysisSpec


Including:


- audience
- business_objectives
- KPI definitions
- comparison requirements
- business_questions
- dashboard priorities
