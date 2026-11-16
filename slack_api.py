#!/usr/bin/env python3
"""
Minimal Slack Incoming Webhook client. stdlib only.

Shared by the weekly X suggester, the visual suggester and the CEO monthly
bot. One copy on purpose, same reasoning as compliance_checks.py: two would
drift, and the drift that matters here is the URL leaking into a log line.

The webhook URL is the credential. Its destination is fixed at creation and
it must never be printed. Actions logs on this repo are public.
"""

import json
import sys
import urllib.error
import urllib.request


def post_to_slack(webhook_url, text):
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    # The URL is the credential, so it must never reach a log line.
    except urllib.error.HTTPError as exc:
        sys.exit(f"ERROR: Slack webhook returned HTTP {exc.code}.")
    except urllib.error.URLError as exc:
        sys.exit(f"ERROR: Slack unreachable: {exc.reason}")
