# Set up your own evergreen X bot

This guide gives you a bot that posts one of your best old tweets to your own
X account every two days, at a sensible morning hour, with no work after
setup.

It copies the bot Relai already runs for @relai_app. The code is public at
<https://github.com/arsen-collab/relai-x-bot>. You get your own private copy;
nothing in Relai's repo changes and nobody else gets access to your account.

**How it works, in one picture:** your old tweets go into a text file. GitHub
runs a small program on a timer. The program picks the next line from the
file and posts it to your X account using keys only you hold.

**Time:** about 45 minutes of your time, spread over two sittings, because X
takes a day or two to prepare your archive.

**You need:**

- A Mac with the Claude desktop app, using the **Code** tab
- A GitHub account
- Your X account, and its password
- A payment card for X's developer account (posting costs a few cents a post)

**Rules for the whole guide:**

- Each step says what you do yourself and what to paste into Claude. Paste the
  grey boxes into Claude exactly as written.
- **Never paste a key, token or password into Claude.** Keys go only into
  GitHub's settings page, in step 5. Claude will never need to see them.
- Start each new Claude chat inside your bot's folder once step 3 is done, so
  Claude sees the project.

---

## Step 1. Ask X for your archive (5 minutes, then wait)

Do this first, because X needs time to prepare it.

Your archive is a zip file of everything on your account. We only need the
tweets in it, but X only offers the whole thing.

1. On x.com, click **More** (the three dots in the left menu), then
   **Settings and privacy**.
2. Click **Your account**, then **Download an archive of your data**.
3. Type your password, then the code X sends you by email or text.
4. Click **Request archive**.
5. Wait. X says it can take 24 hours or longer. You get a notification when
   it is ready. Carry on with steps 2 to 5 while you wait.

---

## Step 2. Get the tools ready (10 minutes)

Claude needs two free tools on your Mac to copy the bot to your GitHub: `git`
(copies code) and `gh` (talks to GitHub for you).

Open the Claude desktop app, go to the **Code** tab, start a new session in
your home folder, and paste:

```
I want to set up a small bot. First, check whether git, the GitHub CLI (gh)
and python3 are installed on this Mac. Install whatever is missing, explaining
each step in plain words. Then log me in to GitHub with "gh auth login". I
will do the browser login myself; just tell me when to click what. Do not ask
me for any password or token in this chat.
```

When it asks you to log in, a browser window opens. Log in to GitHub there
and click **Authorize**. That is the only part you do by hand.

---

## Step 3. Make your own copy of the bot (5 minutes)

Paste this into Claude. Replace `YOURHANDLE` with your X handle, without the
@, in both places.

```
Make me my own private copy of the evergreen X bot from the public repo
https://github.com/arsen-collab/relai-x-bot. Read that repo's CLAUDE.md first
so you understand how the bot works.

Do this:

1. Create a new PRIVATE GitHub repo under my account called YOURHANDLE-x-bot,
   and a folder for it in ~/Documents. Do not fork; a fork of a public repo
   cannot be private. Make a fresh repo and copy files in.
2. Copy only these files, keeping their folders:
   post_evergreen.py, x_api.py, find_evergreen_candidates.py,
   .github/workflows/evergreen.yml, tools/evergreen_picker.html, .gitignore.
   Do not copy anything else: not evergreen.txt, fresh.txt, the other
   workflows, the suggesters, the skills, or Relai's CLAUDE.md.
3. Create an empty evergreen.txt containing only this comment line:
   # My evergreen pool. One post per line.
4. In post_evergreen.py:
   - set SHUFFLE_SEED to "YOURHANDLE-evergreen-v1"
   - change the "Posted:" link from x.com/relai_app to x.com/YOURHANDLE
   - change the docstring to describe my account, not Relai's
   Change nothing else in the logic.
5. In find_evergreen_candidates.py, change the relai_app link and docstring
   the same way.
6. Write a short CLAUDE.md for my repo: what the bot does, the schedule
   (every 2 days, 09:00 to 13:00 Zurich time), that evergreen.txt is the only
   file I normally edit, that every workflow run should be a dry run first,
   and that the X archive must never be committed.
7. Commit and push. Then switch the Evergreen Tweet workflow off with
   "gh workflow disable", because the pool is still empty and timed runs
   would fail until I add tweets. Show me the repo link when done.
```

Check: open the link Claude gives you. You should see your new repo marked
**Private**.

---

## Step 4. Get your keys from X (15 minutes)

This is the fiddliest step. X's developer site moves its buttons around now
and then, so if a name below does not match exactly, look for the nearest
match, or ask Claude "on developer.x.com, where do I find X now?".

**What you are doing:** telling X "this little program is allowed to post as
me", and getting four keys that prove it. Think of them as four parts of one
house key.

1. Go to <https://developer.x.com> and sign in with your normal X account.
2. Sign up for a developer account. Choose the **pay per use** option. If it
   asks what you will use it for, write something like:
   *"Scheduling posts of my own past tweets to my own account, from a private
   GitHub Action. No data collection, no other accounts."*
3. Add a payment method or buy a small amount of credit when it asks.
   Posting costs a few cents per post. The live price is shown in the
   console.
4. Create a **Project** and an **App** inside it. Any names work, for
   example `my-evergreen-bot`.
5. **Do this before making any keys.** Open your app, find **User
   authentication settings**, and click **Set up** (or **Edit**). Fill in:
   - **App permissions:** Read and write
   - **Type of App:** Web App, Automated App or Bot
   - **Callback URI / Redirect URL:** `https://localhost`
     (it is required but never used)
   - **Website URL:** `https://x.com/YOURHANDLE`

   Click **Save**.

   *Why first:* keys made before this change can only read, not post. It is
   the most common reason a first post fails. If you already made keys, just
   regenerate them after saving.
6. Open the **Keys and tokens** tab.
   - Under **Consumer Keys**, click **Regenerate** (or **Generate**). Copy the
     **API Key** and **API Key Secret** into a note in your password manager.
   - Under **Access Token and Secret**, click **Generate**. Copy both into the
     same note. Check it says **Read and Write** next to them. If it says
     **Read only**, go back to item 5, save, and regenerate.

You now have four values. Keep the browser tab open for the next step.

---

## Step 5. Give the keys to GitHub (5 minutes)

GitHub keeps the keys in a locked box called **Secrets**. The bot can use
them; nobody can read them back, not even you.

1. Open your new repo on github.com.
2. Click **Settings** (top bar of the repo), then in the left menu
   **Secrets and variables**, then **Actions**.
3. Click **New repository secret** and add these four, one at a time. The
   name must match exactly, capitals and underscores included:

| Name | Paste this value |
|---|---|
| `API_KEY` | API Key |
| `API_KEY_SECRET` | API Key Secret |
| `ACCESS_TOKEN` | Access Token |
| `ACCESS_TOKEN_SECRET` | Access Token Secret |

4. Delete the note from your password manager if you like. You can always
   regenerate keys on developer.x.com.

---

## Step 6. Pick your best tweets (20 minutes or more, at your own pace)

When X tells you the archive is ready:

1. Download it and double-click the zip to unzip it. You get a folder.
2. Paste this into Claude, in a session opened in your bot's folder:

```
My X archive is unzipped in my Downloads folder. Open
tools/evergreen_picker.html from this repo in my web browser. Do not read,
copy or move the archive yourself; I will load it in the page.
```

3. In the page, click **Choose archive folder** and pick the unzipped
   folder. Your browser may ask "Upload files?". It is not uploading
   anything; the page runs on your Mac only and reads only your tweets file,
   never your DMs. Click **Upload** to allow it.
4. Go through your tweets:
   - **Keep** (press `K`): good to post again.
   - **Discard** (press `D`): dated, private joke, or just not great.
   - **Edit** (press `E`): fix a word or update an old fact, then keep.
   - **Back** (press `B`): undo the last choice.
5. Settings at the top:
   - **At least N likes**: start at 100. Lower it if you want to see more.
   - **Hide dated tweets**: on by default. It hides tweets with prices, news
     events or words like "today". Switch it off to see them anyway.
6. You can stop and come back. The page remembers your choices in this
   browser.
7. When done, click **Download evergreen.txt**. Aim for at least 50 tweets.
   The bar at the bottom shows how long the pool lasts before a repeat.
8. Paste into Claude:

```
I downloaded evergreen.txt to my Downloads folder. Move it into this repo,
replacing the empty one. Check it loads correctly by running
post_evergreen.load_pool(), and tell me how many lines it has. Make sure no
archive files are in the repo, then commit and push.
```

Then **delete the archive** from Downloads (both the zip and the folder). It
contains your DMs and there is no reason to keep it lying around.

---

## Step 7. Test it (5 minutes)

1. On your repo page on github.com, click **Actions** (top bar).
2. Click **Evergreen Tweet** in the left list. It was switched off in step
   3, so click **Enable workflow** first.
3. Click **Run workflow** on the
   right. Leave **Preview only, do not post** ticked. Click the green
   **Run workflow**.
4. Wait about 20 seconds, click the run, then click **post**, then **Post**.
   You should see one of your tweets between two `---` lines, and
   `DRY_RUN enabled. Nothing posted.`
5. Now the real test. Run it again with **Preview only** **unticked**. A
   manual run posts straight away, whatever the day.
6. Check your X profile. The tweet should be there.

If the real run fails, copy the red error text into Claude and ask what it
means. The usual causes:

- `401` means a key was pasted wrong. Re-paste all four secrets.
- `403` and "not permitted" means read-only keys. Redo step 4, items 5 and 6.
- "credits" or "payment" means the developer account needs credit.

That's it. From now on it posts on its own.

---

## Living with it

- **Adding or removing tweets:** edit `evergreen.txt`, one tweet per line.
  Ask Claude to "add this tweet to my evergreen pool and push", or to
  "remove the line about X". Adding or removing a line reshuffles the order, so
  a tweet that posted recently can come round sooner than usual. That is
  harmless, just expected.
- **Pausing:** on the Actions page, click **Evergreen Tweet**, then the
  **...** menu, then **Disable workflow**. Enable it again the same way.
- **Timing:** GitHub's timer is not exact and can run hours late. The bot
  checks the real Zurich time and skips the day if it is past 20:00, so it
  never posts at night. Four timed runs a posting day give it four chances;
  only one posts.
- **Cost:** a few cents per post, plus a small charge each time the bot
  checks your recent posts so it never posts twice. See live usage on
  developer.x.com.
- **Revoking access:** to cut the bot off instantly, regenerate the keys on
  developer.x.com, or delete the app there.

## One compliance note

If your tweets talk about Relai, or encourage people to buy Bitcoin, they can count as Relai
marketing under MiCA Art. 66, even from a personal account, depending on your
role. Before turning it on, send the final `evergreen.txt` to Guglielmo in
Compliance for a look, the same as Relai's own pool.
