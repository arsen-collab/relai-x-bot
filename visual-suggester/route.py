#!/usr/bin/env python3
"""
Weekly visual suggester - route a reviewed batch.

Takes the decisions JSON saved from the review board and files every
mechanical outcome in one pass:

  make, clean    -> printed as a brief payload, for the design-brief-creator
                    skill to file on Paula's Notion board
  make, flagged  -> queued/YYYY-Www.md, held. Not sent to Paula.
  cut            -> state/rejected.json, so it never comes back

Edited concepts are filed as edited. The original is kept beside them so a
change is never silent.

Why a flag holds a visual but not a copy rewrite
------------------------------------------------
route.py in weekly-suggester promotes a rewrite of an already-published tweet
straight into fresh.txt, on Arsen's standing approval as Marketing Lead. That
rests on the source line having already gone out from the account.

A visual concept has no such source. It is a new asset, and the flagged terms
(savings terminology above all) need written compliance approval before the
asset goes live, not after Paula has built it. So a flagged concept stops here
and Guglielmo sees it first. This matches skills/design-brief-creator/SKILL.md,
which stops to ask when a line carries a compliance flag.

An unflagged concept does reach Paula, and that is not publication: a Notion
task is internal work. What she builds is reviewed before it posts, same as
every other asset on that board.

This script does not create the Notion task itself. It prints the payload and
the design-brief-creator skill files it, which keeps every Notion write in one
place with one set of field rules.

stdlib only, same as the rest of this folder.

Usage:
  python3 visual-suggester/route.py                  # newest file in ~/Downloads
  python3 visual-suggester/route.py path/to.json
"""

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

sys.path.insert(0, HERE)
import config  # noqa: E402
import record  # noqa: E402

QUEUED_DIR = os.path.join(HERE, "queued")
REJECTED_FILE = os.path.join(HERE, "state", "rejected.json")
ROUTED_FILE = os.path.join(HERE, "state", "routed.json")
MADE_FILE = os.path.join(HERE, "state", "made.json")
BATCH_DIR = os.path.join(HERE, "batches")

DOWNLOAD_GLOB = os.path.expanduser("~/Downloads/visual-batch-*-decisions.json")


def newest_download():
    hits = sorted(glob.glob(DOWNLOAD_GLOB), key=os.path.getmtime, reverse=True)
    if not hits:
        sys.exit(f"ERROR: no decisions file matching {DOWNLOAD_GLOB}.\n"
                 "Hit Save decisions on the review board first.")
    return hits[0]


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def render_queue(week, held, existing):
    lines = [
        f"# Held from visual week {int(week.split('-W')[1])}",
        "",
        "Concepts marked make that carry a compliance flag. Not sent to the",
        "designer. Nothing reads this file.",
        "",
        "A visual concept has no already-published source line, so the",
        "standing approval that covers X rewrites does not reach it. These",
        "need Guglielmo's written sign-off on the flagged term first. Savings",
        "terminology always lands here.",
        "",
    ]
    for item in held:
        lines.append(f"## {item['id']}  {item.get('subject', '')}".rstrip())
        lines.append("")
        lines.append(f"Headline: {item.get('headline', '')}")
        lines.append(f"Caption:  {item.get('caption', '')}")
        lines.append(f"Visual:   {item.get('visual_direction', '')}")
        lines.append("")
        if item.get("original_headline"):
            lines.append("Edited during review. Original headline was:")
            lines.append(f"> {item['original_headline']}")
            lines.append("")
        if item.get("note"):
            lines.append(f"Note from review: {item['note']}")
            lines.append("")
        lines.append(f"Held because: {', '.join(item['hold_reasons'])}")
        if item.get("needs_check"):
            lines.append("Verify before build:")
            for entry in item["needs_check"]:
                lines.append(f"  - {entry}")
        lines.append("Compliance: unapproved")
        lines.append("")
    body = "\n".join(lines).rstrip() + "\n"
    return (existing.rstrip() + "\n\n" + body) if existing else body


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else newest_download()
    payload = read_json(source)
    if not payload:
        sys.exit(f"ERROR: could not read {source}.")

    week = payload.get("week")
    decisions = payload.get("decisions", [])
    if not week or not decisions:
        sys.exit("ERROR: file has no week or no decisions.")

    print(f"Reading {source}")
    print(f"Week {week}, {len(decisions)} decided")

    # The same shipped review can be seen many times. queued/ and
    # rejected.json are idempotent, but a Notion task is not: filing it twice
    # leaves Paula two of the same job. These markers are the guard.
    stamp = payload.get("submitted_at")
    routed = read_json(ROUTED_FILE, {"runs": {}, "briefed": {}})
    routed.setdefault("runs", {})
    routed.setdefault("briefed", {})
    if not payload.get("submitted"):
        print("Not marked shipped. The review is still open, nothing routed.")
        return
    if routed["runs"].get(week) == stamp:
        print(f"Already routed {week} at {stamp}. Nothing to do.")
        return

    # Briefs are tracked per concept, not per week. Ship a review, mark two
    # more concepts make, ship again: only the two new ones get briefed.
    briefed = set(routed["briefed"].get(week, []))

    # The batch file in the repo is the record. The board is editable in a
    # browser, so anything the reviewer cannot change comes from here.
    batch = read_json(os.path.join(BATCH_DIR, f"{week}.json"))
    by_id = {}
    if batch:
        by_id = {c["id"]: c for c in batch["concepts"]}
    else:
        print(f"WARNING: no batches/{week}.json. Falling back to board data only.")

    flag_checks = [(label, re.compile(pattern, re.IGNORECASE))
                   for label, pattern in config.FLAG_CHECKS]
    drop_checks = [(label, re.compile(pattern, re.IGNORECASE))
                   for label, pattern in config.DROP_CHECKS]

    def gate(item):
        """Reasons this concept must not reach the designer yet.

        Re-run rather than trusted: headline and caption are editable on the
        review board, so an edit can introduce a term the batch never had.
        """
        published = f"{item.get('headline', '')}\n{item.get('caption', '')}"
        reasons = [label for label, pattern in drop_checks if pattern.search(published)]
        reasons += [label for label, pattern in flag_checks if pattern.search(published)]
        # Flags the generator recorded, which include the model's own honest
        # judgment calls that no regex would catch.
        reasons += [f for f in (by_id.get(item["id"], {}).get("flags") or [])]
        if len(item.get("headline", "")) > config.MAX_HEADLINE_CHARS:
            reasons.append(f"headline over {config.MAX_HEADLINE_CHARS} chars")
        return sorted(set(reasons))

    makes = [d for d in decisions if d["action"] == "make"]
    cuts = [d for d in decisions if d["action"] == "cut"]
    edited = [d for d in decisions if d.get("original_headline")]

    # Fill in whatever the board did not carry, from the batch file.
    for item in makes + cuts:
        stored = by_id.get(item["id"], {})
        for field in ("subject", "caption", "visual_direction", "purpose",
                      "target_feeling", "format", "shape", "needs_check",
                      "source_kind", "source_ref"):
            item.setdefault(field, stored.get(field))

    send, held = [], []
    for item in makes:
        reasons = gate(item)
        if reasons:
            item["hold_reasons"] = reasons
            held.append(item)
        else:
            send.append(item)

    # flagged makes -> held
    if held:
        os.makedirs(QUEUED_DIR, exist_ok=True)
        path = os.path.join(QUEUED_DIR, f"{week}.md")
        existing = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                existing = fh.read()
            already = [h["id"] for h in held if f"## {h['id']}" in existing]
            if already:
                print(f"  Already held, skipping: {', '.join(already)}")
                held = [h for h in held if h["id"] not in already]
        if held:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(render_queue(week, held, existing))
            print(f"  {len(held)} held -> {os.path.relpath(path, REPO_ROOT)}")
            for item in held:
                print(f"    {item['id']}: {', '.join(item['hold_reasons'])}")
            print("    These are NOT going to Paula. They need written "
                  "compliance sign-off first.")

    # cut -> rejected
    if cuts:
        rejected = read_json(REJECTED_FILE, {"concepts": []})
        rejected.setdefault("concepts", [])
        known = {(entry.get("week"), entry.get("concept_id"))
                 for entry in rejected["concepts"]}
        added = 0
        for cut in cuts:
            if (week, cut["id"]) in known:
                continue
            rejected["concepts"].append({
                "week": week,
                "concept_id": cut["id"],
                "subject": cut.get("subject", ""),
                "headline": cut.get("headline", ""),
                "format": cut.get("format", ""),
                "note": cut.get("note", ""),
            })
            added += 1
        write_json(REJECTED_FILE, rejected)
        print(f"  {added} cut -> {os.path.relpath(REJECTED_FILE, REPO_ROOT)}")

    # clean makes -> brief payload, printed for the skill to pick up
    done = [s["id"] for s in send if s["id"] in briefed]
    if done:
        print(f"  Briefs already on Paula's board, skipping: {', '.join(done)}")
    send = [s for s in send if s["id"] not in briefed]

    if send:
        print(f"\n{len(send)} for design briefs:")
        # Keyed to the brief sections in skills/design-brief-creator/SKILL.md,
        # in its order: Purpose, Target feeling, Format, Headline and copy,
        # Visual direction, Image specs. The skill fills the Notion fields
        # from its own defaults, so nothing here needs translating and no
        # section it does not want appears.
        #
        # No German. The skill translates at filing time, from whatever the
        # English says then, which is what stops the two drifting after an
        # edit on the review board.
        print(json.dumps({
            "week": week,
            "briefs": [{
                "concept_id": item["id"],
                "task_title": item.get("subject", ""),
                "purpose": item.get("purpose", ""),
                "target_feeling": item.get("target_feeling", ""),
                "format": f"{item.get('shape', 'single image')}, "
                          f"{(item.get('format') or '').replace('_', ' ')}",
                "headline": item.get("headline", ""),
                "caption": item.get("caption", ""),
                "visual_direction": item.get("visual_direction", ""),
                "image_specs": config.BRIEF_IMAGE_SPEC,
                "verify_before_build": item.get("needs_check") or [],
                "direction_from_review": item.get("note", ""),
                "source": f"Visual suggester, week {int(week.split('-W')[1])}, "
                          f"{item['id']}, from {item.get('source_kind', 'unknown source')}",
            } for item in send],
        }, ensure_ascii=False, indent=1))

        # made.json is what stops next week proposing the same thing again.
        # record.py is the only writer on it, so a brief filed straight from a
        # chat session lands in the same place by the same rules.
        added = record.add([{
            "week": week,
            "concept_id": item["id"],
            "subject": item.get("subject", ""),
            "headline": item.get("headline", ""),
            "format": item.get("format", ""),
            "source": "visual suggester review",
        } for item in send])
        print(f"\nRecorded {len(added)} in "
              f"{os.path.relpath(MADE_FILE, REPO_ROOT)} so next week does not "
              "re-propose them.")

    if edited:
        print(f"\nEdited during review: {', '.join(d['id'] for d in edited)}")

    # Notes are instructions, not filing. Printed rather than written so they
    # get read and acted on rather than buried in a file.
    noted = [d for d in decisions if d.get("note")]
    if noted:
        print("\nNotes from review:")
        for item in noted:
            action = item.get("action") or "no decision yet"
            print(f"  {item['id']} ({action}): {item['note']}")

    if batch:
        decided_ids = {d["id"] for d in decisions}
        undecided = [c["id"] for c in batch["concepts"] if c["id"] not in decided_ids]
        if undecided:
            print(f"\nStill undecided ({len(undecided)}): {', '.join(undecided)}")

    routed["runs"][week] = stamp
    routed["briefed"][week] = sorted(briefed | {s["id"] for s in send})
    write_json(ROUTED_FILE, routed)
    print(f"\nMarked {week} routed at {stamp}.")
    if send:
        print("Design briefs are NOT created by this script. Create them from "
              "the payload above with the design-brief-creator skill.")
        print("Carry verify_before_build into the brief. A figure nobody "
              "sourced must not be set in artwork.")


if __name__ == "__main__":
    main()
