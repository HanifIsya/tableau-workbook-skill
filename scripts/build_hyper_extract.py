"""
build_hyper_extract — create a permanent .hyper extract for a Tableau workbook.

Tableau Public REQUIRES an extract. If a workbook's <extract> points at a file
under AppData/Local/Temp, Windows will eventually delete it and the workbook
will fail with error 575215AA ("Unable to create extract").

This script reads the extract schema straight out of the .twb and builds a
matching .hyper, so the column types always agree with the workbook.

Usage:
    python build_hyper_extract.py workbook.twb "Data.xlsx" "Sheet1$" -o extract.hyper
    python build_hyper_extract.py workbook.twb data.csv -o extract.hyper

Requires: pip install tableauhyperapi pandas xlrd openpyxl
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tableau_workbook import Workbook  # noqa: E402

#: Tableau's <local-type> values mapped to Hyper SQL types.
LOCAL_TYPE_TO_SQL = {
    "integer": "big_int",
    "real": "double",
    "string": "text",
    "date": "date",
    "datetime": "timestamp",
    "boolean": "bool",
}


def read_source(path: str, sheet: str = ""):
    """Load a spreadsheet or CSV into a pandas DataFrame.

    Tableau refers to Excel sheets as ``Orders$`` while pandas uses ``Orders``,
    so a trailing ``$`` is tolerated.
    """
    import pandas as pd

    lower = path.lower()
    if lower.endswith(".csv"):
        return pd.read_csv(path)
    if lower.endswith((".xls", ".xlsx")):
        if sheet:
            return pd.read_excel(path, sheet_name=_resolve_sheet(path, sheet))
        return pd.read_excel(path)
    if lower.endswith(".json"):
        return pd.read_json(path)
    raise ValueError(f"Unsupported source format: {path}")


def _resolve_sheet(path: str, sheet: str) -> str:
    """Map a Tableau-style sheet name (``Orders$``) onto the real one."""
    import pandas as pd

    try:
        available = pd.ExcelFile(path).sheet_names
    except Exception:
        return sheet
    if sheet in available:
        return sheet
    stripped = sheet.rstrip("$")
    if stripped in available:
        print(f"NOTE: sheet {sheet!r} not found; using {stripped!r} instead.")
        return stripped
    raise SystemExit(
        f"Sheet {sheet!r} not found in {os.path.basename(path)}. "
        f"Available sheets: {available}"
    )


def build(workbook_path: str, source_path: str, sheet: str, out_path: str,
          table_schema: str = "Extract", table_name: str = "Extract") -> str:
    """Build a .hyper from ``source_path`` matching the workbook's extract schema."""
    from tableauhyperapi import (Connection, CreateMode, HyperProcess, Inserter,
                                 SqlType, TableDefinition, TableName, Telemetry)

    wb = Workbook.load(workbook_path)
    metadata = wb.extract_metadata()
    if not metadata:
        raise SystemExit(
            f"{workbook_path} has no <extract> metadata records, so there is no schema to "
            "match. Open the workbook in Tableau, create an extract, and save it first."
        )

    df = read_source(source_path, sheet)
    if len(df.columns) != len(metadata):
        print(
            f"WARNING: source has {len(df.columns)} columns but the workbook's extract "
            f"declares {len(metadata)}."
        )

    columns = []
    for record in metadata:
        name = record["remote-name"]
        local_type = record["local-type"]
        sql_type = LOCAL_TYPE_TO_SQL.get(local_type)
        if sql_type is None:
            print(f"WARNING: unknown local-type {local_type!r} for column {name!r}; using text")
            sql_type = "text"
        if name not in df.columns:
            raise SystemExit(
                f"Source is missing column {name!r}. Workbook extract columns: "
                f"{[m['remote-name'] for m in metadata]}"
            )
        columns.append(TableDefinition.Column(name, getattr(SqlType, sql_type)()))

    table_def = TableDefinition(
        table_name=TableName(table_schema, table_name),
        columns=columns,
    )

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
        with Connection(hp.endpoint, out_path, create_mode=CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema(table_schema)
            conn.catalog.create_table(table_def)
            with Inserter(conn, table_def) as inserter:
                for row in df.itertuples(index=False):
                    inserter.add_row(_coerce(list(row)))
                inserter.execute()

    print(f"Wrote {out_path} ({len(df)} rows, {len(columns)} columns).")
    return out_path


def _coerce(values: list) -> list:
    """Cast pandas values into types the Hyper inserter accepts."""
    import pandas as pd

    out = []
    for value in values:
        if pd.isna(value):
            out.append(None)
        elif hasattr(value, "date") and hasattr(value, "hour"):
            out.append(value.to_pydatetime())
        elif hasattr(value, "date"):
            out.append(value.date())
        elif hasattr(value, "item"):
            out.append(value.item())
        else:
            out.append(value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a .hyper extract that matches a Tableau workbook's schema.")
    parser.add_argument("workbook", help="Path to the .twb file (source of the schema)")
    parser.add_argument("source", help="Path to the source data (.xls, .xlsx, .csv, .json)")
    parser.add_argument("sheet", nargs="?", default="", help="Sheet name for Excel sources")
    parser.add_argument("-o", "--out", required=True, help="Output .hyper path")
    args = parser.parse_args()

    try:
        build(args.workbook, args.source, args.sheet, args.out)
    except ImportError as exc:
        print(f"ERROR: missing dependency — {exc}")
        print("Install with: pip install tableauhyperapi pandas xlrd openpyxl")
        return 2
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
