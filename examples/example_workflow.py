"""
example_workflow.py — a complete, runnable walkthrough of the tableau-workbook skill.

Run it against your own workbook:

    python example_workflow.py "C:\\path\\to\\workbook.twb"

It performs a read-only dry run by default. Pass --write to actually modify the
workbook (it still backs up first, and writes to a copy).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from tableau_workbook import Workbook, summarize  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Demonstrate the tableau-workbook workflow.")
    parser.add_argument("workbook", help="Path to a .twb file")
    parser.add_argument("--write", action="store_true",
                        help="Actually apply the changes (default: read-only dry run)")
    args = parser.parse_args()

    # ---- 1. Load and inspect -------------------------------------------
    wb = Workbook.load(args.workbook)
    print(summarize(wb))
    print()

    # ---- 2. Validate the workbook as-is --------------------------------
    problems = wb.validate()
    if problems:
        print("PROBLEMS in the incoming workbook:")
        for p in problems:
            print(f"  ! {p}")
        print()
    else:
        print("Incoming workbook passes all structural checks.")
        print()

    # ---- 3. Show what a clone would look like --------------------------
    source = wb.worksheet_names()[0]
    new_name = "Example Cloned Sheet"
    print(f"Would clone worksheet {source!r} -> {new_name!r}")
    print(f"  rows:    {wb.field(source.split()[0], 'None')}")
    print(f"  cols:    {wb.field('Sales', 'Sum')}")
    print(f"  mark:    Bar")
    print(f"  color:   {wb.field('Profit', 'Sum')}")
    print()

    if not args.write:
        print("Dry run only. Re-run with --write to apply the changes.")
        return 0

    # ---- 4. Back up, then edit -----------------------------------------
    backup = wb.backup("backups")
    print(f"Backed up to {backup}")

    ws = wb.clone_worksheet(source, new_name)
    wb.set_shelves(ws, rows=wb.field("Region", "None"), cols=wb.field("Sales", "Sum"))
    wb.set_mark_class(ws, "Bar")
    wb.set_encodings(ws, [("color", wb.field("Profit", "Sum"))])
    wb.show_mark_labels(ws)
    wb.set_palette(ws, wb.field("Profit", "Sum"), "red_green_gold_diverging_10_0")

    wb.add_dashboard("Example Dashboard", [
        {"name": new_name, "id": 3, "x": 1000, "y": 2000, "w": 98000, "h": 88000},
    ])

    # ---- 5. Validate before saving ------------------------------------
    problems = wb.validate()
    if problems:
        print("REFUSING TO SAVE — the edit would produce an invalid workbook:")
        for p in problems:
            print(f"  ! {p}")
        return 1

    out = wb.save()
    print(f"Saved {out}")
    print(summarize(wb))
    print()
    print("Now verify it opens:")
    print(f'  python scripts/verify_workbook.py "{out}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
