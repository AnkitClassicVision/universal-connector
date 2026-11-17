# Running build-my-connector in Claude Code

- Open the registry folder (`universal-connector/`) as the project. `CLAUDE.md` loads `AGENTS.md`.
- Ask: "Run build-my-connector." The agent routes through `ROUTE.md` to this runbook.
- Or link the runbooks into your skills folder: `python tools/sync.py . --target ~/.claude/skills --include-draft --dry-run`, then again without `--dry-run`. `--include-draft` is needed while the runbooks are drafts. Never sync the QA registry to a maker's harness.
- Stages `01a` and `01b` can run as two subagents side by side; each gets its own output folder.
- Claude Code may have safety hooks that block reads of credential files. That is expected: the scanner reads them in its own process, and the agent never needs to. If a hook blocks a command, stop that step and tell the person.
- Run the tools with the Python that has PyYAML (Python 3.11 or newer).
