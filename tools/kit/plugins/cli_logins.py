"""CLI credential stores: presence, profile and host names, and where each login lives."""

from __future__ import annotations

import re
from pathlib import Path

from kit.core import Collector, Ctx, Finding, bounded_glob, load, read_text
from kit.plugins import Plugin, shown

MOVE = ("A token sits in a plain file. Prefer the CLI's keyring option, or a scoped token kept in the vault "
        "that you store yourself; then remove it from this file.")
KEEP = "The CLI's own sign-in. Leave it there; for the door, create a scoped token or service account for that service."


def _add(ctx: Ctx, col: Collector, path: Path, name: str, where: list[str], auth: str, detail: str = "") -> None:
    plain = bool(set(where) & {"file", "inline"})
    col.add(Finding(col.source, shown(ctx, path), "cli-login", ctx.redactor.name(name), key_where=where,
                    auth_kind=auth, plain_file=plain, how_to_add=MOVE if plain else KEEP, detail=detail))


# gh
def _gh(ctx: Ctx) -> Path:
    base = ctx.env_path("GH_CONFIG_DIR") or ((ctx.appdata() / "GitHub CLI") if ctx.platform == "windows" else ctx.xdg_config() / "gh")
    return base / "hosts.yml"


def scan_gh(ctx: Ctx, col: Collector) -> None:
    p = _gh(ctx)
    data = load(col, p, "yaml")
    if isinstance(data, dict):
        for host, info in sorted(data.items()):
            in_file = isinstance(info, dict) and (bool(info.get("oauth_token")) or any(
                isinstance(u, dict) and u.get("oauth_token") for u in (info.get("users") or {}).values()))
            _add(ctx, col, p, str(host), ["file"] if in_file else ["keyring"], "oauth")


# gcloud
def _gcloud(ctx: Ctx) -> Path:
    return ctx.env_path("CLOUDSDK_CONFIG") or ((ctx.appdata() / "gcloud") if ctx.platform == "windows" else ctx.xdg_config() / "gcloud")


def scan_gcloud(ctx: Ctx, col: Collector) -> None:
    base = _gcloud(ctx)
    adc = base / "application_default_credentials.json"
    data = load(col, adc, "json")
    if isinstance(data, dict):
        kind = str(data.get("type", "unknown"))
        auth = {"authorized_user": "oauth", "service_account": "service-account",
                "external_account": "service-account", "impersonated_service_account": "service-account"}.get(kind, "oauth")
        _add(ctx, col, adc, "application default credentials", ["file"], auth, detail=f"type {ctx.redactor.name(kind)}")
    for db in ("credentials.db", "access_tokens.db"):
        p = base / db
        col.look(p, "found" if p.is_file() else "missing")
        if p.is_file() and db == "credentials.db":
            _add(ctx, col, p, "gcloud user sign-ins", ["file"], "oauth")
    configs = bounded_glob(base / "configurations", "config_*", 100)
    if configs:
        col.notes.append(f"gcloud has {len(configs)} named configuration(s).")


# aws
def scan_aws(ctx: Ctx, col: Collector) -> None:
    creds = ctx.env_path("AWS_SHARED_CREDENTIALS_FILE") or ctx.home / ".aws" / "credentials"
    cp = load(col, creds, "ini")
    if cp is not None:
        for section in cp.sections():
            if cp.has_option(section, "aws_access_key_id") or cp.has_option(section, "aws_secret_access_key"):
                _add(ctx, col, creds, section, ["file"], "api-key", detail="static access key")
            elif cp.has_option(section, "credential_process"):
                _add(ctx, col, creds, section, ["helper"], "api-key", detail="credential_process")
    conf = ctx.env_path("AWS_CONFIG_FILE") or ctx.home / ".aws" / "config"
    cp = load(col, conf, "ini")
    if cp is not None:
        for section in cp.sections():
            name = re.sub(r"^profile\s+", "", section)
            if section.startswith("sso-session"):
                continue
            opts = set(cp.options(section))
            if opts & {"sso_session", "sso_start_url"}:
                _add(ctx, col, conf, name, ["oauth"], "oauth", detail="SSO sign-in (short-lived)")
            elif "credential_process" in opts:
                _add(ctx, col, conf, name, ["helper"], "api-key", detail="credential_process")
            elif "role_arn" in opts:
                _add(ctx, col, conf, name, ["helper"], "service-account", detail="assumes a role")
            elif opts & {"aws_access_key_id", "aws_secret_access_key"}:
                _add(ctx, col, conf, name, ["file"], "api-key", detail="static access key")


# azure
def scan_azure(ctx: Ctx, col: Collector) -> None:
    base = ctx.env_path("AZURE_CONFIG_DIR") or ctx.home / ".azure"
    for fname, where, auth, label in (
        ("msal_token_cache.json", ["file"], "oauth", "azure cli sign-in (plain token cache)"),
        ("msal_token_cache.bin", ["keyring"], "oauth", "azure cli sign-in (encrypted token cache)"),
        ("service_principal_entries.json", ["file"], "service-account", "azure service principal"),
    ):
        p = base / fname
        col.look(p, "found" if p.is_file() else "missing")
        if p.is_file():
            _add(ctx, col, p, label, where, auth)


# docker
def scan_docker(ctx: Ctx, col: Collector) -> None:
    p = (ctx.env_path("DOCKER_CONFIG") or ctx.home / ".docker") / "config.json"
    data = load(col, p, "json")
    if not isinstance(data, dict):
        return
    helpers = data.get("credHelpers") if isinstance(data.get("credHelpers"), dict) else {}
    store = data.get("credsStore")
    auths = data.get("auths") if isinstance(data.get("auths"), dict) else {}
    for reg in sorted(set(auths) | set(helpers)):
        entry = auths.get(reg) if isinstance(auths.get(reg), dict) else {}
        if entry.get("auth") or entry.get("identitytoken") or entry.get("password"):
            _add(ctx, col, p, reg, ["file"], "password", detail="registry login in config.json")
        elif reg in helpers or store:
            _add(ctx, col, p, reg, ["helper"], "password", detail="credential helper")


# kube
def scan_kube(ctx: Ctx, col: Collector) -> None:
    sep = ";" if ctx.platform == "windows" else ":"
    raw = ctx.env.get("KUBECONFIG", "").strip()
    paths = [ctx.expand(x) for x in raw.split(sep) if x] if raw else [ctx.home / ".kube" / "config"]
    for p in paths:
        data = load(col, p, "yaml")
        if not isinstance(data, dict):
            continue
        for u in data.get("users") or []:
            if not isinstance(u, dict):
                continue
            user = u.get("user") if isinstance(u.get("user"), dict) else {}
            if "exec" in user:
                cmd = user["exec"].get("command", "") if isinstance(user["exec"], dict) else ""
                _add(ctx, col, p, str(u.get("name", "user")), ["helper"], "oauth", detail=f"exec {ctx.redactor.command(cmd or 'helper')}")
            elif "auth-provider" in user:
                _add(ctx, col, p, str(u.get("name", "user")), ["file", "oauth"], "oauth", detail="auth-provider")
            elif user.get("token") or user.get("client-key-data") or user.get("password"):
                _add(ctx, col, p, str(u.get("name", "user")), ["file"], "password" if user.get("password") else "api-key")
            elif user.get("tokenFile") or user.get("client-key"):
                _add(ctx, col, p, str(u.get("name", "user")), ["file"], "api-key", detail="key file referenced by path")


# npm
NPM_LINE = re.compile(r"^\s*//([^/:\s]+)[^:]*:(_authToken|_auth|_password)\s*=\s*(.*)$")


def scan_npm(ctx: Ctx, col: Collector) -> None:
    for p in [ctx.home / ".npmrc"] + [proj / ".npmrc" for proj in ctx.projects]:
        status, text = read_text(p)
        col.look(p, status)
        for line in (text or "").splitlines():
            m = NPM_LINE.match(line)
            if m:
                ref = "${" in m.group(3)
                _add(ctx, col, p, m.group(1), ["env-reference"] if ref else ["file"],
                     "password" if m.group(2) != "_authToken" else "api-key")


# pypi and pip
def scan_pypi(ctx: Ctx, col: Collector) -> None:
    p = ctx.home / ".pypirc"
    cp = load(col, p, "ini")
    if cp is not None:
        for section in cp.sections():
            if section == "distutils":
                continue
            if cp.has_option(section, "password"):
                _add(ctx, col, p, section, ["file"], "api-key", detail="upload token or password in .pypirc")
    pip_files = [ctx.xdg_config() / "pip" / "pip.conf", ctx.home / ".pip" / "pip.conf", ctx.appdata() / "pip" / "pip.ini"]
    for pf in pip_files:
        status, text = read_text(pf)
        col.look(pf, status)
        for line in (text or "").splitlines():
            m = re.match(r"^\s*(extra-)?index-url\s*=\s*(\S+)", line)
            if m and "@" in m.group(2):
                host = m.group(2).split("@", 1)[1].split("/", 1)[0]
                _add(ctx, col, pf, host, ["inline"], "password", detail="credential inside the index URL")


# netrc
def scan_netrc(ctx: Ctx, col: Collector) -> None:
    p = ctx.env_path("NETRC") or (ctx.home / ("_netrc" if ctx.platform == "windows" else ".netrc"))
    status, text = read_text(p)
    col.look(p, status)
    if text is None:
        return
    words = text.split()
    i = 0
    while i < len(words):
        w = words[i]
        if w == "machine" and i + 1 < len(words):
            _add(ctx, col, p, words[i + 1], ["file"], "password")
            i += 2
        elif w == "default":
            _add(ctx, col, p, "default", ["file"], "password")
            i += 1
        elif w == "macdef":
            while i < len(words) and words[i] != "machine":
                i += 1
        else:
            i += 1


# git credentials
def scan_git(ctx: Ctx, col: Collector) -> None:
    for p in (ctx.home / ".git-credentials", ctx.xdg_config() / "git" / "credentials"):
        status, text = read_text(p)
        col.look(p, status)
        for line in (text or "").splitlines():
            m = re.match(r"^\s*[a-z][a-z0-9+.-]*://[^@\s]*@([^/\s:]+)", line)
            if m:
                _add(ctx, col, p, m.group(1), ["file"], "password", detail="git credential store")
    for p in (ctx.home / ".gitconfig", ctx.xdg_config() / "git" / "config"):
        status, text = read_text(p)
        col.look(p, status)
        for line in (text or "").splitlines():
            m = re.match(r"^\s*helper\s*=\s*(\S+)", line)
            if m:
                helper = m.group(1).strip("\"'")
                where = ["file"] if helper.split()[0] == "store" else ["helper"]
                _add(ctx, col, p, "git credential helper", where, "password", detail=f"helper {ctx.redactor.command(helper.split()[0])}")


PLUGINS = [
    Plugin("gh", "GitHub CLI", "cli-login", lambda ctx: [ctx.show(_gh(ctx))], scan_gh),
    Plugin("gcloud", "Google Cloud CLI and application default credentials", "cli-login",
           lambda ctx: [ctx.show(_gcloud(ctx) / f) for f in ("application_default_credentials.json", "credentials.db", "configurations")], scan_gcloud),
    Plugin("aws", "AWS CLI profiles", "cli-login",
           lambda ctx: [ctx.show(ctx.env_path("AWS_SHARED_CREDENTIALS_FILE") or ctx.home / ".aws" / "credentials"),
                        ctx.show(ctx.env_path("AWS_CONFIG_FILE") or ctx.home / ".aws" / "config")], scan_aws),
    Plugin("azure", "Azure CLI", "cli-login", lambda ctx: [ctx.show(ctx.env_path("AZURE_CONFIG_DIR") or ctx.home / ".azure") + "/msal_token_cache.*, service_principal_entries.json"], scan_azure),
    Plugin("docker", "Docker registries", "cli-login", lambda ctx: [ctx.show((ctx.env_path("DOCKER_CONFIG") or ctx.home / ".docker") / "config.json")], scan_docker),
    Plugin("kube", "Kubernetes contexts", "cli-login", lambda ctx: ["$KUBECONFIG files, else " + ctx.show(ctx.home / ".kube" / "config")], scan_kube),
    Plugin("npm", "npm registries", "cli-login", lambda ctx: [ctx.show(ctx.home / ".npmrc"), "<each project>/.npmrc"], scan_npm),
    Plugin("pypi", "PyPI and pip indexes", "cli-login", lambda ctx: [ctx.show(ctx.home / ".pypirc"), ctx.show(ctx.xdg_config() / "pip" / "pip.conf")], scan_pypi),
    Plugin("netrc", "netrc machines", "cli-login", lambda ctx: [ctx.show(ctx.env_path("NETRC") or ctx.home / ".netrc")], scan_netrc),
    Plugin("git-credentials", "Git credential store and helper", "cli-login",
           lambda ctx: [ctx.show(ctx.home / ".git-credentials"), ctx.show(ctx.home / ".gitconfig") + " (helper name)"], scan_git),
]
