"""Stand-in for op, bw, gopass and busctl in tests. Prints fake listings with planted values.

The test suite writes tiny wrappers named after each CLI that run this file, and puts only
those wrappers on PATH, so no real password manager is ever called.
"""

import json
import os
import sys

name = os.path.basename(sys.argv[1] if len(sys.argv) > 1 else "")
args = sys.argv[2:]

if name == "op" and args[:2] == ["item", "list"]:
    print(json.dumps([
        {"id": "item-one", "title": "GitHub read token", "vault": {"name": "Work"}, "category": "API_CREDENTIAL",
         "additional_information": "Qz9FAKEopv01x"},
        {"id": "item-two", "title": "Forum login", "vault": {"name": "Personal"}, "category": "LOGIN"},
    ]))
elif name == "bw" and args[:1] == ["status"]:
    print(json.dumps({"status": "unlocked"}))
elif name == "bw" and args[:2] == ["list", "items"]:
    print(json.dumps([{"name": "Email login", "type": 1, "login": {"username": "demo", "password": "Qz9FAKEbwv01x"}},
                      {"name": "Recovery codes", "type": 2, "notes": "Qz9FAKEbwv02x"}]))
elif name == "gopass" and args[:1] == ["ls"]:
    print("work/api-token\npersonal/site")
elif name == "busctl" and "SearchItems" in args:
    print('ao 1 "/org/freedesktop/secrets/collection/login/1" ao 0')
elif name == "busctl" and "get-property" in args:
    print('s "Demo keyring item"')
else:
    sys.exit(1)
