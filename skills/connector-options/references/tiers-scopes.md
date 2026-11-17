# Tiers and scopes

## Tiers (per tool)

| Tier | Means | Examples | Default |
|---|---|---|---|
| green (read) | Looks and changes nothing | list, search, get, read a file, read a calendar | Allowed |
| yellow (draft) | A reversible write that nobody else acts on | create a mail draft, a private draft page | Allowed only where the plan says so |
| red (blocked) | Sends, posts, deletes, pays, deploys, changes access, or writes to a record other people or bots act on | send mail, post a message, refund, merge, deploy, edit a CRM record, comment on a shared board | Refused by the door |

Rules:

- Every tool gets a tier. A tool with no tier does not exist for agents.
- When unsure, red. A tool can move down a tier later, on purpose, as a versioned change.
- A tool's name is not proof. Read what it does in the vendor's docs or the recipe.
- Some logins can do more than their tier: a mail login that makes drafts may also be able to send. The door enforces the tier; say plainly that the stored login could do more if it leaked.

## Scopes (per connection)

A scope is a label for whose data a connection touches. Use the person's own words, for example `work` and `personal`. Each harness key is granted a set of scopes; a connection outside them is invisible to that harness.

- Keep work and personal accounts as separate connections, even for the same service.
- Grant each harness the fewest scopes it needs.
- Any scope that holds other people's sensitive records needs its own explicit decision by the person, and a review process of their own. The kit does not decide it.

## Vendor scopes

Ask the vendor for the narrowest scope that covers the green tools: read-only scopes, a read-only role, or a key limited to one workspace or project. The recipes in `recipes/` give hints and mark what to check in the vendor docs.
