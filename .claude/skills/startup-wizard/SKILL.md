---
name: startup-wizard
description: Bootstrap this resume-tailoring project on a fresh clone — build experience_bank.json from the user's resume files or by interview, set up a Python environment and write .claude/env.local, record whether the user wants LaTeX or Word resumes in .claude/format.local, and initialize git. Use on first run in a new checkout, when experience_bank.json, .claude/env.local or .claude/format.local is missing, or when the user asks to set up, onboard, or configure the project.
---

# startup-wizard

Bootstrap this project on a fresh clone. The repo carries only reusable,
non-personal artifacts:

```
.claude/skills/            add-experience, fit-check, tailor-resume, startup-wizard
resume_template.tex.jinja  Jinja2 LaTeX template
render_resume.py           deterministic renderer
requirements.txt           Jinja2, PyYAML, pydantic, python-docx
README.md
```

Everything personal — `experience_bank.json`, `jobs/`, any resume file
used for bootstrap — is git-ignored and does not exist yet. **This skill
creates that personal layer.**

## Assume nothing about the machine

No hardcoded usernames. No hardcoded environment name. No assumption of
Windows, macOS, or Linux. No assumption that `conda` exists. **Detect,
report what you found, then ask.**

This is also the one skill that does **not** read `.claude/env.local` for
its interpreter — it is the skill that *writes* that file. Until it
exists, use whatever Python you detect on PATH for detection purposes
only, and never for running `render_resume.py`.

---

# Part 1 — Build `experience_bank.json`

## Bank schema

This is the exact structural shape the other three skills consume. Every
field below is real and load-bearing. Populate it with **this user's own
data** — nothing here is a value to carry over, only the shape.

```json
{
  "profile": {
    "legal_name": "",
    "preferred_name": "",
    "email": "",
    "school_email": "",
    "phone": "",
    "location": "",
    "linkedin": "",
    "github": "",
    "work_authorization": "",
    "_note": "",
    "_note_email": "",
    "_note_visa": ""
  },
  "experience": [
    {
      "id": "exp_001",
      "type": "work | internship",
      "org": "",
      "title": "",
      "start": "YYYY-MM",
      "end": "YYYY-MM | present",
      "one_liner": "",
      "bullets": [
        { "id": "exp_001_b1", "text": "", "short": "", "tags": [] }
      ],
      "skills": []
    }
  ],
  "projects": [
    {
      "id": "proj_001",
      "type": "project | research",
      "org": "",
      "title": "",
      "tech": "",
      "start": "YYYY-MM",
      "end": "YYYY-MM | present",
      "one_liner": "",
      "bullets": [ /* same shape as experience bullets */ ],
      "skills": []
    }
  ],
  "activities": [
    {
      "id": "act_001",
      "type": "club",
      "org": "",
      "title": "",
      "start": "YYYY-MM",
      "end": "YYYY-MM | present",
      "one_liner": "",
      "bullets": [ /* same shape */ ],
      "skills": []
    }
  ],
  "education": [
    {
      "id": "edu_001",
      "institution": "",
      "degree": "",
      "start": "YYYY-MM",
      "end": "YYYY-MM",
      "location": "",
      "gpa": "",
      "coursework": "",
      "coursework_extra": "",
      "details": []
    }
  ],
  "certifications": [
    {
      "id": "cert_001",
      "name": "",
      "issuer": "",
      "date": "YYYY-MM",
      "expires": "YYYY-MM | null",
      "credential_id": ""
    }
  ],
  "skills": [
    { "name": "", "category": "Languages | ML & AI | Frameworks & Libraries | Infrastructure & Tools | Concepts | Test Scores", "tags": [] }
  ]
}
```

**IDs.** Entry IDs are unique across experience + projects + activities +
education + certifications combined. Bullet IDs (`<entry_id>_b<n>`) are a
separate namespace, also unique, with no collisions against entry IDs.
Assign both correctly on the first write so no migration is ever needed.

### Two places the schema above is a type hint, not a literal value

The `""` and `"YYYY-MM | null"` placeholders show *shape*. Transcribing
them literally produces a bank that validates but breaks at render time.

**`short` and `one_liner`: omit the key entirely when there isn't one.
Never write `""`.**
`render_resume.py` tests these with `not bullet.get("short")`, so an empty
string is treated as *missing* — a selection requesting
`variant: "short"` on such a bullet fails with *"requests variant 'short'
but has no 'short' field in the bank."* And the blank slips past
validation, because `"" < text` is true, so a "short must be strictly
shorter than text" check passes it. A bullet with no short variant should
have **no `short` key at all**; same for an entry with no `one_liner`.

**`certifications[].expires`: write JSON `null`, not the string
`"null"`.**
A cert with no expiry gets a real `null`. `"YYYY-MM | null"` in the schema
above is describing the two allowed forms, not a value to copy.

## Three fields that get under-populated unless asked for explicitly

**`short` and `one_liner` are not optional afterthoughts.** Ask about
them inline while authoring each bullet and entry. A bank without them
works, but loses the tool's primary mechanism for fitting a resume to one
page — `tailor-resume` reaches for `mode: "one_liner"` first whenever a
selection overflows, and has nothing to reach for if the field is empty.

- `short` — a compression of a bullet to roughly 60–75% length, preserving
  every technology, metric, and outcome, cutting only connective and
  qualifying language. Never a rewrite, never new facts. **Skip it when
  the bullet is already under ~120 characters** — that already fits one
  rendered line, so compressing buys nothing.
- `one_liner` — one sentence standing in for an **entire entry**:
  identity, core technical contribution, outcome. Drawn only from that
  entry's own bullets, `org`, and `title`.

**`education[].coursework` vs `coursework_extra` — ask for both.**
`coursework` is the short line that actually renders on a resume.
`coursework_extra` holds anything else worth keeping for JD-keyword
matching but never printed. Don't dump everything into `coursework` and
leave `coursework_extra` empty by default — an over-long `coursework`
line is a known cause of one-page overflow.

**`projects[].tech` vs `skills` — two separate questions.** Don't derive
one from the other. `tech` is a short display string of concrete tools
shown beside the title (e.g. tools and languages only — conceptual
entries make that line overflow the page width). `skills` is the fuller
list, concepts included, used for JD-relevance matching.

## `profile._note*` — generate these, never leave them blank

These three fields are **not decorative comments**. They are load-bearing
instructions that `fit-check` and `tailor-resume` read at runtime. A bank
missing them makes those skills behave generically or incorrectly.

Generate wording appropriate to **this user's actual answers**. Do not
copy example text from anywhere. Every bank this skill produces must end
with all three populated.

**1. `_note` — legal name handling.**
Ask whether the user has a legal name that differs from what they'd want
on a resume (a longer full legal name vs. a shorter preferred/display
name). If so, `legal_name` holds the full legal name, and `_note` must
state plainly that it is for records only and must never be printed —
`preferred_name` is what appears on every generated resume. If legal and
preferred names are the same, the two fields can match, but still write a
`_note` establishing which field (if any) is record-only and off-limits
for rendering.

**2. `_note_email` — which email to default to.**
Ask whether the user has more than one email they might use (e.g.
personal and school/work). If so, ask which is the default on a generated
resume, and under what **specific** condition the other should be used
instead. Write `_note_email` stating the default and the exact trigger for
the exception, so `tailor-resume` never has to guess.

**3. `_note_visa` — work authorization reasoning.**
Ask about the user's current work authorization (citizen, permanent
resident, student visa needing future sponsorship, existing work visa,
etc.) and write it into `work_authorization`. Then write `_note_visa`
explaining how `fit-check` should read that status when judging a JD's
`visa_flag` — what counts as a positive signal and what counts as a hard
negative, **given this user's specific situation** — and state explicitly
that `work_authorization` must never be printed on a resume, only used for
internal fit-check reasoning.

If the user is a citizen or permanent resident with no sponsorship
considerations at all, **ask** whether they want `work_authorization` and
`_note_visa` populated anyway (some users still want `fit-check` to flag
citizenship-required postings) or left empty. Don't assume either way.

## Two entry paths — same destination

**Always ask first. Never detect and branch silently.** Even if a resume
file is already sitting in the project root, open by telling the user both
options exist and let them choose. Its presence does not mean they want
Path A; its absence does not mean they want Path B. A first-time user has
no reason to know Path A exists unless you say so.

Open with something like:

> I can build your experience bank two ways: **(A)** you give me one or
> more resume files (PDF or `.tex`) and I extract everything
> automatically, or **(B)** I ask you about your background section by
> section and build it from scratch. If you have resumes on hand — even
> old or outdated ones — (A) is usually faster and more thorough. Go with
> (B) only if you don't have anything written up yet. Which would you
> like?

### Path A — bootstrap from one or more resume files

Ask the user to place the file(s) in the project root, or to point you at
their location, if they haven't already.

**A resume file cannot give you everything.** Legal name vs. preferred
name, work authorization status, and an email-default preference are not
extractable from a document in any reliable form. These must be asked
directly, separately from parsing. See the `profile._note*` section above
— do not skip it just because it falls outside the document-parsing flow.

1. **If more than one file is provided, establish source-of-truth order
   before parsing anything.** Ask which is most recent and most
   authoritative, or infer the order from filenames, dates, or content
   when unambiguous — but **confirm the order with the user rather than
   guessing silently.** This determines which version wins on any
   conflict: a changed GPA, a reworded bullet, a corrected date. State it
   back before proceeding:

   > I'll treat X as the newest/primary source, and Y as an older one I'll
   > pull additional history from — confirm?

2. **Parse the primary (newest) source first** into the schema. Do not
   summarize or compress. Extract every role, project, education entry,
   certification, and skill, preserving original phrasing — these become
   resume-ready bullets directly, not raw notes to be rewritten later.

3. **Flag every ambiguity rather than guessing silently** — inferred
   dates, an unclear organization, an unstated location, a certification
   with no visible issuer. **Never invent a fact absent from the source.**

4. **Merge additional (older) sources additively only.**
   - Never remove or overwrite an entry that came from the primary source.
   - Where an older source **conflicts** with the primary on the same fact
     (different GPA, different date range for the same role), the primary
     wins — but **say so explicitly** rather than silently picking one.
   - Where an older source has an entry the primary lacks (an earlier job,
     a project cut from the newer resume), **add it**.
   - **Ask before assuming** two entries from different sources describe
     the same underlying thing rather than two different ones.

5. **Assign entry and bullet IDs correctly from this first write** —
   sequential per array, per-entry for bullets — so no ID migration is
   ever needed later.

6. **For every bullet, ask inline whether a `short` is warranted** (skip
   if already under ~120 characters). **For every
   experience/project/activity entry, ask whether a `one_liner` is worth
   authoring now.** Same governance as `add-experience`: propose, show
   beside the original, write only what the user confirms or edits. Inline
   means while working through that entry — not as a separate pass at the
   end, which invites skipping it.

7. **For every project, ask for `tech` and `skills` as two separate
   questions.** Don't derive one from the other.

8. **Ask for and generate `_note`, `_note_email`, and `_note_visa`** as
   described above. None of this comes from the resume text.

9. **Show the fully assembled bank for review before writing anything** to
   `experience_bank.json`.

### Path B — no source document, conversational build

Walk the schema sections in order:

**profile → education → experience → projects → activities →
certifications → skills**

One entry at a time. When you reach `profile`, ask for the contact fields
directly, then work through the `_note` / `_note_email` / `_note_visa`
questions **as part of that same section** — don't treat the notes as a
separate pass tacked on at the end.

This is effectively `add-experience` run in a loop for first-time setup.
**Delegate to that skill's per-entry procedure** — bullet ID assignment,
tag suggestion from existing bank vocabulary, `short`/`one_liner`
offering, validation — rather than re-implementing it here.

After each section, ask "anything else in this section?" until the user
says no, then move on.

### Both paths converge here

**Full validation before the final write:**

- all required fields present for each array
- dates parse as `YYYY-MM` (or `present` for an ongoing `end`), and
  `start <= end`
- no duplicate entry IDs across the five ID-bearing arrays
- no duplicate bullet IDs; no collision between the two namespaces
- no empty or whitespace-only bullet `text`
- **no empty-string `short` or `one_liner` anywhere** — the key is either
  absent or holds real text (a bare "strictly shorter than `text`" check
  passes `""`, so test for emptiness separately)
- every `short` present is strictly shorter than its `text`
- every `certifications[].expires` is either a `YYYY-MM` string or JSON
  `null` — never the string `"null"`
- every `skills[].category` is one of the six allowed values

**Show the complete assembled `experience_bank.json` for review. Write
only after explicit confirmation.**

---

# Part 2 — Environment setup

Fresh clone. Assume nothing.

### 1. Choose the resume format: Auto, LaTeX, or Word

Three possible values, stored as `format` in `.claude/format.local`:

- **`auto`** *(recommended)* — LaTeX when an engine is available, Word
  when it isn't. The renderer announces which one it used.
- **`latex`** — LaTeX only: compiled PDF, exact one-page check, best
  typography. A missing engine is an error, never a silent Word fallback.
- **`docx`** — Word only: a `.docx`, no LaTeX needed, easy to hand-edit.
  The renderer can't count pages, so fit has to be checked by eye.
  `python-docx` is verified in step 4.

**Detect first.** Look for `pdflatex`, then `xelatex`, on PATH. Verify
each candidate actually runs (`<engine> --version`, exit 0) — resolving on
PATH is not enough.

**A. LaTeX found — don't ask.** Report where, record `format=auto` (no
`latex_engine`; PATH lookup is enough), and say so in one line:

> Found pdflatex at `<path>`. I'll use LaTeX, and fall back to Word if it's
> ever missing. Say so if you'd rather lock in LaTeX-only or Word-only.

If they do want to lock one in, record that instead and move on.

**B. LaTeX not found — ask.** Say so plainly and give the ways forward:

- **Install it**: [MiKTeX](https://miktex.org/) (Windows) or
  [TeX Live](https://tug.org/texlive/) / MacTeX (macOS, Linux). Once
  installed, re-run the detection above.
- **Point to an existing install.** Many installs aren't on PATH (on
  Windows, MiKTeX often sits under
  `AppData\Local\Programs\MiKTeX\miktex\bin\x64`). Ask for the path to
  the `pdflatex`/`xelatex` executable, or the folder containing it.
  Resolve it to the executable file, verify with `--version`, and record
  it as `latex_engine`.
- **Skip LaTeX for now.** Offer **Word-only** (`docx`), or **auto**: Word
  today, and LaTeX automatically once an engine appears. Auto is the
  better pick for anyone who might install LaTeX later.

A successful install/path lookup records `auto` by default (or `latex` if
they ask for LaTeX-only). Don't let this stall them: if they can't decide,
recommend `auto` — it works immediately and needs no revisit.

**Don't block the rest of setup on this.** The bank and Python
environment don't depend on it.

### 2. Detect before asking

Check what's actually present and **report it** rather than opening with a
blind question:

- `python3` and `python` on PATH — report version and location for each
- whether `conda` is available

A user who sees "found Python 3.12 at /usr/bin/python3, no conda detected"
can answer the next question meaningfully. A user asked "what Python do
you want to use?" with no context usually can't.

**Verify each candidate actually executes — resolving on PATH is not
enough.** Run `<candidate> -c "import sys"` and require exit 0 before
treating it as usable.

On Windows this is not a corner case. `python3` commonly resolves to a
Microsoft Store shim at
`...\AppData\Local\Microsoft\WindowsApps\python3` which exits 0 from
`command -v` / `where`, but running it prints *"Python was not found; run
without arguments to install from the Microsoft Store"* and installs
nothing. A detection that only checks PATH resolution will report it as
available and then fail confusingly at `python -m venv`. Report such a
candidate as **"on PATH but not usable"** and move to the next one.

### 3. Offer a concrete choice, informed by what you found

**Recommend a dedicated venv, and say so up front.** Lead with option (a)
as your recommendation and give the reason in a sentence: it keeps this
project's pinned packages (Jinja2, pydantic, python-docx) isolated from
the user's other Python work, can't be broken by a system Python upgrade,
and is trivial to delete and recreate. Present (b) and (c) as valid
alternatives for people who already have a setup they prefer — but don't
open with a neutral menu of equals. Only skip (a) when the user has
already chosen otherwise.

**a. Create a new venv** *(default, recommended)*
Using the detected Python, run `python -m venv .venv` in the project root,
then install `requirements.txt` into it. Resolve the interpreter path
inside it afterward:

- Windows: `.venv\Scripts\python.exe`
- macOS/Linux: `.venv/bin/python`

**Detect which platform applies rather than assuming.**

**b. Create a new conda env** *(offer only if `conda` was detected)*
Ask for a name, create it, install `requirements.txt` into it, then
resolve its interpreter path **as a file path, directly**. Do not assume
`conda activate` works from a non-interactive shell — it frequently
doesn't, and `conda` itself may not be on PATH even when an installation
exists. Locate the interpreter via `conda env list` or the environment's
known install location, and verify the file exists before using it.

**c. Point to an existing environment**
This accepts a path to **any** Python interpreter the user already has,
**however it was created** — pyenv, poetry, pipenv, uv, a hand-rolled
venv, a system install, a conda env, anything. Frame it that way:

> Give me the path to any Python interpreter you already have set up,
> however it was made — I just need the path, I don't need to know how it
> was created.

The mechanism downstream doesn't care about provenance: verify the
interpreter can import Jinja2, PyYAML, pydantic, and python-docx, then write its
resolved path to `.claude/env.local`. A working path is the only
requirement. Don't imply venv and conda are the only supported managers.

If the user doesn't know the path, ask them to activate their environment
in a terminal and run `where python` (Windows) or `which python`
(macOS/Linux) and paste the result.

### 4. Install or verify dependencies

- **New-env paths:** install `requirements.txt`. **Get the user's
  confirmation before installing anything.**
- **Point-to-existing path:** verify rather than install.

**Read the installer's own exit code, not a piped one.** Don't pipe pip
through `tail`/`head`/`grep` and then check `$?` — that returns the
*filter's* status, so a failed install reports success. Run the installer
unpiped, or capture its exit status explicitly.

Either way, confirm the environment can import **Jinja2, PyYAML, python-docx, and
pydantic** before moving on. This import check is the real gate: it
catches a failed install regardless of what any exit code claimed.

### 5. Write `.claude/env.local`

One line: the resolved absolute interpreter path. No trailing whitespace,
no extra newline beyond a single line ending.

**Write this carefully, not via a naive string dump.** On Windows
especially, a CRLF or stray trailing character produces a path like
`C:\...\python.exe\r`, which fails in a way that looks like a missing
interpreter rather than a formatting bug — the most confusing possible
failure for a first-time user.

### 5b. Write `.claude/format.local`

Plain `key=value` lines, no quotes, no trailing whitespace or CR:

```
format=latex
latex_engine=C:\path\to\pdflatex.exe
```

- `format` is `auto`, `latex` or `docx`. Required.
- `latex_engine` is written **only** when the engine was found off-PATH
  (the "point to an existing install" route). Omit it when PATH works, so
  the file stays valid if PATH changes. Keep it for `auto` and `latex`;
  it's meaningless for `docx`.

### 6. Validate your own output before declaring success

After writing the file, **run the same preflight the other three skills
use**:

1. read `.claude/env.local`
2. strip surrounding whitespace and newlines
3. run `<resolved path> -c "import jinja2, pydantic"`

Confirm it exits 0. If `format.local` was written, also confirm it: for
`format=latex`, or `auto` where an engine was found, run
`<latex_engine> --version` (or the PATH engine when there is no
`latex_engine`) and require exit 0. `auto` with no engine found and
`docx` have nothing to verify beyond `import docx`. **Writing the file is not
the same as confirming it works** — do not report the environment as configured until this
round-trip succeeds. If it fails, fix the path or the install and repeat.

---

# Part 3 — Git setup

If `.git` does not exist in this directory:

### 1. Write `.gitignore` FIRST

**Before `git init`, and before any `git add`. Never the other way
around** — a personal file committed once stays in history even after
being ignored later.

At minimum:

```
experience_bank.json
jobs/
*.pdf
.claude/env.local
.claude/format.local
.venv/
```

Adjust if needed: if the user's source resume file is still in the project
root at this point and isn't covered by `*.pdf` (e.g. a `.tex` resume), it
must be git-ignored too, or deleted before init.

### 2. Then `git init`

### 3. Remind the user to delete the bootstrap resume

Any resume file used for Path A was a **one-time input**. Once the bank is
built and reviewed, it should be deleted — the project doesn't depend on it
going forward, and leaving it in the working tree is an ongoing risk of
accidentally committing personal data.

---

# Part 4 — Wrap up

Give the user a short summary:

- **What's in the bank** — counts per section (experience, projects,
  activities, education, certifications, skills; plus total bullets, and
  how many carry `short` / `one_liner`)
- **What environment setup was done** — which option they chose, the
  resolved interpreter path, the resume format they chose (and the LaTeX
  engine path, if one was needed)
- **Whether git was initialized**
- **Confirm `jobs/` does not exist yet** — it's created on the first
  `fit-check` run, not here

Then point them at **`fit-check`** as the natural next step, once they
have a real job description to try. Mention `add-experience` as the way to
add anything that got missed.
