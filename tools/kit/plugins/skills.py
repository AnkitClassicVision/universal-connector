"""Skill folders per harness. Names and one-line descriptions from the frontmatter only.

The body of a SKILL.md and every script in a skill folder are never opened. File
names in the folder are listed to spot a `scripts/` folder, nothing more.

Each skill gets one class:
  external-api           it wraps an outside service: turn that service into a door connection
  portable-instructions  plain instructions: carry it to other harnesses through the registry
  harness-specific       it depends on one harness's features: keep it where it is
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from kit.classify import CRED_WORD
from kit.core import FOUND, MISSING, Collector, Ctx, SkillEntry, bounded_glob, frontmatter
from kit.plugins import Plugin, shown

API_WORDS = re.compile(
    r"(?i)\b(api|apis|oauth|token|tokens|api key|webhook|endpoint|graphql|sdk|send (an )?email|"
    r"crm|inbox|calendar|invoice|payments?|sms|slack|gmail|github|gitlab|jira|linear app|notion|hubspot|"
    r"salesforce|stripe|quickbooks|zendesk|intercom|airtable|supabase|postgres|aws|cloudflare|vercel|"
    r"asana|clickup|monday\.com|trello|microsoft teams|zoom meetings?|fathom|google (drive|sheets|docs))\b"
)
HARNESS_WORDS = re.compile(
    r"(?i)\b(claude code|codex|hermes|cursor|windsurf|goose|zed|oddboro|openmausbot|grok|settings\.json|"
    r"slash command|statusline|status line|hook|hooks|keybinding|plugin|subagent|claude\.md|agents\.md|"
    r"mcp__[a-z0-9_]+)\b"
)
HARNESS_KEYS = {"hooks", "context", "agent", "disable-model-invocation", "user-invocable", "argument-hint"}
CRED_KEYS = {"env", "requires", "credentials", "primaryEnv", "secrets", "api_key", "apiKey"}
MAX_SKILLS = 2000


def roots(ctx: Ctx) -> list[tuple[str, Path, str]]:
    """(harness, folder, glob) for every skill location."""
    claude_dir = ctx.env_path("CLAUDE_CONFIG_DIR") or ctx.home / ".claude"
    codex = ctx.env_path("CODEX_HOME") or ctx.home / ".codex"
    hermes = ctx.env_path("HERMES_HOME") or ctx.home / ".hermes"
    out = [
        ("claude-code", claude_dir / "skills", "*/SKILL.md"),
        ("claude-code-plugin", claude_dir / "plugins", "**/skills/*/SKILL.md"),
        ("codex", codex / "skills", "**/SKILL.md"),
        ("hermes", hermes / "skills", "**/SKILL.md"),
        ("hermes-profile", hermes / "profiles", "*/skills/**/SKILL.md"),
        ("agents", ctx.home / ".agents" / "skills", "*/SKILL.md"),
    ]
    for proj in ctx.projects:
        out += [("project-claude", proj / ".claude" / "skills", "*/SKILL.md"),
                ("project-agents", proj / ".agents" / "skills", "*/SKILL.md"),
                ("project-codex", proj / ".codex" / "skills", "**/SKILL.md")]
    return out


def where(ctx: Ctx) -> list[str]:
    return [f"{ctx.show(folder)}/{pattern} ({harness})" for harness, folder, pattern in roots(ctx)]


def _cred_in(value: Any, key: str = "") -> bool:
    if isinstance(value, dict):
        return any((str(k) in CRED_KEYS and bool(v)) or _cred_in(v, str(k)) for k, v in value.items())
    if isinstance(value, list):
        return any(_cred_in(v, key) for v in value)
    return key in CRED_KEYS and isinstance(value, str) and bool(CRED_WORD.search(value))


def classify(fm: dict[str, Any], has_scripts: bool) -> tuple[str, list[str]]:
    text = f"{fm.get('name', '')} {fm.get('description', '')}"
    signals: list[str] = []
    if API_WORDS.search(text):
        signals.append("mentions an outside service or API")
    if _cred_in({k: v for k, v in fm.items() if k not in ("name", "description")}):
        signals.append("frontmatter names a credential")
    if has_scripts:
        signals.append("has a scripts folder")
    harness = bool(HARNESS_WORDS.search(text)) or bool(HARNESS_KEYS & set(map(str, fm)))
    if harness:
        signals.append("depends on one harness")
    if "frontmatter names a credential" in signals or "mentions an outside service or API" in signals:
        return "external-api", signals
    if harness:
        return "harness-specific", signals
    return "portable-instructions", signals


NEXT = {
    "external-api": "Turn its API into a door connection (02-plan, step 'skills to connections'); keep the instructions, drop its own key handling.",
    "portable-instructions": "Carry it: add it to the registry skills/ folder and sync it to each chosen harness (05n-carry-skills).",
    "harness-specific": "Keep it in its harness.",
}


def scan(ctx: Ctx, col: Collector) -> None:
    red = ctx.redactor
    count = 0
    for harness, folder, pattern in roots(ctx):
        files = bounded_glob(folder, pattern, 500) if folder.is_dir() else []
        col.look(folder, FOUND if files else MISSING)
        for f in files:
            if count >= MAX_SKILLS:
                col.notes.append(f"Stopped after {MAX_SKILLS} skills.")
                return
            status, fm = frontmatter(f)
            skill_dir = f.parent
            try:
                has_scripts = (skill_dir / "scripts").is_dir()
            except OSError:
                has_scripts = False
            if fm is None:
                col.look(f, status)
                col.skills.append(SkillEntry(harness, shown(ctx, skill_dir.parent), red.name(skill_dir.name),
                                             "[no readable frontmatter]", "harness-specific", ["no frontmatter"],
                                             "Open it yourself and decide; the scanner did not read the body."))
                count += 1
                continue
            klass, signals = classify(fm, has_scripts)
            col.skills.append(SkillEntry(harness, shown(ctx, skill_dir.parent), red.name(fm.get("name") or skill_dir.name),
                                         red.text(fm.get("description", "")), klass, signals, NEXT[klass]))
            count += 1
    names: dict[str, list[SkillEntry]] = {}
    for s in col.skills:
        names.setdefault(s.name.lower(), []).append(s)
    for group in names.values():
        if len(group) > 1:
            for s in group:
                s.signals.append("same name in another harness")


PLUGINS = [Plugin("skills", "Skill folders (Claude Code, plugins, Codex, Hermes, ~/.agents, projects)", "skills", where, scan)]
