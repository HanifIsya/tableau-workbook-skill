> **Adapted for the `tableau-workbook` skill.** The examples below come from a real
> workbook (Tableau Public 2026.2, `version="18.1"`) and use placeholder identifiers.
> Replace `federated.xxxxxxxxxxxxxxxxxxxx` with your own datasource id — read it from
> `<datasource name="...">` in your `.twb`.

# 05 — Window Structure Pitfall (DOM Loader Crash / Stack Unwind)

## The Symptom

Opening the modified workbook causes Tableau Public to fail with:

```
Errors occurred while trying to load the workbook "...". The load was not able to complete successfully.
```

Log signature:
- `k":"end-workbook-dom-loader.load-workbook-dom"` with `"type":"stack-unwind"`, `"msg":"an exception caused early termination..."`
- `tabdoc:show-detailed-error-dialog` with `errorcode=d2e8da72`, `error-code-id="3538475634"`
- `tabs=False` (Sheet tabs never finish setting up)

## The Cause

The workbook's `<windows>` section contains an incomplete `<window>` element. 
In `02-editing-guide.md`, the sample snippet suggested:

```xml
<!-- ❌ WRONG: Minimal self-closing window crashes DOM loader -->
<window xmlns:user="http://www.tableausoftware.com/xml/user" class="worksheet" name="My Sheet"/>
```

Tableau's internal workbook DOM loader expects `<window class="worksheet">` to have the full UI structure:
- `<cards>` with edges (`left`, `top`, `right`) containing cards for `pages`, `filters`, `marks`, `columns`, `rows`, `title`, etc.
- `<simple-id uuid="{...}"/>`
- `<active id="-1"/>` (optional depending on view)

When Tableau parses an empty `<window class="worksheet"/>` tag, its UI layout generator encounters missing card structures, throws an internal exception during `load-workbook-dom`, and unwinds the stack.

## The Solution

**Always deep-copy an existing `<window>` element from a working worksheet (or dashboard), update its `name` attribute, and assign a unique GUID to its `<simple-id>`.**

```python
import copy, uuid

def new_guid():
    return "{" + str(uuid.uuid4()).upper() + "}"

# 1. Clone the worksheet
new_ws = copy.deepcopy(existing_ws)
new_ws.set("name", new_name)
new_ws.find("simple-id").set("uuid", new_guid())
root.find("worksheets").append(new_ws)

# 2. Clone the window (DO NOT use bare <window class="worksheet" name="..." />)
new_win = copy.deepcopy(existing_win)
new_win.set("name", new_name)
sid = new_win.find("simple-id")
if sid is not None:
    sid.set("uuid", new_guid())
else:
    new_win.append(etree.fromstring(f'<simple-id uuid="{new_guid()}"/>'))
root.find("windows").append(new_win)
```

## Verification

When `<window>` is deep-copied properly:
- `pid` log shows 0 error dialogs
- `setup-sheet-tabs` executes successfully (`tabs=True`)
- UI initializes with default cards and shelf layout intact
