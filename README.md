# Resume Tailorer

A personal resume-tailoring system built as [Claude Code](https://claude.com/claude-code)
skills. Your career history lives in a structured **experience bank** —
every bullet written once, reviewed once, and stored with a stable ID.
Tailoring a resume to a job description means *selecting* from that bank
by ID, never generating prose: an LLM picks which entries and bullets fit
the job, and a deterministic Python renderer fills a LaTeX template with
that content verbatim. Nothing on a generated resume can be invented,
because nothing on the generation path is capable of writing text.

> ## ⚠️ First step after cloning: run `/startup-wizard`
>
> Open the cloned folder in Claude Code and run **`/startup-wizard`
> before anything else.** Nothing works without it: it builds your
> experience bank, creates the Python environment (a venv, recommended),
> and records your LaTeX/Word choice. `fit-check`, `tailor-resume` and
> `add-experience` all depend on what it sets up, and will stop and send
> you back to it if it hasn't been run.

---

## Prerequisites

| | |
|---|---|
| **Python** | Built and tested against **3.12.13**. Other 3.x versions very likely work but aren't verified. |
| **LaTeX engine** | `pdflatex` or `xelatex`, for compiled PDFs. [MiKTeX](https://miktex.org/) (Windows) or [TeX Live](https://tug.org/texlive/) (cross-platform). |
| **Claude Code** | The skills live in `.claude/skills/` and run inside Claude Code. |

**Use a dedicated virtual environment.** It keeps this project's pinned
dependencies separate from your other Python work and is easy to delete
and recreate. You don't need to make it yourself: all you need beforehand
is a working Python install, and `startup-wizard` creates the venv
(`.venv/`), installs the dependencies and verifies it. If you already
have an environment you'd rather use, the wizard accepts that too, but a
wizard-made venv is the path of least surprise.

`startup-wizard` records your output format in `.claude/format.local`:

- **`auto`** (the default when LaTeX is found) — LaTeX when an engine is
  available, Word when it isn't; `tailor-resume` tells you which you got.
- **`latex`** — LaTeX only; a missing engine is an error.
- **`docx`** — Word only.

`tailor-resume` sticks to that choice and offers the other format when it
finishes. LaTeX needs `pdflatex` or `xelatex` (on PATH, or give the wizard
the path to an existing install). Word needs no LaTeX: it builds a `.docx`
with the same content and section order (ATS-friendly — tab stops and
real bullets, no tables), but it can't count pages, so open it and
confirm it fits on one.

Calling `render_resume.py` yourself: `--format latex|docx|auto` (auto =
LaTeX if found, else Word) and `--latex-engine <path>` for an off-PATH
install.

Python dependencies are pinned in `requirements.txt` (Jinja2, PyYAML,
pydantic, python-docx). `startup-wizard` installs them for you.

---

## What's in this repo vs. what's yours

This repo is a **reusable system**, not a copy of anyone's resume. The
personal layer is git-ignored and created on your machine at setup.

**Tracked (public, reusable):**

| Path | What it is |
|---|---|
| `.claude/skills/` | The four skills that drive everything |
| `render_resume.py` | Deterministic renderer — selection + bank → `.tex` → `.pdf`, or `.docx` when no LaTeX |
| `resume_template.tex.jinja` | LaTeX template (Jinja2, LaTeX-safe delimiters) |
| `requirements.txt` | Pinned Python dependencies |
| `tests/` | Renderer tests (format selection, Word fallback, LaTeX/Word content parity). Run `<python> -m unittest discover -s tests`; needs no LaTeX install |
| `README.md` | This file |

**Git-ignored (private, yours):**

| Path | What it is |
|---|---|
| `experience_bank.json` | Your entire career history — the source of truth |
| `jobs/` | Per-job folders: JD, fit assessment, selection, rendered resume |
| `.claude/env.local` | Absolute path to your Python interpreter (machine-specific) |
| `.claude/format.local` | Your output format (auto / latex / docx), plus a LaTeX engine path if off-PATH |
| `.venv/` | Local virtualenv, if you create one |
| `*.pdf` | Rendered resumes and any bootstrap source resume |

If you fork or clone this, you get the machinery and none of the content.

---

## Getting started from a fresh clone

```bash
git clone <this-repo>
cd Resume-Tailorer
```

Open the directory in Claude Code and run:

```
/startup-wizard
```

**Do this first, before any other skill.** Don't create the venv, install
dependencies, or write `experience_bank.json` by hand — the wizard does
all of it, verifies each step, and writes the machine-specific config
files the other skills read. It's a one-time setup step. It will:

1. **Build your experience bank** — either **(A)** from one or more
   existing resume files you point it at (PDF or `.tex`), extracting
   every role, project, education entry, certification and skill, or
   **(B)** by interviewing you section by section if you have nothing
   written up yet. It asks which you'd prefer; (A) is usually faster and
   more thorough, and old or outdated resumes are still useful input.
2. **Set up a Python environment** — detects what's on your machine,
   recommends creating a dedicated venv (a conda env, or one you already
   have, also work), installs dependencies, and writes the resolved interpreter path to
   `.claude/env.local`. It verifies the path actually works before
   declaring success.
3. **Initialize git** if needed, writing `.gitignore` *before* `git init`
   so nothing personal is ever committed.

Nothing is written to your bank without you reviewing it first.

---

## The four skills

| Skill | When |
|---|---|
| **`startup-wizard`** | Once, on a fresh clone. Described above. |
| **`add-experience`** | Any time. Add or edit bank content — a new role, a new bullet, a `short` variant, tags. Nothing saves without your confirmation. |
| **`fit-check`** | Paste a job description. Get a structured fit assessment. **Stops there** — no resume is generated. |
| **`tailor-resume`** | After you approve a fit-check. Builds the selection and renders the actual one-page resume. |

### The day-to-day loop

```
/fit-check
[paste a job description]

    → review the fit assessment: score, reasons, missing must-haves,
      visa/sponsorship read, company stability, seniority analysis
    → it stops here and waits for you

/tailor-resume
Tailor a resume for <job_id>

    → review jobs/<job_id>/resume_v1.pdf
```

The split is deliberate. `fit-check` answers *"is this worth applying
to?"* and costs nothing to run on a posting you end up skipping.
`tailor-resume` only runs on jobs you've decided are worth the effort.

Each job gets a folder under `jobs/<job_id>/`:

```
jobs/acme-ml-engineer-20260916/
├── jd.txt                  the posting, verbatim
├── fit_check.json          structured assessment + source URLs
├── notes_for_tailorer.md   reasoning handed forward to tailor-resume
├── selection.json          which bank IDs were chosen
├── selection_notes.md      why those, and what was compressed or omitted
├── resume_v1.tex
└── resume_v1.pdf
```

`jobs/index.md` tracks every job and its status.

---

## Why generated resumes can't contain fabrications

`tailor-resume` never writes resume prose. Its entire output is a
selection file of IDs:

```json
{
  "experience": ["exp_001", {"id": "exp_002", "bullets": ["exp_002_b1"]}],
  "projects": [{"id": "proj_004", "mode": "one_liner"}],
  "skills": ["Python", "PyTorch"]
}
```

`render_resume.py` resolves every ID against the bank using pydantic
validation and fails loudly — listing *every* problem at once — if
anything doesn't resolve. It never silently drops or substitutes. Then it
fills the Jinja2 template with the resolved strings **verbatim**. There is
no generation step anywhere in the render path.

When a bullet needs to be shorter, the answer is a `short` variant or an
entry-level `one_liner` **already authored and reviewed in the bank** —
never a fresh rewrite at render time.

---

## Defaults you can change

These are starting points, not constraints. Nothing in the pipeline
enforces them.

### One page, letter, 10pt

| What | Default | Where to change it |
|---|---|---|
| Paper size and font | `letterpaper`, `10pt` | `\documentclass[...]` at the top of `resume_template.tex.jinja` |
| Section allocation | 2 education, top 2 experience, 2–3 projects, certs as space allows | `tailor-resume` → *Standard section allocation* |
| Page target | one page | `tailor-resume` → *If it overflows one page* |

`render_resume.py` **only reports** the page count and prints a warning
above one page — it never blocks or truncates. A two-page resume renders
fine if that's what you want.

Two notes if you do change the template: the `documentclass` line carries
a comment explaining why it's `letterpaper` and not `legalpaper` (legal
paper fits more but breaks ATS parsing), and why `10pt` rather than
Jake's original `11pt` (at 11pt the text column fits ~110 characters per
line instead of ~126, so long bullets wrap an extra line each and a
standard selection spills to page 2). Both were measured, not guessed —
re-check the tradeoff rather than assuming.

### How much external research `fit-check` does

By default `fit-check` uses web search, where available, to look up a
company's sponsorship history and financial stability, and records every
claim with its URL in `fit_check.json`'s `sources` array.

You can tell it to skip research entirely and judge from the JD text
alone, or to restrict itself to primary sources (SEC filings, company
newsrooms) and ignore third-party aggregators. Sponsorship and layoff
figures in particular often come from aggregator sites of varying
quality — the `sources` array exists so you can check the provenance of
any number before relying on it for a real decision.

---

## Known limitations

- **Bank bloat accumulates when merging old resumes.** Building a bank
  from several resume versions produces near-duplicate bullets that
  restate each other. `proj_004` in the reference bank still carries
  three such bullets. The fix is either trimming the bank via
  `add-experience` or leaning on `mode: "one_liner"` at selection time.
  Worth a periodic review rather than a one-time cleanup.

- **Tested primarily on Windows.** `startup-wizard`'s environment
  detection is written to be cross-platform (it detects the OS to resolve
  `.venv/Scripts/python.exe` vs `.venv/bin/python`, and handles a `conda`
  that isn't on PATH), but **it has not been verified on macOS or Linux.**

- **Job statuses are free-form.** `jobs/index.md` uses
  `pending → fit-checked → tailored` during the automated flow. Anything
  past that (`applied`, `rejected`, `onsite`, …) is yours to track and
  isn't enforced or validated.

- **Fitting one page is a judgment call, not an automatic step.** The
  renderer warns on overflow but doesn't fix it. `tailor-resume` works
  through a documented ladder — switch a low-relevance entry to its
  `one_liner`, then use `short` variants, then drop an entry — but
  choosing *what* to compress is a decision, and a bank with no
  `one_liner`/`short` variants authored has nothing to fall back on.
