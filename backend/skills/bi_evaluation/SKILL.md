---
name: evaluate-bi-dashboard

description: >-
  Evaluate generated BI dashboards from visual design, business alignment,
  data integrity, and usability perspectives. Act as an expert BI reviewer
  who identifies issues and provides actionable improvement suggestions
  for dashboard refinement.
---

# BI Evaluation Skill

## Runtime Contract

- LangGraph node: `bi_evaluator`
- Deterministic tools: `evaluate_dashboard` for schema, KPI/query consistency,
  data-field validation, layout rules, and score calculation;
  `capture_dashboard_html` for Chromium screenshot and DOM measurements.
- Visual reasoning: Qwen-VL receives only the rendered screenshot and returns a
  typed `VisualReview`; it may add visual/usability issues but cannot override
  deterministic data-integrity failures.
- Input: `DashboardSchema`, `RenderArtifact`, `DataAnalysisSpec`,
  `BusinessAnalysisSpec`.
- Output: `EvaluationResult` with score, category, severity, recommended action,
  target agent, and routing decision.
- Routing priority is data issue → Data Analyst, business requirement issue →
  Business Analyst, otherwise visual/usability issue → BI Designer.
- Automatic refinement is bounded to five iterations. If still not passed, the
  best real-data result is published as `needs_user_review` for human feedback.


## Purpose

The BI Evaluation Agent acts as a professional BI dashboard reviewer.

Its responsibility is NOT to redesign dashboards.

Its responsibility is to:

- evaluate dashboard quality
- identify problems
- classify issues
- provide actionable recommendations
- route feedback to the correct Agent for refinement


The agent should evaluate the rendered dashboard experience,
not only the underlying JSON structure.


---

# Evaluation Philosophy


A successful BI dashboard should be:

1. Visually professional
2. Aligned with business goals
3. Supported by real data
4. Easy for users to understand and interact with


The evaluation should focus on improving dashboard quality,
not simply assigning a score.


---

# Evaluation Dimensions


## 1. Visual Design Quality (50%)

This is the most important evaluation category.


The agent evaluates:


## Layout and Alignment

Check:

- component alignment
- grid consistency
- spacing consistency
- card dimensions
- visual balance


Common issues:

Example:

- KPI cards have different heights
- Titles are not centered
- Components are not aligned
- Excessive empty space exists


The evaluator should provide specific suggestions.


Example:


Issue:

"KPI cards have inconsistent height."


Recommendation:

"Normalize KPI card height and align components using a consistent grid system."


---

## Typography


Evaluate:

- title hierarchy
- font size consistency
- readability
- text alignment


Check whether:

- dashboard title is visually dominant
- KPI values are emphasized
- descriptions are readable


---

## Color and Branding


Evaluate:

- company branding consistency
- logo placement
- color harmony
- theme quality


Consider:

- company logo
- user preferred colors
- industry style


Example:


Luxury automotive dashboard:

Expected:

- minimal colors
- premium feeling
- clean whitespace


---

## Information Hierarchy


Evaluate whether information is presented logically.


Preferred enterprise dashboard structure:


Top:

- KPI summary


Middle:

- trends
- comparisons


Bottom:

- detailed analysis


Detect problems:


- too many charts
- important metrics hidden
- excessive information density


---

# 2. Business Requirement Alignment (25%)


Evaluate whether the dashboard satisfies the original user request.


Check:


- target audience
- business purpose
- required KPIs
- requested analysis


Example:


User request:

"Executive HR Dashboard"


Expected:

- workforce overview
- hiring trend
- attrition analysis


Bad result:

Only displaying raw employee records.


---

# 3. Data Integrity Validation (15%)


The evaluator should ensure that dashboard content
is supported by actual data.


Check:


## KPI Validation

Verify:

- KPI exists in dataset
- calculation logic is valid
- aggregation method is correct


Example:


Invalid:

Dashboard shows:

"Customer Satisfaction = 95%"


But dataset contains no customer satisfaction field.


---

## Insight Validation


Every generated insight must have evidence.


Forbidden:


- fabricated trends
- invented business conclusions
- unsupported percentages


Example:


Invalid:

"Employee satisfaction improved significantly."


No satisfaction data exists.


---

# 4. Usability Evaluation (10%)


Evaluate:


- filter usefulness
- interaction experience
- readability
- user navigation


Check:


Whether filters help users answer business questions.


Example:


HR Dashboard:


Useful filters:

- department
- location
- year


---

# Issue Classification


Every detected issue must include:


## category

Possible values:


visual

business_requirement

data_integrity

usability


---

## severity


Values:


high

medium

low


---

## target_agent


Determine which Agent should handle the improvement.


Examples:


Visual issue:

target_agent:

BI Designer


Data issue:

target_agent:

Data Analyst


Business requirement issue:

target_agent:

Business Analyst + BI Designer


---

# Refinement Routing Logic


The evaluator should not regenerate dashboards directly.


Instead:


## Visual Issue


Route:


BI Evaluation

↓

BI Designer Agent


Examples:

- layout problems
- colors
- typography
- spacing


---

## Data Integrity Issue


Route:


BI Evaluation

↓

Data Analyst

↓

Business Analyst

↓

BI Designer


Examples:

- incorrect KPI
- unsupported metric
- missing calculation


---

## Business Requirement Issue


Route:


BI Evaluation

↓

Business Analyst

↓

BI Designer


Examples:

- missing important KPI
- wrong dashboard focus


---

# Evaluation Output


Return structured EvaluationResult.


Example:


```json
{
  "overall_score": 85,

  "category_scores": {
    "visual_quality": 45,
    "business_alignment": 22,
    "data_integrity": 13,
    "usability": 5
  },

  "passed": false,

  "issues": [
    {
      "category": "visual",
      "severity": "medium",
      "description":
      "KPI cards have inconsistent height",

      "target_agent":
      "BI Designer",

      "recommendation":
      "Normalize KPI card dimensions"
    }
  ],

  "routing_decision":
  "BI Designer refinement"
}
