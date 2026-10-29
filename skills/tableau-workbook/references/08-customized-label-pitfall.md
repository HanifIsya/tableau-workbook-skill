> **Adapted for the `tableau-workbook` skill.** The examples below come from a real
> workbook (Tableau Public 2026.2, `version="18.1"`) and use placeholder identifiers.
> Replace `federated.xxxxxxxxxxxxxxxxxxxx` with your own datasource id — read it from
> `<datasource name="...">` in your `.twb`.

# 08 — Customized Label Pitfall (`<customized-label>` DOM Loader Crash)

## The Symptom

Tableau Public fails to open with:
```
Errors occurred while trying to load the workbook "...". The load was not able to complete successfully.
```

Log signature:
- `tabdoc:show-detailed-error-dialog` with `errorcode=d2e8da72` and `error-code-id="3538475634"`
- `k":"end-workbook-dom-loader.load-workbook-dom"` with `"type":"stack-unwind"`
- `tabs=False`

## The Cause

Attempting to inject custom rich-text label markup directly into `<pane>` using:

```xml
<!-- ❌ WRONG: Tableau DOM loader throws an exception on manual <customized-label> in <pane> -->
<customized-label>
  <formatted-text>
    <run bold="true">&lt;[federated...].[field]&gt;</run>
    <run>Sales: &lt;[federated...].[sum:Sales:qk]&gt;</run>
  </formatted-text>
</customized-label>
```

In Tableau Public 2026.2 XML, `<customized-label>` is not accepted as an arbitrary child of `<pane>`. Tableau's DOM parser expects standard mark label structures.

## The Solution

To provide rich, detailed labels on chart marks (such as dimension names and multiple quantitative measures):

1. **Add multiple `<text column="..."/>` encodings inside `<encodings>`**:
```xml
<encodings>
  <color column="[federated...].[none:Category:nk]"/>
  <text column="[federated...].[none:Category:nk]"/>
  <text column="[federated...].[sum:Sales:qk]"/>
  <text column="[federated...].[sum:Profit:qk]"/>
</encodings>
```

2. **Format measures cleanly using `default-format` on `<column>`**:
```xml
<column datatype="real" default-format="c$#,##0" name="[Sales]" role="measure" type="quantitative"/>
<column datatype="real" default-format="c$#,##0" name="[Profit]" role="measure" type="quantitative"/>
```

3. **Enable mark labels in `<style-rule element="mark">`**:
```xml
<style-rule element="mark">
  <format attr="mark-labels-show" value="true"/>
  <format attr="mark-labels-cull" value="false"/>
</style-rule>
```

Tableau automatically formats and displays the detailed multi-variable labels on the marks without crashing.
