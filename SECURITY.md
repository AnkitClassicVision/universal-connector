# Security

## Report a problem

Please report a security problem privately, through this repository's private vulnerability reporting ("Report a vulnerability" on the Security tab), rather than in a public issue. Include the tool, the command you ran (without any value), what you expected and what happened.

Never include a real key, token, password or config file in a report. If a kit tool printed a value, rotate that value in its service first, then tell us which tool, which flags, and the rule name it matched.

## What counts

- Any kit tool printing, logging, storing or returning a secret value, or a slice of one.
- The scanner reading outside the places `--list-sources` names, or following a path it should not.
- A smoke test sending a key anywhere but the door URL it was given.
- A runbook step that asks the agent to see, type or move a secret, or to skip a human yes.
- A recipe that would grant more than its stated tier.

## Design rules we hold ourselves to

- Values are read only in the scanning process, only to classify where a key lives, and are dropped at once.
- Every output passes a key-shape guard; on a match the tool stops and writes nothing.
- No network calls, except smoke tests to the door the person names and `tools/oddboro_version.py` to the local loopback office.
- Tests use fake fixtures only. Fixture values are built so that no real key shape is committed.
- `python tools/keyshape.py .` must report nothing before any release.

## Limits

Key-shape rules catch common key formats, not every secret. A short key with no known shape can only be protected by never copying values, which is how the tools are built. The door does not sandbox the harnesses that use it.
