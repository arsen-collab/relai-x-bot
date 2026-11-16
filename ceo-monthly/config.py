"""
CEO monthly bot - every tunable lives here.

A Python module rather than YAML or JSON, same as both suggesters: stdlib
only, and comments can sit next to the values they explain. Edit the values,
not the code in post_monthly.py.

Anything you change here changes public copy on Julian's account. The tweet
text is part of what gets approved each month, so an edit after approval
cancels that month's approval and it has to be approved again.
"""

# The tweet. {handle} is the company's X handle including the @, {name} is
# the company name. Compliance owns this wording; change it here only.
TEMPLATE = "Relai holds more Bitcoin than {handle}"

# The first month of the rotation, and the company it starts with. Month N
# after this posts active company N, counting from 0, modulo the number of
# active companies. Changing this re-times the whole rotation.
START_YEAR = 2026
START_MONTH = 12

# When it posts: the POST_WEEK-th POST_WEEKDAY of the month, at POST_TIME
# Europe/Zurich. Weekday 0 is Monday, so 1 is Tuesday. POST_WEEK 1 to 4.
#
# POST_TIME must stay covered by a cron slot in
# .github/workflows/ceo_monthly.yml. The slots fire from 13:58 local in both
# CET and CEST. Move the time earlier and the workflow needs new slots too;
# `python3 post_monthly.py` with MODE=preview warns when it is not covered.
POST_WEEKDAY = 1
POST_WEEK = 1
POST_HOUR = 13
POST_MINUTE = 58

# Past this local hour on the post day nothing posts, and you get a Slack
# message instead. Same cutoff as the other bots.
HARD_CUTOFF_HOUR = 20

# How many days before the post date the approval request goes to Slack.
APPROVAL_LEAD_DAYS = 3

# How many of the account's recent posts the double-post guard reads. One
# read per posting attempt, pay per use, so not more than needed.
RECENT_POSTS_TO_CHECK = 20

# The rotation, in order. Each entry: name, X handle with the @, active.
# An inactive entry is skipped and the next active one takes its turn.
#
# Toggling active, adding or removing an entry changes how many companies
# are active, which re-maps every future month, not just the next one.
# Run the preview before and after to see the effect.
#
# Handles are as configured on 16 Nov 2026 and have not yet been checked
# against X. Run the workflow with action verify_handles before going live.
COMPANIES = [
    {"name": "Apple", "handle": "@Apple", "active": True},
    {"name": "NVIDIA", "handle": "@nvidia", "active": True},
    {"name": "Microsoft", "handle": "@Microsoft", "active": True},
    {"name": "Google", "handle": "@Google", "active": True},
    {"name": "Amazon", "handle": "@amazon", "active": True},
    {"name": "Meta", "handle": "@Meta", "active": True},
    {"name": "Netflix", "handle": "@netflix", "active": True},
    # No official X account found. Kept for the record, replaced by Visa.
    {"name": "Berkshire Hathaway", "handle": "", "active": False},
    {"name": "Visa", "handle": "@Visa", "active": True},
    {"name": "Walmart", "handle": "@Walmart", "active": True},
    {"name": "Coca-Cola", "handle": "@CocaCola", "active": True},
    {"name": "McDonald's", "handle": "@McDonalds", "active": True},
    {"name": "Disney", "handle": "@Disney", "active": True},
    {"name": "Nike", "handle": "@Nike", "active": True},
    {"name": "Samsung", "handle": "@Samsung", "active": True},
    {"name": "Nestlé", "handle": "@Nestle", "active": True},
]

# Where the approval request points. Only the homepage: no per-company URL
# has been checked.
TREASURY_CHECK_URL = "https://bitcointreasuries.net/"

# Fallback if GITHUB_REPOSITORY is not set, e.g. a local preview.
REPO = "arsen-collab/relai-x-bot"
WORKFLOW_FILE = "ceo_monthly.yml"

MAX_CHARS = 280
