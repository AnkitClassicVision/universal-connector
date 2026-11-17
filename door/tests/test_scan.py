import pytest

from universal_connector.scan import find_secrets

# Every fake is built at run time, so no line of this file has a key shape itself: the repo-wide
# scans (this door's `check` and the kit's keyshape) then need no allowance for it.
HITS = {
    "aws-access-key": "id AK" + "IAABCDEFGHIJKLMNOP end",
    "connector-key": "pc_" + "a" * 43,
    "openai-style-key": "sk-" + "b" * 24,
    "github-token": "ghp_" + "c" * 36,
    "slack-token": "xo" + "xb-1234567890-abcdef",
    "google-access-token": "ya29." + "d" * 30,
    "google-refresh-token": "1//" + "e" * 30,
    "jwt": "ey" + "JhbGciOiJI." + "ey" + "JzdWIiOiIx.c2lnbmF0dXJl",
    "private-key-block": "-----BEGIN RSA " + "PRIVATE KEY-----",
    "assigned-secret": 'x-brain-key: "' + "f" * 32 + '"',
    "long-hex": "0" * 40,
    "bearer-value": "Authorization: bEaReR " + "g" * 12 + "-" + "h" * 12,
    "google-api-key": "AI" + "za" + "k" * 35,
    "github-fine-grained-token": "github" + "_pat_" + "m" * 40,
    "stripe-style-key": "rk" + "_live_" + "n" * 16,
    "aws-secret-key": "aws_secret" + "_access_key = " + "p" * 20 + "/" + "q" * 18 + "+",
}

@pytest.mark.parametrize("rule,text", HITS.items())
def test_each_rule_hits(rule, text):
    assert rule in find_secrets(text)

@pytest.mark.parametrize("text", [
    "auth: {type: header, header: x-brain-key, secret: connector/brain/work-key-entry}",
    "upstream: https://example.invalid/mcp",
    "sha256 of args stored, never the args",
    "token_secret: connector/tracker/api-token",
    "${SERVICE_TOKEN}",
])
def test_pointers_and_placeholders_do_not_hit(text):
    assert find_secrets(text) == []

def test_result_never_contains_matched_text():
    secret = "sk-" + "z" * 30
    assert all(secret not in name for name in find_secrets("k " + secret))


@pytest.mark.parametrize("text", ["Bearer ${TOKEN}", "Bearer <key in file>", "Bearer short"])
def test_bearer_placeholder_does_not_hit(text):
    assert "bearer-value" not in find_secrets(text)


def test_lowercase_pointer_still_exempt():
    assert find_secrets("token: connector/tracker/api-token") == []
    assert find_secrets("secret: connector/brain/work-key-entry") == []


def test_long_hyphenated_pointer_segment_still_exempt():
    segment = "alpha-bravo-gamma-delta-omega"  # 29 characters
    assert len(segment) == 29
    assert find_secrets("secret: team/" + segment) == []


def test_mixed_case_value_with_slash_hits():
    assert "assigned-secret" in find_secrets("token=" + "Aa1" * 5 + "/" + "Bb2" * 5)


def test_lowercase_hex_run_with_slash_hits():
    assert "assigned-secret" in find_secrets("token=team/" + "ab12" * 8)


def test_aws_secret_key_needs_exactly_forty_characters():
    base = "AWS_SECRET_ACCESS_KEY="
    assert "aws-secret-key" in find_secrets(base + "r" * 40)
    assert "aws-secret-key" not in find_secrets(base + "r" * 39)
    assert "aws-secret-key" not in find_secrets(base + "r" * 41)
