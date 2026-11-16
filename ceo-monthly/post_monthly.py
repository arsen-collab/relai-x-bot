#!/usr/bin/env python3
"""
CEO monthly bot - one approved tweet a month on Julian's personal X account.

Posts config.TEMPLATE for the company due this month, on the first Tuesday at
13:58 Europe/Zurich by default. Nothing posts without a recorded human
approval for that month's exact text.

Rotation:
  The company due is (months since START) modulo (active companies). Derived
  from the date, so a missed run or a redeploy cannot break the order, and
  there is no rotation state to keep.

Approval:
  APPROVAL_LEAD_DAYS before the post date a Slack message goes to Arsen with
  the exact text, company, date and a BitcoinTreasuries reminder. Approving
  is a workflow run (action approve) that commits the month and a hash of the
  exact text to approvals.txt. The hash means a wording or company change
  after approval cancels it. No approval by the post time: no post, and a
  Slack message says so.

Reliability, same pattern as the other bots:
  Four cron slots a day, any of which can act. Every other day each run exits
  before any API call. Before posting, posted.txt is checked, then the
  account's recent posts for the exact text. notices.txt records which Slack
  messages already went out, so four slots send one message, not four.

Modes (first argument, or MODE):
  run             the scheduled path: send a request, post, or send a notice
  preview         next 15 months with dates, company, tweet and status
  approve MONTH   record approval for MONTH (YYYY-MM)
  post_now MONTH  post MONTH's tweet now. Still needs its approval
  verify_handles  look the configured handles up on X

DRY_RUN defaults to on. Only DRY_RUN=false (or 0, no) acts for real.
"""

import hashlib
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

sys.path.insert(0, HERE)
sys.path.append(REPO_ROOT)
import config  # noqa: E402
import x_api  # noqa: E402
from slack_api import post_to_slack  # noqa: E402

TZ = ZoneInfo("Europe/Zurich")

APPROVALS_FILE = os.path.join(HERE, "approvals.txt")
POSTED_FILE = os.path.join(HERE, "posted.txt")
NOTICES_FILE = os.path.join(HERE, "notices.txt")

# Must match .github/workflows/ceo_monthly.yml. 11:58 UTC is 13:58 in CEST,
# 12:58 UTC is 13:58 in CET; the later two are backups for runner failures.
SLOT_UTC_TIMES = {1: (11, 58), 2: (12, 58), 3: (13, 41), 4: (14, 37)}

# The preview warns when no slot lands within this many minutes after the
# post time.
SLOT_COVER_MINUTES = 60

PREVIEW_MONTHS = 15


# --------------------------------------------------------------------------
# Months
# --------------------------------------------------------------------------

def parse_month(text):
    try:
        year, month = (int(part) for part in text.strip().split("-"))
    except (ValueError, AttributeError):
        sys.exit(f"ERROR: month must be YYYY-MM, got {text!r}.")
    if not 1 <= month <= 12:
        sys.exit(f"ERROR: month must be YYYY-MM, got {text!r}.")
    return (year, month)


def month_str(ym):
    return f"{ym[0]:04d}-{ym[1]:02d}"


def add_months(ym, n):
    total = ym[0] * 12 + (ym[1] - 1) + n
    return (total // 12, total % 12 + 1)


def months_since_start(ym):
    return (ym[0] - config.START_YEAR) * 12 + (ym[1] - config.START_MONTH)


# --------------------------------------------------------------------------
# Rotation
# --------------------------------------------------------------------------

def active_companies(companies=None):
    return [c for c in (companies or config.COMPANIES) if c.get("active")]


def company_for(ym, companies=None):
    index = months_since_start(ym)
    if index < 0:
        raise ValueError(f"{month_str(ym)} is before the start month.")
    active = active_companies(companies)
    if not active:
        raise ValueError("No active companies in config.COMPANIES.")
    return active[index % len(active)]


def build_tweet(company, template=None):
    return (template or config.TEMPLATE).format(
        handle=company["handle"], name=company["name"])


def validate_config():
    """Stops the run on a config mistake rather than posting a broken tweet."""
    if "{handle}" not in config.TEMPLATE:
        sys.exit("ERROR: config.TEMPLATE has no {handle}.")
    active = active_companies()
    if not active:
        sys.exit("ERROR: no active companies in config.COMPANIES.")
    seen = set()
    for company in active:
        handle = company.get("handle", "")
        if not handle.startswith("@") or len(handle) < 2:
            sys.exit(f"ERROR: {company['name']} is active but its handle {handle!r} "
                     "does not start with @.")
        if handle.lower() in seen:
            sys.exit(f"ERROR: {handle} appears twice among active companies.")
        seen.add(handle.lower())
        try:
            tweet = build_tweet(company)
        except (KeyError, IndexError) as exc:
            sys.exit(f"ERROR: config.TEMPLATE uses an unknown placeholder: {exc}")
        if len(tweet) > config.MAX_CHARS:
            sys.exit(f"ERROR: tweet for {company['name']} is {len(tweet)} chars.")
    if not 1 <= config.POST_WEEK <= 4:
        sys.exit("ERROR: config.POST_WEEK must be 1 to 4.")


# --------------------------------------------------------------------------
# Schedule
# --------------------------------------------------------------------------

def post_datetime(ym):
    """The POST_WEEK-th POST_WEEKDAY of the month at POST_TIME, Zurich time.
    zoneinfo applies CET or CEST for that date, so DST needs no handling."""
    first = date(ym[0], ym[1], 1)
    offset = (config.POST_WEEKDAY - first.weekday()) % 7
    day = 1 + offset + 7 * (config.POST_WEEK - 1)
    return datetime(ym[0], ym[1], day, config.POST_HOUR, config.POST_MINUTE, tzinfo=TZ)


def request_date(ym):
    return post_datetime(ym).date() - timedelta(days=config.APPROVAL_LEAD_DAYS)


def post_time_covered(ym):
    """Whether some cron slot lands within SLOT_COVER_MINUTES after the post
    time on the post date. False means the time in config has moved away
    from the workflow's slots and the post would go out late or not at all."""
    target = post_datetime(ym)
    d = target.date()
    latest = target + timedelta(minutes=SLOT_COVER_MINUTES)
    for h, m in SLOT_UTC_TIMES.values():
        local = datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc).astimezone(TZ)
        if target <= local <= latest:
            return True
    return False


def human_date(moment):
    return f"{moment:%A} {moment.day} {moment:%B %Y}"


# --------------------------------------------------------------------------
# Logs: approvals, posts, notices. Committed text files, one line each.
# --------------------------------------------------------------------------

def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _entries(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            rows.append(line.split())
    return rows


def is_approved(ym, text):
    key, digest = month_str(ym), text_hash(text)
    return any(len(r) >= 2 and r[0] == key and r[1] == digest
               for r in _entries(APPROVALS_FILE))


def is_posted(ym):
    key = month_str(ym)
    return any(r[0] == key for r in _entries(POSTED_FILE))


def has_notice(ym, kind):
    key = month_str(ym)
    return any(len(r) >= 2 and r[0] == key and r[1] == kind
               for r in _entries(NOTICES_FILE))


def append_line(path, line):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line.rstrip("\n") + "\n")


def commit(paths, message, fatal=False):
    """Push a log change. Non-fatal for post and notice logs: the account
    check and a repeat Slack message are the fallbacks. Fatal for approvals,
    which must never be silently lost."""
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email",
                        "41898282+github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add"] + list(paths), check=True)
        subprocess.run(["git", "commit", "-m", message], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Committed and pushed.")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        if fatal:
            sys.exit(f"ERROR: could not push: {exc}")
        print(f"WARNING: could not push: {exc}")


# --------------------------------------------------------------------------
# Slack
# --------------------------------------------------------------------------

def workflow_url():
    repo = os.environ.get("GITHUB_REPOSITORY") or config.REPO
    return f"https://github.com/{repo}/actions/workflows/{config.WORKFLOW_FILE}"


def request_message(ym, company, tweet):
    when = post_datetime(ym)
    return "\n".join([
        f"*Julian's monthly X post: approval needed for {when:%B %Y}*",
        f"Post date: {human_date(when)}, {when:%H:%M} Zurich",
        f"Company: {company['name']} ({company['handle']})",
        "Tweet:",
        f">{tweet}",
        "",
        f"Before approving, confirm {company['name']} still holds no Bitcoin: "
        f"{config.TREASURY_CHECK_URL}",
        f"To approve: {workflow_url()} > Run workflow > action approve, "
        f"month {month_str(ym)}, untick dry run.",
        "No approval by the post time means no post. Changing the wording or "
        "the company after approving cancels the approval.",
    ])


def skipped_message(ym, company, tweet):
    when = post_datetime(ym)
    return "\n".join([
        f"*Julian's monthly X post for {when:%B %Y} did not go out: not approved.*",
        f"Company: {company['name']} ({company['handle']})",
        f">{tweet}",
        "",
        "The rotation moves on next month. To post this one anyway, approve it, "
        f"then run action post_now, month {month_str(ym)}: {workflow_url()}",
    ])


def missed_message(ym, company, tweet):
    when = post_datetime(ym)
    return "\n".join([
        f"*Julian's monthly X post for {when:%B %Y} was approved but did not go out.*",
        f"No scheduled run got through on {human_date(when)} before "
        f"{config.HARD_CUTOFF_HOUR}:00 Zurich.",
        f">{tweet}",
        "",
        f"To post it now: action post_now, month {month_str(ym)}, untick dry run: "
        f"{workflow_url()}",
    ])


def posted_message(ym, tweet, tweet_id):
    link = f"https://x.com/i/status/{tweet_id}" if tweet_id else "(already on the account)"
    return f"*Julian's monthly X post for {post_datetime(ym):%B %Y} is out.*\n>{tweet}\n{link}"


def send_slack(text):
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        sys.exit("ERROR: SLACK_WEBHOOK_URL is not set.")
    post_to_slack(webhook_url, text)
    print("Sent to Slack.")


def send_notice(ym, kind, text, dry_run):
    print("--- Slack")
    print(text)
    print("---")
    if dry_run:
        print("DRY_RUN enabled. Not sent, not logged.")
        return
    send_slack(text)
    append_line(NOTICES_FILE, f"{month_str(ym)}  {kind}  {date.today():%Y-%m-%d}")
    commit([NOTICES_FILE], f"CEO monthly: {kind} notice for {month_str(ym)}")


# --------------------------------------------------------------------------
# Posting
# --------------------------------------------------------------------------

def guard_not_relai_account():
    """The workflow maps Julian's secrets onto the names x_api reads. If they
    were ever set to @relai_app's token, this bot would post to the company
    account. Compared, never printed."""
    relai = os.environ.get("RELAI_ACCESS_TOKEN")
    if relai and relai == os.environ.get("ACCESS_TOKEN"):
        sys.exit("ERROR: CEO_ACCESS_TOKEN is @relai_app's token. Nothing posted.")


def publish(ym, tweet, dry_run):
    print("--- Tweet")
    print(tweet)
    print("---")
    if dry_run:
        print("DRY_RUN enabled. Nothing posted.")
        return

    guard_not_relai_account()
    creds = x_api.get_credentials()

    if x_api.already_posted(creds, tweet, config.RECENT_POSTS_TO_CHECK):
        print("Already on the account. Logging it, not posting again.")
        tweet_id = None
    else:
        tweet_id = x_api.post(creds, tweet)
        if tweet_id:
            print(f"Posted: https://x.com/i/status/{tweet_id}")

    append_line(POSTED_FILE, f"{month_str(ym)}  {date.today():%Y-%m-%d}  "
                             f"{tweet_id or 'on-account'}  {tweet}")
    commit([POSTED_FILE], f"CEO monthly: posted {month_str(ym)}")
    if os.environ.get("SLACK_WEBHOOK_URL"):
        send_slack(posted_message(ym, tweet, tweet_id))


# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------

def maybe_request(ym, today, dry_run):
    if not request_date(ym) <= today < post_datetime(ym).date():
        return
    company = company_for(ym)
    tweet = build_tweet(company)
    if is_approved(ym, tweet):
        print(f"{month_str(ym)} is already approved. No request needed.")
        return
    if has_notice(ym, "request"):
        print(f"Approval request for {month_str(ym)} already sent.")
        return
    send_notice(ym, "request", request_message(ym, company, tweet), dry_run)


def maybe_post(ym, now, dry_run):
    when = post_datetime(ym)
    if now.date() < when.date():
        print(f"{month_str(ym)} posts {human_date(when)} {when:%H:%M}. Nothing to do today.")
        return
    if is_posted(ym):
        print(f"{month_str(ym)} already posted.")
        return
    if has_notice(ym, "skipped") or has_notice(ym, "missed"):
        print(f"{month_str(ym)} was already closed without posting.")
        return
    if now < when:
        print(f"Before {when:%H:%M} on the post day. Too early.")
        return

    company = company_for(ym)
    tweet = build_tweet(company)

    if not is_approved(ym, tweet):
        print("Not approved. Not posting.")
        send_notice(ym, "skipped", skipped_message(ym, company, tweet), dry_run)
        return

    if now.date() != when.date() or now.hour >= config.HARD_CUTOFF_HOUR:
        print("Approved, but past the post day's cutoff. Not posting.")
        send_notice(ym, "missed", missed_message(ym, company, tweet), dry_run)
        return

    publish(ym, tweet, dry_run)


def run_scheduled(now, dry_run):
    validate_config()
    this_month = (now.year, now.month)
    for ym in (this_month, add_months(this_month, 1)):
        if months_since_start(ym) >= 0:
            maybe_request(ym, now.date(), dry_run)
    if months_since_start(this_month) >= 0:
        maybe_post(this_month, now, dry_run)
    else:
        print(f"Rotation starts {config.START_YEAR}-{config.START_MONTH:02d}.")


def preview(from_ym):
    validate_config()
    start = from_ym
    if months_since_start(start) < 0:
        start = (config.START_YEAR, config.START_MONTH)
    active = active_companies()
    print(f"{len(active)} active companies. Template: {config.TEMPLATE!r}")
    print()
    for n in range(PREVIEW_MONTHS):
        ym = add_months(start, n)
        when = post_datetime(ym)
        tweet = build_tweet(company_for(ym))
        if is_posted(ym):
            status = "posted"
        elif is_approved(ym, tweet):
            status = "approved"
        else:
            status = "not approved"
        warn = "" if post_time_covered(ym) else "  WARNING: no cron slot covers this time"
        print(f"{month_str(ym)}  {when:%a %d %b %Y %H:%M %Z}  "
              f"request {request_date(ym):%d %b}  [{status}]  {tweet}{warn}")


def approve(ym, dry_run):
    validate_config()
    if months_since_start(ym) < 0:
        sys.exit(f"ERROR: {month_str(ym)} is before the start month.")
    company = company_for(ym)
    tweet = build_tweet(company)
    when = post_datetime(ym)
    print(f"Month: {month_str(ym)}, posts {human_date(when)} {when:%H:%M} Zurich")
    print(f"Company: {company['name']} ({company['handle']})")
    print(f">{tweet}")
    if is_approved(ym, tweet):
        print("Already approved. Nothing to do.")
        return
    if dry_run:
        print("DRY_RUN enabled. Not approved. Untick dry run to approve.")
        return
    actor = os.environ.get("GITHUB_ACTOR", "local")
    append_line(APPROVALS_FILE, f"{month_str(ym)}  {text_hash(tweet)}  {actor}  {tweet}")
    commit([APPROVALS_FILE], f"CEO monthly: {actor} approved {month_str(ym)}", fatal=True)
    print(f"Approved by {actor}.")
    if has_notice(ym, "skipped") or has_notice(ym, "missed"):
        print(f"The scheduled post for {month_str(ym)} already closed. "
              "Use action post_now to post it.")


def post_now(ym, dry_run):
    validate_config()
    if months_since_start(ym) < 0:
        sys.exit(f"ERROR: {month_str(ym)} is before the start month.")
    tweet = build_tweet(company_for(ym))
    if is_posted(ym):
        print(f"{month_str(ym)} already posted. Nothing to do.")
        return
    if not is_approved(ym, tweet):
        print(f">{tweet}")
        sys.exit(f"ERROR: {month_str(ym)} is not approved for this exact text. "
                 "Run action approve first.")
    publish(ym, tweet, dry_run)


def verify_handles(dry_run):
    entries = [c for c in config.COMPANIES if c.get("handle")]
    for c in config.COMPANIES:
        if not c.get("handle"):
            print(f"  {c['name']}: no handle configured")
    if dry_run:
        print("DRY_RUN enabled. Untick dry run to look these up on X (one read):")
        for c in entries:
            print(f"  {c['name']}: {c['handle']}")
        return
    creds = x_api.get_credentials()
    names = ",".join(c["handle"].lstrip("@") for c in entries)
    result = x_api._request(
        "GET", f"{x_api.API}/users/by", creds,
        query_params={"usernames": names, "user.fields": "verified,verified_type"},
    )
    if "_error" in result:
        sys.exit(f"ERROR: lookup failed: {result['_error']} {result['_detail']}")
    found = {u["username"].lower(): u for u in result.get("data") or []}
    for c in entries:
        user = found.get(c["handle"].lstrip("@").lower())
        if not user:
            print(f"  NOT FOUND  {c['name']}: {c['handle']}")
            continue
        badge = user.get("verified_type") or ("verified" if user.get("verified") else "none")
        print(f"  {c['name']}: @{user['username']} | display name {user.get('name')!r} "
              f"| badge {badge}{'' if c.get('active') else ' | inactive'}")
    print("A gold badge shows as 'business'. Anything else needs a manual look.")


def main():
    args = sys.argv[1:]
    mode = (args[0] if args else os.environ.get("MODE") or "run").strip()
    month_arg = args[1] if len(args) > 1 else os.environ.get("MONTH", "").strip()
    dry_run = os.environ.get("DRY_RUN", "true").lower() not in ("0", "false", "no")

    now = datetime.now(TZ)
    print(f"Now: {now:%Y-%m-%d %H:%M %Z} | mode {mode} | slot {os.environ.get('SLOT', '0')} "
          f"| dry run {'on' if dry_run else 'off'}")

    if mode == "run":
        run_scheduled(now, dry_run)
    elif mode == "preview":
        preview(parse_month(month_arg) if month_arg else (now.year, now.month))
    elif mode in ("approve", "post_now"):
        if not month_arg:
            sys.exit(f"ERROR: {mode} needs a month, YYYY-MM.")
        (approve if mode == "approve" else post_now)(parse_month(month_arg), dry_run)
    elif mode == "verify_handles":
        verify_handles(dry_run)
    else:
        sys.exit(f"ERROR: unknown mode {mode!r}.")


if __name__ == "__main__":
    main()
