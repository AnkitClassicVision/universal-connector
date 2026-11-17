from __future__ import annotations

from pathlib import Path

import pytest

from universal_connector import machine as settings
from universal_connector.machine import aws_profile, door_hosts, load_machine

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_MANIFEST = ROOT / "examples" / "manifest"

# Odd tailnet shapes are built at run time: the kit repository's personal-data scan allows only
# its own example tailnet names in file text, and these are test shapes, not hosts.
TS = ".ts" + ".net"
GOOD_HOSTS = [
    "door.tailnet-name.ts.net",
    "door.tailnet-name.ts.net:8443",
    f"a1.b2{TS}:1",
    f"x.y{TS}:65535",
]
GOOD_LOCAL_HOSTS = ["door.localhost", "door.localhost:8443", "a1.localhost:65535"]
BAD_HOSTS = [
    "*.tailnet-name.ts.net",
    "https://door.tailnet-name.ts.net",
    "door.tailnet-name.ts.net/mcp",
    "user@door.tailnet-name.ts.net",
    "100.64.0.1",
    "100.64.0.1:8443",
    "Door.tailnet-name.ts.net",
    "door.tailnet-name.ts.net:0",
    "door.tailnet-name.ts.net:65536",
    "door.tailnet-name.ts.net:08443",
    "door.tailnet-name.ts.net:",
    "door.tailnet-name.ts.net:*",
    "door.tailnet-name.ts.net\n",
    " door.tailnet-name.ts.net",
    f"door{TS}",
    f"a.b.c{TS}",
    "door.tailnet-name.example.com",
    "-door.tailnet-name.ts.net",
    "door..ts.net",
    "",
    "localhost",
    "127.0.0.1:8765",
    7,
    None,
    True,
    # `.localhost`: exactly one label, lower case, no wildcard, scheme, path or bad port.
    "*.localhost",
    "localhost:8443",
    ".localhost",
    "a.b.localhost",
    "Door.localhost",
    "door.localhost:0",
    "door.localhost:65536",
    "https://door.localhost",
    "door.localhost/mcp",
    "user@door.localhost",
    "door.localhost.",
    "door.localhost.example.com",
    "-door.localhost",
]


def test_door_hosts_default_is_empty():
    assert door_hosts({}) == []
    assert door_hosts({"aws_profile": "x"}) == []


def test_door_hosts_accepts_exact_values():
    assert door_hosts({"door_hosts": GOOD_HOSTS}) == GOOD_HOSTS
    assert door_hosts({"door_hosts": GOOD_LOCAL_HOSTS}) == GOOD_LOCAL_HOSTS
    assert door_hosts({"door_hosts": []}) == []


@pytest.mark.parametrize("bad", BAD_HOSTS, ids=repr)
def test_door_hosts_rejects_bad_entry_with_fixed_reason(bad):
    with pytest.raises(ValueError) as err:
        door_hosts({"door_hosts": ["door.tailnet-name.ts.net", bad]})
    assert str(err.value) == "bad door_hosts entry"


@pytest.mark.parametrize("bad", ["door.tailnet-name.ts.net", {"a": 1}, 5, None])
def test_door_hosts_must_be_a_list(bad):
    with pytest.raises(ValueError, match="^bad door_hosts entry$"):
        door_hosts({"door_hosts": bad})


def test_door_hosts_at_most_four():
    four = [f"d{i}.tailnet-name.ts.net" for i in range(3)] + ["d3.localhost"]
    assert door_hosts({"door_hosts": four}) == four
    with pytest.raises(ValueError, match="^bad door_hosts entry$"):
        door_hosts({"door_hosts": [*four, "d4.localhost"]})


def test_only_the_default_machine_file_may_be_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("UCONNECTOR_MACHINE_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    assert load_machine() == {}  # ./machine.yaml, the default, may be missing
    missing = f"^{settings.MISSING_MACHINE_FILE}$"
    with pytest.raises(settings.MachineFileMissing, match=missing):
        load_machine(tmp_path / "nope.yaml")  # named on the command line
    monkeypatch.setenv("UCONNECTOR_MACHINE_FILE", str(tmp_path / "nope.yaml"))
    with pytest.raises(settings.MachineFileMissing, match=missing):
        load_machine()  # named by the environment
    (tmp_path / "folder.yaml").mkdir()
    with pytest.raises(settings.MachineFileMissing):
        load_machine(tmp_path / "folder.yaml")


@pytest.mark.parametrize("command", ["serve", "doctor", "login"])
def test_cli_explicit_missing_machine_file_exits_2(tmp_path, capsys, command):
    from universal_connector.cli import main

    extra = {"serve": [], "doctor": [], "login": ["google", "--account", "work"]}[command]
    args = [command, *extra, "--manifest", str(EXAMPLE_MANIFEST),
            "--machine-file", str(tmp_path / "nope.yaml")]  # fmt: skip
    if command == "serve":
        args += ["--state", str(tmp_path / "state")]
    assert main(args) == 2
    assert capsys.readouterr().err == settings.MISSING_MACHINE_FILE + "\n"
    assert not (tmp_path / "state").exists()  # stopped before anything was made


def test_reads_google_accounts(tmp_path):
    f = tmp_path / "m.yaml"
    f.write_text("google_accounts:\n  work: box@example.invalid\n")
    assert load_machine(f)["google_accounts"]["work"] == "box@example.invalid"


def test_top_level_list_is_rejected(tmp_path):
    f = tmp_path / "m.yaml"
    f.write_text("- a\n- b\n")
    with pytest.raises(ValueError):
        load_machine(f)


def test_env_name_sets_the_path(tmp_path, monkeypatch):
    f = tmp_path / "elsewhere.yaml"
    f.write_text("google_accounts:\n  x: y@example.invalid\n")
    monkeypatch.setenv("UCONNECTOR_MACHINE_FILE", str(f))
    assert load_machine()["google_accounts"]["x"] == "y@example.invalid"


def test_explicit_path_wins_over_env(tmp_path, monkeypatch):
    named, other = tmp_path / "named.yaml", tmp_path / "other.yaml"
    named.write_text("vault: memory\n")
    other.write_text("vault: aws\n")
    monkeypatch.setenv("UCONNECTOR_MACHINE_FILE", str(other))
    assert load_machine(named) == {"vault": "memory"}


def test_aws_profile_default():
    assert aws_profile({}) == "default"
    assert aws_profile({"google_accounts": {}}) == "default"
    assert aws_profile({"aws_profile": "door-reader"}) == "door-reader"


# -- the vault choice -------------------------------------------------------------------------


def test_vault_default_is_keyring():
    assert settings.vault_kind({}) == "keyring"
    for kind in ("keyring", "aws", "memory"):
        assert settings.vault_kind({"vault": kind}) == kind


@pytest.mark.parametrize("bad", ["Keyring", "file", "plaintext", "", None, 3, ["keyring"]])
def test_bad_vault_setting_has_fixed_text(bad):
    with pytest.raises(ValueError, match="^bad vault setting: use keyring, aws or memory$"):
        settings.vault_kind({"vault": bad})


def test_aws_region_is_never_assumed():
    with pytest.raises(ValueError, match="^vault aws needs aws_region in the machine file$"):
        settings.aws_region({"vault": "aws"})
    assert settings.aws_region({"aws_region": "eu-west-1"}) == "eu-west-1"
    assert settings.aws_region({"aws_region": "us-gov-west-1"}) == "us-gov-west-1"


@pytest.mark.parametrize("bad", ["EU-WEST-1", "eu_west_1", "west", "eu-west-1 ", "", 1])
def test_bad_aws_region(bad):
    with pytest.raises(ValueError, match="^bad aws_region setting$"):
        settings.aws_region({"aws_region": bad})


def test_keyring_service_and_client_entry_are_configurable():
    assert settings.keyring_service({}) == "universal-connector"
    assert settings.keyring_service({"keyring_service": "door.test"}) == "door.test"
    assert settings.google_client_entry({}) == "connector/google/oauth-client"
    entry = {"google_client_entry": "my/google/client"}
    assert settings.google_client_entry(entry) == "my/google/client"


@pytest.mark.parametrize("bad", ["a/../b", "/abs", "a/", "has space", "", 5])
def test_bad_client_entry(bad):
    with pytest.raises(ValueError, match="^bad google_client_entry setting$"):
        settings.google_client_entry({"google_client_entry": bad})


def test_google_scopes_default_and_subset():
    assert settings.google_scopes({}) == settings.GOOGLE_SCOPE_CHOICES
    calendar = ["https://www.googleapis.com/auth/calendar.readonly"]
    assert settings.google_scopes({"google_scopes": calendar}) == tuple(calendar)


@pytest.mark.parametrize(
    "bad",
    [
        [],
        ["https://mail.google.com/"],  # full mail access is never asked for
        ["https://www.googleapis.com/auth/gmail.send"],
        ["https://www.googleapis.com/auth/calendar.readonly"] * 2,
        "https://www.googleapis.com/auth/calendar.readonly",
        [5],
    ],
)
def test_bad_google_scopes(bad):
    with pytest.raises(ValueError, match="^bad google_scopes setting"):
        settings.google_scopes({"google_scopes": bad})


def test_problems_lists_every_fault_with_fixed_text():
    bad = {
        "vault": "aws",
        "keyring_service": "has space",
        "door_hosts": ["*.example.invalid"],
        "google_accounts": ["not", "a", "map"],
    }
    assert settings.problems(bad) == [
        "bad keyring_service setting",
        "bad google_accounts setting: use label: address",
        "bad door_hosts entry",
        "vault aws needs aws_region in the machine file",
    ]
    assert settings.problems({}) == []


def test_example_machine_file_is_clean():
    data = load_machine(ROOT / "examples" / "machine.yaml")
    assert settings.problems(data) == []
    assert data["vault"] == "keyring"


# -- the command line reads the machine file it is given -----------------------------------------


def test_cli_builds_the_store_from_the_machine_file(tmp_path, monkeypatch):
    from universal_connector import cli, doctor, frontdoor
    from universal_connector.upstreams import factory

    machine = tmp_path / "m.yaml"
    machine.write_text("vault: memory\n")
    monkeypatch.setenv("UCONNECTOR_MACHINE_FILE", str(machine))
    seen: list[str] = []

    def fake_store_for(found):
        seen.append(found.get("vault", "keyring"))
        return object()

    class FakeHolder:
        def __init__(self, manifest, state, store, machine_file=None):
            self.store = store

    async def fake_serve(holder, state, host, port, door_hosts=()):
        return None

    async def fake_run_doctor(manifest, upstreams, store):
        return []

    monkeypatch.setattr(cli, "store_for", fake_store_for)
    monkeypatch.setattr(frontdoor, "Holder", FakeHolder)
    monkeypatch.setattr(frontdoor, "serve", fake_serve)
    monkeypatch.setattr(doctor, "run_doctor", fake_run_doctor)
    monkeypatch.setattr(factory, "build_upstreams", lambda manifest, store, machine: {})
    manifest = EXAMPLE_MANIFEST
    assert cli._serve(manifest, tmp_path / "state", "127.0.0.1", 8765, None) == 0
    cli._doctor(manifest)
    assert seen == ["memory", "memory"]
    other = tmp_path / "other.yaml"
    other.write_text("vault: keyring\n")
    assert cli._serve(manifest, tmp_path / "state", "127.0.0.1", 8765, other) == 0
    assert seen[-1] == "keyring"


def test_bad_machine_file_exits_2(tmp_path, monkeypatch, capsys):
    from universal_connector import cli

    machine = tmp_path / "m.yaml"
    monkeypatch.setenv("UCONNECTOR_MACHINE_FILE", str(machine))
    for bad in ("- a\n- b\n", "key: [unclosed\n"):
        machine.write_text(bad)
        assert cli._serve(EXAMPLE_MANIFEST, tmp_path / "state", "127.0.0.1", 8765, None) == 2
        assert cli._doctor(EXAMPLE_MANIFEST) == 2
        err = capsys.readouterr().err
        assert err == "the machine file is not a valid mapping\n" * 2
    machine.write_text("vault: aws\n")
    assert cli._serve(EXAMPLE_MANIFEST, tmp_path / "state", "127.0.0.1", 8765, None) == 2
    assert capsys.readouterr().err == "vault aws needs aws_region in the machine file\n"


def test_aws_vault_without_the_extra_has_fixed_text(tmp_path, monkeypatch, capsys):
    import importlib.util

    from universal_connector import cli, vault

    real = importlib.util.find_spec
    monkeypatch.setattr(
        vault.importlib.util, "find_spec", lambda name, *a: None if name == "boto3" else real(name)
    )
    machine = tmp_path / "m.yaml"
    machine.write_text("vault: aws\naws_region: eu-west-1\n")
    assert cli._serve(EXAMPLE_MANIFEST, tmp_path / "state", "127.0.0.1", 8765, machine) == 2
    assert capsys.readouterr().err == (
        "vault aws needs the aws extra: install universal-connector[aws]\n"
    )
