#!/usr/bin/env python3
"""
Weekly X suggester - build the review board.

Joins a week's batch JSON with the source tweets in state/pool.json, injects
the result into board_template.html and writes board/YYYY-Www.html, ready to
publish as an artifact.

The board is a template plus data rather than hand-written HTML each week, so
a change to the review UI applies to every future week and cannot half-apply.
Publish the output as the SAME artifact each week rather than minting a new
one, so config.REVIEW_URL in the Slack message stays valid. The Action cannot
do that step, which is why the link shows last week until someone runs it.

The data goes in as <script type="application/json"> literals, so it is
escaped for that context: a "</script>" inside any suggestion text would
otherwise end the block early and drop the rest of the page.

Usage:
  python3 weekly-suggester/build_board.py             # current ISO week
  python3 weekly-suggester/build_board.py 2026-W41

stdlib only, same as the rest of this folder.
"""

import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

TEMPLATE = os.path.join(HERE, "board_template.html")
BATCH_DIR = os.path.join(HERE, "batches")
BOARD_DIR = os.path.join(HERE, "board")
POOL_PATH = os.path.join(HERE, "state", "pool.json")

BOARD_TOKEN = "__BOARD_JSON__"
DECISIONS_TOKEN = "__DECISIONS_JSON__"
TZ = ZoneInfo("Europe/Zurich")


def js_literal(payload):
    """JSON safe to embed in an inline <script> block.

    </script> and <!-- both terminate or comment out the surrounding block
    when they appear literally in the source, whatever the JSON says. U+2028
    and U+2029 are line terminators in JavaScript but not in JSON.
    """
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    return (text.replace("<", "\\u003c")
                .replace(">", "\\u003e")
                .replace("&", "\\u0026")
                .replace(" ", "\\u2028")
                .replace(" ", "\\u2029"))


def load_sources():
    if not os.path.exists(POOL_PATH):
        return {}
    with open(POOL_PATH, encoding="utf-8") as fh:
        pool = json.load(fh)
    return {str(t["id"]): t for t in pool.get("items", [])}


def board_data(batch, sources):
    items = []
    missing = []
    for s in batch["suggestions"]:
        source = None
        if s.get("source_id"):
            tweet = sources.get(str(s["source_id"]))
            if tweet:
                source = {
                    "id": str(tweet["id"]),
                    "text": tweet["text"],
                    "likes": tweet["likes"],
                    "reposts": tweet["reposts"],
                    "date": tweet["date"],
                }
            else:
                missing.append(s["id"])
        items.append({
            "id": s["id"],
            "type": s["type"],
            "theme": s["theme"],
            "why": s["rationale"],
            "text": s["text"],
            "source": source,
            "note": "",
            "brief": s["brief"],
            # Flags are shown on the card by the template. They are not an
            # approval state: route.py re-runs the checks on whatever it gets.
            "flags": s.get("flags", []),
        })
    return {
        "week": batch["week"],
        "generated": (batch.get("generated_at") or "")[:10],
        "items": items,
        "already": {},
    }, missing


def main():
    week = sys.argv[1] if len(sys.argv) > 1 else None
    if not week:
        year, iso_week, _ = datetime.now(TZ).isocalendar()
        week = f"{year}-W{iso_week:02d}"

    batch_path = os.path.join(BATCH_DIR, f"{week}.json")
    if not os.path.exists(batch_path):
        sys.exit(f"ERROR: no batch at {os.path.relpath(batch_path, REPO_ROOT)}.\n"
                 "Run generate.py for that week first.")

    with open(batch_path, encoding="utf-8") as fh:
        batch = json.load(fh)
    with open(TEMPLATE, encoding="utf-8") as fh:
        template = fh.read()

    for token in (BOARD_TOKEN, DECISIONS_TOKEN):
        if token not in template:
            sys.exit(f"ERROR: {token} not found in board_template.html.")

    data, missing = board_data(batch, load_sources())
    html = template.replace(BOARD_TOKEN, js_literal(data))
    html = html.replace(DECISIONS_TOKEN,
                        js_literal({"week": week, "decisions": [], "submitted": False}))

    os.makedirs(BOARD_DIR, exist_ok=True)
    out = os.path.join(BOARD_DIR, f"{week}.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)

    flagged = sum(1 for s in batch["suggestions"] if s.get("flags"))
    print(f"Week {week}: {len(batch['suggestions'])} suggestions, {flagged} flagged")
    if missing:
        print(f"WARNING: no source tweet in state/pool.json for {', '.join(missing)}.")
    print(f"Wrote {os.path.relpath(out, REPO_ROOT)}")
    print("Publish it as the review board artifact, at the same URL as last "
          "week, then check config.REVIEW_URL still matches.")


if __name__ == "__main__":
    main()
