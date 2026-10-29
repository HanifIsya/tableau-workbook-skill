---
name: tableau-workbook
description: >-
  Edit Tableau workbooks (.twb/.twbx) programmatically with Python and lxml. Use when adding
  or removing worksheets and dashboards, changing chart types or encodings, creating calculated
  fields, adding reference lines, fixing a missing .hyper extract or "Error 575215AA", packaging
  a .twbx, or checking whether a workbook actually opens in Tableau. Triggers on: .twb, .twbx,
  Tableau workbook, Tableau dashboard, Tableau worksheet, add a chart, twb XML, hyper extract,
  "must use extracts", "unable to create extract", Tableau crash on open, d2e8da72.
license: MIT
---

# Tableau Workbook Editing

Edit `.twb` files as XML. A `.twb` is plain XML; a `.twbx` is a ZIP containing a `.twb`
plus its data extracts.

**This skill exists because Tableau's DOM loader crashes on malformed XML with no useful
error message.** Every rule below was learned by breaking a real workbook and reading
Tableau's log to find out why. The reference files under `references/` document each
failure mode in full.

---

## Non-negotiable safety rules

1. **Never edit the original in place.** Call `wb.backup()` before any mutation.
   A malformed edit makes the workbook unopenable and the backup is the only way back.
2. **Never write a `.twb` you haven't re-parsed.** `wb.save()` re-parses the file after
   writing and raises if the XML is broken. Don't bypass it with a raw `tree.write()`.
3. **Validate before and after.** `wb.validate()` returns a list of structural problems.
   An empty list means the workbook is consistent.
4. **Clone, don't author.** Build new sheets by deep-copying an existing worksheet and
   its window, then edit the copy. Writing `<table>` from scratch is how you end up with
   a workbook that won't load.
5. **Test in Tableau when you can.** `scripts/verify_workbook.py` launches Tableau and
   greps the log. Run it after every change.
6. **Document the change.** Write a markdown file recording the goal, the files touched,
   the exact edits, the verification result, and how to roll back.

---

## Setup

```bash
pip install lxml                    # required — XML editing
pip install tableaudocumentapi       # optional — validation and inspection
pip install tableauhyperapi pandas   # optional — building .hyper extracts
```

The helper library lives in `scripts/tableau_workbook.py`. Copy it next to your work,
or add that directory to `PYTHONPATH`.

---

## The workflow

```python
from tableau_workbook import Workbook

wb = Workbook.load("AVD TEO.twb")
wb.backup("backups")                        # 1. always

ws = wb.clone_worksheet("Sales by Month", "Regional Sales and Profit")  # 2. clone
wb.set_shelves(ws, rows=wb.field("Region", "None"), cols=wb.field("Sales", "Sum"))
wb.set_mark_class(ws, "Bar")
wb.set_encodings(ws, [("color", wb.field("Profit", "Sum"))])

wb.add_dashboard("Dashboard 7", [          # 3. dashboard
    {"name": "Regional Sales and Profit", "id": 3, "x": 1000, "y": 2000,
     "w": 98000, "h": 88000},
])

problems = wb.validate()                    # 4. validate
assert not problems, problems

wb.save()                                    # 5. save (re-parses automatically)
wb.package_twbx("AVD TEO.twbx", "Orders.hyper")  # 6. ship it self-contained
```

Then verify:

```bash
python scripts/verify_workbook.py "AVD TEO.twb"
python scripts/verify_workbook.py "AVD TEO.twbx"
```

---

## The one structural rule that matters most

**Every worksheet must appear in both `<worksheets>` and `<windows>`. Every dashboard
must appear in both `<dashboards>` and `<windows>`.** Miss one and Tableau shows a
broken or missing view.

`clone_worksheet()` handles this for you. If you hand-roll the XML, remember:

```xml
<workbook>
  <datasources/>
  <worksheets>  <worksheet name="My Sheet">...</worksheet>  </worksheets>
  <dashboards>  <dashboard name="Dashboard 7">...</dashboard>  </dashboards>
  <windows>     <window class="worksheet" name="My Sheet">...</window>  </windows>
</workbook>
```

---

## Pitfalls that crash Tableau

Each of these produces the same symptom — *"Errors occurred while trying to load the
workbook"* with error code `d2e8da72` in the log. The reference files have the exact
XML for each fix.

| # | The mistake | The fix | Reference |
|---|---|---|---|
| 05 | Writing `<window class="worksheet" name="X"/>` by hand | Deep-copy an existing `<window>` and rename it | `references/05-window-structure-pitfall.md` |
| 06 | `<reference-line formula="constant" value="0.0"/>` | Use `formula="average"` with a `value-column` | `references/06-reference-line-formula-pitfall.md` |
| 07 | Reference line on a `[usr:Calculation...]` field | Reference lines only attach to native measures | `references/07-calculated-field-and-refline-pitfall.md` |
| 08 | `<customized-label>` inside `<pane>` | Multiple `<text column="..."/>` encodings + `mark-labels-show` | `references/08-customized-label-pitfall.md` |
| 09 | `<mark class="Map"/>` | `Circle` for symbol maps, `Polygon` for filled maps | `references/09-map-chart-and-tooltip-pitfall.md` |
| 09 | `<customized-tooltip>` inside `<pane>` | `<tooltip column="..."/>` encodings | `references/09-map-chart-and-tooltip-pitfall.md` |
| 10 | `<column>` inserted in the wrong position in `<datasource>` | All `<column>` elements together, then all `<column-instance>` | `references/10-datasource-column-order.md` |
| 11 | Two `<viewpoint>` elements with the same name | One viewpoint per **worksheet**, not per zone | `references/11-duplicate-visual-element-ids.md` |
| 11 | Two `<reference-line>` elements sharing an id | Replace the existing one, or use a fresh id | `references/11-duplicate-visual-element-ids.md` |
| 04 | Removing `<extract>` to fix a broken extract | Tableau Public *requires* an extract — rebuild it instead | `references/04-data-extract-fix.md` |

Pitfalls 10 and 11 were found by testing against a real Tableau install; both produce
the *same* unhelpful dialog as the others, so check them whenever a workbook that
"should be fine" refuses to open.

The library raises `WorkbookError` for most of these before you can save a broken file,
and `validate()` catches the rest.

---

## Fixing a broken extract (Error 575215AA)

The symptom is `Error Code: 575215AA ... Unable to create extract`, caused by the
workbook's `<extract>` pointing at a file under `AppData/Local/Temp` that Windows has
since deleted.

**Never let a workbook depend on a temp path.** The fix:

```bash
# 1. Build a permanent .hyper matching the workbook's extract schema
python scripts/build_hyper_extract.py workbook.twb "data.xlsx" "Orders$" -o "Orders.hyper"

# 2. Point the workbook at it and save
```

```python
wb.point_extract_at("Orders.hyper")
wb.save()
wb.package_twbx("workbook.twbx", "Orders.hyper")   # relative path inside the zip
```

Prefer shipping the `.twbx` — the extract travels with the workbook and the path inside
is relative, so it can never break again.

> Removing `<extract>` or setting `enabled="false"` does **not** fix this. It converts
> the crash into *"Workbooks saved to Tableau Public must use extracts."*

---

## Reading Tableau's log

The log is one JSON object per line at
`%USERPROFILE%\Documents\My Tableau Repository\Logs\log.txt`.

| Signal | Meaning |
|---|---|
| `setup-sheet-tabs` / `get-dashboard-sizing` | ✅ Workbook fully loaded, UI built |
| `load-workbook-dom` + `stack-unwind` | ❌ XML is broken — your edit is invalid |
| `show-detailed-error-dialog` | ❌ Runtime or data error — read the message |
| `excp-error-code":"0x575215AA"` | ❌ Missing `.hyper` extract |
| `errorcode=3c242d89` | ❌ No extract configured |
| `excp-error-code":"0xB0EF223F"` at `sev=info` | ✅ Benign query chatter — ignore |

**Always match by `pid`**, not by "the last N lines" — the log is multi-process and
interleaved, and tail-filtering gives false results. Always kill the exact process you
started.

`scripts/verify_workbook.py` handles all of this for you.

---

## Field references

Tableau addresses fields as `[datasource].[derivation:Column:suffix]`.

```python
wb.field("Sales", "Sum")     # [federated.xxx].[sum:Sales:qk]
wb.field("Region", "None")   # [federated.xxx].[none:Region:nk]
```

| Derivation | Suffix | Use |
|---|---|---|
| `None` | `nk` | Nominal dimension |
| `Sum`, `Avg`, `Count`, `Min`, `Max` | `qk` | Quantitative measure |
| `Month`, `Year`, `Day`, `Weekday` | `ok` | Ordinal date part |
| `User` | `qk` | Calculated field (`[usr:...]`) |

---

## Dashboards

Zone coordinates are in **1/1000 of a percent** — `98000` means 98%.

```xml
<zone h="88000" id="3" name="My Sheet" w="98000" x="1000" y="2000"/>
<zone h="7000" id="4" name="My Sheet" pane-specification-id="0"
      param="[federated.xxx].[sum:Profit:qk]" type-v2="color"
      w="24000" x="74000" y="4000"/>
```

- Zone `id`s must be unique within a dashboard and match the ids used in `<devicelayouts>`.
- Zone `name` must exactly match an existing worksheet.
- Each worksheet zone usually gets a matching `type-v2="color"` legend zone.

---

## Reference files

Read these when you hit the corresponding problem:

| File | Covers |
|---|---|
| `references/01-workbook-structure.md` | Anatomy of a `.twb` — sections, worksheets, dashboards, windows, datasources, extract |
| `references/02-editing-guide.md` | Step-by-step editing with Python/lxml |
| `references/03-testing-guide.md` | Verifying a workbook opens, and reading the log |
| `references/04-data-extract-fix.md` | Fixing Error 575215AA and packaging a `.twbx` |
| `references/05`–`09` | The five crash pitfall files, one per failure mode |
| `references/10-datasource-column-order.md` | Why `<column>` must be grouped inside `<datasource>` — with the probe results |
| `references/11-duplicate-visual-element-ids.md` | "Duplicate visual element IDs" — viewpoints, reference lines, zone ids |
| `references/SAFETY-RULES.md` | The mandatory rules, written out |
| `references/changelog.md` | Worked examples of real changes, with before/after metrics |

---

## Checklist before you finish

- [ ] `wb.backup()` was called before any edit
- [ ] `wb.validate()` returns an empty list
- [ ] The saved file re-parses (automatic in `wb.save()`)
- [ ] `verify_workbook.py` reports PASSED for the `.twb` and the `.twbx`
- [ ] No extract path points at `AppData` or `Temp`
- [ ] Every new worksheet has a `<window>`
- [ ] No reference line sits on a `[usr:...]` field
- [ ] No `<customized-label>`, `<customized-tooltip>`, or `class="Map"`
- [ ] The change is documented with a rollback path
