# Commonly missed places

Ask each line. Mark it yes, no or skip in `interview.md`. A yes gets a short note: which service, and where.

1. A second machine, a server or a virtual machine that runs an agent or holds keys.
2. A second user account or a work profile on this machine.
3. Agent harness profiles: Hermes profiles, Codex or Claude Code config folders set by an environment variable, Oddboro tool accounts.
4. Connectors hosted inside a chat app or a vendor's website (their logins stay on the vendor's servers).
5. Browser extensions that hold a sign-in or an API key.
6. Browser profiles used only for one service.
7. Keys inside a shell profile, a launch agent, a systemd user unit, a cron job or a scheduled task.
8. Keys inside a project's CI settings or a hosting dashboard (they stay there; note the service only).
9. Desktop apps with their own connectors or plug-ins (chat apps, note apps, editors).
10. Docker or compose files with an `environment:` block.
11. Password-manager items used by scripts (service accounts, API tokens, SSH keys).
12. OAuth apps they created themselves in a vendor console (client ids and secrets).
13. Webhooks they set up (incoming or outgoing) that act as a credential.
14. Database clients with saved connections (desktop database tools, notebooks).
15. Phone apps or home devices that an agent should reach.
16. Shared team vaults or company secret managers they can read from.
