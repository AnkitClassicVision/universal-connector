# How each harness connects, and its known limits

Each harness gets its own entry pointing at the door, with its own door key. Print the exact entry with `python tools/entry.py --harness <id> --url <door url> --key-env <variable name>`; it never holds a key. The connect stage for each harness (`05a` to `05m`) has the file places per operating system, the read-timeout setting and the steps.

## Ways a harness can hold the key

Best first:

1. **By reference**: the config names an environment variable or the harness's own secret store, and the key itself lives elsewhere (Codex `bearer_token_env_var`, Claude Code `${NAME}` expansion, VS Code `${input:...}` with `password: true`).
2. **In the harness's own store**: you paste the key into the harness's settings screen and it keeps it (Oddboro's desk task).
3. **In the config file**: only when the harness offers nothing else. Use the door key for that harness, never an upstream key, and make the file readable only by you. The door key is revocable on its own.

## Formats

| Harness | Format | Server entry, in short |
|---|---|---|
| Claude Code | JSON, `mcpServers` | `{"type": "http", "url": ..., "headers": {"Authorization": "Bearer ${DOOR_KEY}"}}` |
| Claude Desktop | JSON, `mcpServers`, local programs only | A local bridge program that adds the header; the key comes from a 0600 file the bridge reads |
| Codex | TOML, `[mcp_servers.<name>]` | `url = ...`, `bearer_token_env_var = "DOOR_KEY"`, `tool_timeout_sec = 120` |
| Cursor | JSON, `mcpServers` | `{"url": ..., "headers": {"Authorization": "Bearer ${env:DOOR_KEY}"}}` (check the vendor docs) |
| Windsurf | JSON, `mcpServers` | `{"serverUrl": ..., "headers": {...}}` (check the vendor docs) |
| VS Code | JSON, `servers` plus `inputs` | `{"type": "http", "url": ..., "headers": {"Authorization": "Bearer ${input:door-key}"}}` |
| Cline | JSON, `mcpServers` | `url`, `headers`, `timeout` (check the vendor docs) |
| Continue | YAML, `mcpServers` list | `type: streamable-http`, `url`, `requestOptions.headers` (check the vendor docs) |
| Zed | JSON with comments, `context_servers` | `url` plus `headers` in newer versions (check the vendor docs) |
| Goose | YAML, `extensions` | `type: streamable_http`, `uri`, `headers`, `timeout` |
| Hermes | YAML, `mcp_servers` | `url`, `headers`, `timeout` |
| OpenMausBot | JSON, `mcpServers` | `{"type": "http", "url": ..., "headers": {...}, "enabled": true}` |
| Oddboro | Services tab | Hosted MCP service, https address, "Takes a key", header `Authorization`, Read only grant to one Odd |
| GrokBot | Its CLI reads Claude Code's list | Connect Claude Code; the desktop app keeps its own logins |
| Any other MCP client | Its own settings | The door URL plus one header, `Authorization: Bearer <key>` |

## Known limits

This table is generated from `tools/kit/harnesses.py` (`python tools/entry.py --limits-table`); a test keeps the two equal. "seen-in-build" rows were hit while the reference door was built. Other rows come from vendor docs at the time of writing or are unverified. Where the tool name form is not known, the table uses the longest common form, `mcp__{server}__{tool}`, so a check against it is safe.

<!-- limits:start -->
| Harness | Tool name form | Name limit | Read timeout setting | https only | Header support | Tool-list paging | Source |
|---|---|---|---|---|---|---|---|
| Claude Code | `mcp__{server}__{tool}` | 64 | MCP_TOOL_TIMEOUT env var, in milliseconds (MCP_TIMEOUT is start-up only) | no | yes | unknown: check the vendor docs | vendor-docs |
| Claude Desktop | `mcp__{server}__{tool}` | 64 | unknown: check the vendor docs | yes for custom connectors added in Settings; no for a local stdio bridge | not in the JSON file (stdio only); use a local stdio bridge that adds the header | unknown: check the vendor docs | vendor-docs |
| Codex | `mcp__{server}__{tool}` | 64 | tool_timeout_sec per server (default 60); startup_timeout_sec for start-up | no | yes | unknown: check the vendor docs | vendor-docs |
| Cursor | `mcp__{server}__{tool}` | 60 | unknown: check the vendor docs | no | yes | unknown: check the vendor docs | unverified |
| Windsurf | `mcp__{server}__{tool}` | 64 | unknown: check the vendor docs | no | yes | unknown: check the vendor docs | unverified |
| VS Code (native, Continue, Cline) | `mcp__{server}__{tool}` | 64 | Cline: timeout per server in seconds (default 60). VS Code and Continue: check the vendor docs | no | yes | unknown: check the vendor docs | vendor-docs |
| Zed | `mcp__{server}__{tool}` | 64 | unknown: check the vendor docs | no | url plus headers in newer versions: check the vendor docs | unknown: check the vendor docs | unverified |
| Goose | `mcp__{server}__{tool}` | 64 | timeout per extension, in seconds (default 300) | no | yes | unknown: check the vendor docs | unverified |
| Hermes | `mcp__{server}__{tool}` | 64 | timeout and connect_timeout per server: check the vendor docs | no | yes | unknown: check the vendor docs | unverified |
| OpenMausBot | `mcp__{server}__{tool}` | 64 | unknown: check the vendor docs | no | yes | unknown: check the vendor docs | seen-in-build |
| Oddboro | `mcp__{server}__{tool}` | 64 | unknown: check the vendor docs | yes: only https:// service addresses | one header: name Authorization; a bare value gets 'Bearer ' added | first page of tools only | seen-in-build |
| GrokBot | `mcp__{server}__{tool}` | 64 | unknown: check the vendor docs | no | yes | unknown: check the vendor docs | unverified |
| Any other MCP client | `mcp__{server}__{tool}` | 64 | unknown: check the vendor docs | no | yes | unknown: check the vendor docs | unverified |
<!-- limits:end -->

## What the limits mean for the door

- Keep the door's server name short in every harness (for example `door`), and keep the door's own tool names short and fixed. Most model APIs refuse a tool name over 64 characters.
- Put all of the door's tools on the first `tools/list` page.
- Set each harness's read timeout above the door's slowest call.
- Use an https route only for the harnesses that need one.
