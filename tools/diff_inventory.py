#!/usr/bin/env python3
"""Compare two inventories from tools/scan.py. Names only, like the inventories themselves.

  python tools/diff_inventory.py <last>/inventory.json <new>/inventory.json [--json]

Reports connections and skills that were added or removed, findings whose key
location, auth kind, transport or host changed (for example a key that moved from a
plain file into the vault), and sources whose status changed.
Exit codes: 0 compared (changes or not), 2 an input is missing or not an inventory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit.report import SCHEMA, guard  # noqa: E402

FIELDS = ("key_where", "auth_kind", "transport", "host", "plain_file", "key_fields")


def load(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("not an inventory")
    return data


def diff(old: dict, new: dict) -> dict:
    of = {f["id"]: f for f in old.get("findings", [])}
    nf = {f["id"]: f for f in new.get("findings", [])}
    osk = {s["id"]: s for s in old.get("skills", [])}
    nsk = {s["id"]: s for s in new.get("skills", [])}
    changed = []
    for fid in sorted(set(of) & set(nf)):
        delta = {k: {"was": of[fid].get(k), "now": nf[fid].get(k)} for k in FIELDS if of[fid].get(k) != nf[fid].get(k)}
        if delta:
            changed.append({"id": fid, "name": nf[fid]["name"], "source": nf[fid]["source"], "changes": delta})
    os_ = {s["id"]: s["status"] for s in old.get("sources", [])}
    ns_ = {s["id"]: s["status"] for s in new.get("sources", [])}
    return {
        "added": [nf[i] for i in sorted(set(nf) - set(of))],
        "removed": [of[i] for i in sorted(set(of) - set(nf))],
        "changed": changed,
        "skills_added": [nsk[i] for i in sorted(set(nsk) - set(osk))],
        "skills_removed": [osk[i] for i in sorted(set(osk) - set(nsk))],
        "skills_reclassified": [{"id": i, "was": osk[i]["class"], "now": nsk[i]["class"]}
                                for i in sorted(set(osk) & set(nsk)) if osk[i]["class"] != nsk[i]["class"]],
        "sources_changed": [{"id": i, "was": os_.get(i), "now": ns_.get(i)}
                            for i in sorted(set(os_) | set(ns_)) if os_.get(i) != ns_.get(i)],
    }


def text(d: dict) -> str:
    out = [f"added {len(d['added'])}, removed {len(d['removed'])}, changed {len(d['changed'])}; "
           f"skills added {len(d['skills_added'])}, removed {len(d['skills_removed'])}, "
           f"reclassified {len(d['skills_reclassified'])}; sources changed {len(d['sources_changed'])}"]
    for f in d["added"]:
        out.append(f"  + {f['source']}: {f['name']} ({f['kind']}, {', '.join(f['key_where'])})")
    for f in d["removed"]:
        out.append(f"  - {f['source']}: {f['name']} ({f['kind']})")
    for c in d["changed"]:
        parts = "; ".join(f"{k} {v['was']} -> {v['now']}" for k, v in c["changes"].items())
        out.append(f"  ~ {c['source']}: {c['name']}: {parts}")
    for s in d["skills_added"]:
        out.append(f"  + skill {s['harness']}: {s['name']} ({s['class']})")
    for s in d["skills_removed"]:
        out.append(f"  - skill {s['harness']}: {s['name']}")
    for s in d["skills_reclassified"]:
        out.append(f"  ~ skill {s['id']}: {s['was']} -> {s['now']}")
    for s in d["sources_changed"]:
        out.append(f"  ~ source {s['id']}: {s['was']} -> {s['now']}")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        d = diff(load(a.old), load(a.new))
    except (OSError, ValueError, KeyError):
        sys.stderr.write("error: both inputs must be inventory.json files from tools/scan.py\n")
        return 2
    sys.stdout.write(guard(json.dumps(d, indent=2) + "\n" if a.json else text(d)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
