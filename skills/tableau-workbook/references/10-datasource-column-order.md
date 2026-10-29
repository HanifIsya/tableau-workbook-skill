# Probe results — the datasource `<column>` rule

All probes were built from the real, working `AVD TEO.twb` and opened in Tableau
Public 2026.2. Each probe changes exactly one thing.

| Probe | Change | Result |
|---|---|---|
| baseline | unmodified workbook | ✅ PASSED |
| **h** | plain `<column>` inserted right after `<aliases>` (before existing columns) | ✅ PASSED |
| **p** | calc `<column>` after last `<column>`, `<column-instance>` after all columns | ✅ PASSED |
| **q** | calc `<column>` after last `<column>`, **no** `<column-instance>` | ✅ PASSED |
| **r** | plain `<column>` + `<column-instance>`, correctly grouped | ✅ PASSED |
| **m** | calc `<column>` in a worksheet's `<datasource-dependencies>` | ✅ PASSED |
| **i** | plain `<column>` appended at the **end** (after `<object-graph>`) | ❌ FAILED |
| **g** | calc `<column>` + `<column-instance>` inserted right after `<aliases>` | ❌ FAILED |
| **k** | same as g, calc references `[Sales]` | ❌ FAILED |
| **l** | same as g, calc has a `<table-calc>` child | ❌ FAILED |
| **n** | calc `<column>` at datasource **plus** a worksheet dependency reference | ❌ FAILED |
| **o** | calc `<column>` at datasource plus an `<extract>` metadata-record | ❌ FAILED |
| **a** | calc `<column>` + instance appended at the end | ❌ FAILED |
| **b** | calc `<column>` referencing a nonexistent field | ❌ FAILED |
| **c** | `<column-instance>` pointing at a nonexistent column | ❌ FAILED |
| **d** | `<column>` with no datatype/role/type attributes | ❌ FAILED |

## The rule

Inside `<datasource>`, the child elements must appear in this order:

```xml
<datasource>
  <connection/>
  <aliases/>
  <column/>            ← all columns, together
  <column/>            ←
  <column-instance/>   ← then all instances, together
  <column-instance/>   ←
  <extract/>
  <layout/>
  <style/>
  <semantic-values/>
  <object-graph/>
</datasource>
```

**The rule is about ORDER, not about whether `<column>` is allowed.**

- Probe **h** inserted a plain `<column>` in the correct position → loaded fine.
- Probe **i** inserted the *same* column at the end of the datasource → crashed.
- Probe **g** inserted a `<column>` and its `<column-instance>` *adjacent* → crashed,
  because the instance came before the remaining `<column>` elements.
- Probe **p** put the instance after all columns → loaded fine.

So the failure in every ❌ case was one of:

1. a `<column>` placed after `<extract>` / `<object-graph>`, or
2. a `<column-instance>` placed before all `<column>` elements were finished.

## Correction to the original notes

The project notes said *"adding `<column>` tags directly under `<datasources>` makes the
workbook fail to load."* That is **not** the rule. The pristine, Tableau-authored
workbook contains **9** `<column>` elements and **2** `<column-instance>` elements
directly under `<datasource>`, and it loads perfectly.

What actually broke the original attempt was the **insertion position** — the elements
were appended at the end of the datasource instead of being grouped in the canonical
order.

**Both approaches work, provided the order is right:**

- Datasource-level `<column>` — the global field list; the field is available to every
  worksheet in the workbook. Must be grouped with the other columns.
- Worksheet-level `<datasource-dependencies>` `<column>` — scoped to one worksheet.
  Must be inside that worksheet's `<datasource-dependencies>` element.

## Why the crash was so hard to diagnose

Every failure produced the identical dialog (*"Errors occurred while trying to load the
workbook"*) and the identical log signature (`d2e8da72` + `stack-unwind`). Nothing in
the message points at element ordering. It took controlled probes against the real
application to establish the rule.
