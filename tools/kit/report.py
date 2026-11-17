"""Inventory output: JSON, the owner sheet (Markdown) and the short human summary.

Every text leaves through `guard`, which refuses to print or write anything
key-shaped. The guard is the last net, not the plan: the plan is that no value
is ever copied into a finding.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from kit import __version__
from kit.core import Collector, Ctx
from kit.keyshape import rule_hits

SCHEMA = "universal-connector/inventory@1"


class GuardTripped(Exception):
    """Text about to leave the scanner matched a key-shape rule. Nothing was written."""


def guard(text: str) -> str:
    hits = rule_hits(text)
    if hits:
        raise GuardTripped(", ".join(hits))
    return text


def build(ctx: Ctx, results: list[tuple[Any, Collector]]) -> dict[str, Any]:
    sources, findings, skills = [], [], []
    for plugin, col in results:
        statuses = Counter(x["status"] for x in col.looked)
        overall = ("found" if col.findings or col.skills or statuses.get("found") else
                   "malformed" if statuses.get("malformed") else
                   "opt-in-required" if statuses.get("opt-in-required") else
                   "unreadable" if statuses.get("unreadable") else
                   "skipped" if statuses and set(statuses) == {"skipped"} else "missing")
        sources.append({"id": plugin.id, "label": plugin.label, "group": plugin.group, "opt_in": plugin.opt_in,
                        "status": overall, "looked_at": col.looked, "findings": len(col.findings),
                        "skills": len(col.skills), "notes": col.notes})
        findings += [f.as_dict() for f in col.findings]
        skills += [s.as_dict() for s in col.skills]
    findings.sort(key=lambda f: f["id"])
    skills.sort(key=lambda s: s["id"])
    auth = Counter(f["auth_kind"] for f in findings if f["kind"] not in ("listening-port", "account-home"))
    where = Counter(w for f in findings for w in f["key_where"])
    return {
        "schema": SCHEMA, "tool_version": __version__,
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": ctx.platform,
        "options": {"include_vaults": ctx.include_vaults, "projects": len(ctx.projects)},
        "sources": sources, "findings": findings, "skills": skills,
        "totals": {
            "findings": len(findings), "skills": len(skills),
            "plain_file_secrets": sum(1 for f in findings if f["plain_file"]),
            "hidden_fields": ctx.redactor.hidden_count,
            "by_auth_kind": dict(sorted(auth.items())), "by_key_location": dict(sorted(where.items())),
            "skills_by_class": dict(sorted(Counter(s["class"] for s in skills).items())),
        },
    }


def _cell(value: Any) -> str:
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown(inv: dict[str, Any]) -> str:
    t = inv["totals"]
    lines = [
        "# Connection inventory", "",
        f"Made by `tools/scan.py` {inv['tool_version']} on {inv['generated']} ({inv['platform']}). "
        "Names, kinds and locations only. No values.", "",
        f"- Findings: {t['findings']}. Skills: {t['skills']}.",
        f"- Keys in plain files: {t['plain_file_secrets']}. Move each one into the vault yourself (stage 03-vault).",
        f"- Fields hidden because they looked like keys: {t['hidden_fields']}.",
        "- By auth kind: " + (", ".join(f"{k} {v}" for k, v in t["by_auth_kind"].items()) or "none"),
        "- By key location: " + (", ".join(f"{k} {v}" for k, v in t["by_key_location"].items()) or "none"), "",
        "## Sources", "", "| Source | Group | Status | Findings | Where it looked |", "|---|---|---|---|---|",
    ]
    for s in inv["sources"]:
        looked = "; ".join(f"{x['path']} ({x['status']})" for x in s["looked_at"][:12])
        if len(s["looked_at"]) > 12:
            looked += f"; and {len(s['looked_at']) - 12} more"
        lines.append(f"| {_cell(s['label'])} | {s['group']} | {s['status']} | {s['findings'] + s['skills']} | {_cell(looked)} |")
    lines += ["", "## Connections and credentials", "",
              "| Name | Source | Kind | Transport | Host | Key fields | Key location | Auth | Plain file | How to add it as a connector |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for f in inv["findings"]:
        lines.append("| " + " | ".join(_cell(x) for x in (
            f["name"], f"{f['source']}: {f['location']}", f["kind"], f["transport"], f["host"], f["key_fields"],
            f["key_where"], f["auth_kind"], "yes" if f["plain_file"] else "no",
            (f["how_to_add"] + (f" ({f['detail']})" if f["detail"] else "")))) + " |")
    lines += ["", "## Skills", "", "| Name | Harness | Class | Next step | Description |", "|---|---|---|---|---|"]
    for s in inv["skills"]:
        lines.append("| " + " | ".join(_cell(x) for x in (s["name"], f"{s['harness']}: {s['location']}", s["class"],
                                                            s["next_step"], s["description"])) + " |")
    notes = [n for s in inv["sources"] for n in s["notes"]]
    if notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in notes]
    lines += ["", "Next: stage 01b-ask covers what a scan cannot see (SaaS logins, websites, databases, other machines).", ""]
    return "\n".join(lines)


def summary(inv: dict[str, Any]) -> str:
    t = inv["totals"]
    out = [f"Universal Connector scan {inv['tool_version']}: {t['findings']} finding(s), {t['skills']} skill(s), "
           f"{t['plain_file_secrets']} key(s) in plain files, {t['hidden_fields']} field(s) hidden.", ""]
    width = max((len(s["id"]) for s in inv["sources"]), default=10)
    for s in inv["sources"]:
        out.append(f"  {s['id']:<{width}}  {s['status']:<16} {s['findings'] + s['skills']:>4}")
    out.append("")
    if t["by_auth_kind"]:
        out.append("Auth kinds: " + ", ".join(f"{k} {v}" for k, v in t["by_auth_kind"].items()))
    if t["skills_by_class"]:
        out.append("Skills: " + ", ".join(f"{k} {v}" for k, v in t["skills_by_class"].items()))
    opt = [s["id"] for s in inv["sources"] if s["status"] == "opt-in-required"]
    if opt:
        out.append("Present but not listed (run with --include-vaults to list entry names): " + ", ".join(opt))
    return "\n".join(out) + "\n"
