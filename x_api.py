#!/usr/bin/env python3
"""
Minimal X API client for the Relai bots.

Standard library only. No tweepy, no pip install step, so the workflow has
one less thing that can fail before the code runs.

Signs requests with OAuth 1.0a HMAC-SHA1, which is what X uses for
user-context calls. Tokens never expire, unlike OAuth 2.0.
"""

import os
import sys
import time
import json
import hmac
import base64
import hashlib
import secrets
import urllib.parse
import urllib.request
import urllib.error

API = "https://api.twitter.com/2"

RETRY_ON = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = [5, 20]


def get_credentials():
    keys = ["API_KEY", "API_KEY_SECRET", "ACCESS_TOKEN", "ACCESS_TOKEN_SECRET"]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        sys.exit(f"ERROR: missing variables: {', '.join(missing)}")
    return {k: os.environ[k] for k in keys}


def _quote(value):
    """RFC 3986 percent encoding, which is stricter than the urllib default."""
    return urllib.parse.quote(str(value), safe="~-._")


def _auth_header(method, url, query_params, creds):
    oauth = {
        "oauth_consumer_key": creds["API_KEY"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": creds["ACCESS_TOKEN"],
        "oauth_version": "1.0",
    }

    # Only query params take part in the signature. A JSON body does not.
    combined = {**(query_params or {}), **oauth}
    param_string = "&".join(
        f"{_quote(k)}={_quote(v)}" for k, v in sorted(combined.items())
    )
    base_string = f"{method.upper()}&{_quote(url)}&{_quote(param_string)}"
    signing_key = f"{_quote(creds['API_KEY_SECRET'])}&{_quote(creds['ACCESS_TOKEN_SECRET'])}"

    oauth["oauth_signature"] = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()

    return "OAuth " + ", ".join(
        f'{_quote(k)}="{_quote(v)}"' for k, v in sorted(oauth.items())
    )


def _request(method, url, creds, query_params=None, body=None):
    """One HTTP call with retries on transient failures."""
    full_url = url
    if query_params:
        full_url += "?" + urllib.parse.urlencode(query_params)

    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        req = urllib.request.Request(full_url, method=method)
        req.add_header("Authorization", _auth_header(method, url, query_params, creds))
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req.add_header("Content-Type", "application/json")
            req.data = data

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8")[:300]
            last_error = (exc.code, detail)
            if exc.code in RETRY_ON and attempt < MAX_ATTEMPTS - 1:
                wait = BACKOFF_SECONDS[attempt]
                print(f"  HTTP {exc.code}, retrying in {wait}s "
                      f"(attempt {attempt + 2}/{MAX_ATTEMPTS})")
                time.sleep(wait)
                continue
            return {"_error": exc.code, "_detail": detail}
        except urllib.error.URLError as exc:
            last_error = (0, str(exc))
            if attempt < MAX_ATTEMPTS - 1:
                wait = BACKOFF_SECONDS[attempt]
                print(f"  Network error, retrying in {wait}s "
                      f"(attempt {attempt + 2}/{MAX_ATTEMPTS})")
                time.sleep(wait)
                continue
            return {"_error": 0, "_detail": str(exc)}

    return {"_error": last_error[0], "_detail": last_error[1]}


def get_user_id(creds):
    """Cached via X_USER_ID if set, which saves one API read per run."""
    cached = os.environ.get("X_USER_ID")
    if cached:
        return cached
    result = _request("GET", f"{API}/users/me", creds)
    if "_error" in result:
        print(f"  Could not resolve user id: {result['_error']} {result['_detail']}")
        return None
    return result.get("data", {}).get("id")


def recent_texts(creds, count=10):
    """Most recent posts on the account. Returns None if the check failed,
    which callers must treat differently from an empty list."""
    user_id = get_user_id(creds)
    if not user_id:
        return None
    result = _request(
        "GET", f"{API}/users/{user_id}/tweets", creds,
        query_params={"max_results": max(5, min(count, 100))},
    )
    if "_error" in result:
        print(f"  Could not read recent posts: {result['_error']} {result['_detail']}")
        return None
    return [t.get("text", "") for t in (result.get("data") or [])]


def already_posted(creds, text, count=10):
    """True if this exact text is already on the account.

    Returns False when the check itself fails, so a read outage does not
    silently stop the bot from posting. Worst case is a duplicate attempt,
    which X rejects harmlessly.
    """
    texts = recent_texts(creds, count)
    if texts is None:
        print("  Duplicate check unavailable, proceeding.")
        return False
    normalised = text.strip()
    return any(t.strip() == normalised for t in texts)


def post(creds, text):
    result = _request("POST", f"{API}/tweets", creds, body={"text": text})
    if "_error" in result:
        code, detail = result["_error"], result["_detail"]
        if code == 403 and "duplicate" in detail.lower():
            print("  Already posted (duplicate). Treating as success.")
            return None
        sys.exit(f"ERROR: post failed with {code}: {detail}")
    return result.get("data", {}).get("id")
