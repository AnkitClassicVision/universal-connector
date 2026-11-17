# Deliverable: 02-plan

This is the definition of done for the maker. It says what good looks like.
It does not say how the work is tested. Keep tests out of this file.

## Hand in

- `plan.md`: the plan in plain words, with the person's confirmation.
- `manifest-draft.yaml`: the connections, for the door.
- `harnesses.yaml`: the chosen harnesses.
- `skills-plan.md`: what happens to each skill.

## Format

`manifest-draft.yaml`:

```yaml
version: 1
vault: os-keyring            # or 1password, bitwarden, aws-secrets-manager, hashicorp-vault, pass, encrypted-file
door:
  placement: loopback        # or tailnet-route, server
  url: http://127.0.0.1:8765/mcp
  https_route: ""            # the https address, when a harness needs one
  door_hosts: [127.0.0.1:8765]
connections:
  - name: tracker
    service: linear          # a recipes/ file name, or custom
    kind: remote-mcp         # remote-mcp | local-mcp | direct-api | browser-lane | hosted-not-portable
    auth: api-key            # api-key | oauth | service-account | browser-session | none
    secret: work/tracker/read-key   # a vault entry name or a key file path; never a value
    scopes: [work]
    seen_in: [claude-code, codex]   # where the scan or the interview found it
    tools:
      - {match: "list_*", tier: green}
      - {match: "*", tier: red}
```

`harnesses.yaml`: one entry per harness in the checklist, each with `chosen: true` or `false`; for chosen ones, `server_name`, `key_held_by` (env-var, harness-store, keyring, file), `key_env` where used, `read_timeout_s`, `url` (loopback or the https route); for Oddboro also `address`, `kind` and `version`.

`plan.md`: sections Harnesses, Connections (a table), Not connected (each with a reason), Vault, Door placement, Plain-file keys and how they move, Gotcha pre-checks, Owner confirmation.

`skills-plan.md`: a table of every skill from the inventory with its harness, its location, its class and its decision (connect, carry to which harnesses, or keep).

## Must be true

- Every connection found by the scan and every service from the interview is accounted for: connected, merged into another row, hosted-not-portable, or not connected with a reason.
- One connection per real service and account. No duplicates.
- Every connection has an auth kind, a secret pointer (or `none` with a reason) and at least one scope.
- Every connection has tool rules, every rule has a tier, and the last rule makes everything else red.
- Nothing that sends, posts, deletes, pays, deploys or changes access is green or yellow unless the person chose it in their own words, recorded in `plan.md`.
- Every chosen harness has a server name, a key holding method and a read timeout. A harness that needs https has an https URL.
- If Oddboro is chosen, its address, kind and version are recorded, and its full tool names fit its limit.
- The person confirmed the tiers and scopes, and `plan.md` records it.
- No value appears anywhere.

## Out of scope

- Storing, moving or creating any secret. That is `03-vault`.
- Installing anything or editing any harness config.
