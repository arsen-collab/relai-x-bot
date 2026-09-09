#!/usr/bin/env python3
"""
Weekly visual suggester - record a design as made.

state/made.json is the running record of every visual brief filed with Claude,
whatever the entry point. generate.py reads it and will not propose anything
in it again.

Two entry points, one writer
----------------------------
route.py calls add() when it sends a reviewed concept out. The
design-brief-creator skill calls this from the command line when a brief is
filed straight from a chat session, which is most of them: Arsen pitches an
idea, the skill writes the brief, and without this the suggester would happily
propose it again next Tuesday.

Both go through add() so there is only ever one writer on the file.

This is what replaced refreshing the Notion snapshot every month, decided
9 Sep 2026. state/board.json is now a frozen baseline of the 47 concepts that
existed on 9 Sep 2026, and everything after that date is recorded here as it
happens. A baseline plus a running log needs no monthly chore and is never
stale by more than one brief.

Usage:
  python3 visual-suggester/record.py \\
      --subject "wages against cost of living" \\
      --headline "Same work. Less bread." \\
      --format two_line_chart \\
      --source "chat session" \\
      --notion-url https://notion.so/...

  python3 visual-suggester/record.py --list

Only --subject and --headline are required. Recording the same headline twice
is a no-op, so it is safe to run again if you are not sure it was logged.

stdlib only, same as the rest of this folder.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

MADE_FILE = os.path.join(HERE, "state", "made.json")
TZ = ZoneInfo("Europe/Zurich")


def normalize(text):
    return re.sub(r"[^a-z0-9 ]", "", (text or "").lower().replace("\n", " ")).strip()


def read():
    if not os.path.exists(MADE_FILE):
        return {"concepts": []}
    with open(MADE_FILE, encoding="utf-8") as fh:
        payload = json.load(fh)
    payload.setdefault("concepts", [])
    return payload


def write(payload):
    os.makedirs(os.path.dirname(MADE_FILE), exist_ok=True)
    with open(MADE_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def add(entries):
    """Append entries, skipping any headline already recorded.

    Returns the entries actually added. Deduped on the normalized headline
    rather than an id, because a brief filed from a chat session has no
    concept id and the headline is the thing that must not repeat.
    """
    payload = read()
    seen = {normalize(c.get("headline")) for c in payload["concepts"]}
    seen.discard("")

    added = []
    for entry in entries:
        key = normalize(entry.get("headline"))
        if not key or key in seen:
            continue
        seen.add(key)
        entry.setdefault("recorded", datetime.now(TZ).strftime("%Y-%m-%d"))
        payload["concepts"].append(entry)
        added.append(entry)

    if added:
        write(payload)
    return added


def main():
    parser = argparse.ArgumentParser(
        description="Record a visual design as made, so it is never suggested again.")
    parser.add_argument("--subject", help="Three to six words naming the concept.")
    parser.add_argument("--headline", help="The line set on the image.")
    parser.add_argument("--format", default="", help="Catalog format key, if it maps to one.")
    parser.add_argument("--source", default="chat session",
                        help="Where it came from. Defaults to 'chat session'.")
    parser.add_argument("--notion-url", default="", help="The task on Paula's board.")
    parser.add_argument("--list", action="store_true", help="Print the record and exit.")
    args = parser.parse_args()

    if args.list:
        payload = read()
        concepts = payload["concepts"]
        print(f"{len(concepts)} recorded in {os.path.relpath(MADE_FILE, REPO_ROOT)}")
        for concept in concepts:
            when = concept.get("recorded") or concept.get("week") or "?"
            print(f"  {when}  {concept.get('subject', '?')}: "
                  f"{concept.get('headline', '?')}")
        return

    if not args.subject or not args.headline:
        parser.error("--subject and --headline are both required.")

    entry = {
        "subject": args.subject,
        "headline": args.headline,
        "format": args.format,
        "source": args.source,
    }
    if args.notion_url:
        entry["notion_url"] = args.notion_url

    added = add([entry])
    if added:
        print(f"Recorded: {args.subject}")
        print(f"Wrote {os.path.relpath(MADE_FILE, REPO_ROOT)}")
        print("The suggester will not propose this again.")
    else:
        print(f"Already recorded, nothing changed: {args.headline!r}")


if __name__ == "__main__":
    main()
