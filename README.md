# Tableau Workbook Skill

**Edit Tableau workbooks programmatically — as XML, with Python.**

A `.twb` file is plain XML. This skill gives Claude Code the knowledge, the library, and
the verification harness to add worksheets and dashboards, change chart types, create
calculated fields, fix broken data extracts, and ship self-contained `.twbx` packages —
without the trial-and-error that normally comes with Tableau's XML schema.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-skill-blueviolet.svg)](https://code.claude.com/docs/en/skills)

---

## Why this exists

Tableau's DOM loader crashes on malformed XML and tells you nothing useful:

```
Errors occurred while trying to load the workbook "...".
The load was not able to complete successfully.
```

Every error — a bare `<window>`, a reference line on a calculated field, a `<column>` in
the wrong place, two viewpoints sharing a name — produces **that same message**. The
useful information is only in Tableau's log file.

This skill encodes the rules, provides a library that refuses to create the broken
structures in the first place, and includes a harness that reads the log and tells you
what actually went wrong.

---

## Install

### Option 1 — install as a plugin (recommended)

Add the marketplace, then install the plugin:

```bash
# 1. Add this repo as a marketplace
claude plugin marketplace add HanifIsya/tableau-workbook-skill

# 2. Install the plugin
claude plugin install tableau-workbook-skill@hanifisya-tableau
```

Restart Claude Code (or run `/reload-plugins`). The skill is then available as
`/tableau-workbook:tableau-workbook`, and Claude can invoke it automatically whenever you
mention a `.twb` file, a Tableau dashboard, or a broken extract.

To remove it:

```bash
claude plugin uninstall tableau-workbook-skill@hanifisya-tableau
claude plugin marketplace remove hanifisya-tableau
```

### Option 2 — clone and load directly

```bash
git clone https://github.com/HanifIsya/tableau-workbook-skill.git
cd tableau-workbook-skill

# Load for a single session
claude --plugin-dir .

# Or copy the skill into your personal skills folder (available in every project)
cp -r skills/tableau-workbook ~/.claude/skills/
```

On Windows (PowerShell):

```powershell
git clone https://github.com/HanifIsya/tableau-workbook-skill.git
cd tableau-workbook-skill
claude --plugin-dir .
Copy-Item -Recurse skills\tableau-workbook "$env:USERPROFILE\.claude\skills\"
```

### Option 3 — use the library on its own

The Python library has no Claude Code dependency. Copy `scripts/tableau_workbook.py` into
your project and use it directly:

```bash
pip install lxml
```

---

## Use it

### In Claude Code

Ask for what you want, in plain language:

```
Add a worksheet showing Sales by Region colored by Profit, then put it on a new dashboard.
```

```
My workbook shows "Error 575215AA - Unable to create extract". Fix it.
```

```
The workbook opens but the dashboard is empty and Tableau says it may be corrupted.
```

Claude loads the skill, reads the reference docs for the specific failure, uses the
library, and verifies the result in Tableau.

### From Python

```python
import sys
sys.path.insert(0, "scripts")          # or wherever you cloned this repo
from tableau_workbook import Workbook

wb = Workbook.load("AVD TEO.twb")
wb.backup("backups")                   # always

ws = wb.clone_worksheet("Sales by Month", "Regional Sales and Profit")
wb.set_shelves(ws, rows=wb.field("Region", "None"), cols=wb.field("Sales", "Sum"))
wb.set_mark_class(ws, "Bar")
wb.set_encodings(ws, [("color", wb.field("Profit", "Sum"))])
wb.show_mark_labels(ws)

wb.add_dashboard("Dashboard 7", [
    {"name": "Regional Sales and Profit", "id": 3,
     "x": 1000, "y": 2000, "w": 98000, "h": 88000},
    {"name": "Regional Sales and Profit", "id": 4, "type": "color",
     "param": wb.field("Profit", "Sum"), "x": 74000, "y": 4000, "w": 24000, "h": 7000},
])

problems = wb.validate()
assert not problems, problems          # refuses to save a broken workbook

wb.save()
wb.package_twbx("AVD TEO.twbx", "Orders.hyper")
```

Then verify it actually opens:

```bash
python scripts/verify_workbook.py "AVD TEO.twb"
python scripts/verify_workbook.py "AVD TEO.twbx"
```

```
Verification Results for pid=16724:
 - Total log lines: 712
 - Error dialogs:   0
 - XML / DOM bad:   0
 - Sheet tabs OK:   True
==> VERDICT: PASSED
```

---

## What the library does

| Method | Purpose |
|---|---|
| `Workbook.load(path)` | Parse a `.twb`; raises if the XML is broken |
| `wb.backup(dir)` | Copy the workbook before you touch it |
| `wb.save(path)` | Write **and re-parse** — never returns an unverified file |
| `wb.validate()` | Return a list of structural problems (empty = healthy) |
| `wb.clone_worksheet(src, new)` | Clone a sheet **and** its window, with fresh GUIDs |
| `wb.remove_worksheet(name)` | Remove from `<worksheets>`, `<windows>`, `<thumbnails>`, zones |
| `wb.add_dashboard(name, zones)` | Add a dashboard with zones and a phone layout |
| `wb.set_shelves(ws, rows=, cols=)` | Set the rows/cols shelves |
| `wb.set_mark_class(ws, cls)` | Set the mark type (rejects invalid classes) |
| `wb.set_encodings(ws, pairs)` | Set color/size/lod/text/tooltip encodings |
| `wb.add_calculated_field(ws, ...)` | Define a calculated field, returns its `[usr:...]` ref |
| `wb.add_datasource_field(...)` | Add a field to the datasource's global column list |
| `wb.add_reference_line(ws, ...)` | Attach a reference line (rejects calculated fields) |
| `wb.set_palette(ws, field, palette)` | Apply a colour palette |
| `wb.show_mark_labels(ws)` | Turn on mark labels |
| `wb.point_extract_at(path)` | Point the extract at a `.hyper` file |
| `wb.package_twbx(out, hyper)` | Build a self-contained `.twbx` with a relative path |
| `wb.field("Sales", "Sum")` | Build a field reference like `[federated.x].[sum:Sales:qk]` |

---

## The pitfalls it prevents

Every entry here was found by breaking a real workbook and reading Tableau's log. All
of them produce the same useless dialog, which is why they're worth encoding.

| # | The mistake | What Tableau says |
|---|---|---|
| 05 | Writing `<window class="worksheet" name="X"/>` by hand | DOM loader crash |
| 06 | `<reference-line formula="constant">` | DOM loader crash |
| 07 | Reference line on a `[usr:Calculation...]` field | DOM loader crash |
| 08 | `<customized-label>` inside `<pane>` | DOM loader crash |
| 09 | `<mark class="Map"/>` | DOM loader crash |
| 09 | `<customized-tooltip>` inside `<pane>` | DOM loader crash |
| 10 | `<column>` inserted in the wrong position in `<datasource>` | DOM loader crash |
| 11 | Two `<viewpoint>` elements sharing a name | "duplicate visual element IDs" |
| 11 | Two `<reference-line>` elements sharing an `id` | "duplicate visual element IDs" |
| 04 | Removing `<extract>` | "Tableau Public must use extracts" |
| 04 | Extract path under `AppData\Local\Temp` | Error 575215AA |

Two of these — #10 and #11 — were **not** in the original project notes. They were
found by building controlled variants of a working workbook, changing exactly one thing
each, and opening every one in Tableau. The evidence is in
[`references/10-datasource-column-order.md`](skills/tableau-workbook/references/10-datasource-column-order.md)
and
[`references/11-duplicate-visual-element-ids.md`](skills/tableau-workbook/references/11-duplicate-visual-element-ids.md).

Note that #10 corrects an earlier assumption: `<column>` elements under `<datasource>`
are perfectly valid — they just have to be **grouped** (all columns together, then all
column-instances). The pristine Tableau-authored workbook contains nine of them.

---

## Repository layout

```
tableau-workbook-skill/
├── .claude-plugin/
│   ├── plugin.json               # plugin manifest
│   └── marketplace.json          # marketplace entry
├── skills/tableau-workbook/
│   ├── SKILL.md                  # the skill itself
│   └── references/               # 12 reference docs, one per topic
├── scripts/
│   ├── tableau_workbook.py       # the editing library
│   ├── verify_workbook.py        # log-based verification harness
│   └── build_hyper_extract.py    # rebuild a missing .hyper extract
├── tests/
│   └── test_tableau_workbook.py  # 40 assertions against a real workbook
└── examples/
    └── example_workflow.py       # runnable end-to-end walkthrough
```

---

## Requirements

| Component | Needed for | Install |
|---|---|---|
| Python 3.9+ | everything | — |
| `lxml` | XML editing | `pip install lxml` |
| `tableaudocumentapi` | optional extra validation | `pip install tableaudocumentapi` |
| `tableauhyperapi`, `pandas` | rebuilding `.hyper` extracts | `pip install tableauhyperapi pandas xlrd openpyxl` |
| Tableau Public or Desktop | the verification harness | [tableau.com](https://www.tableau.com/products/public/download) |

The verification harness is **optional** — you can edit workbooks without Tableau
installed. It just won't be able to prove the result opens.

---

## Development

```bash
# Run the test suite against your own workbook
python tests/test_tableau_workbook.py "C:\\path\\to\\workbook.twb"

# Dry-run the example workflow
python examples/example_workflow.py "C:\\path\\to\\workbook.twb"
```

The test suite builds modified copies in a temporary directory and never touches your
original workbook.

---

## Contributing

Found a new way to break a workbook? That's the most valuable contribution possible.

1. Reproduce it against a working workbook — change exactly one thing.
2. Open the result in Tableau and confirm the failure.
3. Grep Tableau's log for the pid and identify the signature.
4. Add a reference doc under `skills/tableau-workbook/references/` with the symptom, the
   cause, the fix, and the probe results.
5. Add a check to `Workbook.validate()` so it can't be reintroduced silently.
6. Add a test to `tests/test_tableau_workbook.py`.

---

## License

MIT — see [LICENSE](LICENSE).

Tableau, Tableau Public, and `.twb`/`.twbx` are trademarks of Tableau Software, LLC.
This project is not affiliated with or endorsed by Tableau Software.
