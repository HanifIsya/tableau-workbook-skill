> **Adapted for the `tableau-workbook` skill.** The examples below come from a real
> workbook (Tableau Public 2026.2, `version="18.1"`) and use placeholder identifiers.
> Replace `federated.xxxxxxxxxxxxxxxxxxxx` with your own datasource id — read it from
> `<datasource name="...">` in your `.twb`.

# 07 — Calculated Fields and Reference Line Pitfalls

## The Symptom

Tableau Public crashes or shows error `d2e8da72` / `error-code-id="3538475634"` during `workbook-dom-loader.load-workbook-dom` (`stack-unwind`) when a reference line is added to a chart with a calculated measure.

## The Cause

In Tableau XML, `<reference-line>` works properly when attached to native aggregated columns (such as `[sum:Sales:qk]`, `[sum:Profit:qk]`, `[sum:Quantity:qk]`):

```xml
<!-- ✅ WORKS: Reference line on native measure -->
<reference-line axis-column="[federated...].[sum:Sales:qk]" enable-instant-analytics="true"
                formula="average" id="refline0" label="Average Sales" label-type="custom"
                probability="95" scope="per-table" value-column="[federated...].[sum:Sales:qk]" z-order="1"/>
```

However, attaching an instant analytics reference line to a user calculated field `[usr:Calculation...]`:

```xml
<!-- ❌ CRASH: Instant analytics average on user-defined table calculation / calculated field -->
<reference-line axis-column="[federated...].[usr:Calculation_ProfitRatio:qk]" enable-instant-analytics="true"
                formula="average" id="refline0" ... />
```

causes Tableau's internal DOM loader to fail because the instant-analytics averaging engine cannot automatically resolve secondary aggregations over calculated measures without explicit calculation dependency bindings.

## How to Properly Define Calculated Fields in Worksheets

Calculated fields can be safely defined inside the worksheet's `<datasource-dependencies>`:

```xml
<column caption="Profit Ratio" datatype="real" default-format="p0.0%" name="[Calculation_ProfitRatio]" role="measure" type="quantitative">
  <calculation class="tableau" formula="SUM([Profit]) / SUM([Sales])"/>
</column>
<column-instance column="[Calculation_ProfitRatio]" derivation="User" name="[usr:Calculation_ProfitRatio:qk]" pivot="key" type="quantitative"/>
```

You can safely use `[usr:Calculation_ProfitRatio:qk]` in:
- `<rows>` and `<cols>`
- `<shelf-sort-v2>` (sorting bars descending by calculated ratio)
- `<encodings>` (`<color>`, `<text>`, etc.)
- Mark styling and color palettes

Do NOT attach an automated instant-analytics `<reference-line>` to `[usr:...]` fields. Reserve `<reference-line>` for native quantitative measures (`[sum:Sales:qk]`, `[sum:Profit:qk]`).
