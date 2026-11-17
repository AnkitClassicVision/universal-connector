# Running build-my-connector in Codex

- Open the registry folder (`universal-connector/`) as the working folder. Codex reads `AGENTS.md`.
- Ask: "Run build-my-connector." The agent routes through `ROUTE.md` to this runbook.
- Or link the runbooks into your Codex skills folder: `python tools/sync.py . --target ~/.codex/skills --include-draft --dry-run`, then again without `--dry-run` (check the vendor docs for your version's skills folder). `--include-draft` is needed while the runbooks are drafts. Never sync the QA registry to a maker's harness.
- Codex's sandbox may block reading files outside the working folder. The scanner needs read access to your home folder's config files; approve that for the scan command only, or run the scan yourself and give the agent the output folder.
- The scanner, smoke tests and helpers make no network calls except the smoke tests' calls to your own door.
