"""The helper tools: keyshape.py, entry.py, add_entry.py, move_field.py and sync.py --force."""

from __future__ import annotations

import io
import json
import os
import sys
import tomllib
from pathlib import Path

import entry as entry_cli
import keyshape as keyshape_cli
import pytest
import yaml
from conftest import FIX, assert_no_leak, planted_values

SHAPED = "gh" + "p_" + "Zz9" * 12  # a key shape built at run time, never committed


def run_keyshape(*paths):
    out = io.StringIO()
    old, sys.stdout = sys.stdout, out
    try:
        code = keyshape_cli.main([str(p) for p in paths])
    finally:
        sys.stdout = old
    return code, out.getvalue()


def test_keyshape_reads_utf16_and_latin1(tmp_path):
    (tmp_path / "u16.txt").write_bytes(("token note " + SHAPED + "\n").encode("utf-16"))
    (tmp_path / "l1.txt").write_bytes(("caf\xe9 " + SHAPED + "\n").encode("latin-1"))
    code, text = run_keyshape(tmp_path)
    assert code == 1 and "u16.txt:1: github-token" in text and "l1.txt:1: github-token" in text
    assert SHAPED not in text


def test_keyshape_reports_skipped_files_and_fails(tmp_path):
    (tmp_path / "clean.txt").write_text("nothing here\n")
    os.symlink(tmp_path / "clean.txt", tmp_path / "link.txt")
    big = tmp_path / "big.bin"
    with big.open("wb") as handle:
        handle.truncate(6_000_000)
    code, text = run_keyshape(tmp_path)
    assert code == 1 and "skipped" in text and "link.txt" in text and "big.bin" in text
    code, text = run_keyshape(tmp_path / "clean.txt")
    assert code == 0


@pytest.mark.parametrize("args", [
    ["--harness", "codex", "--url", "https://door.example.com/mcp'; rm -rf ~"],
    ["--harness", "codex", "--url", "https://user:pw@door.example.com/mcp"],
    ["--harness", "codex", "--url", "ftp://door.example.com/mcp"],
    ["--harness", "codex", "--name", "door name"],
    ["--harness", "codex", "--key-env", "door-key"],
])
def test_entry_refuses_unsafe_input(args, capsys):
    assert entry_cli.main(args) == 2


HOME_FIX = FIX / "full" / "home"
CASES = {  # harness: (fixture config, top key, existing entry that must survive)
    "cursor": (".cursor/mcp.json", "mcpServers", "design"),
    "windsurf": (".codeium/windsurf/mcp_config.json", "mcpServers", "tickets"),
    "openmausbot": (".openmausbot/config.json", "mcpServers", "door"),
    "cline": (".config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json", "mcpServers", "browser-lane"),
    "codex": (".codex/config.toml", "mcp_servers", "issues"),
    "hermes": (".hermes/config.yaml", "mcp_servers", "kb"),
    "goose": (".config/goose/config.yaml", "extensions", "calendar"),
}
PLAIN = {"openmausbot", "cline", "goose", "zed"}


def _parse(path: Path, fmt: str):
    text = path.read_text(encoding="utf-8")
    return tomllib.loads(text) if fmt == "toml" else yaml.safe_load(text) if fmt == "yaml" else json.loads(text)


def _add(tmp_path, harness, cfg, *more, name="uc-door"):
    import add_entry
    out = io.StringIO()
    code = add_entry.main(["--harness", harness, "--config", str(cfg), "--url", "https://door.tailnet-name.ts.net/mcp",
                           "--name", name, "--backup-dir", str(tmp_path / "run" / "backup"), *more], out=out)
    return code, out.getvalue()


def _keyfile(tmp_path):
    k = tmp_path / "harness.key"
    k.write_text("Qz9FAKEaev01x\n")
    k.chmod(0o600)
    return k


@pytest.mark.parametrize("harness", sorted(CASES))
def test_add_entry_backs_up_adds_and_never_prints_the_config(tmp_path, harness):
    rel, top, keep = CASES[harness]
    cfg = tmp_path / "cfg" / Path(rel).name
    cfg.parent.mkdir()
    original = (HOME_FIX / rel).read_bytes()
    cfg.write_bytes(original)
    fmt = "toml" if cfg.suffix == ".toml" else "yaml" if cfg.suffix == ".yaml" else "json"
    extra = ["--key-file", str(_keyfile(tmp_path))] if harness in PLAIN else ["--key-env", "UC_DOOR_KEY"]
    code, text = _add(tmp_path, harness, cfg, *extra)
    assert code == 0, text
    data = _parse(cfg, fmt)
    assert "uc-door" in data[top] and keep in data[top]
    backups = list((tmp_path / "run" / "backup").iterdir())
    assert len(backups) == 1 and backups[0].read_bytes() == original and backups[0].stat().st_mode & 0o077 == 0
    assert (tmp_path / "run" / "backup").stat().st_mode & 0o077 == 0
    assert_no_leak(text, values=planted_values() | {"Qz9FAKEaev01x"})
    if harness in PLAIN:
        assert "Qz9FAKEaev01x" in json.dumps(data[top]["uc-door"])  # written into the config in-process only


def test_add_entry_keeps_yaml_comments(tmp_path):
    cfg = tmp_path / "cfg" / "config.yaml"
    cfg.parent.mkdir()
    cfg.write_text("# my hermes settings\nmodel: demo\nmcp_servers:\n    kb:\n        url: https://kb.example.com/mcp\n# end\n")
    code, text = _add(tmp_path, "hermes", cfg, "--key-env", "UC_DOOR_KEY")
    assert code == 0, text
    new = cfg.read_text()
    assert "# my hermes settings" in new and "# end" in new
    assert set(yaml.safe_load(new)["mcp_servers"]) == {"kb", "uc-door"}


@pytest.mark.parametrize("why,setup,args", [
    ("backup beside the config", None, ["--backup-dir-is-config-dir"]),
    ("existing name", "cursor-existing", []),
    ("comments without permission", "vscode-comments", []),
    ("does not parse", "broken", []),
    ("plain-key harness without a key file", "zed-no-key", []),
])
def test_add_entry_refuses_and_changes_nothing(tmp_path, why, setup, args):
    import add_entry
    cfg = tmp_path / "cfg" / "mcp.json"
    cfg.parent.mkdir()
    harness, extra = "cursor", ["--key-env", "UC_DOOR_KEY"]
    if setup == "vscode-comments":
        harness = "vscode"
        cfg.write_bytes((HOME_FIX / ".config/Code/User/mcp.json").read_bytes())
    elif setup == "broken":
        cfg.write_text('{"mcpServers": {"x": ')
    elif setup == "zed-no-key":
        harness, extra = "zed", []
        cfg.write_text('{"context_servers": {}}')
    else:
        cfg.write_bytes((HOME_FIX / ".cursor/mcp.json").read_bytes())
    before = cfg.read_bytes()
    name = "design" if setup == "cursor-existing" else "uc-door"
    backup = str(cfg.parent) if args == ["--backup-dir-is-config-dir"] else str(tmp_path / "run" / "backup")
    out = io.StringIO()
    code = add_entry.main(["--harness", harness, "--config", str(cfg), "--url", "https://door.example.com/mcp", "--name", name,
                           "--backup-dir", backup, *extra], out=out)
    assert code == 2, why
    assert cfg.read_bytes() == before
    assert not (tmp_path / "run").exists()
    assert_no_leak(out.getvalue(), values=planted_values())


def test_add_entry_makes_a_file_owner_only_once_it_holds_a_door_key(tmp_path):
    cfg = tmp_path / "cfg" / "mcp.json"
    cfg.parent.mkdir()
    cfg.write_bytes((HOME_FIX / ".cursor/mcp.json").read_bytes())
    cfg.chmod(0o644)
    code, text = _add(tmp_path, "cursor", cfg, "--key-file", str(_keyfile(tmp_path)))
    assert code == 0, text
    assert cfg.stat().st_mode & 0o077 == 0
    assert_no_leak(text, values=planted_values() | {"Qz9FAKEaev01x"})


def test_add_entry_jsonc_rewrite_only_with_permission(tmp_path):
    cfg = tmp_path / "cfg" / "mcp.json"
    cfg.parent.mkdir()
    cfg.write_bytes((HOME_FIX / ".config/Code/User/mcp.json").read_bytes())
    code, text = _add(tmp_path, "vscode", cfg, "--allow-rewrite")
    assert code == 0, text
    data = json.loads(cfg.read_text())
    assert {"crm", "sheets", "uc-door"} <= set(data["servers"]) and any(i["id"] == "uc-door-key" for i in data["inputs"])


def test_add_entry_follows_a_dotfile_link_and_keeps_it(tmp_path):
    real = tmp_path / "dotfiles" / "mcp.json"
    real.parent.mkdir()
    real.write_bytes((HOME_FIX / ".cursor/mcp.json").read_bytes())
    link = tmp_path / "cfg" / "mcp.json"
    link.parent.mkdir()
    os.symlink(real, link)
    code, text = _add(tmp_path, "cursor", link, "--key-env", "UC_DOOR_KEY")
    assert code == 0, text
    assert link.is_symlink() and "uc-door" in json.loads(real.read_text())["mcpServers"]


def test_add_entry_dry_run_writes_nothing(tmp_path):
    cfg = tmp_path / "cfg" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_bytes((HOME_FIX / ".codex/config.toml").read_bytes())
    before = cfg.read_bytes()
    code, text = _add(tmp_path, "codex", cfg, "--key-env", "UC_DOOR_KEY", "--dry-run")
    assert code == 0 and cfg.read_bytes() == before and not (tmp_path / "run").exists()


def _fake_store(tmp_path, name="secret-tool"):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    tool = bin_dir / name
    tool.write_text(f"#!{sys.executable}\nimport os, sys\nopen(os.environ['FAKE_STORE_OUT'], 'w').write(sys.stdin.read())\n"
                    "open(os.environ['FAKE_STORE_OUT'] + '.argv', 'w').write(' '.join(sys.argv[1:]))\n")
    tool.chmod(0o755)
    return bin_dir


def _move(tmp_path, *args):
    import move_field
    store = tmp_path / "stored"
    env = {"PATH": str(_fake_store(tmp_path)), "FAKE_STORE_OUT": str(store)}
    out = io.StringIO()
    code = move_field.main(list(args), env=env, out=out)
    return code, out.getvalue(), store


def test_move_field_moves_one_value_without_printing_it(tmp_path):
    cfg = tmp_path / "claude.json"
    cfg.write_bytes((HOME_FIX / ".claude.json").read_bytes())
    code, text, store = _move(tmp_path, "--file", str(cfg), "--field", "mcpServers.tracker.headers.Authorization",
                              "--strip-bearer", "--to", "secret-service", "--entry", "work/tracker/read-key")
    assert code == 0, text
    assert store.read_text() == "Qz9FAKEccv01x"
    assert "work/tracker/read-key" in (tmp_path / "stored.argv").read_text() and "Qz9FAKE" not in (tmp_path / "stored.argv").read_text()
    assert_no_leak(text, values=planted_values())


@pytest.mark.parametrize("field,why", [
    ("mcpServers.tracker.headers", "not one text value"),
    ("mcpServers.nope.headers.Authorization", "no such field"),
])
def test_move_field_refuses_anything_but_one_text_value(tmp_path, field, why):
    cfg = tmp_path / "claude.json"
    cfg.write_bytes((HOME_FIX / ".claude.json").read_bytes())
    code, text, store = _move(tmp_path, "--file", str(cfg), "--field", field, "--to", "secret-service", "--entry", "e")
    assert code == 2 and not store.exists(), why
    assert_no_leak(text, values=planted_values())


def test_move_field_refuses_stores_that_need_the_value_on_a_command_line(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("API_KEY=Qz9FAKEmvv01x\n")
    code, text, store = _move(tmp_path, "--file", str(env_file), "--field", "API_KEY", "--to", "keychain", "--entry", "e")
    assert code == 2 and "Keychain" in text and not store.exists()
    code, text, store = _move(tmp_path, "--file", str(env_file), "--field", "API_KEY", "--to", "secret-service", "--entry", "e", "--dry-run")
    assert code == 0 and not store.exists() and "Qz9FAKEmvv01x" not in text


def test_sync_force_moves_the_old_folder_aside(tmp_path, capsys):
    import sync
    from conftest import ROOT
    target = tmp_path / "skills"
    old = target / "handle-secrets"
    old.mkdir(parents=True)
    (old / "SKILL.md").write_text("mine\n")
    sync.main([str(ROOT), "--target", str(target), "--include-draft", "--force"])
    backups = [p for p in target.iterdir() if p.name.startswith("handle-secrets.bak-")]
    assert len(backups) == 1 and (backups[0] / "SKILL.md").read_text() == "mine\n"
    assert (target / "handle-secrets").is_symlink()


def test_gotchas_names_derive_the_oddboro_id_and_toolsdiff_flags_writers(tmp_path):
    import gotchas
    names = tmp_path / "door-tools.json"
    names.write_text(json.dumps(["tracker__list_projects_for_workspace"]))
    out = io.StringIO()
    url = "https://a-very-long-workstation-name-for-the-office.tailnet-name.ts.net/mcp"
    assert gotchas.main(["names", "--harness", "oddboro", "--url", url, "--tools", str(names), "--json"], out=out) == 1
    out = io.StringIO()
    assert gotchas.main(["names", "--harness", "oddboro", "--url", "https://door.example.com/mcp", "--tools", str(names)], out=out) == 0
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    old.write_text(json.dumps([{"name": "guide", "annotations": {"readOnlyHint": True}}]))
    new.write_text(json.dumps([{"name": "guide", "annotations": {"readOnlyHint": True}}, {"name": "mail__send"}]))
    out = io.StringIO()
    assert gotchas.main(["toolsdiff", "--old", str(old), "--new", str(new)], out=out) == 1 and "mail__send" in out.getvalue()


def test_entry_shell_line_is_quoted(capsys):
    assert entry_cli.main(["--harness", "claude-code", "--url", "https://door.example.com/mcp?x=1&y=2"]) == 0
    text = capsys.readouterr().out
    line = next(ln for ln in text.splitlines() if ln.startswith("claude mcp add-json"))
    import shlex
    words = shlex.split(line)
    assert words[:5] == ["claude", "mcp", "add-json", "--scope", "user"] and json.loads(words[6])["url"].endswith("y=2")
