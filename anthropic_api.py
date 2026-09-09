#!/usr/bin/env python3
"""
Anthropic Messages API over urllib, stdlib only.

Same reasoning as x_api.py hand-rolling OAuth: this repo has no pip install
step, and removing it was deliberate. Extracted to the repo root once a second
suggester needed the same plumbing, so the retry policy and the
refusal/max_tokens handling exist in one place rather than two.

Every caller here wants the same thing: one structured-output request, retried
on the transient codes, returning parsed JSON. Nothing streams, nothing holds
a conversation.

Never log the key. This repo is public and so are its Actions logs.
"""

import json
import sys
import time
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
API_RETRIES = 4

# Long. A high-effort batch with adaptive thinking sits well past the default.
TIMEOUT_SECONDS = 900


def call_json(api_key, model, system_text, user_text, schema, key,
              max_tokens, effort, label=None):
    """One structured-output request. Returns payload[key] from the response.

    system_text is sent with a cache breakpoint on it. Callers that issue
    several requests in a run with a byte-identical system prompt get the
    later ones read from cache instead of paying for it again, which is the
    whole reason the skill text is in the system block rather than the user
    turn.

    Exits the process on anything unrecoverable: a bad key, a refusal, or a
    truncated response. A half-written batch is worse than no batch.
    """
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [{
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }],
        "thinking": {"type": "adaptive"},
        "output_config": {
            "effort": effort,
            "format": {"type": "json_schema", "schema": schema},
        },
        "messages": [{"role": "user", "content": user_text}],
    }

    payload = None
    last_error = None
    for attempt in range(API_RETRIES):
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "anthropic-version": API_VERSION,
                "x-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            if exc.code in (408, 409, 429) or exc.code >= 500:
                delay = min(2 ** attempt, 30)
                print(f"  API {exc.code}, retrying in {delay}s: {detail}")
                last_error = f"HTTP {exc.code}: {detail}"
                time.sleep(delay)
                continue
            sys.exit(f"ERROR: Anthropic API returned {exc.code}: {detail}")
        except urllib.error.URLError as exc:
            delay = min(2 ** attempt, 30)
            print(f"  Connection error, retrying in {delay}s: {exc.reason}")
            last_error = str(exc.reason)
            time.sleep(delay)

    if payload is None:
        sys.exit(f"ERROR: Anthropic API unreachable after {API_RETRIES} attempts: {last_error}")

    stop = payload.get("stop_reason")
    if stop == "refusal":
        sys.exit("ERROR: the request was declined by safety classifiers. Nothing generated.")
    if stop == "max_tokens":
        sys.exit(f"ERROR: hit max_tokens ({max_tokens}). Raise it in config.py and rerun.")

    usage = payload.get("usage", {})
    prefix = f"  {label}: " if label else "  "
    print(
        f"{prefix}tokens in {usage.get('input_tokens', 0)}"
        f" (cache read {usage.get('cache_read_input_tokens', 0)},"
        f" write {usage.get('cache_creation_input_tokens', 0)})"
        f" out {usage.get('output_tokens', 0)}"
    )

    text = next((b["text"] for b in payload.get("content", []) if b.get("type") == "text"), None)
    if not text:
        sys.exit("ERROR: response carried no text block.")
    return json.loads(text)[key]
