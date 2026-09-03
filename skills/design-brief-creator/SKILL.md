---
name: design-brief-creator
description: Write Relai design briefs and create them as tasks on Paula's Notion Design board. Use this skill whenever Arsen pitches a visual idea, asks for a design brief, wants a post turned into a graphic or carousel, marks a tweet or line as repurpose-into-image, or asks to send something to Paula. Also use it as a visual brainstorming partner when Arsen shares a Figma link or an image and wants directions or a critique. Trigger it even on short asks like "make this a graphic" or "send to Paula".
---

# Relai design brief creator

Writes briefs for Paula Boehme and files them on the Relai Design board in Notion.

## Workflow

1. Do not ask about platform, language, priority or due date. The defaults
   below cover them. Take initiative on every standard detail.
2. Draft the brief. Sections, in this order and no others:
   - Purpose
   - Target feeling
   - Format
   - Headline and copy
   - Visual direction
   - Image specs
   No font references, Paula handles that. No safe zone callouts unless asked. No compliance section inside the brief.
3. Create the Notion page. Show the brief in the reply alongside the URL,
   not before it. Arsen marking a line as image is the approval; a second
   round of approving text he has already chosen is a step he does not want.
4. Reply with the direct task URL immediately, then the brief itself so he
   can read what went out.
5. If he wants it changed, update the page with notion-update-page rather
   than creating a second one.

Exception: ask first when the line carries a compliance flag. That changes
whether the asset can ship, not just how it reads.

## Visual rules

Every brief follows these unless Arsen overrides:

- One bold short headline.
- One simple visual device: chart, comparison, prop, or code snippet. Never two combined. Never illustration-heavy.
- Generous white space.
- One accent color maximum, Relai orange.
- Relai logo bottom right.
- Minimal elements so Paula can produce fast.

Data in captions, not on the image. The image carries one headline and one visual device. All stats and context go in the caption.

Image specs: always 1080 x 1350 px, Instagram feed portrait, for every platform. Never square. Never offer multiple sizes unless asked.

Carousels: always include a standalone single-image version for WhatsApp and X, using the main carousel image plus one additional element that you propose. Note the other slides as not for standalone posting.

Language: English and German together, both in the same brief. Write the
English headline and caption, then the German. German is not a translation
of the English, it is the same idea written natively.

## Compliance, flag in chat and keep drafting

Flags do not block the brief. Raise them in the reply, not inside the brief.

- MiCA and EU retail: forward-return framing, directive language.
- Savings terminology: the term describes recurring DCA purchases, never a product, account, or deposit. No interest, yield, capital protection, or safety claims. Risk disclaimer must be visible pre-purchase. New uses need prior written compliance approval.
- Trademarks: Apple terms such as Face ID and Touch ID become "face or fingerprint login". Branded products become generic equivalents. Euro banknote imagery triggers ECB reproduction rules.
- Marketing numbers must come from Relai's actual backtest tool or verified data. Never approximate. Flag discrepancies before the brief is final.

## Notion

Database / data source id: c33f79ad-bc09-490b-8b95-32578426c036
Owner (Arsen): f0e5090d-ed80-4c74-88ff-1ab60b4c1b64
Assignee (Paula): 1abd872b-594c-819a-975e-0002e5b89f57

- Use `data_source_id` as parent, not `database_id`. The database_id format fails.
- Platform: JSON array string, for example '["IG", "LI", "WA"]'. Valid values: LI, IG, WA, Blog, Newsletter. There is no X option, so X-sourced content goes in as IG plus whatever else applies.
- Language: JSON array string with flag emoji, for example '["🇬🇧 EN", "🇩🇪 DE"]'.
- Due date: `date:Due (mandatory):start` in YYYY-MM-DD, `is_datetime` set to 0.
- Status: To Do. Type: Design request.
- Full brief goes in Notes / context as a plain text block.
- To update an existing page use notion-update-page and rewrite the whole Notes / context block rather than patching lines.

## Defaults when unspecified

Apply these silently. They are not questions.

- Platform: IG
- Language: EN and DE, both
- Priority: Medium
- Image size: 1080 x 1350 portrait
- Due: three days from the day the brief is filed, not from the batch date

## Entry point from the weekly X batch

When a suggestion in a `weekly-suggester/batches/` file is marked image:

- Purpose is the suggestion's stated theme.
- Headline is the suggestion text, tightened to fit one line on the image if needed.
- Note the source in the brief: repurposed from X batch, week number, suggestion id.
- The brief is already drafted. generate.py writes one for every suggestion
  at batch time, so by the time Arsen ticks image he has read it on the review
  board and the tick is the approval. Do not redraft it from scratch.
- Take the brief from the decisions file. If he edited it there, his version
  wins outright. If he left a note, apply it to the drafted brief.
- Only stop to ask when the note contradicts the brief in a way you cannot
  resolve, or when the line carries a compliance flag.
