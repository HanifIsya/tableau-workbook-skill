# 10 — Duplicate Visual Element IDs

## The Symptom

Tableau Public refuses to open the workbook:

```
Workbook dashboard contains duplicate visual element IDs;
the workbook may be corrupted.
```

Log signature: `tabdoc:show-detailed-error-dialog` with `error-code-id="547512337"` and
`errorcode=20a26011`. Sheet tabs never finish setting up.

## The Cause

Two elements inside the same view share an identifier. Tableau builds a registry of
visual elements per view and refuses to load the workbook when two entries collide.

There are **three** ways to trigger it:

### 1. Two `<viewpoint>` elements with the same name

This is the most common one. A dashboard window holds one `<viewpoint>` per **worksheet**
it displays — not per zone.

```xml
<!-- ❌ WRONG: one viewpoint per zone, so the legend zone repeats the sheet name -->
<viewpoints>
  <viewpoint name="Sales by Month"><zoom type="entire-view"/></viewpoint>
  <viewpoint name="Sales by Month"><zoom type="entire-view"/></viewpoint>
</viewpoints>

<!-- ✅ CORRECT: one viewpoint per worksheet -->
<viewpoints>
  <viewpoint name="Sales by Month"><zoom type="entire-view"/></viewpoint>
</viewpoints>
```

A dashboard with a sheet zone *and* a colour legend for that sheet has two zones but only
**one** worksheet, so it needs exactly one viewpoint.

### 2. Two `<reference-line>` elements sharing an `id`

```xml
<!-- ❌ WRONG: both use id="refline0" -->
<reference-line id="refline0" .../>
<reference-line id="refline0" .../>
```

Cloning a worksheet that already has a reference line and then adding another one
produces this. Either replace the existing reference line or give the new one a
different id (`refline1`, `refline2`, ...).

### 3. Duplicate zone `id` inside one dashboard

```xml
<!-- ❌ WRONG -->
<zone id="3" name="Sheet A" .../>
<zone id="3" name="Sheet B" .../>
```

Zone ids must be unique within a dashboard.

## The Solution

```python
# One viewpoint per worksheet — dedupe the zone names
seen = []
for z in zones:
    if z["name"] in seen:
        continue
    seen.append(z["name"])
    vps.append(f'<viewpoint name="{z["name"]}"><zoom type="entire-view"/></viewpoint>')
```

`Workbook.add_dashboard()` does this for you, and `Workbook.validate()` reports any
duplicate viewpoint names, duplicate reference-line ids and duplicate zone ids before
you save.

## How it was found

The symptom is identical to the DOM-loader crash in pitfalls 05–09, so the error
message alone does not distinguish them. It was isolated by building variants of a
working workbook that changed exactly one thing and opening each in Tableau:

| Variant | Result |
|---|---|
| Clone a worksheet only | ✅ PASSED |
| Clone + dashboard, worksheet zone only | ✅ PASSED |
| Clone + dashboard, sheet zone + colour legend | ❌ FAILED |
| Legend `param` matching the sheet's colour card | ❌ FAILED |
| Legend `param` differing from the sheet's colour card | ❌ FAILED |
| Clone + dashboard + legend, one viewpoint per worksheet | ✅ PASSED |

The legend zone itself was never the problem — **the second viewpoint it generated was.**

## Lesson

When adding a zone to a dashboard, ask what *worksheet* it displays, not how many zones
there are. Legends, parameter controls and filter cards all point back at a worksheet
that already has its own viewpoint.
