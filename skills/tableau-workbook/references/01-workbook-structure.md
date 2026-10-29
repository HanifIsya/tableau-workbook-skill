> **Adapted for the `tableau-workbook` skill.** The examples below come from a real
> workbook (Tableau Public 2026.2, `version="18.1"`) and use placeholder identifiers.
> Replace `federated.xxxxxxxxxxxxxxxxxxxx` with your own datasource id — read it from
> `<datasource name="...">` in your `.twb`.

# 01 — Tableau Workbook (`.twb`) Structure

A `.twb` file is **plain XML**. You can read and edit it with any XML library. A `.twbx` is a ZIP archive containing the `.twb` plus its data extracts.

## Top-level `<workbook>` children (in file order)

```xml
<workbook ... version="18.1" source-build="2026.2.1 (...)" source-platform="win">
  <document-format-change-manifest .../>
  <preferences/>
  <datasources>...</datasources>
  <worksheets>...</worksheets>
  <dashboards>...</dashboards>
  <windows saved-dpi-scale-factor="1.25" source-height="37">...</windows>
  <thumbnails>...</thumbnails>
</workbook>
```

| Section | Purpose |
|---|---|
| `datasources` | Data connections, calculations, the `<extract>` element |
| `worksheets` | Every chart/sheet definition (`<table>` = rows/columns/marks) |
| `dashboards` | Dashboard layout: `<zones>` + `<devicelayouts>` |
| `windows` | One `<window>` per openable view (worksheet **and** dashboard) — controls open tabs |
| `thumbnails` | Cached preview images — one `<thumbnail>` per sheet |

## ⚠️ The golden consistency rule

**Every worksheet you add must appear in BOTH `<worksheets>` and `<windows>`, and every dashboard in `<dashboards>` and `<windows>`.**

Miss one and Tableau shows a broken/missing view. When **removing** a sheet, delete it from `worksheets`, `windows`, *and* `thumbnails`.

## Worksheet anatomy

```xml
<worksheet name="Regional Sales and Profit Analysis">
  <table>
    <rows>  ... aggregation / column refs ... </rows>
    <cols>  ... </cols>
    <marks> <aggregation>...</aggregation> </marks>
    <slices/>
    <panes> <pane> ... encodings, reference lines ... </pane> </panes>
    <style/>
    <column caption="..." datatype="..." ...>
      <calculation .../>          <!-- optional: computed fields -->
    </column>                     <!-- belongs under datasource, see warning -->
    <formatted-value .../>
    <repository-location .../>
  </table>
  <simple-id uuid="{GUID}"/>
</worksheet>
```

- `<simple-id><uuid>` must be a **unique GUID** per element.
- `xmlns:user="http://www.tableausoftware.com/xml/user"` namespace must be present on root/elements that use `user:` prefixed attributes.

## Dashboard anatomy

```xml
<dashboard name="Dashboard 3" enable-sort-zone-taborder="true">
  <style/>
  <size maxheight="860" maxwidth="650" minheight="560" minwidth="420"/>
  <zones>
    <zone h="44000" id="3" name="Regional Sales and Profit Analysis" w="98000" x="1000" y="2000"/>
    <zone h="42000" id="5" name="Category and Segment Breakdown"    w="98000" x="1000" y="52000"/>
    <!-- legend/parameter zones: carry type-v2="color" and param="[federated...]" -->
  </zones>
  <devicelayouts>
    <devicelayout auto-generated="true" name="Phone">
      <size maxheight="950" minheight="950" sizing-mode="vscroll"/>
      <zones> <zone type-v2="layout-basic" ...> <zone type-v2="layout-flow" ...> ... </zone> </zones>
    </devicelayout>
  </devicelayouts>
  <simple-id uuid="{GUID}"/>
</dashboard>
```

- Coordinates `x`, `y`, `w`, `h` are in **1/1000 percent** (98000 = 98%).
- `zone id` numbers must be unique within the dashboard and **match the ids used in `devicelayouts`**.
- Zone `name` = worksheet name it displays; must exactly match a worksheet.
- `<devicelayouts>` is optional but recommended (phone/tablet layout).

## Window anatomy

```xml
<window class="worksheet" name="Regional Sales and Profit Analysis"> ... </window>
<window class="dashboard" name="Dashboard 3">
  <viewpoints>
    <viewpoint name="Some Sheet">
      <zoom type="entire-view"/>   <!-- fit-width | fit-height | entire-view | normal -->
      <highlight field="[federated...].[...]"> ... </highlight>
    </viewpoint>
  </viewpoints>
</window>
```

- `class` is `worksheet` or `dashboard`.

## Datasource & extract anatomy

```xml
<datasources>
  <datasource caption="the datasource" inline="true"
              name="federated.xxxxxxxxxxxxxxxxxxxx">
    <connection class="federated">
      <named-connections>
        <named-connection caption="excel-direct.1twfgy20mxen4o1c8ml551ijwrs6" name="...">
          <connection class="excel" dbname="data.xlsx" ...>
            <relation name="Orders" table="[Sheet1$]" type="table"/>
          </connection>
        </named-connection>
      </named-connections>
      <relation name="Orders" table="[Sheet1$]" type="table" .../>
    </connection>

    <extract enabled="true">          <!-- ← THE FRAGILE PART -->
      <metadata-record>
        <remote-name>Row ID</remote-name><remote-type>20</remote-type>
        <local-type>integer</local-type>
      </metadata-record>
      ... one record per column ...
      <connection class="hyper" dbname="path\to\file.hyper" .../>
      <relation .../>
    </extract>
  </datasource>
</datasources>
```

- `<extract enabled="true">` makes Tableau Public read from a `.hyper` file instead of the Excel.
- Tableau Public **requires** an extract ("Workbooks saved to Tableau Public must use extracts").
- See [04-data-extract-fix.md](04-data-extract-fix.md) for what happens when that `.hyper` path is wrong.

## Column type reference (from `<extract>` metadata)

| Tableau `remote-type` | `local-type` |
|---|---|
| 20 | integer (BIGINT) |
| 129 | string |
| 133 | date |
| 5 | real (double) |

## Common editing pitfalls

| Pitfall | Fix |
|---|---|
| Raw `&` or `<`/`>` inside names/labels | XML-escape (`&amp;`) — or avoid: use the word "and" instead of `&` |
| Adding `<column>` directly under a datasource | **Don't** — Tableau failed to load; put computed fields inside the worksheet `<table>` or use the datasource's existing schema |
| Forgetting `<windows>` entry | Sheet shows missing — always mirror worksheet↔window |
| Duplicate `uuid` GUIDs | Generate a fresh GUID for every new element |
| Namespace `user:` attrs | Keep `xmlns:user="http://www.tableausoftware.com/xml/user"` on the root |
