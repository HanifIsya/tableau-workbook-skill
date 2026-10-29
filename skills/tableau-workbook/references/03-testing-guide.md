> **Adapted for the `tableau-workbook` skill.** The examples below come from a real
> workbook (Tableau Public 2026.2, `version="18.1"`) and use placeholder identifiers.
> Replace `federated.xxxxxxxxxxxxxxxxxxxx` with your own datasource id — read it from
> `<datasource name="...">` in your `.twb`.

# 03 — Testing Guide: Verify a Workbook Actually Opens

Opening the file by hand works, but the **log** tells you whether it truly loaded. Automate it.

## Environment

| Item | Value |
|---|---|
| App | `C:\Program Files\Tableau\Tableau Public 2026.2\bin\tabpublic.exe` |
| Log | `%USERPROFILE%\Documents\My Tableau Repository\Logs\log.txt` |
| Log format | one JSON object per line, with `pid`, `sev`, `k` (event key), `v`/`a` (payload) |

---

## Test script

```python
import os, subprocess, time, json, uuid

TWB      = r"workbook.twb"
EXE      = r"C:\Program Files\Tableau\Tableau Public 2026.2\bin\tabpublic.exe"
LOG      = os.path.expanduser(r"~\Documents\My Tableau Repository\Logs\log.txt")

def test_workbook(twb=TWB, wait=8):
    # 1. launch
    p = subprocess.Popen([EXE, twb])
    time.sleep(wait)

    # 2. kill (always kill OUR pid — Start-Process reuse can grab a stale window)
    if p.poll() is None:
        p.kill()
    pid = p.pid
    p.wait()

    # 3. read only this run's log lines
    with open(LOG, encoding="utf-8", errors="replace") as f:
        lines = [l for l in f if f'"pid":{pid}' in l]

    errors  = [l for l in lines if "show-detailed-error-dialog" in l]
    xml_bad = [l for l in lines if "stack-unwind" in l or "parse-error" in l.lower()]
    ok_tab  = any("setup-sheet-tabs" in l for l in lines)

    print(f"pid={pid}  lines={len(lines)}  error-dialogs={len(errors)}  xml-errors={len(xml_bad)}  tabs={ok_tab}")
    for e in errors:
        try:
            msg = json.loads(e)["v"]["args"]
            print("  ERROR:", msg[:300])
        except Exception:
            print("  ERROR:", e[:300])
    return len(errors) == 0 and not xml_bad

if __name__ == "__main__":
    print("PASS" if test_workbook() else "FAIL")
```

---

## How to read the results

| Signal | Meaning |
|---|---|
| `k":"end-workspace.setup-sheet-tabs` / `get-dashboard-sizing` | ✅ workbook fully loaded, UI built |
| `k":"load-workbook-dom"` + `stack-unwind` / parse exception | ❌ XML broken — your edit is invalid |
| `tabdoc:show-detailed-error-dialog` with `error-short-message` | ❌ runtime/data error — read the message |
| `excp-error-code":"0x575215AA"` + `hyper-protocol-connection-failure` | ❌ missing `.hyper` extract → see [04-data-extract-fix.md](04-data-extract-fix.md) |
| `errorcode=3c242d89` / "must use extracts" | ❌ no extract configured — Tableau Public requires one |
| `excp-error-code":"0xB0EF223F"` at `info` sev (no dialog) | ✅ benign — usually harmless query chatter |

**PASS criteria:** no `show-detailed-error-dialog` for your pid **and** at least one `setup-sheet-tabs` line.

---

## Reading the error dialog line

```json
{"k":"begin-commands-controller.invoke-command",
 "v":{"args":"tabdoc:show-detailed-error-dialog error-code-id=\"1009003913\" \
 error-short-message=\"...\" error-details=[\"...\"] \
 error-help-link=\"https://help.tableau.com/...?errorcode=...\" \
 error-dialog-title=\"\"","name":"tabdoc:show-detailed-error-dialog"},
 "ctx":{"wb":"test_ext_removed"}}
```

- `error-short-message` → human explanation
- `errorcode=` inside `error-help-link` → searchable Tableau help article
- `ctx.wb` → which workbook file it came from (handy when testing several at once)

---

## Important gotchas

1. **Always kill the process you started.** A leftover `tabpublic.exe` will keep the log locked / steal your `Start-Process` capture. Check first:
   ```powershell
   Get-Process -Name "*tabpublic*" -ErrorAction SilentlyContinue
   ```
2. **Match by `pid`, not by "last N lines".** The log is multi-process and interleaved; line-tail filtering gives false results.
3. **Log writes are buffered** — add a 1–2 s pause before killing if results look stale.
4. **Only one test at a time** — concurrent runs make `pid` filtering ambiguous.

---

## Manual check (when in doubt)

Open the file in Tableau Public yourself and confirm:
- No red error dialog
- All sheets appear in the left pane
- Dashboard tiles render actual charts (not "empty"/grey)
- Data pane shows all 21 fields
