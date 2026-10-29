"""End-to-end test of the tableau_workbook library against a real workbook.

Run it against your own workbook:

    python tests/test_tableau_workbook.py "C:\\path\\to\\workbook.twb"

The test builds modified copies in a temporary folder and never touches the
original. It exercises the library's editing helpers and its validator; it does
not launch Tableau. Use scripts/verify_workbook.py for that.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from lxml import etree  # noqa: E402
from tableau_workbook import Workbook  # noqa: E402

USER_NS = "http://www.tableausoftware.com/xml/user"

SRC = sys.argv[1] if len(sys.argv) > 1 else ""
if not SRC:
    print("usage: python tests/test_tableau_workbook.py <workbook.twb>")
    sys.exit(2)

TMP = tempfile.mkdtemp(prefix="tableau_workbook_test_")
WORK = os.path.join(TMP, "test.twb")
shutil.copy2(SRC, WORK)

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f"  -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def frag(xml):
    return etree.fromstring(f'<wrap xmlns:user="{USER_NS}">{xml}</wrap>')[0]


print("1. Load and validate the untouched workbook")
wb = Workbook.load(WORK)
check("loads", wb is not None)
check("validates clean", wb.validate() == [], str(wb.validate()))
check("counts", wb.counts()["worksheets"] >= 1, str(wb.counts()))

print("\n2. Validator catches a MISORDERED datasource column")
ds = wb.root.find(".//datasources/datasource")
ds.append(frag('<column datatype="string" name="[Bad]" role="dimension" type="nominal"/>'))
problems = wb.validate()
check("detects wrong order", any("expects" in p for p in problems), str(problems))
for child in list(ds):
    if child.get("name") == "[Bad]":
        ds.remove(child)
check("clean again after removal", wb.validate() == [], str(wb.validate()))

print("\n3. Validator catches an orphan column-instance")
ds.append(frag('<column-instance column="[Ghost]" derivation="None" '
                'name="[none:Ghost:nk]" pivot="key" type="nominal"/>'))
problems = wb.validate()
check("detects orphan instance", any("not declared" in p for p in problems), str(problems))
for child in list(ds):
    if child.get("name") == "[none:Ghost:nk]":
        ds.remove(child)

print("\n4. clone_worksheet mirrors the window")
source_sheet = wb.worksheet_names()[0]
before_ws, before_win = len(wb.worksheet_names()), len(wb.window_names())
ws = wb.clone_worksheet(source_sheet, "Test Cloned Sheet")
check("worksheet added", len(wb.worksheet_names()) == before_ws + 1)
check("window added", len(wb.window_names()) == before_win + 1)
check("window has cards", wb.window("Test Cloned Sheet").find("cards") is not None)
check("window has simple-id", wb.window("Test Cloned Sheet").find("simple-id") is not None)
check("worksheet has simple-id", ws.find("simple-id") is not None)
u1 = ws.find("simple-id").get("uuid")
u2 = wb.window("Test Cloned Sheet").find("simple-id").get("uuid")
check("uuids differ from source", u1 != wb.worksheet(source_sheet).find("simple-id").get("uuid"))
check("uuids differ from each other", u1 != u2)

print("\n5. Edit shelves, mark, encodings")
wb.set_shelves(ws, rows=wb.field("Region", "None"), cols=wb.field("Sales", "Sum"))
check("rows set", "Region" in ws.find(".//rows").text)
check("cols set", "Sales" in ws.find(".//cols").text)
wb.set_mark_class(ws, "Bar")
check("mark class", ws.find(".//panes/pane/mark").get("class") == "Bar")
wb.set_encodings(ws, [("color", wb.field("Profit", "Sum")), ("text", wb.field("Sales", "Sum"))])
encs = ws.find(".//panes/pane/encodings")
check("encodings count", len(encs) == 2, str(len(encs)))

print("\n6. set_mark_class rejects Map")
try:
    wb.set_mark_class(ws, "Map")
    check("rejects Map", False)
except Exception as e:
    check("rejects Map", "invalid" in str(e).lower())

print("\n7. add_reference_line guards")
try:
    wb.add_reference_line(ws, "[federated.x].[usr:Calc:qk]", "Avg")
    check("rejects usr field", False)
except Exception as e:
    check("rejects usr field", "calculated" in str(e).lower())
try:
    wb.add_reference_line(ws, "[federated.x].[sum:Sales:qk]", "Avg", formula="constant")
    check("rejects bad formula", False)
except Exception as e:
    check("rejects bad formula", "formula" in str(e).lower())
wb.add_reference_line(ws, wb.field("Sales", "Sum"), "Average Sales")
check("adds valid refline", len(ws.findall(".//reference-line")) >= 1,
      str(len(ws.findall(".//reference-line"))))
pane_kids = [c.tag for c in ws.find(".//panes/pane")]
if "style" in pane_kids and "reference-line" in pane_kids:
    check("refline before style", pane_kids.index("reference-line") < pane_kids.index("style"),
          str(pane_kids))

print("\n8. add_calculated_field")
ref = wb.add_calculated_field(ws, "TestCalc", "SUM([Profit]) / SUM([Sales])", fmt="p0.0%")
check("returns usr ref", "[usr:Calculation_TestCalc:qk]" in ref, ref)
check("calc in deps",
      ws.find(".//datasource-dependencies/column[@name='[Calculation_TestCalc]']") is not None)
ref2 = wb.add_calculated_field(ws, "Profit Ratio", "SUM([Profit]) / SUM([Sales])")
check("sanitises name", "[usr:Calculation_Profit_Ratio:qk]" in ref2, ref2)

print("\n9. add_dashboard")
wb.add_dashboard("Test Dashboard", [
    {"name": "Test Cloned Sheet", "id": 3, "x": 1000, "y": 2000, "w": 98000, "h": 88000},
    {"name": "Test Cloned Sheet", "id": 4, "type": "color",
     "param": wb.field("Profit", "Sum"), "x": 74000, "y": 4000, "w": 24000, "h": 7000},
])
check("dashboard added", "Test Dashboard" in wb.dashboard_names())
check("dashboard window added", "Test Dashboard" in wb.window_names())
check("has phone layout", wb.dashboard("Test Dashboard").find("devicelayouts") is not None)

print("\n10. add_dashboard rejects unknown sheet")
try:
    wb.add_dashboard("Bad Dashboard", [{"name": "Does Not Exist"}])
    check("rejects unknown sheet", False)
except Exception as e:
    check("rejects unknown sheet", "unknown worksheet" in str(e).lower())

print("\n11. add_datasource_field inserts in the right place")
r = wb.add_datasource_field("TestGlobal", datatype="string", role="dimension")
check("returns ref", "TestGlobal" in r, r)
kids = [c.tag for c in ds]
first_inst = kids.index("column-instance")
last_col = len(kids) - 1 - kids[::-1].index("column")
check("column before instances", last_col < first_inst, f"{kids}")

print("\n12. Save, re-parse, and validate")
problems = wb.validate()
check("still validates", problems == [], str(problems))
out = wb.save()
check("saved", os.path.exists(out))
etree.parse(out)
check("re-parses", True)

print("\n13. remove_worksheet cleans up everywhere")
wb2 = Workbook.load(out)
wb2.remove_worksheet("Test Cloned Sheet")
check("worksheet gone", "Test Cloned Sheet" not in wb2.worksheet_names())
check("window gone", "Test Cloned Sheet" not in wb2.window_names())
check("no orphan zones", not any(
    z.get("name") == "Test Cloned Sheet"
    for z in wb2.root.findall("dashboards/dashboard/zones/zone")))
check("validates after removal", wb2.validate() == [], str(wb2.validate()))

print("\n14. package_twbx writes a relative extract path")
twbx = os.path.join(TMP, "test.twbx")
wb2.package_twbx(twbx)
import zipfile
with zipfile.ZipFile(twbx) as z:
    names = z.namelist()
    inner = z.read([n for n in names if n.endswith(".twb")][0]).decode("utf-8")
check("twbx has twb", any(n.endswith(".twb") for n in names), str(names))
check("relative extract path", 'dbname="Data/Extracts/extract.hyper"' in inner)

print("\n15. backup() creates a restorable copy")
b = wb2.backup(TMP)
check("backup exists", os.path.exists(b))

print("\n16. Validator catches duplicate viewpoint names")
wb3 = Workbook.load(out)
dwin = wb3.root.find("windows/window[@name='Test Dashboard']")
vps = dwin.find("viewpoints")
vps.append(frag('<viewpoint name="Test Cloned Sheet"><zoom type="entire-view"/></viewpoint>'))
problems = wb3.validate()
check("detects duplicate viewpoint", any("duplicate visual element" in p for p in problems),
      str(problems))

print("\n17. add_dashboard emits one viewpoint per WORKSHEET")
wb4 = Workbook.load(out)
dwin4 = wb4.root.find("windows/window[@name='Test Dashboard']")
vp_names = [vp.get("name") for vp in dwin4.findall("viewpoints/viewpoint")]
check("one viewpoint per sheet", len(vp_names) == len(set(vp_names)), str(vp_names))
check("viewpoint count matches sheets", len(vp_names) == 1, str(vp_names))

print("\n18. add_reference_line replaces rather than duplicates")
wb5 = Workbook.load(out)
ws5 = wb5.worksheet("Test Cloned Sheet")
before = len(ws5.findall(".//reference-line"))
wb5.add_reference_line(ws5, wb5.field("Sales", "Sum"), "Another Average")
after = len(ws5.findall(".//reference-line"))
check("no duplicate reflines", after == before, f"{before} -> {after}")
ids = [rl.get("id") for rl in ws5.findall(".//reference-line")]
check("unique refline ids", len(ids) == len(set(ids)), str(ids))
check("validates", wb5.validate() == [], str(wb5.validate()))

print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    print(f"Artifacts left in {TMP}")
    sys.exit(1)
shutil.rmtree(TMP, ignore_errors=True)
print("ALL TESTS PASSED")
