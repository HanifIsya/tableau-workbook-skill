> **Adapted for the `tableau-workbook` skill.** The examples below come from a real
> workbook (Tableau Public 2026.2, `version="18.1"`) and use placeholder identifiers.
> Replace `federated.xxxxxxxxxxxxxxxxxxxx` with your own datasource id — read it from
> `<datasource name="...">` in your `.twb`.

# 02 — Editing Guide: How to Modify a Tableau Workbook Programmatically

Tool: **Python + `lxml`** (precise XML control). Optionally `tableaudocumentapi` for validation.

```powershell
pip install lxml tableaudocumentapi
```

---

## Step 0 — Safety first

```powershell
Copy-Item "workbook.twb" "workbook.twb.bak" -Force   # backup FIRST
```

Work on a copy, verify, then replace the real file.

---

## Step 1 — Load the workbook

```python
from lxml import etree

SRC = "workbook.twb"
tree = etree.parse(SRC)          # raises if XML is malformed
root = tree.getroot()

# handy handles
worksheets = root.find("worksheets")
dashboards = root.find("dashboards")
windows    = root.find("windows")
thumbs     = root.find("thumbnails")
```

> Use **`lxml.etree`**, not `xml.etree` — lxml preserves namespaces, comments and attribute order much better.

---

## Step 2 — Add a worksheet

A worksheet needs **3 pieces**: `<worksheet>` + `<window>` (+ optional `<thumbnail>`).

```python
import uuid

def new_guid():
    return "{" + str(uuid.uuid4()).upper() + "}"

def add_worksheet(root, name, table_xml):
    """
    table_xml: an XML string for the <table>...</table> body.
    name: must NOT contain '&' (use 'and').
    """
    ws_xml = f'''
    <worksheet xmlns:user="http://www.tableausoftware.com/xml/user" name="{name}">
      {table_xml}
      <simple-id uuid="{new_guid()}"/>
    </worksheet>'''
    ws = etree.fromstring(ws_xml)
    root.find("worksheets").append(ws)

    # mirror into <windows>  ← REQUIRED (deep-copy an existing window to keep <cards>!)
    # ⚠️ Do NOT use bare `<window class="worksheet" name="{name}"/>` — see 05-window-structure-pitfall.md
    existing_win = root.find("windows/window[@class='worksheet']")
    win = copy.deepcopy(existing_win)
    win.set("name", name)
    sid = win.find("simple-id")
    if sid is not None:
        sid.set("uuid", new_guid())
    else:
        win.append(etree.fromstring(f'<simple-id uuid="{new_guid()}"/>'))
    root.find("windows").append(win)
    return ws
```

### Minimal `<table>` body (a bar chart)

```xml
<table>
  <rows>
    <column agg='sum'>
      <datatype>real</datatype>
      <caption>Sales</caption>
      <remote>...datasource ref...</remote>
    </column>
  </rows>
  <cols>
    <column>
      <datatype>string</datatype>
      <caption>Region</caption>
    </column>
  </cols>
  <marks>
    <aggregation>Sum</aggregation>
    <type>Bar</type>
  </marks>
  <slices/>
  <panes>
    <pane>
      <view>
        <column caption="Region" datatype="string" .../>
        <column caption="Sales"  datatype="real"   .../>
      </view>
      <!-- encodings / reference lines -->
    </pane>
  </panes>
  <style/>
</table>
```

> **Tip used in this project:** build the new worksheet by **deep-copying an existing worksheet** (`copy.deepcopy`) and then editing its captions/columns. This guarantees you inherit valid encodings, style and datasource references — far safer than writing `<table>` from scratch.

```python
import copy
existing = root.find("worksheets/worksheet[@name='Sales by Month']")
new_ws   = copy.deepcopy(existing)
new_ws.set("name", "Regional Sales and Profit Analysis")
# ... then edit captions/encodings inside new_ws ...
root.find("worksheets").append(new_ws)
```

---

## Step 3 — Add a dashboard

```python
def add_dashboard(root, name, zones_xml, devicelayout_xml=""):
    dash_xml = f'''
    <dashboard xmlns:user="http://www.tableausoftware.com/xml/user"
               enable-sort-zone-taborder="true" name="{name}">
      <style/>
      <size maxheight="860" maxwidth="650" minheight="560" minwidth="420"/>
      <zones>
        {zones_xml}
      </zones>
      <devicelayouts>{devicelayout_xml}</devicelayouts>
      <simple-id uuid="{new_guid()}"/>
    </dashboard>'''
    root.find("dashboards").append(etree.fromstring(dash_xml))

    # mirror into <windows>  ← REQUIRED
    win = etree.fromstring(f'''
    <window xmlns:user="http://www.tableausoftware.com/xml/user"
            class="dashboard" name="{name}">
      <viewpoints>
        <viewpoint name="{name}"><zoom type="entire-view"/></viewpoint>
      </viewpoints>
    </window>''')
    root.find("windows").append(win)
```

### Zone XML

```xml
<!-- worksheet zone: x/y/w/h are 1/1000 of a percent -->
<zone h="44000" id="3" name="Regional Sales and Profit Analysis"
      w="98000" x="1000" y="2000"/>
<!-- legend zone for that sheet -->
<zone h="10000" id="4" name="Regional Sales and Profit Analysis"
      pane-specification-id="0"
      param="[federated.xxxxxxxxxxxxxxxxxxxx].[sum:Profit:qk]"
      type-v2="color" w="45000" x="52000" y="44000"/>
```

Rules:
- `id` unique inside the dashboard; **reuse the same ids** in `<devicelayouts>`.
- `name` must equal an existing worksheet name.
- Each worksheet zone usually gets a matching `type-v2="color"` legend zone.

---

## Step 4 — Remove a worksheet

```python
def remove_worksheet(root, name):
    for path in ("worksheets/worksheet", "windows/window", "thumbnails/thumbnail"):
        el = root.find(f"{path}[@name='{name}']")
        if el is not None:
            el.getparent().remove(el)
    # ALSO remove any dashboard <zone name="{name}">
    for z in root.findall(f"dashboards/dashboard/zones/zone[@name='{name}']"):
        z.getparent().remove(z)
```

---

## Step 5 — Validate

```python
# 1. XML still parses
tree.write("workbook.twb", encoding="utf-8", xml_declaration=True)
etree.parse("workbook.twb"); print("XML OK")

# 2. Structural counts
from tableaudocumentapi import Workbook
wb = Workbook("workbook.twb")
print(len(wb.worksheets), "worksheets /", len(wb.dashboards), "dashboards")

# 3. Consistency: every worksheet has a window, every zone points to a real sheet
ws_names = {w.get("name") for w in root.findall("worksheets/worksheet")}
win_names = {w.get("name") for w in root.findall("windows/window")}
assert ws_names <= win_names, ws_names - win_names
for z in root.findall("dashboards/dashboard/zones/zone"):
    if z.get("name") and z.get("type-v2") != "color":
        assert z.get("name") in ws_names, z.get("name")
print("Consistency OK")
```

---

## Step 6 — Test in Tableau Public (automated)

See [03-testing-guide.md](03-testing-guide.md).

---

## Step 7 — Document the change

Create `docs/changes/YYYY-MM-DD-<description>.md` following [SAFETY-RULES.md](SAFETY-RULES.md) Rule 2.

---

## Worked example — what was done to `workbook.twb`

| Step | Action | Result |
|---|---|---|
| A | Tried adding `<column>` tags under the datasource | ❌ workbook failed to load — **never do this** |
| B | Added 2 worksheets (deep-copied + edited) + 2 `<window>` entries, removed empty `Sheet 1` (worksheet + window + thumbnail) | ✅ loaded cleanly |
| C | Added `Dashboard 3` with 4 zones (2 sheets + 2 legends) + Phone devicelayout + window | ✅ loaded cleanly |
| D | Fixed missing `.hyper` extract → packaged `.twbx` | ✅ data loads, 0 error dialogs |

Final state: **8 worksheets, 3 dashboards, 11 windows**.
