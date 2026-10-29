# Worked examples — real changes, with before/after metrics

These are condensed from an actual multi-week project where a Tableau Public workbook was
extended from 8 worksheets / 3 dashboards up to 13 worksheets / 6 dashboards, with every
pitfall in `references/05`–`09` discovered along the way.

Each entry follows the [change-log format](#change-log-format) from `SAFETY-RULES.md`.

---

## Change 1 — Add 2 worksheets + a dashboard, remove an empty sheet

**Goal.** Extend the workbook with two analytical charts and a dashboard showing them side
by side. Drop the unused default `Sheet 1`.

**What was added.**

| Worksheet | Chart | Detail |
|---|---|---|
| `Regional Sales and Profit Analysis` | Bar | Sales by Region, colored by Profit, average reference line on Sales |
| `Category and Segment Breakdown` | Stacked bar | Sales by Category, stacked by Segment |

Both worksheets were produced by **deep-copying an existing sheet and its window**, then
editing the copy — not by writing `<table>` from scratch.

`Sheet 1` was removed from `<worksheets>`, `<windows>` **and** `<thumbnails>`. Leaving the
thumbnail behind leaves a dangling preview.

**Dashboard.** `Dashboard 3`, size `minwidth=420 maxwidth=650 minheight=560 maxheight=860`,
four zones:

| id | name | type | x | y | w | h |
|---|---|---|---|---|---|---|
| 3 | Regional Sales and Profit Analysis | worksheet | 1000 | 2000 | 98000 | 44000 |
| 4 | Regional Sales and Profit Analysis | color legend | 52000 | 44000 | 45000 | 10000 |
| 5 | Category and Segment Breakdown | worksheet | 1000 | 52000 | 98000 | 42000 |
| 6 | Category and Segment Breakdown | color legend | 52000 | 93000 | 45000 | 10000 |

Plus a `<devicelayouts>` block with an auto-generated **Phone** layout
(nested `layout-basic` → `layout-flow` → the two worksheet zones).

**Counts after.** 8 worksheets, 3 dashboards, 11 windows.

**What was tried and rejected.** Adding `<column>` tags directly under `<datasources>` made
the workbook fail to load entirely. Computed fields belong in the worksheet's
`<datasource-dependencies>`.

**Lesson.** Raw `&` in a sheet name breaks XML parsing — use the word "and".

---

## Change 2 — Fix the missing `.hyper` extract (Error 575215AA)

**Goal.** The workbook opened but showed:

```
Error Code: 575215AA   [SQLSTATE: 58S01]
Unable to create extract
```

**Diagnosis.** The `<extract enabled="true">` pointed at a file under
`AppData/Local/Temp/TableauTemp/`. Windows had already deleted it. The *pristine backup
referenced the same missing file* — so this was a pre-existing bug, not caused by the XML
edits.

**Fixes that were tested and rejected.**

| Option | Result |
|---|---|
| `extract enabled="false"` | ❌ still 575215AA — the connection still references the hyper |
| Remove `<extract>` entirely | ❌ *"Workbooks saved to Tableau Public must use extracts"* (`errorcode=3c242d89`) |

**What worked.** Rebuild a permanent `.hyper` from the source data with `tableauhyperapi`,
typed to match the workbook's `<extract>` `<metadata-record>` list exactly, then repoint the
workbook:

```xml
<connection class="hyper" dbname="C:\...\extract.hyper" .../>
```

Then package into a `.twbx` with a **relative** `dbname` so the data travels with the file:

```xml
<connection class="hyper" dbname="Data/Extracts/extract.hyper" .../>
```

**Verification.** Both `.twb` (absolute path) and `.twbx` (relative path) loaded with
**0 error dialogs** and `setup-sheet-tabs` present.

**Lesson.** Never let a workbook depend on files under `AppData/Local/Temp`. Always ship a
`.twbx`.

---

## Change 3 — Dashboard 4 and advanced visualizations

**Goal.** Add profit-margin, discount-vs-segment and portfolio-risk visuals, then compose
them into an executive dashboard.

**Three worksheets.**

| Worksheet | Chart | Shelves | Encodings |
|---|---|---|---|
| `Sub-Category Profit Margin Analysis` | Bar | rows: Sub-Category, cols: `[usr:Calculation_ProfitRatio:qk]` | color: profit ratio, diverging palette, sorted descending |
| `Discount and Segment Profitability Matrix` | Square | rows: Sub-Category, cols: Segment | color: net Profit, diverging palette |
| `Portfolio Risk and Volume Analysis` | Circle | cols: Sales, rows: Profit | size: Quantity, color: Avg Discount, lod + text: Sub-Category |

**Calculated field.** `[Calculation_ProfitRatio]` = `SUM([Profit]) / SUM([Sales])`,
defined inside `<datasource-dependencies>`:

```xml
<column caption="Profit Ratio" datatype="real" default-format="p0.0%"
        name="[Calculation_ProfitRatio]" role="measure" type="quantitative">
  <calculation class="tableau" formula="SUM([Profit]) / SUM([Sales])"/>
</column>
<column-instance column="[Calculation_ProfitRatio]" derivation="User"
                 name="[usr:Calculation_ProfitRatio:qk]" pivot="key" type="quantitative"/>
```

**Dashboard.** `Dashboard 4`, six zones (three sheets + three legends), plus a Phone
layout with vertical flow.

**Counts after.** 11 worksheets, 4 dashboards, 15 windows.

---

## Change 4 — Area chart with multi-variable labels

**Goal.** A colourful stacked area chart with detailed labels on every mark.

**Worksheet.** `Monthly Sales Trend by Product Category`.

- Mark class `Area`
- Columns: `[mn:Order Date:ok]` (Month), rows: `[sum:Sales:qk]`
- Color: discrete palette on `[none:Category:nk]` — sapphire `#2b5c8f`, amber `#f28e2b`,
  emerald `#2ca02c`
- White stroke between layers (`has-stroke="true"`, `stroke-color="#ffffff"`)
- Three `<text>` encodings: Category, Sales, Profit
- `mark-labels-show="true"`, `mark-labels-cull="false"`

**The pitfall.** The first attempt injected `<customized-label><formatted-text>` directly
into `<pane>`. Tableau crashed with `d2e8da72` / `stack-unwind`. The fix was multiple
`<text column="..."/>` encodings plus `default-format` on the `<column>` elements — see
`references/08-customized-label-pitfall.md`.

**Counts after.** 12 worksheets, 5 dashboards, 17 windows.

---

## Change 5 — Geographic map with a rich tooltip

**Goal.** A US map with size by sales, color by profit, and a multi-field tooltip.

**Worksheet.** `US Geographic Sales and Profitability Map`.

- Rows `[avg:Latitude (generated):qk]`, columns `[avg:Longitude (generated):qk]`
- Mark class **`Circle`** — *not* `Map`, which is invalid and crashes the loader
- Size: `[sum:Sales:qk]`, color: `[sum:Profit:qk]` (diverging red/green)
- Detail + text: `[none:State:nk]`
- Tooltip shelf: Region, Quantity, Avg Discount, and a "biggest loss" flag field
- Window carries `default-map-tool-selection tool="16"` for pan/zoom

**The pitfall.** `<customized-tooltip>` inside `<pane>` throws `TableauException`. The
correct approach is `<tooltip column="..."/>` encodings — see
`references/09-map-chart-and-tooltip-pitfall.md`.

**Counts after.** 13 worksheets, 6 dashboards, 19 windows.

---

## Change-log format

Every change gets its own markdown file:

```
docs/changes/YYYY-MM-DD-short-description.md
```

```markdown
# <Change title>

**Date:** YYYY-MM-DD
**Files touched:** ...

## Goal
What we wanted to achieve.

## Changes made
Exact edits — element added/removed/renamed, values set.

## Verification
How we proved it works (commands run, log lines, counts).

## Rollback
How to undo.

## Notes / gotchas
What to remember next time.
```

---

## Summary of what actually broke

| Attempt | Symptom | Root cause | Reference |
|---|---|---|---|
| `<column>` under `<datasources>` | Workbook won't load | Computed fields don't belong there | `01` |
| Bare `<window class="worksheet"/>` | `d2e8da72` + `stack-unwind` | DOM loader needs the full card structure | `05` |
| `formula="constant"` reference line | `d2e8da72` | Only standard analytics formulas are accepted | `06` |
| Reference line on `[usr:...]` | `d2e8da72` | Instant-analytics can't resolve calculated measures | `07` |
| `<customized-label>` in `<pane>` | `d2e8da72` | Not accepted as a pane child | `08` |
| `<mark class="Map"/>` | `d2e8da72` | Invalid mark class | `09` |
| `<customized-tooltip>` in `<pane>` | `d2e8da72` | Not accepted as a pane child | `09` |
| Removing `<extract>` | `3c242d89` | Tableau Public requires an extract | `04` |
| Extract path under `AppData\Local\Temp` | `575215AA` | Windows deleted the file | `04` |

**Every one of these produced the same unhelpful dialog.** The log is the only reliable
diagnostic — which is why `scripts/verify_workbook.py` filters by `pid` and maps error
codes to these causes.
