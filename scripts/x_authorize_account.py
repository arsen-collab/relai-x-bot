#!/usr/bin/env python3
"""
One-off helper: lets another X account authorize Relai's X app, then stores
that account's access token straight into a GitHub repo's secrets.

Run locally, never in CI. Uses X's PIN flow (OAuth 1.0a, oauth_callback=oob):

  1. Prints an authorize link. Send it to the account owner.
  2. They open it while logged in to their own X account, click
     "Authorize app", and send back the 7-digit PIN.
  3. You type the PIN here. The script swaps it for their access token and
     writes API_KEY, API_KEY_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET and
     X_USER_ID into the target repo with `gh secret set`.

The tokens are never printed, logged or written to disk. Only the account's
handle and user id are shown, so you can confirm the right account approved.

The app keys are Relai's existing consumer keys, the same values as this
repo's API_KEY and API_KEY_SECRET. Do not regenerate them in the developer
console to get them: that changes the keys @relai_app's bot depends on.

Usage:
    python3 scripts/x_authorize_account.py OWNER/REPO

API_KEY and API_KEY_SECRET are read from the environment if set, otherwise
asked for with hidden input, so they never land in shell history.

The owner can revoke access at any time: X > Settings > Security and account
access > Apps and sessions > Connected apps.
"""

import base64
import getpass
import hashlib
import hmac
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from x_api import _quote  # noqa: E402

REQUEST_TOKEN_URL = "https://api.twitter.com/oauth/request_token"
AUTHORIZE_URL = "https://api.twitter.com/oauth/authorize"
ACCESS_TOKEN_URL = "https://api.twitter.com/oauth/access_token"


def secret_input(name):
    value = os.environ.get(name) or getpass.getpass(f"{name} (hidden): ").strip()
    if not value:
        sys.exit(f"ERROR: {name} is required.")
    return value


def signed_post(url, consumer_key, consumer_secret, extra_oauth, token_secret=""):
    """POST with every parameter in the Authorization header, no body."""
    oauth = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_version": "1.0",
        **extra_oauth,
    }
    param_string = "&".join(f"{_quote(k)}={_quote(v)}" for k, v in sorted(oauth.items()))
    base_string = f"POST&{_quote(url)}&{_quote(param_string)}"
    signing_key = f"{_quote(consumer_secret)}&{_quote(token_secret)}"
    oauth["oauth_signature"] = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    header = "OAuth " + ", ".join(f'{_quote(k)}="{_quote(v)}"' for k, v in sorted(oauth.items()))

    req = urllib.request.Request(url, data=b"", method="POST")
    req.add_header("Authorization", header)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return dict(urllib.parse.parse_qsl(resp.read().decode()))
    except urllib.error.HTTPError as exc:
        # The error body names the problem, never a token.
        sys.exit(f"ERROR: {url} returned {exc.code}: {exc.read().decode()[:300]}")


def set_secret(repo, name, value):
    result = subprocess.run(
        ["gh", "secret", "set", name, "--repo", repo],
        input=value, text=True, capture_output=True,
    )
    if result.returncode != 0:
        sys.exit(f"ERROR: could not set {name} on {repo}: {result.stderr.strip()}")
    print(f"  set {name}")


def main():
    if len(sys.argv) != 2 or "/" not in sys.argv[1]:
        sys.exit("Usage: python3 scripts/x_authorize_account.py OWNER/REPO")
    repo = sys.argv[1]

    check = subprocess.run(["gh", "repo", "view", repo], capture_output=True, text=True)
    if check.returncode != 0:
        sys.exit(f"ERROR: gh cannot see {repo}. Create it first, or run gh auth login.")

    consumer_key = secret_input("API_KEY")
    consumer_secret = secret_input("API_KEY_SECRET")

    request = signed_post(REQUEST_TOKEN_URL, consumer_key, consumer_secret,
                          {"oauth_callback": "oob"})
    if request.get("oauth_callback_confirmed") != "true":
        sys.exit("ERROR: X did not confirm the PIN flow. Check the app's "
                 "User authentication settings have OAuth 1.0a switched on.")

    link = f"{AUTHORIZE_URL}?oauth_token={request['oauth_token']}"
    print("\nSend this link to the account owner. They open it logged in as")
    print("themselves, click Authorize app, and send you the PIN:\n")
    print(f"  {link}\n")
    print("The link is single use. Ask for the PIN straight away.\n")

    pin = input("PIN: ").strip()
    if not pin.isdigit():
        sys.exit("ERROR: the PIN is digits only.")

    access = signed_post(
        ACCESS_TOKEN_URL, consumer_key, consumer_secret,
        {"oauth_token": request["oauth_token"], "oauth_verifier": pin},
        token_secret=request["oauth_token_secret"],
    )
    for field in ("oauth_token", "oauth_token_secret", "user_id", "screen_name"):
        if field not in access:
            sys.exit(f"ERROR: X's reply had no {field}. Nothing was stored.")

    print(f"\nAuthorized by @{access['screen_name']} (user id {access['user_id']}).")
    if input(f"Store these on {repo}? Type yes: ").strip().lower() != "yes":
        sys.exit("Stopped. Nothing was stored.")

    set_secret(repo, "API_KEY", consumer_key)
    set_secret(repo, "API_KEY_SECRET", consumer_secret)
    set_secret(repo, "ACCESS_TOKEN", access["oauth_token"])
    set_secret(repo, "ACCESS_TOKEN_SECRET", access["oauth_token_secret"])
    set_secret(repo, "X_USER_ID", access["user_id"])
    print("Done. Do a dry run, then one live run, from the repo's Actions tab.")


if __name__ == "__main__":
    main()
