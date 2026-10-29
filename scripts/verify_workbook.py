"""
verify_workbook — prove a Tableau workbook actually opens.

Opening a file by hand works, but Tableau's log tells you whether it *truly*
loaded. This harness launches Tableau, captures only that process's log lines,
and reports PASS or FAIL.

Usage:
    python verify_workbook.py "C:\\path\\to\\workbook.twb"
    python verify_workbook.py workbook.twb --exe "C:\\...\\tabpublic.exe" --wait 25

PASS criteria:
  * zero "show-detailed-error-dialog" lines for this pid
  * zero "stack-unwind" / XML parse errors
  * at least one "setup-sheet-tabs" line (the UI finished building)

The harness is optional. Without Tableau installed it exits with a clear
message rather than a confusing traceback.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

DEFAULT_EXE_NAMES = ("tabpublic.exe", "tableau.exe", "tableau64.exe")

#: Error codes that mean "the extract is missing or unreadable" (pitfall 04).
EXTRACT_ERRORS = ("0x575215AA", "575215AA", "hyper-protocol-connection-failure")

#: Error code for "Tableau Public cannot open live connections" (pitfall 04).
NO_EXTRACT_ERROR = "3c242d89"

#: DOM loader crash signature shared by pitfalls 05-09.
DOM_LOADER_ERROR = "d2e8da72"


def find_tableau_exe(explicit: str = "") -> str:
    """Locate the Tableau executable, preferring an explicit path."""
    if explicit:
        if os.path.exists(explicit):
            return explicit
        raise FileNotFoundError(f"Tableau executable not found: {explicit}")

    env = os.environ.get("TABLEAU_EXE") or os.environ.get("TABLEAU_PUBLIC_EXE")
    if env and os.path.exists(env):
        return env

    program_files = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ]
    for base in program_files:
        tableau_dir = os.path.join(base, "Tableau")
        if not os.path.isdir(tableau_dir):
            continue
        for version in sorted(os.listdir(tableau_dir), reverse=True):
            for exe_name in DEFAULT_EXE_NAMES:
                candidate = os.path.join(tableau_dir, version, "bin", exe_name)
                if os.path.exists(candidate):
                    return candidate

    for exe_name in DEFAULT_EXE_NAMES:
        found = _which(exe_name)
        if found:
            return found
    raise FileNotFoundError(
        "Could not find Tableau. Install Tableau Public/Desktop, or pass --exe with the "
        "full path to tabpublic.exe."
    )


def find_log(explicit: str = "") -> str:
    """Locate Tableau's log.txt."""
    if explicit:
        if os.path.exists(explicit):
            return explicit
        raise FileNotFoundError(f"Tableau log not found: {explicit}")

    env = os.environ.get("TABLEAU_LOG")
    if env and os.path.exists(env):
        return env

    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, "Documents", "My Tableau Repository", "Logs", "log.txt"),
        os.path.join(home, "OneDrive", "Documents", "My Tableau Repository", "Logs", "log.txt"),
        os.path.join(home, "My Tableau Repository", "Logs", "log.txt"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(
        "Could not find Tableau's log.txt. Pass --log with its full path."
    )


def _which(name: str) -> str:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            return candidate
    return ""


def _running_tableau_pids() -> set[int]:
    """PIDs of already-running Tableau processes, so we don't reuse a stale one."""
    pids: set[int] = set()
    try:
        output = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq tabpublic.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=20,
        ).stdout
        for match in re.finditer(r'"([^"]+)","(\d+)"', output):
            pids.add(int(match.group(2)))
    except Exception:
        pass
    try:
        output = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq tableau.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=20,
        ).stdout
        for match in re.finditer(r'"([^"]+)","(\d+)"', output):
            pids.add(int(match.group(2)))
    except Exception:
        pass
    return pids


def verify(file_path: str, exe: str = "", log: str = "", wait: int = 25,
           verbose: bool = False) -> tuple[bool, dict]:
    """Launch Tableau with the file, then inspect the log for this run only.

    Returns ``(passed, details)``.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Target file does not exist: {file_path}")

    exe_path = find_tableau_exe(exe)
    log_path = find_log(log)

    print(f"Launching Tableau for '{os.path.basename(file_path)}'...")
    before = _running_tableau_pids()

    proc = subprocess.Popen([exe_path, file_path])
    time.sleep(wait)

    # Always kill the exact pid we started. A leftover Tableau keeps the log
    # locked and breaks the pid filter.
    if proc.poll() is None:
        proc.kill()
    pid = proc.pid
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass

    time.sleep(1.5)  # log writes are buffered

    with open(log_path, encoding="utf-8", errors="replace") as f:
        lines = [line for line in f if f'"pid":{pid}' in line]

    errors = [l for l in lines if "show-detailed-error-dialog" in l]
    xml_bad = [l for l in lines if "stack-unwind" in l or "parse-error" in l.lower()]
    ok_tabs = any("setup-sheet-tabs" in l for l in lines)

    details = {
        "pid": pid,
        "exe": exe_path,
        "log": log_path,
        "total_lines": len(lines),
        "error_dialogs": len(errors),
        "xml_errors": len(xml_bad),
        "sheet_tabs_ok": ok_tabs,
        "diagnoses": [],
    }

    for line in errors:
        message = _extract_message(line)
        details["diagnoses"].append(_diagnose(message))
        if verbose:
            print(f"   Dialog Error: {message[:400]}")

    passed = len(errors) == 0 and len(xml_bad) == 0 and ok_tabs
    return passed, details


def _extract_message(line: str) -> str:
    """Pull the human-readable message out of a log line."""
    try:
        payload = json.loads(line)
        return payload.get("v", {}).get("args", line)
    except Exception:
        return line


def _diagnose(message: str) -> str:
    """Map a Tableau error message to the pitfall that causes it."""
    if DOM_LOADER_ERROR in message:
        return ("DOM loader crash (d2e8da72). The XML is structurally invalid — see the "
                "pitfall docs: bare <window>, <customized-label>, <customized-tooltip>, "
                "<mark class=\"Map\"/>, or a reference line on a [usr:...] field.")
    if any(code in message for code in EXTRACT_ERRORS):
        return ("Missing or unreadable .hyper extract (575215AA). Rebuild the extract and "
                "repoint the workbook at it, or ship a .twbx with a relative path.")
    if NO_EXTRACT_ERROR in message:
        return ("Tableau Public requires an extract (3c242d89). Add an <extract> element "
                "instead of removing the existing one.")
    if "must use extracts" in message.lower():
        return "Tableau Public requires an extract. Add an <extract> element."
    return message.split("error-short-message=")[-1][:300]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a Tableau workbook opens cleanly.")
    parser.add_argument("workbook", help="Path to the .twb or .twbx file")
    parser.add_argument("--exe", default="", help="Full path to tabpublic.exe (auto-detected if omitted)")
    parser.add_argument("--log", default="", help="Full path to Tableau's log.txt (auto-detected if omitted)")
    parser.add_argument("--wait", type=int, default=25, help="Seconds to wait before killing Tableau")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print full error dialog text")
    args = parser.parse_args()

    try:
        passed, details = verify(args.workbook, args.exe, args.log, args.wait, args.verbose)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        print("\nThe verification harness needs a local Tableau install. "
              "It is optional — you can still edit workbooks without it.")
        return 2

    print(f"Verification Results for pid={details['pid']}:")
    print(f" - Total log lines: {details['total_lines']}")
    print(f" - Error dialogs:   {details['error_dialogs']}")
    print(f" - XML / DOM bad:   {details['xml_errors']}")
    print(f" - Sheet tabs OK:   {details['sheet_tabs_ok']}")
    for diagnosis in details["diagnoses"]:
        print(f"   Diagnosis: {diagnosis}")
    print(f"==> VERDICT: {'PASSED' if passed else 'FAILED'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
