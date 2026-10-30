---
name: tailor-resume
description: For a job already approved via fit-check, build a selection JSON of bank entry/bullet IDs and call render_resume.py to produce a tailored one-page resume. Use only after the user explicitly approves a fit-checked job. Writes no LaTeX and no resume prose — its only output is a selection file.
---

# tailor-resume

Produce a tailored resume for a job the user has **already approved** via
`fit-check`. Never run this unprompted or before approval.

## The one rule that defines this skill

**Your entire output is a selection JSON file of IDs.** You do not write
LaTeX. You do not write, rewrite, trim, or rephrase resume prose. Every
string that lands on the resume is placed verbatim from
`experience_bank.json` by `render_resume.py`.

If a bullet needs different wording, the answer is a `short` variant or a
`one_liner` **already authored in the bank** — or a request to the user to
add one via `add-experience`. It is never an edit made here.

Do not edit `resume_template.tex.jinja`. Do not edit
`experience_bank.json`.

## Environment

**Read `.claude/env.local` for the Python interpreter to use** for every
command in this skill, including every call to `render_resume.py`. It
holds one line: an absolute path to the interpreter of the project's
configured environment. Use whatever path it contains — referred to as
`<PY>` below.

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

## Output format

**Read `.claude/format.local`** (written by `startup-wizard`). Plain
`key=value` lines: `format` is `auto`, `latex` or `docx`; `latex_engine`
is an optional absolute path to a `pdflatex`/`xelatex` that isn't on PATH.
Pass them to the renderer as `--format <format>` and, when present,
`--latex-engine <latex_engine>`.

**Stick to the stored choice.**

- **`latex` / `docx`:** never produce the other format unprompted. If
  `format=latex` and the render reports no usable LaTeX engine (or
  compilation fails), **stop**: say what happened, and offer (a) fixing
  the install/path, or (b) a Word version for this run.
- **`auto`:** the renderer picks — LaTeX if an engine is available,
  otherwise Word. **Always tell the user which one you got**, and if it
  was Word because no engine was found, say that plainly (and that page
  count is unverified). `auto` covers an engine being *unavailable* only:
  if LaTeX is present but compilation fails, **stop** and report the
  error exactly as for `latex`; don't paper over it with Word.

Only change the stored value if the user says to switch from now on, by
editing `format.local`.

**If `.claude/format.local` is missing** (a checkout set up before this
existed, or an old deferral), run the format step from `startup-wizard`
(detect LaTeX; if found, record `auto` and tell them; if not, offer
install / existing path / Word-only / auto), then write the file.

## Selection schema

There is no example selection file in the project. Construct the JSON
directly in this shape:

```json
{
  "education": ["edu_001", "edu_002"],
  "experience": ["exp_001", {"id": "exp_002", "bullets": ["exp_002_b1"]}],
  "projects": [
    {"id": "proj_001", "bullets": ["proj_001_b1", "proj_001_b2"]},
    {"id": "proj_004", "bullets": [{"id": "proj_004_b1", "variant": "short"}]},
    {"id": "proj_002", "mode": "one_liner"}
  ],
  "activities": [],
  "certifications": ["cert_001", "cert_002"],
  "skills": ["Python", "PyTorch", "AWS (EC2, S3, Lambda)"]
}
```

Per-entry forms for `experience` / `projects` / `activities`:

| Form | Meaning |
|---|---|
| `"proj_001"` | all bullets, full `text` |
| `{"id": ..., "bullets": ["proj_001_b2"]}` | that subset, full `text`, in the order listed |
| `{"id": ..., "bullets": [{"id": ..., "variant": "short"}]}` | that subset, using each bullet's pre-authored `short` |
| `{"id": ..., "mode": "one_liner"}` | the entry's `one_liner` as its single line, ignoring `bullets` |

`education` and `certifications` are **bare ID strings only** — no bullets,
no modes. `skills` is a flat list of names from the top-level catalog,
spelled exactly as they appear there (e.g. `"AWS (EC2, S3, Lambda)"`).
Skills render grouped by category, in the order categories first appear in
your list — so the list order controls the section's layout.

## Procedure

### 1. Confirm the job and read everything the fit-check left you

Confirm the `job_id`; ask if ambiguous. Then read, in this order:

1. `jobs/<job_id>/jd.txt`
2. `jobs/<job_id>/fit_check.json` — `reasons` and `missing_must_haves` are
   the best guide to what to emphasize
3. `jobs/<job_id>/notes_for_tailorer.md` **if it exists** — free-form
   reasoning the fit-check recorded specifically for this step: which
   entries are strongest evidence for which JD themes, which
   keyword-matching items are too thin to feature, thoughts on ordering
   and emphasis. Factor it into selection.

   If the file is absent (a job fit-checked before this became standard),
   proceed without it. Its absence is **not** an error and needs no
   comment.

### 2. Select entries and bullets

Every reference must be an existing ID from the bank. Never invent an ID,
a bullet, a metric, or a skill name.

- Judge an entry's relevance using **its own `skills` field**.
- Build the skills section from the **top-level `skills` catalog**.
- Match against `education[].coursework_extra` too when assessing
  relevance — but it never renders, so it can't be "included."

### 3. Two hard rules for every bullet-bearing section

Both come from real failures. Do not default to "all bullets in bank
order."

**Newest-first.** Order entries within a section by date, most recent
first. `render_resume.py` renders selection order verbatim and does not
check this. If JD relevance justifies a different order, say so explicitly
in your report.

**Keep a descriptor bullet.** When selecting a subset, ensure at least one
included bullet establishes *what the thing is* — its architecture or
approach — not only outcome bullets. A section that opens mid-detail
("Engineered a cross-modal alignment algorithm…") with no bullet
establishing the subject reads as fragments, and the project title alone
does not substantiate it.

This is a judgment call `render_resume.py` cannot check. Confirm it
deliberately before finalizing any subset. If a single line can carry both
identity and outcome, `mode: "one_liner"` is usually the better answer
than hand-picking bullets.

### 4. Activities are last-resort filler

Include an activity **only** when nothing in experience or projects is
relevant enough to fill the format. Not a routine addition, even for
early-career-leaning JDs. **Never let an activity displace an experience
or project slot.**

### 5. Contact info

Use `profile.email` by default. Use `profile.school_email` **only** if the
user has explicitly said this application is for on-campus/NEU-affiliated
recruiting.

Never reference `profile.legal_name` or `profile.work_authorization` — the
template never prints them and the selection has no field for them.

### 6. Standard section allocation

Default for the one-page letter format; flex if the JD or the user calls
for a different balance:

- **Education** — both entries, full inclusion, not selective
- **Experience** — top 2 entries, ranked by relevance
- **Projects** — 2–3 entries, ranked by relevance
- **Skills** — filtered from the catalog to what's relevant
- **Certifications** — include as space allows

### 7. Write and render

**Preflight first.** Resolve `<PY>` from `.claude/env.local` (see
Environment above), then confirm that interpreter can actually import the
renderer's dependencies:

```
<PY> -c "import jinja2, pydantic"
```

Exit 0 means proceed. A non-zero exit (typically
`ModuleNotFoundError: No module named 'jinja2'`) means the configured
environment is wrong or incomplete — **stop and tell the user plainly**,
something like:

> The interpreter configured in `.claude/env.local` can't import
> Jinja2/pydantic, so `render_resume.py` won't run. Install the pinned
> dependencies with `<PY> -m pip install -r requirements.txt`, or re-run
> `startup-wizard` if the path itself is wrong.

Do not fall back to system/base Python to get around this — base does not
have these packages, and silently switching interpreters hides the real
problem. Do not proceed to render until the preflight passes.

**Word possible?** If `format` is `docx` or `auto` (or the user asks for
the Word alternative), also check `<PY> -c "import docx"`; if it fails, the fix is
the same `pip install -r requirements.txt`.

Then write the selection to `jobs/<job_id>/selection.json` and render:

```
<PY> render_resume.py \
  --bank experience_bank.json \
  --selection jobs/<job_id>/selection.json \
  --output jobs/<job_id>/resume_v<N>.tex \
  --format <format> [--latex-engine <latex_engine>]
```

`<format>` and the optional engine path come from `.claude/format.local`
(see Output format). For `docx` the renderer replaces the `--output`
extension, writing `jobs/<job_id>/resume_v<N>.docx`. Same selection, same
verbatim content, same section order either way.

`<N>` is 1 for a first tailoring. When a resume already exists, use the
next number up: a user-requested revision is a new version, so don't
overwrite the current one.

**Archive superseded versions (default).** Once version N has rendered and
been accepted, move every earlier resume to `jobs/<job_id>/deprecated/`,
creating that directory if needed. That means `resume_v<M>.tex`,
`.pdf` and `.docx`. Also save each old selection there as `selection_v<M>.json`, so
the job folder's top level only ever holds the current `resume_v<N>` and
the live `selection.json`. Snapshot `selection.json` into `deprecated/`
*before* overwriting it for the new version, or the old selection is
lost. Skip archiving only when the user explicitly asks to keep earlier
versions in place. Overflow re-renders while fitting a single version to
one page overwrite that same `resume_v<N>`; they are not new versions.

### 8. If it overflows one page

The renderer reports a page count and warns above one page. Don't start
deleting content. (In Word mode there is no page count — the renderer says
so. Check the length another way, e.g. export through Word if it's
installed, or ask the user to open the `.docx`; if you can't verify it,
say that in the report rather than claiming one page.) Apply these in order, re-rendering after each:

1. **Switch the lowest-relevance project or activity to
   `mode: "one_liner"`.** This is by far the biggest lever — collapsing a
   multi-bullet entry to one line recovers more space than trimming
   individual bullets ever will.

   **Watch `proj_004` (Intelligent Interactive Study Aid) specifically:**
   `_b6` ("Led the backend development…") overlaps `_b1` — both describe
   the LlamaIndex/RAG backend. It was kept because it is the only record
   that the user *led* the backend. Include `_b1` or `_b6`, not both,
   alongside `_b2`/`_b3` as needed. (`_b4` and `_b5`, which duplicated the
   whole project, were removed from the bank on 2026-10-05.)

2. **Switch remaining long bullets to `variant: "short"`** where a `short`
   field exists. Not every bullet has one, and requesting a missing
   variant fails validation. Note that most `short` variants are denser
   prose without crossing a line boundary — this is fine-tuning for the
   last line or two, not a primary lever.

3. **Only as a last resort, drop a lower-relevance entry entirely.**

If it still doesn't fit after reasonable attempts, **say so plainly**
rather than over-trimming past the point of a readable resume. A
two-page-warning with an honest explanation beats a one-page resume
gutted of substance.

### 9. Confirm the run actually succeeded

`render_resume.py`'s pydantic validation is the hallucination guardrail: a
nonexistent entry ID, bullet ID, skill name, missing `short`, or missing
`one_liner` fails loudly and lists every problem at once before anything
renders. **Don't re-implement that check.**

Do confirm the run succeeded before reporting done — non-zero exit, or no
compiled PDF path (LaTeX) / "Rendered Word document" line (docx) in the
output, means it did not. If validation failed,
read the error, fix the selection, and re-run. Never report success on an
unverified run.

### 10. Write `selection_notes.md`

Once the selection is final **and the render has succeeded**, write
`jobs/<job_id>/selection_notes.md` — a sibling of `selection.json`,
describing what actually got rendered rather than an earlier draft of the
plan.

It must be a separate file. It cannot be a field inside `selection.json`:
the `Selection` pydantic model sets `extra="forbid"`, so any added key
fails validation before anything renders.

Write in plain prose:

- **Which entries and bullets were chosen for each section, and why.**
  Use real IDs and get them right — check each ID against the bank before
  citing it. The first real run described `proj_002_b3`'s content as
  `_b2`, which makes the rationale actively misleading to audit later.
- **Any deviation from the standard section allocation** (e.g. 4 projects
  instead of 2–3), with the specific reason.
- **What compression was used** — which bullets went to `variant: "short"`,
  which entries to `mode: "one_liner"`, and why.
- **Omitted evidence the fit-check flagged as strong.** If
  `fit_check.json` or `notes_for_tailorer.md` named a specific entry as
  strong evidence and it is **not** in the final selection, say so
  explicitly and give the reason.

  This last item is the one most likely to get skipped, because it means
  justifying an absence rather than narrating a choice. Do it anyway. On
  the first real run, `proj_005` was named in the fit-check as the
  GenAI evidence the user "genuinely owns" and then dropped from the
  resume with no mention — a silent drift between the assessment and the
  artifact, which is precisely what this file exists to catch.

### 11. Report

Give the user:

- the final **page count**
- the file paths: `jobs/<job_id>/resume_v<N>.tex` and `.pdf` (or
  `.docx` for the Word format), plus
  which earlier versions were moved to `deprecated/`
- which entries/bullets were chosen and **why**, including any deviation
  from newest-first ordering or the standard allocation
- anything you had to compress (`one_liner` / `short`) to make it fit

Then update that job's row in `jobs/index.md` to `status: tailored`.

**When updating that row, copy the `role` column verbatim from
`fit_check.json`'s `role` field.** Never reformat it or re-derive it from
the JD — `fit_check.json` is authoritative, and independent formatting is
exactly how the two files drifted on the first real run.

Before reporting done, actually look at the rendered output rather than
only trusting the page count. A selection can satisfy every mechanical
check and still read badly — duplicated content, a section opening
mid-detail, entries out of date order. The page count is not a proxy for a
readable resume.

**Offer the other format once, at the end of the report.** The stored
choice governed this run (under `auto`, "the other" is whichever format
it did *not* produce); now ask whether they'd also like the same
resume in the alternative — one short line, e.g. "Want this one as a Word
doc too?" (or "…as a LaTeX PDF too?"). Don't offer it earlier, and don't
ask again for the same job after a no.

- **Yes:** re-render the **same** selection with `--format <other>` into
  the same `resume_v<N>` — it is another rendering of this version, not a
  new version, so nothing is archived. For LaTeX as the alternative, the
  engine must be usable (PATH or `latex_engine`); if it isn't, say so and
  point to the `startup-wizard` format step rather than trying anyway.
  Report the extra file path. Word output has no page count, so say that
  length wasn't verified unless you checked it another way.
- **The stored choice does not change** unless they explicitly say they
  want to switch from now on; then update `.claude/format.local`.

### 12. Status updates

`jobs/index.md`'s `status` moves through
`pending → fit-checked → tailored → applied → ...`, free-form beyond
that — the user tracks application-stage detail separately. Update it
whenever the user says so in conversation, not only right after tailoring.
