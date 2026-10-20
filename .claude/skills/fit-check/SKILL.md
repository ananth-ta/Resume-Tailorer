---
name: fit-check
description: Take a pasted job description, set up its tracking under jobs/, and score how well it fits the user's background from experience_bank.json. Use when the user pastes a JD or asks whether a role is worth applying to. Produces a structured fit assessment, always walks the user through it conversationally (score /10, TL;DR, detailed explanation) unless --silent is passed, and stops — it never generates a resume.
---

# fit-check

Intake a job description, set up tracking for it, and score fit.

**This skill stops after scoring.** It does not generate a resume, build a
selection, or call the renderer. Wait for the user to explicitly approve
before any resume work happens — that's `tailor-resume`'s job, and running
it unprompted wastes the user's review step.

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

## Step 0 — Job intake

1. **Extract the company name and role title** from the JD. If the company
   name isn't clearly stated, ask — don't guess from the domain, the
   recruiter's signature, or the style of the posting.

   **Fix the role string once, here, and reuse it verbatim everywhere.**
   It goes into `fit_check.json`'s `role` field and into the `role` column
   of `jobs/index.md`. `fit_check.json` is authoritative; `index.md` copies
   it character-for-character. Never reformat, abbreviate, or re-derive it
   for the index — the two drifted in the first real run
   (`"Qualcomm AI Research — GenAI for the Edge"` in one file,
   `"AI Research — GenAI for the Edge"` in the other) purely because each
   was written independently.

   If the posting states no explicit title, infer one and record that it
   was inferred in a `_role_note` field.

2. **Generate a `job_id`**: `<company-slug>-<role-slug>-<YYYYMMDD>`,
   lowercase with hyphens only, e.g. `acme-ml-engineer-20260915`. Use
   today's date.

   If a directory for that exact `job_id` already exists, append `-2`,
   `-3`, etc. **Never overwrite an existing job directory** — it may hold
   a fit-check and a tailored resume already. Tell the user this happened
   and which suffix was used.

3. **Create `jobs/<job_id>/`** and save the JD text verbatim to
   `jobs/<job_id>/jd.txt`. `jobs/` will not exist on a first run — create
   it.

4. **Create `jobs/index.md` if absent**, with this header:

   ```markdown
   | job_id | company | role | date_added | status |
   |--------|---------|------|------------|--------|
   ```

   Append a row for this job with `status: pending`. The `role` column
   must be the exact string fixed in step 1 — the same one that will go
   into `fit_check.json`.

## Step 1 — Fit-check

Read the bank (`experience_bank.json`) for education, experience,
projects, skills, and `profile.work_authorization`.

### Calibrate for an early-career candidate

The user has **no full-time job experience** — internships, course
projects, faculty-advised research, and a teaching assistantship. Weigh
entry-level and early-career-friendly signals accordingly. Do not
mechanically penalize "lack of years of experience" when the role is
actually pitched at new grads; that produces uniformly low scores that
carry no information.

Also read `education[].coursework_extra` when matching — it holds course
names kept specifically for keyword matching and never appears on a
rendered resume. A JD mentioning Linear Algebra or Data Analytics may only
hit there.

### 1. Entry-level check — two independent sub-checks

Report these **separately**; they diverge often and the divergence is the
signal:

- **`entry_level_floor_stated`** — does the JD state an explicit
  experience floor? (`"0-2 years"`, `"New Grad"`, `"2+ years"`, or no
  years stated at all.) Quote the literal line if there is one.
- **`seniority_implied_by_content`** — independently, do the actual
  responsibilities imply more seniority than that stated floor? Judge
  from the work described (owning a system end-to-end, setting technical
  direction, mentoring), not from the years number.

A posting can say "New Grad" and describe staff-level scope. Say so.

### 2. Seniority-vs-title check

Record separately:

- **`stated_minimum_bar`** — quote the literal qualifying line
  (`"12+ years"`, `"PhD or equivalent practical experience"`).
- **`title_seniority_signal`** — what the title alone would suggest.

**Flag explicitly when these diverge.** A title reading junior while the
stated bar is a PhD or 12+ years is a recurring failure mode; surface it
as its own field rather than folding it into general `reasons`, where it
gets lost.

### 3. Visa / sponsorship check

The **JD text is the source of truth** and the fallback. Beyond it:

- If web search is available, also look up the company's general
  sponsorship history or policy — known H-1B sponsor, stated OPT/CPT
  friendliness, or a track record of not sponsoring — to corroborate or
  add context.
- If search is unavailable or turns up nothing conclusive, rely on the JD
  text alone. **Do not guess**, and do not present a search-derived
  impression as if the JD stated it.

Judge against `profile.work_authorization` (F-1; will require OPT). Per
`profile._note_visa`: a JD that supports sponsorship or is OPT-friendly is
a positive signal; one explicitly requiring work authorization with no
sponsorship is a hard negative.

- **`visa_flag`**: `supports` | `unsupported` | `unstated`
- **`visa_notes`**: quote or paraphrase the relevant JD line if one
  exists, plus anything corroborating or contradicting found via search.
  If nothing is stated anywhere, say that plainly.

### 4. Company stability check

Worth a quick web search.

- **`stability_flag`**: `green` | `yellow` | `red`
- **`stability_notes`**: 1–2 sentences — layoff history, ownership
  structure, financial health, acquisition status.

### 5. Source reliability

Flag whether the JD reads like a genuine open search or a
generic/compliance-style posting — e.g. a PERM labor-certification posting
likely earmarked for someone already in process. Signals: exhaustively
long tool/skill lists, oddly hyper-specific requirement combinations,
boilerplate phrasing.

When none of these signals are present, say "no visible PERM cues" rather
than asserting the posting is genuine — PERM postings at large sponsors can
read exactly like normal requisitions (see
`google-software-engineer-ai-ml-shopping-relevance-models-20261007`). This
is rare, so it's a caution, not a reason to downgrade: if the user has a
contact at the company, a quick check that the req exists internally is
cheap insurance.

- **`source_reliability`**: `normal` | `likely-earmarked`, plus a brief
  note.

This tells the user how much effort is actually worth investing.

### 6. Produce structured output

```json
{
  "job_id": "...",
  "company": "...",
  "role": "...",
  "fit_score": 7,
  "reasons": ["...", "...", "..."],
  "missing_must_haves": ["..."],
  "entry_level_floor_stated": {"stated": true, "line": "..."},
  "seniority_implied_by_content": {"higher_than_floor": false, "note": "..."},
  "stated_minimum_bar": "...",
  "title_seniority_signal": "...",
  "visa_flag": "unstated",
  "visa_notes": "...",
  "stability_flag": "green",
  "stability_notes": "...",
  "source_reliability": {"verdict": "normal", "note": "..."},
  "recommendation": "apply",
  "sources": [
    {"claim": "brief description of what this source supports", "url": "..."}
  ]
}
```

- **`fit_score`**: 1–10
- **`reasons`**: 3–5 bullets supporting the score
- **`missing_must_haves`**: JD requirements the user doesn't clearly meet
- **`recommendation`**: one of
  - `apply`
  - `stretch`
  - `skip (hard gate)` — an unmeetable requirement with no path, e.g. a
    required PhD
  - `skip (soft stretch)` — borderline, worth revisiting if the user has
    spare application bandwidth

Keep the hard/soft skip distinction. "Skip" alone loses the difference
between impossible and merely unlikely, which is exactly what the user
needs to triage.

**`sources`** — one entry per source actually used, however many that is.
Every external claim in `visa_notes` and `stability_notes` needs
provenance here. Without it, those numbers survive as bare assertions
once the chat that produced them is gone, and nobody can check them —
which is exactly what happened on the first real run.

- List sources **individually**, even when several back the same claim.
  Don't merge them into one entry.
- No field is needed to mark a source as primary or third-party — the URL
  makes that visible to anyone reading later. But **do not state
  aggregator-sourced claims with more confidence than the source
  warrants.** An LCA count from an H-1B aggregator is not the same
  evidentiary weight as a figure from an SEC filing or the company's own
  newsroom, and `visa_notes` / `stability_notes` should read accordingly.

### 7. Write `notes_for_tailorer.md`

Alongside `fit_check.json`, write `jobs/<job_id>/notes_for_tailorer.md` —
free-form prose holding the reasoning and nuance that doesn't fit the
structured schema but matters for building a good selection later.

**This is the continuity mechanism.** Judgment formed during a fit-check —
which project is the strongest evidence for a given JD theme, which
skills are technically true but weak, which bullets are the natural
picks — otherwise exists only in this session's chat response and is lost
the moment the session ends. `tailor-resume` reads this file.

Don't force a fixed template. Write what's actually worth flagging for
whoever builds the selection next. Typical content:

- **Strongest evidence per JD theme** — which specific bank entries and
  bullet IDs back the JD's key asks, and why. E.g. *"proj_005's
  literature survey is the closest thing in the bank to this JD's
  GenAI-safety framing."*
- **Technically-relevant-but-weak items** — anything that matches a
  keyword while being thin enough that featuring it prominently could
  backfire. E.g. *"C/C++ has no project evidence behind it — listing it
  invites a question with no good answer."*
- **Ordering, emphasis, and framing thoughts** that occurred to you while
  doing the fit-check but belong in no structured field.

Write it for `tailor-resume` as the reader, not the user — though the user
can open it any time.

### 8. Save

Write `fit_check.json` and `notes_for_tailorer.md` into
`jobs/<job_id>/`. Optionally update the job's row in `jobs/index.md` to
`status: fit-checked` — if you do, leave the `role` column exactly as
written at intake.

### 9. Walk the user through it, then stop

**The walkthrough is mandatory.** Every fit-check ends with it as your
chat reply. The only exception is `--silent`: if the arguments contain
`--silent`, or the user explicitly asks for no walkthrough, reply with
just the job_id, `fit_score`/10, `recommendation`, and the path to
`jobs/<job_id>/`. Strip `--silent` from the arguments before saving
`jd.txt`. Don't treat brevity, a long JD, or batch intake as an implicit
`--silent`; only an explicit request counts.

The walkthrough is a **conversational explanation** of the fit-check —
not a dump of the JSON, and not a terse bullet summary. The files are the
record; the walkthrough is how the user actually absorbs the judgment.
It always has these three parts, in this order:

1. **Score**: `fit_score` out of 10 plus the recommendation, stated
   up front as a heading or the first line (e.g. "**7/10, apply**").
2. **TL;DR**: one short paragraph (2–4 sentences) giving the verdict,
   the main reason for it, and the most important caveat or next step.
   Someone who reads only this paragraph should know whether to bother.
3. **Detailed explanation**: everything below.

For the detailed explanation, talk them through it the way a sharp
friend who read both the JD and their background would:

- **Explain what the role actually is** — what the company does and what
  the JD is really asking for underneath its phrasing, especially when
  the posting is vague, founder-voiced, or keyword-heavy.
- **Walk through why the score is what it is** — where their background
  genuinely lines up (naming the specific experiences/projects in plain
  terms, not bank IDs), and where the gaps are and how much each one
  actually matters.
- **Cover the flags in context** — seniority, visa, stability, and source
  reliability, each with what it means for *them* specifically (e.g. F-1/
  OPT implications), and how confident the underlying evidence is.
- **Say what you'd do in their position** — whether it's worth the
  effort, and any questions to resolve or cheap moves to make before
  investing in a tailored resume.

Write in flowing prose with light structure (short headed sections are
fine); keep it readable in a few minutes. Include the sources list at the
end. Don't use bank IDs in the walkthrough — the user thinks in project
names, not `proj_006_b2`.

Then **stop**. Do not build a selection, do not call `render_resume.py`,
do not propose specific resume bullets. Wait for explicit approval.
