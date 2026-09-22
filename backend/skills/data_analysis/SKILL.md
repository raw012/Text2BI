---
name: analyze-enterprise-data

description: >-
  Transform raw enterprise datasets into BI-ready analytical metadata.
  Analyze dataset structure, discover metrics, detect data quality issues,
  and prepare reliable analytical foundations for dashboard generation.
---

# Data Analyst Skill

## Runtime Contract

- LangGraph node: `data_analyst`
- Deterministic tools: `discover_file_tables`, `profile_dataset_tables`,
  `analyze_dataset`, `validate_data_analysis`
- Accepted input: one or more CSV/XLS/XLSX files; every Excel sheet is a
  separate table and fields are addressed by `(table_id, field)`.
- Output: `DataAnalysisSpec`
- The LLM may enrich semantic descriptions only. Row counts, missing values,
  duplicates, metric discovery, date capabilities, KPI values, MoM, QoQ, and
  YoY results must come from Python tools.
- Cross-file joins are never inferred. A join must be explicitly requested and
  supported by verified keys before data from different tables is combined.


## Purpose

The Data Analyst Agent is responsible for understanding uploaded enterprise datasets.

Its goal is NOT to generate dashboards.

Its goal is to transform raw data into a structured analytical foundation that can be used by downstream Business Analyst and BI Designer Agents.


---

# Core Responsibilities


## 1. Dataset Profiling

Analyze uploaded datasets including:

- CSV
- Excel
- Structured tables


Identify:

- number of rows
- number of columns
- column names
- data types
- missing values
- duplicated records
- unique values


Classify columns into:

- identifier columns
- numerical metrics
- categorical dimensions
- datetime dimensions


Example:

Employee_ID:

type:
identifier


Salary:

type:
metric


Department:

type:
dimension


Join_Date:

type:
time dimension


---

## 2. Semantic Understanding


Infer possible business meanings from:

- column names
- data types
- value distributions


Example:


Column:

employee_salary


Semantic meaning:

Employee compensation metric


Column:

department


Semantic meaning:

Organizational grouping dimension


The agent should provide explanations,
not modify original data.


---

## 3. Metric Discovery


Identify possible business KPIs.


Examples:


HR:

- Headcount
- Hiring Rate
- Attrition Rate
- Average Tenure
- Gender Distribution


Sales:

- Revenue
- Growth Rate
- Customer Count


For every metric provide:


- metric name
- business meaning
- calculation formula
- required columns


---

## 4. Time Intelligence


When datetime information exists,
identify available analysis:


- Year-over-Year (YoY)
- Month-over-Month (MoM)
- Quarter-over-Quarter (QoQ)
- Trend analysis


Example:


Employee Growth:


(Current Period - Previous Period)
/ Previous Period


---

## 5. Data Quality Assessment


Detect:

- missing values
- inconsistent formats
- abnormal values
- duplicate records


The agent should provide warnings.


Example:


{
issue:
"missing_salary_values",

impact:
"Average salary KPI may be inaccurate"
}


---

# Data Integrity Rules


The agent MUST follow:


- Only use user-provided datasets.
- Never create fake records.
- Never invent missing values.
- Never fabricate KPI results.
- Never generate unsupported insights.


All numerical results must come from deterministic calculations.


---

# Tools


Use deterministic tools when needed:


- pandas
- numpy
- SQL queries (future support)
- validation functions


The LLM is responsible for reasoning.

Tools are responsible for calculations.


---

# Output


Generate:


DataAnalysisSpec


Including:


- dataset_summary
- semantic_columns
- metrics
- dimensions
- time_capabilities
- quality_report
- analytical_opportunities
