#!/usr/bin/env python3
"""
Weekly visual suggester - build the review board.

Injects a week's batch JSON into board_template.html and writes
board/YYYY-Www.html, ready to publish as an artifact.

The board is a template plus data rather than hand-written HTML each week, so
a change to the review UI applies to every future week and cannot half-apply.
Publish the output as the SAME artifact each week rather than minting a new
one, so config.REVIEW_URL in the Slack message stays valid.

The batch JSON goes in as a <script> literal, so it is escaped for that
context: a "</script>" inside any concept text would otherwise end the block
early and drop the rest of the page.

Usage:
  python3 visual-suggester/build_board.py             # current ISO week
  python3 visual-suggester/build_board.py 2026-W37

stdlib only, same as the rest of this folder.
"""

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

TEMPLATE = os.path.join(HERE, "board_template.html")
BATCH_DIR = os.path.join(HERE, "batches")
BOARD_DIR = os.path.join(HERE, "board")

TOKEN = "__BATCH_JSON__"
TZ = ZoneInfo("Europe/Zurich")


def js_literal(payload):
    """JSON safe to embed in an inline <script> block.

    </script> and <!-- both terminate or comment out the surrounding block
    when they appear literally in the source, whatever the JSON says. U+2028
    and U+2029 are line terminators in JavaScript but not in JSON, so they
    break the parse where a plain dump would not.
    """
    text = json.dumps(payload, ensure_ascii=False)
    return (text.replace("<", "\\u003c")
                .replace(">", "\\u003e")
                .replace("&", "\\u0026")
                .replace(" ", "\\u2028")
                .replace(" ", "\\u2029"))


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

    if TOKEN not in template:
        sys.exit(f"ERROR: {TOKEN} not found in board_template.html.")

    html = template.replace(TOKEN, js_literal(batch))

    os.makedirs(BOARD_DIR, exist_ok=True)
    out = os.path.join(BOARD_DIR, f"{week}.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)

    concepts = batch["concepts"]
    sketched = sum(1 for c in concepts if c.get("mock_svg"))
    flagged = sum(1 for c in concepts if c.get("flags"))
    print(f"Week {week}: {len(concepts)} concepts, {sketched} sketched, "
          f"{flagged} flagged")
    print(f"Wrote {os.path.relpath(out, REPO_ROOT)}")
    print("Publish it as the review board artifact, at the same URL as last "
          "week, then check config.REVIEW_URL still matches.")


if __name__ == "__main__":
    main()
