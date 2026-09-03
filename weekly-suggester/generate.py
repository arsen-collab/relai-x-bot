#!/usr/bin/env python3
"""
Weekly X suggester - generation.

Reads state/pool.json (produced offline by rank.py), takes the top unused
slice as this week's shortlist, and drafts suggestions in Relai voice with
Claude. Writes batches/YYYY-Www.md for a human to review, plus a matching
.json for notify_slack.py and the chat review step.

What this script will never do: write to evergreen.txt, or to anything else
post_tweet.py or post_evergreen.py reads. Promotion into the live pool is a
separate manual decision, made later. Every suggestion lands at
Compliance: unapproved.

stdlib only. The Anthropic API is called over urllib for the same reason
x_api.py hand-rolls OAuth: this repo has no pip install step, and removing it
was deliberate.

Env:
  ANTHROPIC_API_KEY  required for a live run
  DRY_RUN            1/true/yes exits before any API call
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

sys.path.insert(0, HERE)
import config  # noqa: E402

POOL_FILE = os.path.join(HERE, "state", "pool.json")
USED_FILE = os.path.join(HERE, "state", "used.json")
REJECTED_FILE = os.path.join(HERE, "state", "rejected.json")
BATCH_DIR = os.path.join(HERE, "batches")
SKILL_FILE = os.path.join(REPO_ROOT, "skills", "relai-social-copy", "SKILL.md")
DESIGN_SKILL_FILE = os.path.join(REPO_ROOT, "skills", "design-brief-creator", "SKILL.md")

TZ = ZoneInfo("Europe/Zurich")

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
API_RETRIES = 4

# Suggestion ids (S01, S02, ...) are assigned here, not by the model. They have
# to be sequential and stable across two separate API calls, and neither call
# can see the other. Everything else in the schema comes from the model.
SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["rewrite", "new"]},
                    "source_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "text": {"type": "string"},
                    "theme": {"type": "string"},
                    "rationale": {"type": "string"},
                    "flags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["type", "source_id", "text", "theme", "rationale", "flags"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}


BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "briefs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "suggestion_id": {"type": "string"},
                    "purpose": {"type": "string"},
                    "target_feeling": {"type": "string"},
                    "headline": {"type": "string"},
                    "caption": {"type": "string"},
                    "headline_de": {"type": "string"},
                    "caption_de": {"type": "string"},
                    "visual_direction": {"type": "string"},
                },
                "required": ["suggestion_id", "purpose", "target_feeling",
                             "headline", "caption", "headline_de", "caption_de",
                             "visual_direction"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["briefs"],
    "additionalProperties": False,
}


def read_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")


def normalize(text):
    return re.sub(r"[^a-z0-9 ]", "", text.lower().replace("\n", " ")).strip()


def load_evergreen_texts(path):
    """Normalized set of live pool lines, for a last-line duplicate check.

    rank.py already fuzzy-matched against the pool as it stood when the
    archive was ranked. This catches anything promoted into the pool since.
    """
    if not os.path.exists(path):
        sys.exit(f"ERROR: {path} not found.")
    texts = set()
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line == "#" or line.startswith("# "):
                continue
            texts.add(normalize(line.replace("\\n", "\n")))
    return texts


def compile_checks(entries):
    return [(label, re.compile(pattern, re.IGNORECASE)) for label, pattern in entries]


def violations(text, checks):
    return [label for label, pattern in checks if pattern.search(text)]


# --- API -------------------------------------------------------------------

def call_claude(api_key, system_text, user_text, schema=None, key="suggestions"):
    body = {
        "model": config.MODEL,
        "max_tokens": config.MAX_TOKENS,
        # The voice skill is byte-identical across the suggestion calls in a
        # run, so a cache breakpoint on it means the second call reads it
        # instead of paying for it again. The brief call appends the design
        # skill, so it caches separately and that is fine, it runs once.
        "system": [{
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }],
        "thinking": {"type": "adaptive"},
        "output_config": {
            "effort": config.EFFORT,
            "format": {"type": "json_schema", "schema": schema or SUGGESTION_SCHEMA},
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
            with urllib.request.urlopen(request, timeout=900) as response:
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
        sys.exit(f"ERROR: hit max_tokens ({config.MAX_TOKENS}). Raise it in config.py and rerun.")

    usage = payload.get("usage", {})
    print(
        f"  tokens in {usage.get('input_tokens', 0)}"
        f" (cache read {usage.get('cache_read_input_tokens', 0)},"
        f" write {usage.get('cache_creation_input_tokens', 0)})"
        f" out {usage.get('output_tokens', 0)}"
    )

    text = next((b["text"] for b in payload.get("content", []) if b.get("type") == "text"), None)
    if not text:
        sys.exit("ERROR: response carried no text block.")
    return json.loads(text)[key]


# --- prompts ---------------------------------------------------------------

SYSTEM_PREAMBLE = """You are drafting X copy for Relai's official account, @relai_app.

The voice and compliance skill below is binding. Treat every rule in it as a
hard constraint, not a preference. Before returning a suggestion, check it
against the hard rules section. If a suggestion breaks one, discard it and
write a different one. Never soften a rule-breaking line into a borderline
one.

Return only the JSON your schema requires. No preamble, no markdown fences,
no commentary.

Field rules:
- text: the tweet itself, ready to post, under 280 characters. Use \\n for a
  line break. No hashtags, no links, no @ mentions. Emojis only where one
  carries meaning.
- theme: two to four words naming what the post is about, lowercase.
- rationale: one line on why this line earns a post. Point at the source
  tweet's performance for a rewrite, or the recurring archive theme for a
  net-new one. Do not invent numbers.
- flags: compliance terms the line brushes against, empty array if clean.
  Name the term, for example "savings terminology". Be honest here rather
  than tidy. A human reads this list and an empty array on a line that
  needed a flag is worse than a flag on a clean line.

--- BEGIN BINDING SKILL ---
{skill}
--- END BINDING SKILL ---"""


def rewrite_prompt(count, shortlist, avoid):
    lines = "\n\n".join(
        f"[{item['id']}] ({item['likes']} likes, {item['reposts']} reposts, {item['date']})\n{item['text']}"
        for item in shortlist
    )
    prompt = f"""Below are {len(shortlist)} of the strongest standalone tweets from Relai's X archive, ranked by likes plus twice reposts with a recency decay. No impression data was available, so treat the ranking as a rough signal of what landed, not a precise one.

Write {count} rewrites. Rules for a rewrite:
- Keep the idea of the source tweet. Change the wording.
- Apply the current voice rules. Some of these tweets are years old and use
  terms the skill now bans, so rewrite against the skill rather than copying
  the source's phrasing.
- Set type to "rewrite" and source_id to the source tweet's id, the number in
  square brackets.
- One rewrite per source tweet. Do not use the same source twice.
- If a source tweet cannot be rewritten without breaking a hard rule, skip it
  and pick a different one. Do not stretch to cover every source.

SOURCE TWEETS

{lines}"""
    if avoid:
        prompt += "\n\nThese are already in this batch. Do not repeat or closely paraphrase them:\n"
        prompt += "\n".join(f"- {t}" for t in avoid)
    return prompt


def new_prompt(count, reference, avoid):
    lines = "\n\n".join(f"({item['likes']} likes, {item['date']})\n{item['text']}" for item in reference)
    prompt = f"""Below are {len(reference)} of Relai's strongest standalone tweets. Use them as voice and theme reference only. Do not rewrite them.

Write {count} net new suggestions. Rules:
- Pick themes that recur across this reference set, then find a new angle on
  them. A different mechanic, a different entry point, a different framing.
- Set type to "new" and source_id to null.
- Nothing time-bound. No prices, no dates, no current events, no product
  announcements. These have to read the same in two years.
- No two suggestions should make the same point.

REFERENCE SET

{lines}"""
    if avoid:
        prompt += "\n\nThese are already in this batch. Do not repeat or closely paraphrase them:\n"
        prompt += "\n".join(f"- {t}" for t in avoid)
    return prompt


# --- generation ------------------------------------------------------------

def brief_prompt(suggestions):
    lines = [
        "Draft one visual brief for every line below. All of them, including "
        "the ones you think are weak: which ones become images is decided "
        "later by a human, and the brief has to already be there.",
        "",
        "Each brief is for a single portrait image, never a carousel.",
        "",
        "headline: what is set ON the image. One short line. It is not the "
        "post text repeated. Tighten it until it fits comfortably at large size.",
        "",
        "caption: what is posted alongside. Every number, stat and piece of "
        "context lives here, never on the image.",
        "",
        "headline_de and caption_de: the German. Not a translation. Write the "
        "same idea the way a German speaker would say it, and let the wording "
        "differ from the English where that reads better. Du, not Sie.",
        "",
        "visual_direction: one visual device and no more. A chart, a "
        "comparison, a prop, a type treatment. Never two combined, never "
        "illustration-heavy. Say what the device is concretely enough to "
        "build. Generous white space. One accent colour, Relai orange, and "
        "say where it goes. Logo bottom right. No font names, the designer "
        "decides those. Name anything to avoid.",
        "",
        "purpose: one sentence on what the image is for.",
        "target_feeling: one sentence on how it should land.",
        "",
        "Return a brief for every id, in the same order.",
        "",
        "LINES",
    ]
    for suggestion in suggestions:
        text = suggestion["text"].replace("\n", " / ")
        lines.append(f"{suggestion['id']}  [{suggestion['theme']}]  {text}")
    return "\n".join(lines)


def collect_briefs(api_key, system_text, suggestions):
    """One brief per suggestion. A failure here is not fatal: the batch is
    still usable, the cards just have no brief on them."""
    try:
        result = call_claude(api_key, system_text, brief_prompt(suggestions),
                             schema=BRIEF_SCHEMA, key="briefs")
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: brief drafting failed: {exc}")
        return {}

    by_id = {b["suggestion_id"]: b for b in result}
    missing = [s["id"] for s in suggestions if s["id"] not in by_id]
    if missing:
        print(f"WARNING: no brief for {', '.join(missing)}")
    return by_id


def build_system_text():
    with open(SKILL_FILE, encoding="utf-8") as fh:
        skill = fh.read()
    return SYSTEM_PREAMBLE.format(skill=skill)


def brief_system_text(system_text):
    design_skill = ""
    if os.path.exists(DESIGN_SKILL_FILE):
        with open(DESIGN_SKILL_FILE, encoding="utf-8") as fh:
            design_skill = fh.read()
    else:
        print(f"WARNING: {DESIGN_SKILL_FILE} not found, briefs will be off-spec.")
    return system_text + "\n\n--- BEGIN BINDING DESIGN SKILL ---\n" + design_skill


def backfill_briefs(batch_json, batch_md, dry_run):
    """Add briefs to a batch that has none, leaving its suggestions alone."""
    if not config.BRIEFS:
        return
    batch = read_json(batch_json, None)
    if not batch:
        print("  No matching .json, nothing to backfill.")
        return

    missing = [s for s in batch["suggestions"] if not s.get("brief")]
    if not missing:
        print("  Every suggestion already has a brief.")
        return

    print(f"  {len(missing)} of {len(batch['suggestions'])} have no visual brief.")
    if dry_run:
        print("  DRY_RUN enabled, not drafting them.")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set.")

    system_text = build_system_text()
    briefs = collect_briefs(api_key, brief_system_text(system_text), missing)
    if not briefs:
        return

    for suggestion in batch["suggestions"]:
        if suggestion["id"] in briefs:
            suggestion["brief"] = briefs[suggestion["id"]]
    batch.setdefault("brief_defaults", {
        "platform": config.BRIEF_PLATFORM,
        "languages": config.BRIEF_LANGUAGES,
        "priority": config.BRIEF_PRIORITY,
        "due_days": config.BRIEF_DUE_DAYS,
        "image_spec": config.BRIEF_IMAGE_SPEC,
    })
    write_json(batch_json, batch)
    print(f"  Backfilled {len(briefs)} briefs into {os.path.relpath(batch_json, REPO_ROOT)}")

    with open(batch_md, "a", encoding="utf-8") as fh:
        fh.write("\n---\n\nVisual briefs, drafted after the fact\n\n")
        for suggestion in batch["suggestions"]:
            brief = suggestion.get("brief")
            if not brief:
                continue
            fh.write(f"## {suggestion['id']}\n"
                     f"  Headline:    {brief['headline']}\n"
                     f"  Caption:     {brief['caption']}\n"
                     f"  Headline DE: {brief['headline_de']}\n"
                     f"  Caption DE:  {brief['caption_de']}\n"
                     f"  Visual:      {brief['visual_direction']}\n"
                     f"  Purpose:     {brief['purpose']}\n"
                     f"  Feeling:     {brief['target_feeling']}\n\n")


def collect(api_key, system_text, prompt_builder, want, existing_texts, drop_checks,
            flag_checks, used_sources, label):
    """Request `want` suggestions, dropping any that fail a mechanical check.

    A dropped suggestion is re-requested, never softened. That is the skill's
    own rule for a broken hard rule.
    """
    kept, dropped_log = [], []
    seen = set(existing_texts)

    for attempt in range(1 + config.MAX_REGENERATION_ROUNDS):
        need = want - len(kept)
        if need <= 0:
            break
        if attempt:
            print(f"  {label}: re-requesting {need} after drops (round {attempt + 1})")
        batch = call_claude(
            api_key,
            system_text,
            prompt_builder(need, [k["text"] for k in kept]),
        )

        for suggestion in batch:
            text = (suggestion.get("text") or "").strip()
            reasons = []
            if not text:
                reasons.append("empty text")
            if len(text) > config.MAX_SUGGESTION_CHARS:
                reasons.append(f"over {config.MAX_SUGGESTION_CHARS} chars")
            reasons += violations(text, drop_checks)
            key = normalize(text)
            if key in seen:
                reasons.append("duplicate of an existing line")

            source = suggestion.get("source_id")
            if suggestion.get("type") == "rewrite":
                if not source:
                    reasons.append("rewrite with no source_id")
                elif source in used_sources:
                    reasons.append("source already used")

            if reasons:
                dropped_log.append({"text": text, "reasons": reasons})
                continue

            seen.add(key)
            if source:
                used_sources.add(source)
            suggestion["text"] = text
            suggestion["flags"] = sorted(
                set(f for f in (suggestion.get("flags") or []) if f)
                | set(violations(text, flag_checks))
            )
            kept.append(suggestion)
            if len(kept) == want:
                break

    return kept[:want], dropped_log


# --- output ----------------------------------------------------------------

def render_batch(week_label, run_date, generated_at, ranking_basis, suggestions, dropped):
    lines = [
        f"# Week {int(week_label.split('-W')[1])} batch, {run_date}",
        "",
        f"Ranking basis: {ranking_basis}",
        f"Generated: {generated_at}",
        "Status: unreviewed",
        "",
        "Advisory draft. A human reviews every line before anything goes live.",
        "Tick one box per suggestion, then hand this file to a chat session.",
        "",
    ]

    for suggestion in suggestions:
        heading = f"## {suggestion['id']}  {suggestion['type']}"
        if suggestion.get("source_id"):
            heading += f"  from {suggestion['source_id']}"
        lines += [
            heading,
            "[ ] copy   [ ] image   [ ] cut",
            "",
            suggestion["text"],
            "",
            f"Theme: {suggestion['theme']}",
            f"Why: {suggestion['rationale']}",
            f"Flags: {', '.join(suggestion['flags']) if suggestion['flags'] else 'none'}",
            "Compliance: unapproved",
            "",
        ]
        brief = suggestion.get("brief")
        if brief:
            lines += [
                "Visual brief, drafted in advance in case this one is picked:",
                f"  Headline:  {brief['headline']}",
                f"  Caption:   {brief['caption']}",
                f"  Headline DE: {brief['headline_de']}",
                f"  Caption DE:  {brief['caption_de']}",
                f"  Visual:    {brief['visual_direction']}",
                f"  Purpose:   {brief['purpose']}",
                f"  Feeling:   {brief['target_feeling']}",
                "",
            ]

    if dropped:
        lines += [
            "---",
            "",
            f"## Dropped before review ({len(dropped)})",
            "",
            "These failed a mechanical voice check and were regenerated rather than",
            "softened. Listed so a false positive in the check patterns stays visible.",
            "",
        ]
        for item in dropped:
            lines.append(f"- {', '.join(item['reasons'])}: {item['text'][:120]}")
        lines.append("")

    return "\n".join(lines)


def main():
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

    now = datetime.now(TZ)
    year, week, _ = now.isocalendar()
    week_label = f"{year}-W{week:02d}"
    batch_md = os.path.join(BATCH_DIR, f"{week_label}.md")
    batch_json = os.path.join(BATCH_DIR, f"{week_label}.json")

    pool = read_json(POOL_FILE, None)
    if pool is None:
        sys.exit(
            f"ERROR: {os.path.relpath(POOL_FILE, REPO_ROOT)} not found.\n"
            "Run rank.py against a downloaded X archive and commit the result."
        )

    used = read_json(USED_FILE, {"ids": {}})
    rejected = read_json(REJECTED_FILE, {"ids": {}})
    evergreen_texts = load_evergreen_texts(os.path.join(REPO_ROOT, config.EVERGREEN_POOL))

    blocked = set(used.get("ids", {})) | set(rejected.get("ids", {}))
    available = [i for i in pool["items"] if i["id"] not in blocked]
    shortlist = available[: config.SHORTLIST_SIZE]
    reference = shortlist[: config.REFERENCE_POOL_SIZE]

    print(f"Now: {now:%Y-%m-%d %H:%M %Z} | week {week_label}")
    print(f"Pool: {len(pool['items'])} eligible, {len(blocked)} used or rejected, {len(available)} available")
    print(f"Shortlist: {len(shortlist)} | reference set: {len(reference)}")
    print(f"Target: {config.REWRITES} rewrites + {config.NET_NEW} net new")
    print(f"Ranking basis: {pool['ranking_basis']}")

    if len(shortlist) < config.REWRITES:
        sys.exit(
            f"ERROR: only {len(shortlist)} shortlist items for {config.REWRITES} rewrites.\n"
            "Re-run rank.py against a fresh archive, or lower config.REWRITES."
        )

    if os.path.exists(batch_md):
        print(f"{os.path.relpath(batch_md, REPO_ROOT)} already exists.")
        # A batch can predate briefs, or the brief call can have failed on the
        # run that made it. Filling those in is not the same as regenerating:
        # the suggestions are untouched, so anything already reviewed against
        # them stays valid.
        backfill_briefs(batch_json, batch_md, dry_run)
        return

    if dry_run:
        print("\nDRY_RUN enabled. No API call, so this does not test the API key.")
        print(f"Would write {os.path.relpath(batch_md, REPO_ROOT)}")
        print("\nShortlist head:")
        for item in shortlist[:5]:
            print(f"  [{item['id']}] {item['score']:>9}  {' '.join(item['text'].split())[:78]}")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set.")

    system_text = build_system_text()

    drop_checks = compile_checks(config.DROP_CHECKS)
    flag_checks = compile_checks(config.FLAG_CHECKS)
    used_sources = set(used.get("ids", {}))

    print("\nRewrites:")
    rewrites, dropped_a = collect(
        api_key, system_text,
        lambda need, avoid: rewrite_prompt(need, shortlist, avoid),
        config.REWRITES, evergreen_texts, drop_checks, flag_checks,
        used_sources, "rewrites",
    )

    print("\nNet new:")
    existing = set(evergreen_texts) | {normalize(r["text"]) for r in rewrites}
    net_new, dropped_b = collect(
        api_key, system_text,
        lambda need, avoid: new_prompt(need, reference, avoid),
        config.NET_NEW, existing, drop_checks, flag_checks,
        used_sources, "net new",
    )

    suggestions = rewrites + net_new
    if not suggestions:
        sys.exit("ERROR: every suggestion failed a check. Nothing written.")
    for index, suggestion in enumerate(suggestions, start=1):
        suggestion["id"] = f"S{index:02d}"
    dropped = dropped_a + dropped_b

    ranking_basis = pool["ranking_basis"]
    if pool.get("ranking_is_weak_proxy"):
        ranking_basis += ", weak proxy, no impression data"

    # A brief for every line, not just the ones that will be picked. Which
    # ones become images is a decision taken later, on the review board, and
    # the brief has to be sitting there when it is taken.
    briefs = {}
    if config.BRIEFS:
        print(f"\nDrafting {len(suggestions)} visual briefs...")
        briefs = collect_briefs(api_key, brief_system_text(system_text), suggestions)
        print(f"  {len(briefs)} drafted")
        for suggestion in suggestions:
            suggestion["brief"] = briefs.get(suggestion["id"])

    os.makedirs(BATCH_DIR, exist_ok=True)
    with open(batch_md, "w", encoding="utf-8") as fh:
        fh.write(render_batch(
            week_label,
            now.strftime("%Y-%m-%d"),
            now.strftime("%Y-%m-%d %H:%M %Z"),
            ranking_basis,
            suggestions,
            dropped,
        ))

    write_json(batch_json, {
        "week": week_label,
        "generated_at": now.strftime("%Y-%m-%d %H:%M %Z"),
        "ranking_basis": ranking_basis,
        "status": "unreviewed",
        "batch_file": os.path.relpath(batch_md, REPO_ROOT),
        "suggestions": [
            {
                "id": s["id"],
                "type": s["type"],
                "source_id": s.get("source_id"),
                "text": s["text"],
                "theme": s["theme"],
                "rationale": s["rationale"],
                "flags": s["flags"],
                "compliance": "unapproved",
                "brief": briefs.get(s["id"]),
            }
            for s in suggestions
        ],
        "brief_defaults": {
            "platform": config.BRIEF_PLATFORM,
            "languages": config.BRIEF_LANGUAGES,
            "priority": config.BRIEF_PRIORITY,
            "due_days": config.BRIEF_DUE_DAYS,
            "image_spec": config.BRIEF_IMAGE_SPEC,
        },
        "dropped_count": len(dropped),
    })

    # Only rewrite sources are burned. Ids shown to the model as voice
    # reference stay available, otherwise the strongest tweets in the archive
    # would be spent as reference material inside a month.
    used.setdefault("ids", {})
    for suggestion in suggestions:
        if suggestion.get("source_id"):
            used["ids"].setdefault(suggestion["source_id"], week_label)
    write_json(USED_FILE, used)
    if not os.path.exists(REJECTED_FILE):
        write_json(REJECTED_FILE, {"ids": {}})

    print(f"\n{len(rewrites)} rewrites + {len(net_new)} net new, {len(dropped)} dropped")
    flagged = [s["id"] for s in suggestions if s["flags"]]
    print(f"Flagged for compliance: {', '.join(flagged) if flagged else 'none'}")
    print(f"Wrote {os.path.relpath(batch_md, REPO_ROOT)}")
    print(f"Wrote {os.path.relpath(batch_json, REPO_ROOT)}")
    print("Every line is at Compliance: unapproved. Nothing is postable yet.")


if __name__ == "__main__":
    main()
