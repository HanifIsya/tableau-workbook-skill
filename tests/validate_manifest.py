"""Validate the plugin manifest and marketplace against Claude Code's documented rules."""
import json
import os
import re
import sys

ROOT = r"E:\download\tableau-workbook-skill"
errors = []
warnings = []

# ---- plugin.json ----
pj = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8"))

if "name" not in pj:
    errors.append("plugin.json: 'name' is required")
name = pj.get("name", "")
if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", name):
    errors.append(f"plugin.json: name {name!r} is not a valid plugin name")
if name.startswith(("claude-", "anthropic-", "cc-plugin-")):
    errors.append(f"plugin.json: name {name!r} is reserved")
if re.search(r"\b(claude|anthropic|anthropics)\b", name, re.I):
    warnings.append(f"plugin.json: name {name!r} reads as one of Anthropic's own")

for field in ("version", "description", "author"):
    if field not in pj:
        errors.append(f"plugin.json: missing recommended field {field!r}")
if "author" in pj and "name" not in pj["author"]:
    errors.append("plugin.json: author.name is required")
if "license" in pj and pj["license"] not in ("MIT", "Apache-2.0", "BSD-3-Clause", "ISC", "GPL-3.0", "MPL-2.0", "Unlicense"):
    warnings.append(f"plugin.json: unusual license {pj['license']!r}")
if "homepage" in pj and not pj["homepage"].startswith("http"):
    errors.append("plugin.json: homepage must be a URL")

# userConfig schema
for key, spec in (pj.get("userConfig") or {}).items():
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key):
        errors.append(f"plugin.json: userConfig key {key!r} is invalid")
    if spec.get("type") not in ("string", "number", "boolean", "directory", "file"):
        errors.append(f"plugin.json: userConfig {key!r} has invalid type {spec.get('type')!r}")
    for req in ("type", "title", "description"):
        if req not in spec:
            errors.append(f"plugin.json: userConfig {key!r} missing {req!r}")

# ---- marketplace.json ----
mj = json.load(open(os.path.join(ROOT, ".claude-plugin", "marketplace.json"), encoding="utf-8"))

for field in ("name", "owner", "plugins"):
    if field not in mj:
        errors.append(f"marketplace.json: missing required field {field!r}")
if "name" in mj and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", mj["name"]):
    errors.append(f"marketplace.json: name {mj['name']!r} is invalid")
if "name" in mj and mj["name"] in ("npm", "pip", "uv", "cargo", "github", "gh", "inline", "builtin", "skills-dir", "synced"):
    errors.append(f"marketplace.json: name {mj['name']!r} is reserved")
if "owner" in mj and "name" not in mj["owner"]:
    errors.append("marketplace.json: owner.name is required")

for i, entry in enumerate(mj.get("plugins", [])):
    if "name" not in entry or "source" not in entry:
        errors.append(f"marketplace.json: plugins[{i}] needs 'name' and 'source'")
        continue
    src = entry["source"]
    if isinstance(src, str):
        if not src.startswith("./") and src != ".":
            errors.append(f"marketplace.json: plugins[{i}].source must start with './'")
        target = os.path.join(ROOT, src.lstrip("./").replace("/", os.sep))
        if not os.path.exists(target):
            errors.append(f"marketplace.json: plugins[{i}].source path not found: {src}")
        elif ".." in src:
            errors.append(f"marketplace.json: plugins[{i}].source contains '..'")
    elif isinstance(src, dict):
        if "source" not in src:
            errors.append(f"marketplace.json: plugins[{i}].source object needs a 'source' key")

# ---- component paths exist ----
for key in ("skills", "commands", "agents", "hooks"):
    if key in pj:
        val = pj[key]
        paths = [val] if isinstance(val, str) else (val if isinstance(val, list) else [])
        for p in paths:
            if not p.startswith("./"):
                errors.append(f"plugin.json: {key} path must start with './': {p}")
            if ".." in p:
                errors.append(f"plugin.json: {key} path contains '..': {p}")
            if not os.path.exists(os.path.join(ROOT, p.lstrip("./").replace("/", os.sep))):
                errors.append(f"plugin.json: {key} path not found: {p}")

# ---- SKILL.md frontmatter ----
skill_path = os.path.join(ROOT, "skills", "tableau-workbook", "SKILL.md")
raw = open(skill_path, encoding="utf-8").read()
if not raw.startswith("---\n"):
    errors.append("SKILL.md: must begin with '---' on the first line")
else:
    end = raw.find("\n---\n", 3)
    if end == -1:
        errors.append("SKILL.md: frontmatter is not closed")
    else:
        fm = raw[4:end]
        if not re.search(r"^description:", fm, re.M):
            errors.append("SKILL.md: frontmatter needs a 'description'")
        if not re.search(r"^name:", fm, re.M):
            warnings.append("SKILL.md: frontmatter has no 'name' (directory name is used)")
        desc = re.search(r"^description:\s*>-\s*\n((?:\s{2,}.*\n?)+)", fm, re.M)
        if desc:
            body = " ".join(l.strip() for l in desc.group(1).splitlines())
            if len(body) > 1536:
                errors.append(f"SKILL.md: description is {len(body)} chars (limit 1536)")
            else:
                print(f"  description length: {len(body)} chars")
        else:
            body = re.search(r"^description:\s*(.+)$", fm, re.M)
            if body:
                print(f"  description length: {len(body.group(1))} chars")

# ---- references referenced by SKILL.md exist ----
for m in re.finditer(r"references/([0-9A-Za-z._-]+\.md)", raw):
    p = os.path.join(ROOT, "skills", "tableau-workbook", "references", m.group(1))
    if not os.path.exists(p):
        errors.append(f"SKILL.md references missing file: {m.group(1)}")

print()
if warnings:
    print("WARNINGS:")
    for w in warnings:
        print("  ~", w)
    print()
if errors:
    print("ERRORS:")
    for e in errors:
        print("  !", e)
    sys.exit(1)
print("Manifest, marketplace and SKILL.md all validate.")
