from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from universal_connector.manifest import ManifestError, load_manifest

ROOT = Path(__file__).resolve().parents[1]
OK = ROOT / "tests" / "fixtures" / "manifest_ok"


def ok_data() -> tuple[dict, dict]:
    connector = yaml.safe_load((OK / "connector.yaml").read_text())
    agents = yaml.safe_load((OK / "agents.yaml").read_text())
    return connector, agents


def write(directory: Path, connector: dict, agents: dict) -> Path:
    (directory / "connector.yaml").write_text(yaml.safe_dump(connector, sort_keys=False))
    (directory / "agents.yaml").write_text(yaml.safe_dump(agents, sort_keys=False))
    return directory


def problems_for(tmp_path: Path, connector: dict, agents: dict) -> list[str]:
    with pytest.raises(ManifestError) as err:
        load_manifest(write(tmp_path, connector, agents))
    return err.value.problems


def test_loads_ok():
    manifest = load_manifest(OK)
    assert len(manifest.connections) == 2
    assert len(manifest.agents) == 2
    assert manifest.connection("brain_work").tools[0].pinned is True
    assert manifest.connection("nope") is None
    assert manifest.agent("beta").name == "beta"


def test_duplicate_connection_name(tmp_path):
    connector, agents = ok_data()
    connector["connections"][1]["name"] = "brain_work"
    problems = problems_for(tmp_path, connector, agents)
    assert len(problems) == 1
    assert "duplicate connection name" in problems[0]


def test_connection_name_with_change_word(tmp_path):
    connector, agents = ok_data()
    connector["connections"][1]["name"] = "mail_send"
    problems = problems_for(tmp_path, connector, agents)
    assert len(problems) == 1
    assert "name contains a change word (send)" in problems[0]


@pytest.mark.parametrize(
    "bad",
    ["", "bad name", "a/b", "a.b", "files/upload", "sendé", "1abc", "-abc", "_abc", "x" * 65, "a\n"],
)
def test_tool_name_pattern_enforced(tmp_path, bad):
    connector, agents = ok_data()
    connector["connections"][0]["tools"][0]["name"] = bad
    problems = problems_for(tmp_path, connector, agents)
    assert any("name must match" in p for p in problems), problems


def test_tool_name_pattern_allows_valid_names(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["tools"][0]["name"] = "A" + "b_c-9" * 12 + "z"  # 62 characters
    load_manifest(write(tmp_path, connector, agents))
    connector["connections"][0]["tools"][0]["name"] = "t" * 64
    load_manifest(write(tmp_path, connector, agents))


def test_empty_scopes(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["scopes"] = []
    agents["agents"][0]["scopes"] = []
    problems = problems_for(tmp_path, connector, agents)
    assert len(problems) == 2
    assert all("scopes" in p for p in problems)


def test_duplicate_tool_name(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["tools"][1]["name"] = "search_thoughts"
    problems = problems_for(tmp_path, connector, agents)
    assert len(problems) == 1
    assert "duplicate tool name" in problems[0]


def test_restricted_agent_rejected(tmp_path):
    connector, agents = ok_data()
    agents["agents"][0]["scopes"] = ["work", "restricted"]
    problems = problems_for(tmp_path, connector, agents)
    assert len(problems) == 1
    assert "restricted cannot be granted in this version" in problems[0]


def test_the_old_scope_name_is_unknown(tmp_path):
    connector, agents = ok_data()
    agents["agents"][0]["scopes"] = ["cli" + "nic"]
    problems = problems_for(tmp_path, connector, agents)
    assert any("scopes" in p for p in problems)


def test_too_many_pinned(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["tools"] = [
        {"name": f"tool_{i}", "tier": "green", "pinned": True} for i in range(21)
    ]
    problems = problems_for(tmp_path, connector, agents)
    assert len(problems) == 1
    assert "pinned" in problems[0]


def test_twenty_pinned_is_fine(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["tools"] = [
        {"name": f"tool_{i}", "tier": "green", "pinned": True} for i in range(20)
    ]
    load_manifest(write(tmp_path, connector, agents))


def test_secret_pointer_shape(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["auth"]["secret"] = "not a pointer!"
    connector["connections"][1]["auth"]["token_secret"] = "also bad?"
    problems = problems_for(tmp_path, connector, agents)
    assert len(problems) == 2
    assert any("auth.secret" in p for p in problems)
    assert any("auth.token_secret" in p for p in problems)
    assert not any("not a pointer!" in p or "also bad?" in p for p in problems)


def test_planted_secret_rejected(tmp_path):
    planted = "sk-" + "q" * 30
    connector, agents = ok_data()
    connector["connections"][0]["options"] = {"headers": {"x-api-key": planted}}
    problems = problems_for(tmp_path, connector, agents)
    assert any("openai-style-key" in p for p in problems)
    assert not any(planted in p for p in problems)


def test_header_auth_needs_secret_and_header(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["auth"] = {"type": "header"}
    connector["connections"][1]["auth"] = {"type": "bearer"}
    problems = problems_for(tmp_path, connector, agents)
    assert len(problems) == 3
    assert sum("brain_work" in p and "auth.secret" in p for p in problems) == 1
    assert sum("brain_work" in p and "auth.header" in p for p in problems) == 1
    assert sum("home_brain" in p and "auth.secret" in p for p in problems) == 1


def test_all_problems_reported_together(tmp_path):
    connector, agents = ok_data()
    connector["connections"][1]["name"] = "brain_work"
    agents["agents"][0]["scopes"] = ["restricted"]
    agents["agents"][1]["name"] = "Beta Bad"
    problems = problems_for(tmp_path, connector, agents)
    assert len(problems) == 3


def test_bad_names_rejected(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["name"] = "brain-work"
    agents["agents"][0]["name"] = "alpha_1"
    problems = problems_for(tmp_path, connector, agents)
    assert len(problems) == 2


def test_schema_errors_are_problems_without_values(tmp_path):
    planted = "sk-" + "w" * 30
    connector, agents = ok_data()
    connector["connections"][0]["tools"][0]["tier"] = planted
    problems = problems_for(tmp_path, connector, agents)
    assert any("tier" in p for p in problems)
    assert not any(planted in p for p in problems)


def test_missing_file_is_a_problem(tmp_path):
    connector, _ = ok_data()
    (tmp_path / "connector.yaml").write_text(yaml.safe_dump(connector))
    with pytest.raises(ManifestError) as err:
        load_manifest(tmp_path)
    assert any("agents.yaml" in p for p in err.value.problems)


def test_trailing_newline_in_connection_name_rejected(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["name"] = "brain_work\n"
    problems = problems_for(tmp_path, connector, agents)
    assert any("connection" in p and "name must match" in p for p in problems)


def test_trailing_newline_in_agent_name_rejected(tmp_path):
    connector, agents = ok_data()
    agents["agents"][0]["name"] = "alpha\n"
    problems = problems_for(tmp_path, connector, agents)
    assert any("agent" in p and "name must match" in p for p in problems)


def test_trailing_newline_in_secret_pointer_rejected(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["auth"]["secret"] = "connector/brain/work-key\n"
    problems = problems_for(tmp_path, connector, agents)
    assert any("auth.secret is not a vault entry name" in p for p in problems)


def _upstream_problems(tmp_path, upstream, kind=None):
    connector, agents = ok_data()
    connector["connections"][0]["upstream"] = upstream
    if kind:
        connector["connections"][0]["kind"] = kind
    return problems_for(tmp_path, connector, agents)


def test_upstream_with_userinfo_rejected(tmp_path):
    for url in ("https://name:word@example.invalid/mcp", "https://name@example.invalid/mcp"):
        problems = _upstream_problems(tmp_path, url)
        assert any("upstream" in p for p in problems)
        assert not any("name:word" in p or "name@" in p for p in problems)


def test_upstream_with_query_rejected(tmp_path):
    for url in ("https://example.invalid/mcp?x=1", "https://example.invalid/mcp#frag"):
        assert any("upstream" in p for p in _upstream_problems(tmp_path, url))


def test_plain_http_only_for_loopback(tmp_path):
    assert any("upstream" in p for p in _upstream_problems(tmp_path, "http://example.invalid/mcp"))
    assert any("upstream" in p for p in _upstream_problems(tmp_path, "ftp://example.invalid/mcp"))
    connector, agents = ok_data()
    for url in ("http://127.0.0.1:8765/mcp", "http://localhost/mcp", "https://example.invalid/mcp"):
        connector["connections"][0]["upstream"] = url
        load_manifest(write(tmp_path, connector, agents))


def test_stdio_upstream_must_be_absolute_path_without_spaces(tmp_path):
    for bad in ("node", "./server", "/usr/bin/my server"):
        assert any("upstream" in p for p in _upstream_problems(tmp_path, bad, "mcp-stdio"))
    connector, agents = ok_data()
    connector["connections"][0]["kind"] = "mcp-stdio"
    connector["connections"][0]["upstream"] = "/usr/local/bin/server"
    load_manifest(write(tmp_path, connector, agents))


def test_timeout_bounds(tmp_path):
    connector, agents = ok_data()
    for bad in (0, -1, 601):
        connector["connections"][0]["tools"][0]["timeout_s"] = bad
        assert any("timeout_s" in p for p in problems_for(tmp_path, connector, agents))
    for good in (1, 600):
        connector["connections"][0]["tools"][0]["timeout_s"] = good
        load_manifest(write(tmp_path, connector, agents))


def test_double_underscore_name_rejected(tmp_path):
    connector, agents = ok_data()
    for bad in ("brain__work", "ob_", "_ob", "brain_work_"):
        connector["connections"][0]["name"] = bad
        assert any("name must match" in p for p in problems_for(tmp_path, connector, agents))


def test_boolean_timeout_rejected(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["tools"][0]["timeout_s"] = True
    assert any("timeout_s" in p for p in problems_for(tmp_path, connector, agents))


def test_integer_pinned_rejected(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["tools"][0]["pinned"] = 1
    assert any("pinned" in p for p in problems_for(tmp_path, connector, agents))
    connector["connections"][0]["tools"][0]["pinned"] = True
    agents["agents"][0]["enabled"] = 0
    assert any("enabled" in p for p in problems_for(tmp_path, connector, agents))


def test_unknown_field_on_agent_rejected(tmp_path):
    connector, agents = ok_data()
    agents["agents"][0]["enable"] = False
    write(tmp_path, connector, agents)
    with pytest.raises(ManifestError) as err:
        load_manifest(tmp_path)
    assert any("agents.yaml" in p and "enable" in p for p in err.value.problems)


def test_unknown_field_on_tool_rejected(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["tools"][0]["pinnned"] = True
    assert any("pinnned" in p for p in problems_for(tmp_path, connector, agents))


def test_unknown_field_on_connection_rejected(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["scope"] = ["work"]
    assert any("connector.yaml" in p and "scope" in p for p in problems_for(tmp_path, connector, agents))


def test_unknown_field_on_auth_rejected(tmp_path):
    connector, agents = ok_data()
    connector["connections"][0]["auth"]["secrt"] = "connector/brain/work-key"
    assert any("secrt" in p for p in problems_for(tmp_path, connector, agents))


def test_unknown_top_level_key_rejected(tmp_path):
    connector, agents = ok_data()
    connector["extra"] = 1
    problems = problems_for(tmp_path, connector, agents)
    assert any("connector.yaml" in p and "unknown key" in p for p in problems)
    connector, agents = ok_data()
    agents["extra"] = 1
    problems = problems_for(tmp_path, connector, agents)
    assert any("agents.yaml" in p and "unknown key" in p for p in problems)


def test_string_enabled_rejected(tmp_path):
    connector, agents = ok_data()
    agents["agents"][0]["enabled"] = "false"
    assert any("enabled" in p for p in problems_for(tmp_path, connector, agents))


def test_string_version_rejected(tmp_path):
    connector, agents = ok_data()
    connector["version"] = "1"
    assert any("version" in p for p in problems_for(tmp_path, connector, agents))
    connector["version"] = 1
    agents["version"] = "1"
    assert any("version" in p for p in problems_for(tmp_path, connector, agents))


def test_remote_upstream_without_scheme_rejected(tmp_path):
    for bad in ("example.invalid/mcp", "//example.invalid/mcp"):
        assert any("upstream" in p for p in _upstream_problems(tmp_path, bad))


def test_upstream_without_host_rejected(tmp_path):
    for bad in ("https:///mcp", "https://:8080/mcp"):
        assert any("upstream" in p for p in _upstream_problems(tmp_path, bad))


def test_remote_kind_without_upstream_rejected(tmp_path):
    for kind in ("mcp-remote", "multica"):
        connector, agents = ok_data()
        connector["connections"][0]["kind"] = kind
        del connector["connections"][0]["upstream"]
        assert any("upstream" in p for p in problems_for(tmp_path, connector, agents))
    connector, agents = ok_data()
    connector["connections"][0]["kind"] = "mcp-stdio"
    del connector["connections"][0]["upstream"]
    assert any("upstream" in p for p in problems_for(tmp_path, connector, agents))


def test_google_kind_with_upstream_rejected(tmp_path):
    for kind in ("google", "browser", "computer"):
        assert any("upstream" in p for p in _upstream_problems(tmp_path, "https://example.invalid", kind))
    connector, agents = ok_data()
    connector["connections"][0]["kind"] = "google"
    del connector["connections"][0]["upstream"]
    load_manifest(write(tmp_path, connector, agents))


def test_example_manifest_loads(monkeypatch):
    monkeypatch.chdir(ROOT)
    manifest = load_manifest(Path("examples") / "manifest")
    assert manifest.version == 1
    assert manifest.agents == []
    kinds = {c.name: c.kind for c in manifest.connections}
    assert kinds == {
        "notes": "mcp-remote", "google_mail_work": "google", "google_calendar_work": "google",
    }  # fmt: skip
    notes = manifest.connection("notes")
    assert notes is not None and notes.auth.type == "header"  # a key-based remote MCP example
    for conn in manifest.connections:  # every address is fake, every secret a vault entry name
        assert conn.upstream is None or conn.upstream.startswith("https://notes.example.invalid/")
        assert conn.auth.secret is not None and conn.auth.secret.startswith("connector/")


def test_call_timeout_is_optional_and_bounded(tmp_path):
    connector, agents = ok_data()
    agents["agents"][0]["call_timeout_s"] = 40
    assert load_manifest(write(tmp_path, connector, agents)).agents[0].call_timeout_s == 40
    for bad in (0, 601, "40", True, 1.5):
        agents["agents"][0]["call_timeout_s"] = bad
        with pytest.raises(ManifestError):
            load_manifest(write(tmp_path, connector, agents))
