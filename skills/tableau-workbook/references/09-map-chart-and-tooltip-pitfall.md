> **Adapted for the `tableau-workbook` skill.** The examples below come from a real
> workbook (Tableau Public 2026.2, `version="18.1"`) and use placeholder identifiers.
> Replace `federated.xxxxxxxxxxxxxxxxxxxx` with your own datasource id — read it from
> `<datasource name="...">` in your `.twb`.

# 09 — Map Chart Mark Class & Tooltip Pitfall (`Error d2e8da72`)

## The Symptoms

Tableau Public fails to open with:
```
Errors occurred while trying to load the workbook "...". The load was not able to complete successfully.
```
Log signature:
- `tabdoc:show-detailed-error-dialog` with `errorcode=d2e8da72` and `error-code-id="3538475634"`
- `k":"end-workbook-dom-loader.load-workbook-dom"` with `"type":"stack-unwind"`
- `tabs=False`

## The Causes

### 1. Unsupported `<mark class="Map"/>`
In Tableau workbook XML, `<mark class="Map"/>` is **invalid**. Tableau's DOM parser rejects `class="Map"` and crashes during `load-workbook-dom`.
- For proportional symbol maps (scatter/bubble over geocoded map), the valid mark class is `class="Circle"` or `class="Automatic"`.
- For filled choropleth maps, the valid mark class is `class="Polygon"` or `class="Automatic"`.

### 2. Manual `<customized-tooltip>` inside `<pane>`
Attempting to directly inject rich-text `<customized-tooltip><formatted-text><run>...</run></formatted-text></customized-tooltip>` as a child of `<pane>` triggers `TableauException` and crashes the workbook DOM loader (just like `<customized-label>` in pitfall 08).

## The Solutions

### 1. Use `class="Circle"` or `class="Polygon"` for Maps
```xml
<!-- ✅ CORRECT: Symbol map mark class -->
<pane>
  <mark class="Circle"/>
  ...
</pane>
```
With geographic shelves:
```xml
<rows>[federated...].[avg:Latitude (generated):qk]</rows>
<cols>[federated...].[avg:Longitude (generated):qk]</cols>
```

### 2. Configure Tooltips via `<tooltip column="..."/>` in `<encodings>`
Tableau's Marks card architecture includes a dedicated **Tooltip shelf**:
```xml
<encodings>
  <color column="[federated...].[sum:Profit:qk]"/>
  <size column="[federated...].[sum:Sales:qk]"/>
  <lod column="[federated...].[none:State:nk]"/>
  <text column="[federated...].[none:State:nk]"/>
  <text column="[federated...].[sum:Sales:qk]"/>
  <text column="[federated...].[sum:Profit:qk]"/>
  <!-- Dedicated Tooltip Shelf fields -->
  <tooltip column="[federated...].[none:Region:nk]"/>
  <tooltip column="[federated...].[sum:Quantity:qk]"/>
  <tooltip column="[federated...].[avg:Discount:qk]"/>
  <tooltip column="[federated...].[none:Calculation_1152062577319936:nk]"/>
</encodings>
```

### 3. Format Measures via `default-format`
Tableau automatically renders all encoded variables inside the interactive hover tooltip formatted cleanly:
```xml
<column datatype="real" default-format="c$#,##0" name="[Sales]" role="measure" type="quantitative"/>
<column datatype="real" default-format="c$#,##0" name="[Profit]" role="measure" type="quantitative"/>
<column datatype="real" default-format="p0.0%" name="[Discount]" role="measure" type="quantitative"/>
<column datatype="integer" default-format="#,##0" name="[Quantity]" role="measure" type="quantitative"/>
```
This loads cleanly with zero crashes and renders multi-field tooltips and labels.
