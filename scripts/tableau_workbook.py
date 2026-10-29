"""
tableau_workbook — a small, safe library for editing Tableau workbooks (.twb) in XML.

Every rule encoded here was learned by breaking a real workbook first:

  * deep-copy existing <worksheet>/<window> elements instead of writing them from
    scratch — a bare <window class="worksheet"/> crashes the DOM loader
  * never put <column> directly under <datasources> — Tableau refuses to load
  * every worksheet needs a mirrored <window>; every dashboard zone name must
    match a real worksheet
  * Tableau Public REQUIRES an extract — removing <extract> is not a fix
  * reference lines only attach to native measures, never [usr:...] fields
  * no <customized-label> / <customized-tooltip> inside <pane>; use <text> and
    <tooltip> encodings instead
  * <mark class="Map"/> is invalid — use Circle (symbol) or Polygon (filled)

Quick start:

    from tableau_workbook import Workbook

    wb = Workbook.load("AVD TEO.twb")
    wb.backup("backups/before_change.twb")
    ws = wb.clone_worksheet("Sales by Month", "New Sheet")
    wb.save()
"""

from __future__ import annotations

import copy
import os
import shutil
import uuid
import zipfile
from typing import Iterable, Iterator, Optional

from lxml import etree

USER_NS = "http://www.tableausoftware.com/xml/user"

#: Mark classes Tableau's DOM parser rejects.
INVALID_MARK_CLASSES = ("Map",)

#: Reference-line formula values Tableau's XML schema accepts.
VALID_REFERENCE_LINE_FORMULAS = ("average", "median", "min", "max", "sum", "count", "total")

#: The order Tableau expects the child elements of a <datasource> to appear in.
#:
#: Getting this order wrong crashes the workbook with error d2e8da72 and a
#: stack-unwind — the same symptom as every other pitfall, which is why it is
#: checked explicitly. Verified by controlled probes against Tableau Public
#: 2026.2; see references/10-datasource-column-order.md.
DATASOURCE_CHILD_ORDER = (
    "connection",
    "aliases",
    "column",
    "column-instance",
    "extract",
    "layout",
    "style",
    "semantic-values",
    "object-graph",
)


class WorkbookError(Exception):
    """Raised when a workbook edit would produce an invalid workbook."""


def new_guid() -> str:
    """Return a fresh Tableau-style GUID, e.g. ``{1B4F0E9C-...}``."""
    return "{" + str(uuid.uuid4()).upper() + "}"


def _parse_fragment(xml: str) -> etree._Element:
    """Parse an XML fragment string into an element, with the user namespace bound."""
    wrapper = f'<wrap xmlns:user="{USER_NS}">{xml}</wrap>'
    root = etree.fromstring(wrapper.encode("utf-8"))
    children = list(root)
    if not children:
        raise WorkbookError("XML fragment produced no elements")
    return children[0]


class Workbook:
    """An in-memory Tableau workbook backed by an lxml element tree.

    The tree is only written to disk on :meth:`save`, so a failed edit never
    leaves a half-written workbook behind.
    """

    def __init__(self, tree: etree._ElementTree, path: Optional[str] = None):
        self._tree = tree
        self._root = tree.getroot()
        self.path = path

    # ------------------------------------------------------------------
    # Loading and saving
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: str) -> "Workbook":
        """Parse a ``.twb`` file. Raises if the XML is malformed."""
        if not os.path.exists(path):
            raise WorkbookError(f"Workbook not found: {path}")
        parser = etree.XMLParser(remove_blank_text=False, huge_tree=True)
        tree = etree.parse(path, parser)
        if tree.getroot().tag != "workbook":
            raise WorkbookError(
                f"{path} is not a Tableau workbook (root element is <{tree.getroot().tag}>)"
            )
        return cls(tree, path)

    def backup(self, dest_dir: str = "backups", suffix: Optional[str] = None) -> str:
        """Copy the source file into ``dest_dir`` and return the backup path.

        Call this before any mutation. It is the only way back from a bad edit.
        """
        if not self.path:
            raise WorkbookError("No source path to back up (workbook was not loaded from disk)")
        os.makedirs(dest_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(self.path))[0]
        suffix = suffix or f"before_{uuid.uuid4().hex[:8]}"
        dest = os.path.join(dest_dir, f"{stem}_{suffix}{os.path.splitext(self.path)[1]}")
        shutil.copy2(self.path, dest)
        return dest

    def save(self, path: Optional[str] = None) -> str:
        """Write the workbook to disk, then re-parse it to prove the XML is valid.

        Returns the path written.
        """
        target = path or self.path
        if not target:
            raise WorkbookError("No path to save to")
        parent = os.path.dirname(os.path.abspath(target))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._tree.write(target, encoding="utf-8", xml_declaration=True)
        # Re-parse as a post-condition: never hand back a file we did not verify.
        etree.parse(target, etree.XMLParser(huge_tree=True))
        self.path = target
        return target

    # ------------------------------------------------------------------
    # Read-only accessors
    # ------------------------------------------------------------------
    @property
    def root(self) -> etree._Element:
        return self._root

    @property
    def datasource_name(self) -> str:
        """The internal identifier of the first datasource, e.g. ``federated.abc123``."""
        ds = self._root.find(".//datasources/datasource")
        if ds is None:
            raise WorkbookError("Workbook has no datasource")
        return ds.get("name")

    @property
    def datasource_caption(self) -> str:
        ds = self._root.find(".//datasources/datasource")
        return ds.get("caption") if ds is not None else ""

    def field(self, column: str, derivation: str = "Sum") -> str:
        """Build a fully-qualified field reference for a column name.

        ``wb.field("Sales", "Sum")`` -> ``[federated.xxx].[sum:Sales:qk]``
        ``wb.field("Region", "None")`` -> ``[federated.xxx].[none:Region:nk]``

        ``derivation`` values map to Tableau's suffixes:
        ``None`` -> ``nk`` (nominal), ``Sum``/``Avg``/``Count`` -> ``qk`` (quantitative),
        ``Month``/``Year`` -> ``ok`` (ordinal), ``ATTR`` -> ``qk``.
        """
        suffix = {"None": "nk", "Month": "ok", "Year": "ok", "Day": "ok", "Weekday": "ok"}
        tag = suffix.get(derivation, "qk")
        return f"[{self.datasource_name}].[{derivation.lower()}:{column}:{tag}]"

    def worksheet_names(self) -> list[str]:
        return [w.get("name") for w in self._root.findall("worksheets/worksheet")]

    def dashboard_names(self) -> list[str]:
        return [d.get("name") for d in self._root.findall("dashboards/dashboard")]

    def window_names(self) -> list[str]:
        return [w.get("name") for w in self._root.findall("windows/window")]

    def worksheet(self, name: str) -> etree._Element:
        ws = self._root.find(f"worksheets/worksheet[@name='{name}']")
        if ws is None:
            raise WorkbookError(f"No worksheet named {name!r}")
        return ws

    def window(self, name: str) -> etree._Element:
        win = self._root.find(f"windows/window[@name='{name}']")
        if win is None:
            raise WorkbookError(f"No window named {name!r}")
        return win

    def dashboard(self, name: str) -> etree._Element:
        dash = self._root.find(f"dashboards/dashboard[@name='{name}']")
        if dash is None:
            raise WorkbookError(f"No dashboard named {name!r}")
        return dash

    def counts(self) -> dict[str, int]:
        return {
            "worksheets": len(self._root.findall("worksheets/worksheet")),
            "dashboards": len(self._root.findall("dashboards/dashboard")),
            "windows": len(self._root.findall("windows/window")),
        }

    # ------------------------------------------------------------------
    # Worksheets
    # ------------------------------------------------------------------
    def clone_worksheet(self, source_name: str, new_name: str) -> etree._Element:
        """Clone an existing worksheet (and its window) under a new name.

        Cloning is far safer than authoring ``<table>`` from scratch: the copy
        already carries valid encodings, styles and datasource references.
        """
        if new_name in self.worksheet_names():
            raise WorkbookError(f"A worksheet named {new_name!r} already exists")
        if not new_name.isascii() or "&" in new_name or "<" in new_name:
            raise WorkbookError(
                f"Worksheet name {new_name!r} contains characters that break Tableau XML "
                "(use 'and' instead of '&')"
            )

        ws = copy.deepcopy(self.worksheet(source_name))
        ws.set("name", new_name)
        sid = ws.find("simple-id")
        if sid is None:
            ws.append(_parse_fragment(f'<simple-id uuid="{new_guid()}"/>'))
        else:
            sid.set("uuid", new_guid())
        self._root.find("worksheets").append(ws)

        # Mirror into <windows> by deep-copying the source window. A bare
        # <window class="worksheet"/> crashes the DOM loader (pitfall 05).
        src_win = self._root.find(f"windows/window[@name='{source_name}']")
        if src_win is not None:
            win = copy.deepcopy(src_win)
            win.set("name", new_name)
            wsid = win.find("simple-id")
            if wsid is None:
                win.append(_parse_fragment(f'<simple-id uuid="{new_guid()}"/>'))
            else:
                wsid.set("uuid", new_guid())
            self._root.find("windows").append(win)
        return ws

    def remove_worksheet(self, name: str) -> None:
        """Remove a worksheet from <worksheets>, <windows>, <thumbnails> and every zone."""
        for path in ("worksheets/worksheet", "windows/window", "thumbnails/thumbnail"):
            el = self._root.find(f"{path}[@name='{name}']")
            if el is not None:
                el.getparent().remove(el)
        for z in self._root.findall(f"dashboards/dashboard/zones/zone[@name='{name}']"):
            z.getparent().remove(z)

    def set_shelves(self, ws: etree._Element, rows: Optional[str] = None, cols: Optional[str] = None) -> None:
        """Set the rows/cols shelf contents of a worksheet to field references."""
        for tag, value in (("rows", rows), ("cols", cols)):
            if value is None:
                continue
            shelf = ws.find(f".//{tag}")
            if shelf is None:
                continue
            shelf.text = value

    def set_mark_class(self, ws: etree._Element, mark_class: str) -> None:
        """Set the mark class, rejecting classes Tableau's parser refuses."""
        if mark_class in INVALID_MARK_CLASSES:
            raise WorkbookError(
                f"mark class {mark_class!r} is invalid. Use 'Circle' for symbol maps, "
                "'Polygon' for filled maps, or 'Automatic'."
            )
        mark = ws.find(".//panes/pane/mark")
        if mark is None:
            raise WorkbookError("Worksheet has no <mark> element")
        mark.set("class", mark_class)

    def set_encodings(self, ws: etree._Element, encodings: Iterable[tuple[str, str]]) -> None:
        """Replace the pane encodings.

        ``encodings`` is an iterable of ``(shelf, field_reference)`` pairs, where
        shelf is one of ``color``, ``size``, ``lod``, ``text``, ``tooltip``,
        ``shape``, ``detail``.
        """
        enc = ws.find(".//panes/pane/encodings")
        if enc is None:
            raise WorkbookError("Worksheet has no <encodings> element")
        enc.clear()
        for shelf, ref in encodings:
            if shelf not in ("color", "size", "lod", "text", "tooltip", "shape", "detail"):
                raise WorkbookError(f"Unknown encoding shelf: {shelf!r}")
            enc.append(_parse_fragment(f'<{shelf} column="{ref}"/>'))

    def add_datasource_field(self, name: str, datatype: str = "string",
                             role: str = "dimension", field_type: str = "nominal",
                             caption: Optional[str] = None,
                             semantic_role: Optional[str] = None,
                             calculation: Optional[str] = None) -> str:
        """Add a field to the datasource's global column list.

        This makes the field available to every worksheet in the workbook. The
        element is inserted in the position Tableau expects — all ``<column>``
        elements together, then all ``<column-instance>`` elements. Inserting in
        the wrong place crashes the workbook with d2e8da72.

        Returns the field reference, e.g. ``[federated.xxx].[none:MyField:nk]``.
        """
        ds = self._root.find(".//datasources/datasource")
        if ds is None:
            raise WorkbookError("Workbook has no datasource")

        identifier = _identifier(name)
        attrs = [f'datatype="{datatype}"', f'name="[{identifier}]"',
                 f'role="{role}"', f'type="{field_type}"']
        if caption:
            attrs.insert(0, f'caption="{caption}"')
        if semantic_role:
            attrs.append(f'semantic-role="{semantic_role}"')

        if calculation:
            attrs.append(f'caption="{caption or name}"')
            column = _parse_fragment(
                f'<column {" ".join(attrs)}>'
                f'<calculation class="tableau" formula="{_escape_attr(calculation)}"/>'
                "</column>"
            )
        else:
            column = _parse_fragment(f'<column {" ".join(attrs)}/>')
        insert_datasource_child(ds, column)

        derivation = "None" if field_type == "nominal" else "Sum"
        tag = "nk" if field_type == "nominal" else "qk"
        instance = _parse_fragment(
            f'<column-instance column="[{identifier}]" derivation="{derivation}"'
            f' name="[{derivation.lower()}:{identifier}:{tag}]" pivot="key" type="{field_type}"/>'
        )
        insert_datasource_child(ds, instance)
        return f"[{self.datasource_name}].[{derivation.lower()}:{identifier}:{tag}]"

    def add_calculated_field(self, ws: etree._Element, name: str, formula: str,
                             datatype: str = "real", fmt: Optional[str] = None) -> str:
        """Define a calculated field inside the worksheet's datasource-dependencies.

        Returns the ``[usr:...]`` instance reference. Calculated fields defined
        here are safe to use on shelves and in encodings — but never attach a
        reference line to them (pitfall 07).
        """
        deps = ws.find(".//datasource-dependencies")
        if deps is None:
            raise WorkbookError("Worksheet has no <datasource-dependencies> element")
        fmt_attr = f' default-format="{fmt}"' if fmt else ""
        identifier = _identifier(name)
        deps.append(_parse_fragment(
            f'<column caption="{name}" datatype="{datatype}" name="[Calculation_{identifier}]"'
            f'{fmt_attr} role="measure" type="quantitative">'
            f'<calculation class="tableau" formula="{_escape_attr(formula)}"/>'
            f"</column>"
        ))
        deps.append(_parse_fragment(
            f'<column-instance column="[Calculation_{identifier}]" derivation="User"'
            f' name="[usr:Calculation_{identifier}:qk]" pivot="key" type="quantitative"/>'
        ))
        return f"[{self.datasource_name}].[usr:Calculation_{identifier}:qk]"

    def add_reference_line(self, ws: etree._Element, measure_ref: str, label: str,
                            formula: str = "average") -> None:
        """Attach an instant-analytics reference line to a native measure.

        ``measure_ref`` must be a native aggregated column such as
        ``[federated.xxx].[sum:Sales:qk]``. Passing a ``[usr:...]`` field
        crashes Tableau (pitfall 07).

        Reference line ids must be unique within a worksheet. If the sheet
        already has a reference line, the existing one is replaced rather than
        duplicated — two elements sharing an id make Tableau report
        "duplicate visual element IDs" and refuse to open the workbook.
        """
        if "[usr:" in measure_ref:
            raise WorkbookError(
                "Reference lines cannot attach to calculated [usr:...] fields "
                "(pitfall 07). Use a native measure like [sum:Sales:qk]."
            )
        if formula not in VALID_REFERENCE_LINE_FORMULAS:
            raise WorkbookError(
                f"Invalid reference-line formula {formula!r}. "
                f"Use one of: {', '.join(VALID_REFERENCE_LINE_FORMULAS)} (pitfall 06)."
            )
        pane = ws.find(".//panes/pane")

        # Reuse a free id, and never collide with one already in this sheet.
        used = {rl.get("id") for rl in ws.findall(".//reference-line")}
        for rl in ws.findall(".//reference-line"):
            pane.remove(rl)
        refline_id = "refline0"
        suffix = 0
        while refline_id in used:
            suffix += 1
            refline_id = f"refline{suffix}"

        refline = _parse_fragment(
            f'<reference-line axis-column="{measure_ref}" enable-instant-analytics="true"'
            f' formula="{formula}" id="{refline_id}" label="{label}" label-type="custom"'
            f' probability="95" scope="per-table" value-column="{measure_ref}" z-order="1"/>'
        )
        # Tableau's canonical pane order puts <reference-line> before <style>.
        style_el = pane.find("style")
        if style_el is not None:
            style_el.addprevious(refline)
        else:
            pane.append(refline)

        # The worksheet-level <style> carries the refline formatting. Replace
        # any existing refline rule so the ids stay in sync.
        style = ws.find(".//style")
        if style is not None:
            for rule in style.findall("style-rule[@element='refline']"):
                style.remove(rule)
            style.append(_parse_fragment(
                '<style-rule element="refline">'
                f'<format attr="fill-above" id="{refline_id}" value="#00000000"/>'
                f'<format attr="fill-below" id="{refline_id}" value="#00000000"/>'
                f'<format attr="line-visibility" id="{refline_id}" value="on"/>'
                f'<format attr="line-pattern-only" id="{refline_id}" value="dashed"/>'
                "</style-rule>"
            ))

    def show_mark_labels(self, ws: etree._Element, cull: bool = False) -> None:
        """Turn on mark labels for every mark in the worksheet."""
        pane = ws.find(".//panes/pane")
        style = pane.find("style")
        if style is None:
            style = etree.SubElement(pane, "style")
        style.append(_parse_fragment(
            '<style-rule element="mark">'
            '<format attr="mark-labels-show" value="true"/>'
            f'<format attr="mark-labels-cull" value="{"true" if cull else "false"}"/>'
            "</style-rule>"
        ))

    def set_palette(self, ws: etree._Element, field_ref: str, palette: str,
                    element: str = "mark", attr: str = "color") -> None:
        """Apply a colour palette to a field."""
        style = ws.find(".//style")
        if style is None:
            style = etree.SubElement(ws.find(".//table"), "style")
        style.append(_parse_fragment(
            f'<style-rule element="{element}">'
            f'<encoding attr="{attr}" field="{field_ref}" palette="{palette}"'
            f' symmetric="false" type="interpolated"/>'
            "</style-rule>"
        ))

    # ------------------------------------------------------------------
    # Dashboards
    # ------------------------------------------------------------------
    def add_dashboard(self, name: str, zones: Iterable[dict], size: Optional[dict] = None,
                      phone_layout: bool = True) -> etree._Element:
        """Add a dashboard with the given zones.

        Each zone is a dict with ``name`` (the worksheet it shows), optional
        ``id``, ``x``, ``y``, ``w``, ``h`` (in 1/1000 of a percent), and
        optional ``type`` (``color``/``size`` legend) and ``param``.
        """
        if name in self.dashboard_names():
            raise WorkbookError(f"A dashboard named {name!r} already exists")
        size = size or {"minwidth": 750, "maxwidth": 1000, "minheight": 600, "maxheight": 800}
        zone_xml = []
        used_ids: set[int] = set()
        for i, zone in enumerate(zones, start=3):
            zid = int(zone.get("id", i))
            if zid in used_ids:
                raise WorkbookError(f"Duplicate zone id {zid} in dashboard {name!r}")
            used_ids.add(zid)
            sheet = zone["name"]
            if sheet not in self.worksheet_names():
                raise WorkbookError(f"Zone refers to unknown worksheet: {sheet!r}")
            attrs = [
                f'id="{zid}"', f'name="{sheet}"',
                f'x="{int(zone.get("x", 1000))}"', f'y="{int(zone.get("y", 2000))}"',
                f'w="{int(zone.get("w", 98000))}"', f'h="{int(zone.get("h", 88000))}"',
            ]
            if zone.get("type"):
                attrs.append(f'type-v2="{zone["type"]}"')
                attrs.append(f'param="{zone.get("param", "")}"')
                attrs.append('pane-specification-id="0"')
            zone_xml.append(f'<zone {" ".join(attrs)}/>')

        phone = ""
        if phone_layout:
            # Only worksheet zones appear in the phone layout. Tableau's own
            # dashboards omit legend zones here, and including them makes the
            # dashboard report "duplicate visual element IDs".
            sheet_zones = [z for z in zones if not z.get("type")]
            inner = "".join(
                f'<zone fixed-size="600" h="{z.get("h", 88000)}" id="{z.get("id", i)}"'
                f' is-fixed="true" name="{z["name"]}" w="{z.get("w", 98000)}"'
                f' x="{z.get("x", 1000)}" y="{z.get("y", 2000)}">'
                '<zone-style>'
                '<format attr="border-color" value="#000000"/>'
                '<format attr="border-style" value="none"/>'
                '<format attr="border-width" value="0"/>'
                '<format attr="margin" value="4"/>'
                '<format attr="padding" value="0"/>'
                "</zone-style></zone>"
                for i, z in enumerate(sheet_zones, start=3)
            )
            phone = (
                '<devicelayouts><devicelayout auto-generated="true" name="Phone">'
                '<size maxheight="900" minheight="900" sizing-mode="vscroll"/>'
                '<zones><zone h="100000" id="10" type-v2="layout-basic" w="100000" x="0" y="0">'
                '<zone h="97616" id="9" param="vert" type-v2="layout-flow"'
                ' w="97538" x="1231" y="1192">' + inner + "</zone></zone></zones>"
                "</devicelayout></devicelayouts>"
            )

        dash_xml = (
            f'<dashboard xmlns:user="{USER_NS}" enable-sort-zone-taborder="true" name="{name}">'
            "<style/>"
            f'<size maxheight="{size["maxheight"]}" maxwidth="{size["maxwidth"]}"'
            f' minheight="{size["minheight"]}" minwidth="{size["minwidth"]}"/>'
            f'<zones>{"".join(zone_xml)}</zones>'
            f"{phone}"
            f'<simple-id uuid="{new_guid()}"/>'
            "</dashboard>"
        )
        dash = _parse_fragment(dash_xml)
        self._root.find("dashboards").append(dash)

        # Mirror into <windows>, cloning the most recent dashboard window so the
        # <viewpoints> structure is valid.
        src = self._root.findall("windows/window[@class='dashboard']")
        if src:
            win = copy.deepcopy(src[-1])
            win.set("name", name)
            wsid = win.find("simple-id")
            if wsid is None:
                win.append(_parse_fragment(f'<simple-id uuid="{new_guid()}"/>'))
            else:
                wsid.set("uuid", new_guid())
            vps = win.find("viewpoints")
            if vps is not None:
                vps.clear()
                # One viewpoint per WORKSHEET. Tableau's own dashboards have
                # exactly one per sheet, and two viewpoints sharing a name make
                # Tableau report "duplicate visual element IDs" and refuse to
                # open the workbook.
                seen_sheets = []
                for z in zones:
                    sheet = z["name"]
                    if sheet in seen_sheets:
                        continue
                    seen_sheets.append(sheet)
                    vps.append(_parse_fragment(
                        f'<viewpoint name="{sheet}"><zoom type="entire-view"/></viewpoint>'
                    ))
            self._root.find("windows").append(win)
        return dash

    # ------------------------------------------------------------------
    # Extracts and packaging
    # ------------------------------------------------------------------
    def extract_connection(self) -> Optional[etree._Element]:
        """The ``<connection>`` element inside the datasource's ``<extract>``."""
        return self._root.find(".//datasources/datasource/extract/connection")

    def extract_metadata(self) -> list[dict[str, str]]:
        """The extract's column schema as a list of dicts."""
        extract = self._root.find(".//datasources/datasource/extract")
        if extract is None:
            return []
        records = []
        for mr in extract.findall(".//metadata-record"):
            records.append({
                "remote-name": mr.findtext("remote-name", ""),
                "remote-type": mr.findtext("remote-type", ""),
                "local-type": mr.findtext("local-type", ""),
            })
        return records

    def point_extract_at(self, hyper_path: str) -> None:
        """Point the extract connection at a ``.hyper`` file on disk."""
        conn = self.extract_connection()
        if conn is None:
            raise WorkbookError(
                "Workbook has no <extract>. Tableau Public requires an extract — "
                "add one rather than removing it (pitfall 04)."
            )
        conn.set("dbname", os.path.abspath(hyper_path))

    def package_twbx(self, out_path: str, hyper_path: Optional[str] = None,
                     extract_arcname: str = "Data/Extracts/extract.hyper") -> str:
        """Package the workbook and its extract into a self-contained ``.twbx``.

        The ``.twb`` written inside the archive uses a *relative* extract path, so
        the packaged workbook never depends on a file at an absolute location.
        """
        tree = copy.deepcopy(self._tree)
        conn = tree.find(".//datasources/datasource/extract/connection")
        if conn is not None:
            conn.set("dbname", extract_arcname)
        twb_xml = etree.tostring(tree, encoding="utf-8", xml_declaration=True)

        base = os.path.basename(self.path or "workbook.twb")
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(base, twb_xml)
            if hyper_path and os.path.exists(hyper_path):
                z.write(hyper_path, extract_arcname)
        return out_path

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self) -> list[str]:
        """Check the workbook's internal consistency. Returns a list of problems.

        An empty list means the workbook passed every structural check.
        """
        problems: list[str] = []
        ws_names = set(self.worksheet_names())
        dash_names = set(self.dashboard_names())
        win_names = set(self.window_names())

        for name in ws_names - win_names:
            problems.append(f"Worksheet {name!r} has no matching <window> — the view will not open")
        for name in dash_names - win_names:
            problems.append(f"Dashboard {name!r} has no matching <window> — the view will not open")

        seen_windows = set()
        for win in self._root.findall("windows/window"):
            n = win.get("name")
            if n in seen_windows:
                problems.append(f"Duplicate <window> named {n!r}")
            seen_windows.add(n)
            # Two viewpoints with the same name make Tableau report "duplicate
            # visual element IDs" and refuse to open the workbook.
            vps = win.find("viewpoints")
            if vps is not None:
                vp_names = [vp.get("name") for vp in vps.findall("viewpoint")]
                for vp_name in set(vp_names):
                    if vp_names.count(vp_name) > 1:
                        problems.append(
                            f"Window {n!r} has {vp_names.count(vp_name)} <viewpoint> elements "
                            f"named {vp_name!r} — Tableau reports 'duplicate visual element "
                            "IDs' and refuses to open the workbook. Use one viewpoint per "
                            "worksheet."
                        )

        seen_uuids: dict[str, str] = {}
        for el in self._root.iter():
            sid = el.find("simple-id") if el.tag in ("worksheet", "dashboard", "window") else None
            if sid is None:
                continue
            u = sid.get("uuid")
            if u in seen_uuids:
                problems.append(f"Duplicate uuid {u} on {el.tag} {el.get('name')!r}")
            seen_uuids[u] = el.tag

        for dash in self._root.findall("dashboards/dashboard"):
            zone_ids = set()
            for z in dash.findall("zones/zone"):
                zid = z.get("id")
                if zid in zone_ids:
                    problems.append(f"Dashboard {dash.get('name')!r} has duplicate zone id {zid}")
                zone_ids.add(zid)
                zname = z.get("name")
                if zname and z.get("type-v2") not in ("color", "size") and zname not in ws_names:
                    problems.append(
                        f"Dashboard {dash.get('name')!r} zone {zid} points at unknown sheet {zname!r}"
                    )

        for ws in self._root.findall("worksheets/worksheet"):
            for mark in ws.findall(".//panes/pane/mark"):
                cls = mark.get("class")
                if cls in INVALID_MARK_CLASSES:
                    problems.append(
                        f"Worksheet {ws.get('name')!r} uses invalid mark class {cls!r} (pitfall 09)"
                    )
            for rl in ws.findall(".//reference-line"):
                for attr in ("axis-column", "value-column"):
                    val = rl.get(attr) or ""
                    if "[usr:" in val:
                        problems.append(
                            f"Worksheet {ws.get('name')!r} has a reference line on calculated field "
                            f"{val!r} — this crashes Tableau (pitfall 07)"
                        )
                if rl.get("formula") not in VALID_REFERENCE_LINE_FORMULAS:
                    problems.append(
                        f"Worksheet {ws.get('name')!r} reference line uses formula "
                        f"{rl.get('formula')!r} (pitfall 06)"
                    )
            # Duplicate visual element ids make Tableau refuse to open the file.
            refline_ids = [rl.get("id") for rl in ws.findall(".//reference-line")]
            for rid in set(refline_ids):
                if refline_ids.count(rid) > 1:
                    problems.append(
                        f"Worksheet {ws.get('name')!r} has {refline_ids.count(rid)} reference "
                        f"lines sharing id {rid!r} — Tableau reports 'duplicate visual element "
                        "IDs' and refuses to open the workbook."
                    )

        for ds in self._root.findall("datasources/datasource"):
            problems.extend(_check_datasource_order(ds))

        for pane in self._root.findall(".//panes/pane"):
            for bad in ("customized-label", "customized-tooltip"):
                if pane.find(bad) is not None:
                    problems.append(
                        f"<{bad}> inside <pane> crashes the DOM loader — use <text> and "
                        "<tooltip> encodings instead (pitfalls 08 and 09)"
                    )

        conn = self.extract_connection()
        if conn is None:
            problems.append(
                "Workbook has no extract. Tableau Public cannot open live connections "
                "(pitfall 04)."
            )
        else:
            dbname = conn.get("dbname") or ""
            if "AppData" in dbname or "Temp" in dbname:
                problems.append(
                    f"Extract path {dbname!r} points into a temp folder that Windows will "
                    "delete. Ship a .twbx with a relative path instead (pitfall 04)."
                )

        return problems


def _escape_attr(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _identifier(name: str) -> str:
    """Turn a human-readable field name into a safe XML identifier.

    Tableau field identifiers cannot contain spaces, so ``"Profit Ratio"``
    becomes ``"Profit_Ratio"``.
    """
    safe = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in name)
    if safe and safe[0].isdigit():
        safe = "_" + safe
    return safe


def _check_datasource_order(ds: etree._Element) -> list[str]:
    """Check that a <datasource>'s children follow Tableau's expected order.

    A <column> placed after <extract>, or a <column-instance> placed before all
    the <column> elements are finished, crashes the workbook with d2e8da72.
    """
    problems: list[str] = []
    name = ds.get("caption") or ds.get("name") or "datasource"

    ranks = []
    for child in ds:
        if child.tag not in DATASOURCE_CHILD_ORDER:
            continue
        ranks.append((DATASOURCE_CHILD_ORDER.index(child.tag), child.tag, child))

    # The sequence of ranks must be non-decreasing.
    for i in range(1, len(ranks)):
        prev_rank, prev_tag, _ = ranks[i - 1]
        rank, tag, _ = ranks[i]
        if rank < prev_rank:
            problems.append(
                f"Datasource {name!r} has <{tag}> after <{prev_tag}> — Tableau expects "
                f"{' < '.join(DATASOURCE_CHILD_ORDER)}. Wrong element order crashes the "
                "workbook with d2e8da72 (see references/10-datasource-column-order.md)."
            )
            break

    # Every <column-instance> must reference a <column> that exists.
    declared = {c.get("name") for c in ds if c.tag == "column"}
    for inst in ds:
        if inst.tag != "column-instance":
            continue
        ref = inst.get("column")
        if ref and ref not in declared:
            problems.append(
                f"Datasource {name!r} has a <column-instance> for {ref!r}, which is not "
                "declared as a <column> — Tableau fails to load the workbook."
            )
    return problems


def insert_datasource_child(ds: etree._Element, element: etree._Element) -> None:
    """Insert an element into a <datasource> at the position Tableau expects.

    Getting this wrong crashes the workbook with d2e8da72 and a stack-unwind.
    All <column> elements go together, then all <column-instance> elements.
    """
    tag = element.tag
    if tag not in DATASOURCE_CHILD_ORDER:
        raise WorkbookError(f"Unknown <datasource> child: {tag!r}")
    rank = DATASOURCE_CHILD_ORDER.index(tag)

    insert_at = len(ds)
    for i, child in enumerate(ds):
        child_rank = DATASOURCE_CHILD_ORDER.index(child.tag) if child.tag in DATASOURCE_CHILD_ORDER else None
        if child_rank is not None and child_rank > rank:
            insert_at = i
            break
    ds.insert(insert_at, element)


def summarize(wb: Workbook) -> str:
    """A short human-readable summary of a workbook's contents."""
    counts = wb.counts()
    lines = [
        f"Workbook: {os.path.basename(wb.path or '(in memory)')}",
        f"Datasource: {wb.datasource_caption}  ({wb.datasource_name})",
        f"Worksheets: {counts['worksheets']}   Dashboards: {counts['dashboards']}   "
        f"Windows: {counts['windows']}",
        "",
        "Worksheets:",
    ]
    for w in wb.worksheet_names():
        lines.append(f"  - {w}")
    lines.append("Dashboards:")
    for d in wb.dashboard_names():
        lines.append(f"  - {d}")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    import sys

    if len(sys.argv) < 2:
        print("usage: python tableau_workbook.py <workbook.twb>")
        raise SystemExit(2)
    wb = Workbook.load(sys.argv[1])
    print(summarize(wb))
    problems = wb.validate()
    print()
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print(f"  ! {p}")
    else:
        print("Validation passed: no structural problems found.")
