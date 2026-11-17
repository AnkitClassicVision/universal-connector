# AWS

Amazon Web Services: infrastructure, logs, costs and more. Agents usually read resource lists, logs and metrics.

## Auth kinds

| Kind | Use it when | Who does each step |
|---|---|---|
| OAuth | You use IAM Identity Center (single sign-on) profiles. This is the usual path. | The person runs the AWS CLI's own sign-in for the profile themselves. The agent never handles codes or tokens. |
| Service account | A machine needs a role without a person present. | An admin creates the role. The door uses the machine's role or a profile that assumes it. No key file is copied. |
| API key | Only when no other option exists. Long-lived access keys are a risk. | The person creates the access key and stores it with the vault's own command. The value never passes through the agent. |

## Connect it

- Official MCP server: yes. AWS publishes many open-source MCP servers that run locally and use your AWS profile. Pick only the ones you need: check the vendor docs.
- Community MCP servers: exist.
- Direct API adapter: for a few fixed reads, if no server fits.

## Tiers

| Tool type | Tier |
|---|---|
| Describe, list and get resources, read metrics and logs | green |
| Read costs | green |
| Read a secret's value | red |
| Create, change or delete any resource | red |
| Deploy, change permissions or policies | red |

Reading a secret's value is red, because it would show the secret.

## Scope hints

- Use a role with the `ViewOnlyAccess` managed policy, or a narrower custom policy.
- `ReadOnlyAccess` is wider: it can read data inside storage and databases. Choose it only on purpose.
- Keep separate accounts as separate connections.

## Smoke test

Run the caller identity read, which shows the signed-in role name.

```bash
python tools/smoke_connection.py --url <door url> --key-file <smoke key file> --plan <run folder>/02-plan/output/manifest-draft.yaml --connection aws --tool <caller identity tool> --args '{}' --auth-kind oauth --whoami-tool <caller identity tool>
```

## Gotchas

- Single sign-on sessions expire. When a call fails with a sign-in error, the person signs in again.
- Many list calls page with a next token. The door must drop tokens from results.
- Pick the region on purpose. Many reads return nothing in the wrong region.
