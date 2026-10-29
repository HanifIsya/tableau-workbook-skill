> **Adapted for the `tableau-workbook` skill.** The examples below come from a real
> workbook (Tableau Public 2026.2, `version="18.1"`) and use placeholder identifiers.
> Replace `federated.xxxxxxxxxxxxxxxxxxxx` with your own datasource id — read it from
> `<datasource name="...">` in your `.twb`.

# ⚠️ SAFETY RULES — READ FIRST BEFORE TOUCHING ANY TABLEAU FILE

These rules are **mandatory**. Never edit a Tableau workbook without following them.

---

## Rule 1 — ALWAYS make a copy before editing

**Never edit the original `.twb` / `.twbx` in place.**

```powershell
# Copy the project BEFORE any edit
Copy-Item "workbook.twb" "workbook.twb.bak"
```

- Keep the `.bak` file untouched for the whole session.
- If anything breaks, restore with:
  ```powershell
  Copy-Item "workbook.twb.bak" "workbook.twb" -Force
  ```
- For a full project, zip the whole folder first:
  ```powershell
  Compress-Archive -Path "workbook*" -DestinationPath "backup_$(Get-Date -Format yyyyMMdd_HHmmss).zip"
  ```

**Why:** A malformed XML edit will make the workbook unopenable. The backup is the only way back.

---

## Rule 2 — Every change gets its own markdown file

**Each time you make a change, write a NEW markdown file in `docs/changes/`.**

- File name pattern: `docs/changes/YYYY-MM-DD-short-description.md`
- It must contain:
  1. **Goal** — what we wanted to achieve
  2. **Files touched** — every file created/modified/deleted
  3. **Exact changes** — what was added/removed/renamed
  4. **Verification** — how we proved it works (log lines, test results)
  5. **Rollback** — how to undo it

This is the permanent memory of the project. Never rely on chat history alone.

---

## Rule 3 — Keep folders neat

**Create a folder for every new topic or batch of work.** Never dump loose files in the root.

Current layout:

```
your-project/
├── docs/                      ← all documentation
│   ├── README.md              ← index, start here
│   ├── SAFETY-RULES.md        ← this file
│   ├── 01-workbook-structure.md
│   ├── 02-editing-guide.md
│   ├── 03-testing-guide.md
│   ├── 04-data-extract-fix.md
│   └── changes/               ← one .md per change (NEW FILE EACH TIME)
├── workbook.twb                ← the live workbook
├── workbook.twb.bak            ← pristine backup
├── workbook.twbx               ← packaged workbook (self-contained)
└── extract.hyper  ← data extract
```

- New tool scripts → `scripts/`
- New temporary test files → `scratch/` (delete when done)
- New backups → `backups/`

---

## Rule 4 — Validate before and after every save

```python
from lxml import etree
tree = etree.parse("workbook.twb")   # raises if XML is broken
print("XML OK")
```

Then open it in Tableau Public and check the log (see `03-testing-guide.md`).

---

## Rule 5 — Clean up temp files when finished

Remove scratch scripts/test workbooks so the folder stays tidy. Keep only:
`workbook.twb`, `workbook.twb.bak`, `workbook.twbx`, data extract, and `docs/`.
