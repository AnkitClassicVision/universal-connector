# 05n-carry-skills

## Purpose

Carry the skills the person chose (plain instructions, class `portable-instructions`) to the other harnesses they named, from one source folder, without changing the skills.

## Inputs

| Source | Location | Why |
|---|---|---|
| Skills plan | `<run folder>/02-plan/output/skills-plan.md` | Which skills to carry, where each lives now, and to which harnesses |
| Secret rules | `skills/handle-secrets/SKILL.md` | A skill folder must hold no keys |

Read only what is listed here. This stage is a human yes point.

## Skill folders per harness

| Harness | User skills folder |
|---|---|
| Claude Code | `~/.claude/skills/<name>/` |
| Codex | `~/.codex/skills/<name>/` (check the vendor docs for your version) |
| Hermes | `~/.hermes/skills/<name>/`, or a profile's `skills/` |
| Shared source | `~/.agents/skills/<name>/` |

## Process

1. Show the person the carry list from the skills plan: each skill, its source folder, and the target harnesses. Ask for their yes.
2. Pick one source folder per skill (default `~/.agents/skills/<name>/`). If the skill lives elsewhere, copy it there once.
3. Before any copy, run `python tools/keyshape.py <the skill folder>`. If it reports anything, do not carry that skill; tell the person which file and rule, and move on.
4. Carry only `SKILL.md` and its `references/` and `assets/`. If the skill has a `scripts/` folder, ask the person first; scripts that call an outside service belong behind the door instead.
5. For each target harness: if a folder with the same name already exists there, stop for that skill and ask; never overwrite. Otherwise make a link to the source folder (or a copy, where the harness does not follow links).
6. Check: the harness lists the skill by name (its skills or slash-command list).
7. Write `carry.md` with the fields in `deliverable.md`.

## Output

Write to `<run folder>/05n-carry-skills/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/handle-secrets`
- `tools/keyshape.py`
