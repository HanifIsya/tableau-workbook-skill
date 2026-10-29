> **Adapted for the `tableau-workbook` skill.** The examples below come from a real
> workbook (Tableau Public 2026.2, `version="18.1"`) and use placeholder identifiers.
> Replace `federated.xxxxxxxxxxxxxxxxxxxx` with your own datasource id — read it from
> `<datasource name="...">` in your `.twb`.

# 04 — Data Extract Fix (Error 575215AA)

> **Shortcut:** `scripts/build_hyper_extract.py` does steps 1–2 automatically, reading the
> schema straight out of the `.twb`:
>
> ```bash
> python scripts/build_hyper_extract.py workbook.twb "data.xlsx" "Sheet1$" -o "extract.hyper"
> ```

## The symptom

Opening the workbook showed:

```
Error Code: 575215AA
[SQLSTATE: 58S01]
DatabaseId: "hyper.file:C:\Users\<you>\AppData\Local\Temp\TableauTemp/
             #TableauTemp_0vh75bt1hbzol612c0jcr0vpfb1k.hyper"
Unable to create extract
```

Log keywords: `excp-error-code":"0x575215AA"` + `k":"hyper-protocol-connection-failure"`.

## The cause

The workbook's `<extract enabled="true">` pointed at a **temporary** file:

```
C:/Users/.../AppData/Local/Temp/TableauTemp/#TableauTemp_<random>.hyper
```

Windows/`TableauTemp` cleanup deleted that file. On reopen, Tableau can't find the database → 575215AA.

> **Pre-existing bug** — the untouched `.bak` references the *same* missing temp file, so this was never caused by our XML edits.

## Important constraint: Tableau Public needs an extract

Simply deleting `<extract>` produced a different error:

```
Workbooks saved to Tableau Public must use extracts. To create an extract,
click the Data Source tab, then select Create Extract.
The data source, the datasource, is not an extract.
```
(log: `errorcode=3c242d89`, `error-code-id="1009003913"`)

So the fix must be: **create a real, permanent `.hyper` extract** — not remove the extract.

---

## The fix (4 steps)

### 1. Build the `.hyper` from the live Excel

```powershell
pip install tableauhyperapi pandas xlrd
```

```python
import pandas as pd
from tableauhyperapi import (HyperProcess, Telemetry, Connection, CreateMode,
                             TableDefinition, TableName, SqlType, Inserter)

df = pd.read_excel("data.xlsx")   # the source rows, 21 cols

table_def = TableDefinition(
    table_name=TableName("Extract", "Extract"),
    columns=[
        TableDefinition.Column("Row ID",       SqlType.big_int()),
        TableDefinition.Column("Order ID",     SqlType.text()),
        TableDefinition.Column("Order Date",   SqlType.date()),
        TableDefinition.Column("Ship Date",    SqlType.date()),
        TableDefinition.Column("Ship Mode",    SqlType.text()),
        TableDefinition.Column("Customer ID",  SqlType.text()),
        TableDefinition.Column("Customer Name",SqlType.text()),
        TableDefinition.Column("Segment",      SqlType.text()),
        TableDefinition.Column("Country",      SqlType.text()),
        TableDefinition.Column("City",         SqlType.text()),
        TableDefinition.Column("State",        SqlType.text()),
        TableDefinition.Column("Postal Code",  SqlType.big_int()),
        TableDefinition.Column("Region",       SqlType.text()),
        TableDefinition.Column("Product ID",   SqlType.text()),
        TableDefinition.Column("Category",     SqlType.text()),
        TableDefinition.Column("Sub-Category", SqlType.text()),
        TableDefinition.Column("Product Name", SqlType.text()),
        TableDefinition.Column("Sales",        SqlType.double()),
        TableDefinition.Column("Quantity",     SqlType.big_int()),
        TableDefinition.Column("Discount",     SqlType.double()),
        TableDefinition.Column("Profit",       SqlType.double()),
    ])

with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
    with Connection(hp.endpoint, "extract.hyper",
                    create_mode=CreateMode.CREATE_AND_REPLACE) as c:
        c.catalog.create_schema("Extract")
        c.catalog.create_table(table_def)
        with Inserter(c, table_def) as ins:
            for row in df.itertuples(index=False):
                v = list(row)
                v[2]  = v[2].date()  if pd.notnull(v[2])  else None   # Order Date
                v[3]  = v[3].date()  if pd.notnull(v[3])  else None   # Ship Date
                v[11] = int(v[11])   if pd.notnull(v[11]) else None   # Postal Code
                ins.add_row(v)
            ins.execute()
```

**Column schema must match the `<extract>` `<metadata-record>` list in the `.twb`.** Dump it to confirm:

```python
for mr in root.find(".//datasources/datasource/extract").findall(".//metadata-record"):
    print(mr.findtext("remote-name"), mr.findtext("remote-type"), mr.findtext("local-type"))
# local_type: integer|date|string|real  →  SqlType.big_int|date|text|double
```

### 2. Point the workbook at it

```python
conn = root.find(".//datasources/datasource/extract/connection")
conn.set("dbname", r".\extract.hyper")
```

### 3. Test

Run the automated test → expect **0 error dialogs**. ✅ (`pid` run confirmed: 0 dialogs, `setup-sheet-tabs` present.)

### 4. Package into a `.twbx` (recommended)

A `.twbx` embeds the data, so it can't be lost again. The `.twb` inside must use a **relative** path:

```python
import zipfile
from lxml import etree

tree = etree.parse("workbook.twb")
tree.find(".//datasources/datasource/extract/connection") \
     .set("dbname", "Data/Extracts/extract.hyper")
twb_xml = etree.tostring(tree, encoding="utf-8", xml_declaration=True)

with zipfile.ZipFile("workbook.twbx", "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("workbook.twb", twb_xml)
    z.write("extract.hyper",
            "Data/Extracts/extract.hyper")
```

Open-test the `.twbx` → 0 error dialogs ✅.

---

## Options summary

| Option | Result |
|---|---|
| `extract enabled="false"` | ❌ still 575215AA (connection still references hyper) |
| Remove `<extract>` entirely | ❌ "Tableau Public must use extracts" |
| Recreate `.hyper` + set absolute `dbname` | ✅ works locally |
| **Package as `.twbx` with relative `dbname`** | ✅✅ best — portable, never loses data |

## Lesson

Never let a workbook depend on files under `AppData/Local/Temp`. Always ship a `.twbx`.
