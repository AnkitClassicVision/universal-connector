# 01b-ask

## Purpose

Find the connections a scan cannot see, and where each one lives, by asking the person.

## Inputs

| Source | Location | Why |
|---|---|---|
| The person | The conversation | Only they know their SaaS logins, websites, databases and other machines |
| Commonly missed places | `references/missed-places.md` in this stage | So nothing obvious is forgotten |
| Recipes index | `recipes/README.md` | Names of common services, to prompt their memory |
| Secret rules | `skills/handle-secrets/SKILL.md` | What you may and may not ask for |

Read only what is listed here. This stage runs side by side with `01a-scan` and does not read its output.

## Process

1. Say once, before the first question: "I only need names and where things live. Never paste a password, key, code or token here. If one appears, I will tell you to rotate it."
2. Ask in these groups, one group at a time. For each thing they name, ask the three follow-ups below.
   - SaaS tools they use for work or home (trackers, chat, mail, calendar, docs, CRM, finance, support, meetings).
   - Internal or company APIs, and admin consoles.
   - Websites they sign in to that have no API, where a browser would have to do the work.
   - Databases and data stores (Postgres, MySQL, spreadsheets used as databases, object storage).
   - Local tools and servers (anything running on this machine or another of theirs, other agent bots and harnesses).
   - Other services they want connected that they have not named yet, for example another bot such as GrokBot.
3. Follow-ups for each item:
   - **Where does the connection live?** One of: a harness config, an environment variable, a file, the OS keychain, a password manager, a browser session, a vendor-hosted connector (for example inside a chat app), another machine, or "I don't know".
   - **How do you sign in?** API key, OAuth sign-in, service account, username and password on a website, or "I don't know".
   - **Work, personal or other?** Their own words.
4. Walk the checklist in `references/missed-places.md` with them. Mark each line yes, no or skip.
5. If they paste anything that looks like a value, stop. Do not repeat it, quote it or write it down. Tell them it is now exposed and should be rotated in that service, and record only "a value was pasted for <service>; rotation advised".
6. Write `interview.md` with the format in `deliverable.md`, read it back to them in short, and fix what they correct.
7. Hand in and pass the task to the QA agent.

## Output

Write to `<run folder>/01b-ask/output/`. `deliverable.md` says what must be in it.

## Uses

- `skills/handle-secrets`
- `recipes/README.md`
