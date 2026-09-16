---
name: add-experience
description: Conversationally add or edit content in experience_bank.json — a new experience/project/activity/education/certification/skill entry, a new bullet on an existing entry, or a tech/one_liner/short value. Use when the user says they want to add, record, log, or update something in the bank, or asks to list or edit existing bank entries. Nothing is written without explicit confirmation.
---

# add-experience

Add or edit entries in `experience_bank.json`. **Nothing is ever written
without the user's explicit confirmation.** The bank is the single source
of truth for every generated resume, so a bad entry propagates silently
into real applications.

## Environment

**Read `.claude/env.local` for the Python interpreter to use** for every
command in this skill. It holds one line: an absolute path to the
interpreter of the project's configured environment. Use whatever path it
contains — referred to as `<PY>` below.

**Never hardcode an interpreter path in this file.** The path is
machine- and username-specific and is git-ignored for that reason, so a
hardcoded copy silently breaks on any other machine or fresh clone.

If `.claude/env.local` is missing or empty, **stop**. Tell the user the
environment isn't configured yet and point them at the `startup-wizard`
skill. If `startup-wizard` doesn't exist in this project yet, ask them
directly which Python interpreter or environment to use, and offer to
write it to `.claude/env.local` yourself once they answer — so this only
has to happen once.

**Never fall back to system/base Python silently.** That is the specific
failure this setup exists to prevent: base Python is on PATH and is what a
bare `python` resolves to, but it lacks the required packages and fails
with a confusing ImportError that looks like an unrelated problem.

## Bank schema

```
profile          { legal_name, preferred_name, email, school_email,
                   work_authorization, phone, location, linkedin, github,
                   _note, _note_email, _note_visa }
experience[]     { id: exp_*, type: work|internship, org, title, start, end,
                   bullets: [{id, text, short?, tags}], skills }
projects[]       { id: proj_*, type: project|research, org, title, start, end,
                   tech, one_liner?, bullets: [...], skills }
activities[]     { id: act_*, type: club, org, title, start, end,
                   one_liner?, bullets: [...], skills }
education[]      { id: edu_*, institution, location, degree, start, end,
                   gpa, coursework, coursework_extra, details }
certifications[] { id: cert_*, name, issuer, date, expires, credential_id }
skills[]         { name, category, tags }
```

`skills[].category` must be one of: `Languages`, `ML & AI`,
`Frameworks & Libraries`, `Infrastructure & Tools`, `Concepts`,
`Test Scores`.

Entry IDs are unique across experience + projects + activities + education
+ certifications combined. Bullet IDs (`<entry_id>_b<n>`) are a separate
namespace, also unique, with no collisions against entry IDs.

### Fields that are never printed on a resume

- `profile.legal_name`, `profile.work_authorization` — internal only
- `education[].coursework_extra` — JD-keyword matching only

Never suggest surfacing these. `coursework` is the short line that renders;
`coursework_extra` holds the overflow.

### `tech` vs `skills` on a project

- `tech` — a short display string of concrete tools, shown beside the
  title (e.g. `"Python, PyTorch, Hugging Face, Librosa"`). Keep it to
  actual tools/languages; conceptual entries make the line overflow.
- `skills` — the full list used for JD-relevance matching. May include
  concepts (`"speech processing"`, `"deep learning"`).

These are deliberately different. Ask for them separately.

## Procedure

### 1. Establish what's being added

Ask which of these it is:

- a new entry in `experience`, `projects`, `activities`, `education`,
  `certifications`, or a standalone `skills` entry
- a new bullet on an existing entry
- a `tech`, `one_liner`, or `short` value on an existing entry/bullet

If the user asks to **list** (`--list`) an array, show its entries briefly
(ID, title, org, dates, bullet count) and stop. If they ask to **edit**
(`--edit <id>`), read that entry, show it, and apply the same
confirm-before-write rule as for new content.

### 2. Gather required fields

Prompt only for the fields that array actually needs. Dates are `YYYY-MM`,
or `present` for an ongoing `end`.

- **project** — also ask for `tech` and `skills` separately (see above)
- **education** — ask for `location`, `gpa`, and `coursework` (the short
  line that will actually render), then ask separately whether there's
  additional coursework worth keeping in `coursework_extra` for matching
  only
- **certification** — `credential_id` may be an opaque ID or a
  verification URL; the renderer hyperlinks it automatically if it looks
  like a URL, so just record it as given

### 3. For each new bullet

1. **Assign the bullet ID** — next sequential `<entry_id>_b<n>` for that
   entry. Check it against the whole bullet-ID namespace before using it.
2. **Hold the bullet to resume-ready phrasing.** These strings are placed
   verbatim into real resumes — no rewriting happens downstream. If a
   bullet reads like a raw note ("worked on the pipeline, made it
   faster"), ask the user to rephrase it as a finished resume line before
   accepting it.
3. **Suggest `tags`, don't impose them.** Propose tags based on the bullet
   text, present them as suggestions, and save only what the user confirms
   or edits. Prefer tag vocabulary already in the bank (e.g.
   `"computer vision"`, `"deep learning"`, `"model deployment"`) over
   near-duplicate variants — tags are only useful if they're consistent
   enough to filter on. Read the existing tags before suggesting.
4. **Ask whether a `short` variant is warranted.** Skip it when the bullet
   is already dense — anything under roughly 120 characters already fits
   one rendered line at 10pt, so compressing it buys nothing. When it is
   warranted:
   - Target roughly 60–75% of the original length.
   - Preserve every concrete fact: technologies, metrics, outcomes.
     Compress connective and qualifying language, not substance.
   - Never invent, generalize, or infer anything absent from the original
     `text`. A `short` is a compression, not a rewrite.
   - Show it beside the original for comparison, flag anything the cut
     actually loses, and save only what the user confirms or edits.

### 4. For a new experience/project/activity entry, offer a `one_liner`

Ask whether to author a `one_liner` now: one sentence standing in for the
**entire entry**, condensing its identity, core technical contribution,
and outcome. Draw only from that entry's own bullets, `org`, and `title` —
every fact in it must already exist in that entry's content.

This is the highest-value field for fitting a resume to one page: a
`one_liner` collapses a six-bullet entry to a single line, recovering far
more space than trimming individual bullets ever does. Worth authoring
even if the entry looks short today.

Same governance as `short`: propose, show, save only what's confirmed.

### 5. Validate before writing

- all required fields present for that array
- dates parse as `YYYY-MM` (or `present`), and `start <= end`
- no duplicate entry IDs across all five ID-bearing arrays
- no duplicate bullet IDs; no collision between the two namespaces
- no empty or whitespace-only bullet `text`
- every `short` strictly shorter than its `text`
- `skills[].category` is one of the six allowed values

### 6. Show, then write

Show the complete entry — or the new bullet/field — exactly as it will
appear in the file. Write to `experience_bank.json` only after the user
confirms.

When writing, preserve the file's existing formatting. Prefer targeted
edits over re-serializing the whole file with `json.dump`, which would
reflow every line and bury the real change in noise. Note that
indentation is not perfectly uniform across the file (some hand-edited
blocks differ) — match whatever indentation the surrounding block uses.

After writing, re-run the validation above against the file on disk and
report the result. Do not re-read the file to "verify" a successful edit
beyond that check.
