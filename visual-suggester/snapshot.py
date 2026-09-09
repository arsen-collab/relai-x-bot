#!/usr/bin/env python3
"""
Weekly visual suggester - board snapshot.

Normalizes a raw dump of Paula's Notion Design board into state/board.json,
which is what generate.py reads to know what Relai has already made.

Why the dump is not fetched here
--------------------------------
Reading Notion from the Action would need a NOTION_TOKEN secret, an internal
integration granted on the board, and a DORA register entry for a new
machine-to-machine path into a system that already holds the design pipeline.
For what: an exclusion list that goes stale slowly.

So the snapshot is refreshed from a chat session, where the Notion connector
is already authenticated as a human, and the result is committed. Same call as
weekly-suggester/rank.py running offline: the Action reads a committed file
and needs no credential it does not already have.

The cost of a stale snapshot is a repeated concept, caught by the reviewer.
state/made.json separately records every concept this suggester has sent to
Paula, and that file is never stale, so the repeats the tool itself could
cause are covered even when the snapshot is a month old. Refresh monthly.

Refreshing it
-------------
In a chat session, query the board and save the result, then:

  python3 visual-suggester/snapshot.py ~/Downloads/design-board.json

Accepts either the bare query response ({"results": [...]}) or the
MCP-wrapped form ([{"type": "text", "text": "{...}"}]). Required columns:

  created, Task, Status, Platform, Notes / context

Then commit state/board.json.

stdlib only, and no zoneinfo, so the system Python 3.9 on a Mac runs it.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

sys.path.insert(0, HERE)
import config  # noqa: E402

BOARD_FILE = os.path.join(HERE, "state", "board.json")

# Notes are written by the design-brief-creator skill, which fixes the section
# order, so these anchors hold for anything it filed. Rows typed by hand in
# Slack style do not have them and fall through to a trimmed note, which is
# fine: the title still carries the concept.
HEADLINE_RE = re.compile(
    r"Headline(?: and copy)?\s*:?\s*\n?(?:EN:\s*)?(.+?)(?:\n\s*\n|\nDE:|\nCaption)",
    re.S | re.IGNORECASE,
)
VISUAL_RE = re.compile(
    r"Visual direction\s*:?\s*(.*?)(?:\n\s*\n|Image specs|COMPLIANCE)",
    re.S | re.IGNORECASE,
)

# Rough format attribution, so generate.py can see which shapes are saturated.
# Keyword matching, not judgment: a wrong guess costs a slightly off
# saturation count, and the format catalog in config.py is the real spec.
FORMAT_HINTS = [
    ("versus", r"\bvs\.?\b|versus|two[- ]column|side by side|split (?:screen|left)"),
    ("then_now", r"then and now|\b20\d\d vs\.? ?20\d\d\b|years? ago.*today"),
    ("two_line_chart", r"\bchart\b|two lines|graph|declin\w+ line"),
    ("timeline", r"timeline|progression|left to right"),
    ("big_number", r"big number|one (?:big|dominant) (?:number|figure)"),
    ("type_only", r"type[- ]only|type treatment|just type|no imagery|checklist"),
    ("phone_mockup", r"phone mockup|app screen|screenshot of the app"),
    ("whatsapp_chat", r"whatsapp"),
    ("myth_rebuttal", r"myth|misconception|rebuttal|rules every"),
    ("step_compounding", r"per slide.*year|year 1|after \d+ years?"),
    ("testimonial", r"testimonial|trustpilot|review of the week"),
    ("single_prop", r"one visual device|single (?:prop|object|illustrated)|silhouette|metaphor"),
]


def load_dump(path):
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    payload = json.loads(raw)

    # The MCP tool result wraps the query response in a content block.
    if isinstance(payload, list):
        text = next((b.get("text") for b in payload
                     if isinstance(b, dict) and b.get("type") == "text"), None)
        if not text:
            sys.exit("ERROR: that JSON is a list with no text block in it.")
        payload = json.loads(text)

    rows = payload.get("results")
    if not isinstance(rows, list):
        sys.exit('ERROR: no "results" array. Expected the Notion query response.')
    return rows


def first_paragraph(note, limit=240):
    body = " ".join(note.split())
    return body[:limit]


def extract(pattern, note):
    found = pattern.search(note)
    if not found:
        return ""
    return " ".join(found.group(1).split())


def guess_format(title, note):
    haystack = f"{title}\n{note}"
    for key, pattern in FORMAT_HINTS:
        if re.search(pattern, haystack, re.IGNORECASE):
            return key
    return ""


def is_concept(title):
    """False for request-driven jobs: blog headers, email art, app icons.

    Those are things Arsen sends Paula when something specific needs a
    picture. They are not concepts a suggester could have proposed, so
    counting them as prior art would suppress ideas that were never had.
    """
    low = (title or "").lower()
    return not any(term in low for term in config.NOT_A_CONCEPT)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip().split("Refreshing it")[1].strip())

    rows = load_dump(sys.argv[1])
    concepts, excluded = [], []

    for row in rows:
        title = (row.get("Task") or "").strip()
        note = row.get("Notes / context") or ""
        created = (row.get("created") or row.get("createdTime") or "")[:10]
        status = row.get("Status") or ""

        platform = row.get("Platform") or ""
        if isinstance(platform, str) and platform.startswith("["):
            try:
                platform = json.loads(platform)
            except json.JSONDecodeError:
                platform = [platform]
        elif isinstance(platform, str):
            platform = [platform] if platform else []

        if not title:
            excluded.append({"title": "(untitled)", "created": created,
                             "why": "no title"})
            continue
        if not is_concept(title):
            excluded.append({"title": title, "created": created,
                             "why": "request-driven, not a concept"})
            continue

        concepts.append({
            "title": title,
            "created": created,
            "status": status,
            "platform": platform,
            "headline": extract(HEADLINE_RE, note),
            "visual_direction": extract(VISUAL_RE, note) or first_paragraph(note),
            "format_guess": guess_format(title, note),
        })

    concepts.sort(key=lambda c: c["created"], reverse=True)

    saturation = {}
    for concept in concepts:
        key = concept["format_guess"] or "unattributed"
        saturation[key] = saturation.get(key, 0) + 1

    payload = {
        "source": "Notion Design board, c33f79ad-bc09-490b-8b95-32578426c036",
        "rows_seen": len(rows),
        "concept_count": len(concepts),
        "excluded_count": len(excluded),
        "covers": {
            "oldest": concepts[-1]["created"] if concepts else "",
            "newest": concepts[0]["created"] if concepts else "",
        },
        "format_saturation": dict(sorted(saturation.items(),
                                         key=lambda kv: -kv[1])),
        "concepts": concepts,
        "excluded": excluded,
    }

    os.makedirs(os.path.dirname(BOARD_FILE), exist_ok=True)
    with open(BOARD_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    print(f"{len(rows)} rows in, {len(concepts)} concepts, {len(excluded)} excluded")
    print(f"Covers {payload['covers']['oldest']} to {payload['covers']['newest']}")
    print("Format saturation:")
    for key, count in payload["format_saturation"].items():
        print(f"  {count:>3}  {key}")
    print(f"Wrote {os.path.relpath(BOARD_FILE, REPO_ROOT)}")
    print("Commit it. generate.py reads this file, not Notion.")


if __name__ == "__main__":
    main()
