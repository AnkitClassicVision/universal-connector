"""End-to-end scanner tests on the fixture trees. The scanner runs as a subprocess with a
controlled environment, a fixture home, a fixture root and fake CLIs only."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from conftest import FIX, assert_no_leak, by_name, load_inventory, run_tool, scan_args, scan_env
from kit.keyshape import line_hits


def _full_scan(tree, *more):
    env = scan_env(tree["bin"], tree["home"])
    r = run_tool("scan.py", scan_args(tree, "--include-vaults", "--out", str(tree["out"]), *more), env, tree["home"])
    assert r.returncode == 0, r.stderr
    return r, load_inventory(tree["out"])


def one(index, source, name):
    rows = index.get((source, name))
    assert rows, f"missing finding {source}: {name}"
    return rows[0]


def test_every_source_finds_its_fixture(full_tree):
    _, inv = _full_scan(full_tree)
    ix = by_name(inv)
    expect = {
        ("claude-code", "tracker"): (["inline"], "api-key"),
        ("claude-code", "notes-local"): (["env-reference"], "api-key"),
        ("claude-code", "files"): (["none"], "not-needed"),
        ("claude-code", "hosted-docs"): (["no-credential-found"], "none-found"),
        ("claude-code", "wiki"): (["inline"], "api-key"),
        ("claude-code", "board"): (["inline"], "api-key"),
        ("claude-code", "plugin-search"): (["inline"], "api-key"),
        ("claude-code", "company-search"): (["env-reference"], "api-key"),
        ("claude-code", "SERVICE_API_KEY"): (["inline"], "api-key"),
        ("codex", "issues"): (["env-reference"], "api-key"),
        ("codex", "db"): (["file", "inline"], "api-key"),
        ("codex", "vaulted"): (["vault"], "api-key"),
        ("codex", "codex sign-in"): (["file"], "oauth"),
        ("claude-desktop", "bridge"): (["env-reference", "inline"], "api-key"),
        ("claude-desktop", "weather-ext"): (["file"], "api-key"),
        ("cursor", "design"): (["env-reference"], "api-key"),
        ("windsurf", "tickets"): (["inline"], "api-key"),
        ("vscode", "crm"): (["prompt"], "api-key"),
        ("vscode", "sheets"): (["inline"], "api-key"),
        ("cline", "browser-lane"): (["browser-session"], "browser-session"),
        ("continue", "search-api"): (["inline"], "api-key"),
        ("continue", "remote-kb"): (["env-reference"], "api-key"),
        ("zed", "git-tools"): (["inline"], "api-key"),
        ("zed", "ext-server"): (["inline"], "api-key"),
        ("goose", "calendar"): (["inline"], "api-key"),
        ("goose", "local-tool"): (["keyring"], "api-key"),
        ("goose", "TOOL_KEY"): (["file"], "api-key"),
        ("hermes", "kb"): (["env-reference"], "api-key"),
        ("hermes", "KB_TOKEN"): (["file"], "api-key"),
        ("hermes", "mail"): (["inline"], "api-key"),
        ("openmausbot", "door"): (["inline"], "api-key"),
        ("oddboro", "DATABASE_URL"): (["file"], "api-key"),
        ("oddboro", "office-tools"): (["inline"], "api-key"),
        ("oddboro", "office-notes"): (["inline"], "api-key"),
        ("grokbot", "search"): (["inline"], "api-key"),
        ("env", "DEMO_SERVICE_TOKEN"): (["environment"], "api-key"),
        ("env", "GOOGLE_APPLICATION_CREDENTIALS"): (["file"], "service-account"),
        ("env-files", "API_KEY"): (["file"], "api-key"),
        ("env-files", "DB_URL"): (["file"], "api-key"),
        ("shell-profiles", "OPENAI_API_KEY"): (["file"], "api-key"),
        ("shell-profiles", "GITHUB_TOKEN"): (["vault"], "api-key"),
        ("gh", "github.com"): (["file"], "oauth"),
        ("gh", "git.example.com"): (["keyring"], "oauth"),
        ("gcloud", "application default credentials"): (["file"], "oauth"),
        ("aws", "default"): (["file"], "api-key"),
        ("aws", "ci"): (["helper"], "api-key"),
        ("aws", "dev"): (["oauth"], "oauth"),
        ("aws", "deploy"): (["helper"], "service-account"),
        ("docker", "registry.example.com"): (["file"], "password"),
        ("docker", "gcr.example.com"): (["helper"], "password"),
        ("kube", "dev-admin"): (["file"], "api-key"),
        ("kube", "cloud-user"): (["helper"], "oauth"),
        ("npm", "registry.example.com"): (["file"], "api-key"),
        ("npm", "npm.example.org"): (["env-reference"], "api-key"),
        ("pypi", "pypi"): (["file"], "api-key"),
        ("pypi", "pypi.example.com"): (["inline"], "password"),
        ("netrc", "api.example.com"): (["file"], "password"),
        ("git-credentials", "git.example.com"): (["file"], "password"),
        ("git-credentials", "git credential helper"): (["file"], "password"),
    }
    for (source, name), (where, auth) in expect.items():
        f = one(ix, source, name)
        assert f["key_where"] == where, (source, name, f["key_where"])
        assert f["auth_kind"] == auth, (source, name, f["auth_kind"])
    assert one(ix, "claude-code", "tracker")["host"] == "https://tracker.example.com"
    assert "NOTES_TOKEN" in one(ix, "claude-code", "notes-local")["key_fields"]
    assert "ISSUES_TOKEN" in one(ix, "codex", "issues")["key_fields"]
    assert one(ix, "claude-code", "tracker")["plain_file"] is True
    assert one(ix, "codex", "issues")["plain_file"] is False
    assert ("env", "SSH_AUTH_SOCK") not in ix
    assert ("hermes", "LOG_LEVEL") not in ix
    assert one(ix, "claude-code", "hosted-docs")["kind"] == "mcp-server"
    assert [f for f in ix[("claude-code", "hosted-docs")] if f["kind"] == "oauth-sign-in"]


def test_vaults_runtime_and_skills(full_tree):
    _, inv = _full_scan(full_tree)
    ix = by_name(inv)
    for source, name in [("1password", "Work/GitHub read token"), ("1password", "Personal/Forum login"),
                         ("bitwarden", "Email login"), ("bitwarden", "Recovery codes"), ("pass", "work/github"),
                         ("pass", "personal/forum"), ("gopass", "work/api-token"), ("secret-service", "Demo keyring item")]:
        assert one(ix, source, name)["kind"] == "vault-entry"
    ports = {f["name"]: f for f in inv["findings"] if f["kind"] == "listening-port"}
    assert set(ports) == {"port 8765", "port 3000", "port 8080"}
    assert ports["port 8765"]["command"] == "node" and "mentions mcp: yes" in ports["port 8765"]["detail"]
    assert "all interfaces" in ports["port 3000"]["detail"]
    assert ports["port 8080"]["host"] == "tcp://[::1]:8080"
    assert one(ix, "browsers", "Chrome: 2 profile(s)")["auth_kind"] == "browser-session"
    skills = {s["name"]: s["class"] for s in inv["skills"]}
    assert skills == {"meeting-notes": "portable-instructions", "crm-lookup": "external-api",
                      "statusline-tweak": "harness-specific", "write-brief": "portable-instructions",
                      "deploy-check": "external-api", "web-digest": "portable-instructions"}
    accounts = {f["name"] for f in inv["findings"] if f["kind"] == "account-home"}
    assert accounts == {"codex/office", "claude/office"}


def test_no_planted_value_reaches_any_output(full_tree):
    r, inv = _full_scan(full_tree)
    env = scan_env(full_tree["bin"], full_tree["home"])
    as_json = run_tool("scan.py", scan_args(full_tree, "--include-vaults", "--json"), env, full_tree["home"])
    listed = run_tool("scan.py", scan_args(full_tree, "--list-sources"), env, full_tree["home"])
    files = [(full_tree["out"] / n).read_text(encoding="utf-8") for n in ("inventory.json", "inventory.md")]
    assert as_json.returncode == 0 and listed.returncode == 0
    assert_no_leak(r.stdout, r.stderr, as_json.stdout, as_json.stderr, listed.stdout, listed.stderr, *files)
    assert json.loads(as_json.stdout)["totals"]["findings"] == inv["totals"]["findings"]


def test_outputs_pass_the_key_shape_scan_and_are_private(full_tree):
    _full_scan(full_tree)
    for name in ("inventory.json", "inventory.md"):
        p = full_tree["out"] / name
        assert line_hits(p.read_text(encoding="utf-8")) == []
        assert p.stat().st_mode & 0o077 == 0


def test_vault_entries_need_the_opt_in(full_tree):
    env = scan_env(full_tree["bin"], full_tree["home"])
    r = run_tool("scan.py", scan_args(full_tree, "--json"), env, full_tree["home"])
    inv = json.loads(r.stdout)
    assert not [f for f in inv["findings"] if f["kind"] == "vault-entry"]
    status = {s["id"]: s["status"] for s in inv["sources"]}
    for sid in ("1password", "bitwarden", "pass", "gopass", "secret-service"):
        assert status[sid] == "opt-in-required", sid


def test_malformed_files_never_crash_or_leak(tmp_path):
    home = tmp_path / "home"
    shutil.copytree(FIX / "malformed" / "home", home)
    (home / ".netrc").write_bytes(b"\xff\xfe machine x password Qz9FAKEmfv10x\n")
    (tmp_path / "root").mkdir()
    (tmp_path / "proj").mkdir()
    env = {"PATH": str(tmp_path / "nobin"), "LANG": "C.UTF-8"}
    args = ["--home", str(home), "--root", str(tmp_path / "root"), "--platform", "linux", "--project", str(tmp_path / "proj")]
    r = run_tool("scan.py", args + ["--json"], env, tmp_path)
    assert r.returncode == 0, r.stderr
    inv = json.loads(r.stdout)
    status = {s["id"]: s["status"] for s in inv["sources"]}
    for sid in ("claude-code", "codex", "hermes", "zed", "aws", "kube", "docker", "gh"):
        assert status[sid] == "malformed", (sid, status[sid])
    looked = {x["path"]: x["status"] for s in inv["sources"] for x in s["looked_at"]}
    assert looked["~/.netrc"] == "malformed"
    assert looked["~/.config/goose/config.yaml"] == "unreadable"
    assert not [f for f in inv["findings"] if f["source"] in ("cursor", "vscode", "continue", "openmausbot")]
    assert all(s["status"] != "error" for s in inv["sources"])
    assert_no_leak(r.stdout, r.stderr, values={v for v in _planted_malformed()})


def _planted_malformed():
    from conftest import PLANT
    out = {"Qz9FAKEmfv10x"}
    for p in (FIX / "malformed").rglob("*"):
        if p.is_file():
            out.update(PLANT.findall(p.read_text(encoding="utf-8")))
    assert len(out) >= 12
    return out


def test_empty_home_reports_missing_and_exits_zero(tmp_path):
    for d in ("home", "root", "proj"):
        (tmp_path / d).mkdir()
    r = run_tool("scan.py", ["--home", str(tmp_path / "home"), "--root", str(tmp_path / "root"), "--platform", "linux",
                             "--project", str(tmp_path / "proj"), "--json"], {"PATH": str(tmp_path)}, tmp_path)
    assert r.returncode == 0, r.stderr
    inv = json.loads(r.stdout)
    assert inv["totals"]["findings"] == 0
    assert {s["status"] for s in inv["sources"]} <= {"missing", "found", "skipped"}


def test_key_shaped_names_are_hidden(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    shaped = "gh" + "p_" + "A1b2C3d4" * 5  # built at run time so no key shape is committed
    (home / ".cursor").mkdir()
    (home / ".cursor" / "mcp.json").write_text(json.dumps({"mcpServers": {shaped: {"url": f"https://{shaped.lower()}.example.com/x"}}}))
    (tmp_path / "root").mkdir()
    r = run_tool("scan.py", ["--home", str(home), "--root", str(tmp_path / "root"), "--platform", "linux",
                             "--project", str(tmp_path), "--only", "cursor", "--json"], {"PATH": ""}, tmp_path)
    assert r.returncode == 0, r.stderr
    f = json.loads(r.stdout)["findings"][0]
    assert f["name"].startswith("[hidden-") and f["host"].startswith("[hidden-")
    assert "A1b2C3d4" not in r.stdout


def test_platform_paths_for_macos_and_windows(tmp_path):
    home = tmp_path / "home"
    mac = home / "Library" / "Application Support" / "Claude"
    mac.mkdir(parents=True)
    (mac / "claude_desktop_config.json").write_text(json.dumps({"mcpServers": {"mac-one": {"command": "x"}}}))
    win = tmp_path / "appdata" / "Claude"
    win.mkdir(parents=True)
    (win / "claude_desktop_config.json").write_text(json.dumps({"mcpServers": {"win-one": {"command": "x"}}}))
    (tmp_path / "root").mkdir()
    base = ["--home", str(home), "--root", str(tmp_path / "root"), "--project", str(tmp_path), "--only", "claude-desktop", "--json"]
    r = run_tool("scan.py", base + ["--platform", "darwin"], {"PATH": ""}, tmp_path)
    assert [f["name"] for f in json.loads(r.stdout)["findings"]] == ["mac-one"]
    r = run_tool("scan.py", base + ["--platform", "windows"], {"PATH": "", "APPDATA": str(tmp_path / "appdata")}, tmp_path)
    assert [f["name"] for f in json.loads(r.stdout)["findings"]] == ["win-one"]


def test_plugin_failure_is_contained(monkeypatch, tmp_path):
    import scan as scan_cli
    from kit.core import Ctx
    from kit.plugins import Plugin

    def boom(ctx, col):
        raise RuntimeError("Qz9FAKEcrv01x would be quoted here")

    p = Plugin("boom", "Boom", "harness", lambda ctx: [], boom)
    results = scan_cli.run(Ctx(home=tmp_path, env={}), [p])
    col = results[0][1]
    assert col.looked[-1]["status"] == "error"
    assert all("Qz9FAKE" not in n for n in col.notes)


def test_unknown_source_id_is_refused(tmp_path):
    r = run_tool("scan.py", ["--home", str(tmp_path), "--only", "nope"], {"PATH": ""}, tmp_path)
    assert r.returncode != 0 and "unknown source id" in r.stderr


def test_tilde_means_the_scan_home_never_the_real_one(tmp_path):
    home = tmp_path / "home"
    (home / "proj").mkdir(parents=True)
    (home / "proj" / ".mcp.json").write_text(json.dumps({"mcpServers": {"from-tilde-project": {"command": "x"}}}))
    (home / ".claude.json").write_text(json.dumps({"projects": {"~/proj": {}}}))
    (home / "kube").mkdir()
    (home / "kube" / "conf").write_text("users:\n  - name: tilde-user\n    user: {token: abc}\n")
    (tmp_path / "root").mkdir()
    env = {"PATH": "", "KUBECONFIG": "~/kube/conf"}
    r = run_tool("scan.py", ["--home", str(home), "--root", str(tmp_path / "root"), "--platform", "linux",
                             "--project", str(tmp_path / "root"), "--only", "claude-code,kube", "--json"], env, tmp_path)
    names = {f["name"] for f in json.loads(r.stdout)["findings"]}
    assert {"from-tilde-project", "tilde-user"} <= names


def test_list_sources_names_every_plugin(full_tree):
    from kit.plugins import all_plugins
    r = run_tool("scan.py", scan_args(full_tree, "--list-sources"), {"PATH": ""}, Path(full_tree["home"]))
    for p in all_plugins():
        assert p.id in r.stdout
