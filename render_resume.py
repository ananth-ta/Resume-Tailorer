#!/usr/bin/env python3
"""Deterministically render a tailored resume from experience_bank.json.

There is no generation step here. The script resolves IDs from a selection
file against the bank, hands the resolved entries to a Jinja2 LaTeX template,
and writes the result. Every character of content in the output came verbatim
from the bank, so nothing can be hallucinated at this stage.

Usage:
    python render_resume.py \
        --bank experience_bank.json \
        --selection jobs/<job_id>/selection.json \
        --template resume_template.tex.jinja \
        --output jobs/<job_id>/resume_v1.tex
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal, Union

import jinja2
from pydantic import ConfigDict, ValidationInfo, model_validator
from pydantic import BaseModel, ValidationError

# Bank array -> required ID prefix for entries selected from it.
SECTION_PREFIX = {
    "education": "edu_",
    "experience": "exp_",
    "projects": "proj_",
    "activities": "act_",
    "certifications": "cert_",
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --------------------------------------------------------------------------
# Jinja2 environment
# --------------------------------------------------------------------------

# LaTeX special characters. Backslash must be handled first, so this is done
# as a single regex pass rather than chained str.replace calls.
_TEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_TEX_PATTERN = re.compile("|".join(re.escape(k) for k in _TEX_ESCAPES))


def escape_tex(value) -> str:
    """Escape LaTeX control characters in bank text (e.g. 'Prob & Stat')."""
    if value is None:
        return ""
    return _TEX_PATTERN.sub(lambda m: _TEX_ESCAPES[m.group()], str(value))


def format_month_year(value) -> str:
    """'2026-06' -> 'Jun 2026'; 'present' -> 'Present'. Anything else passes through."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "present":
        return "Present"
    match = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", text)
    if not match:
        return text
    year, month = match.groups()
    return f"{MONTHS[int(month) - 1]} {year}"


def url_only(value) -> str:
    """Strip a leading scheme so the template can prepend its own."""
    return re.sub(r"^https?://", "", str(value or ""))


# A credential_id is either an opaque ID ("54353") or a verification URL
# ("coursera.org/share/..."). Only the latter gets hyperlinked.
_URL_LIKE = re.compile(r"^https?://|^[\w.-]+\.(com|org|net|io|edu|gov)(/|$)", re.I)


def is_url(value) -> bool:
    """True when a credential_id should render as a hyperlink rather than plain text."""
    return bool(_URL_LIKE.search(str(value or "").strip()))


def build_jinja_env(template_dir: Path) -> jinja2.Environment:
    """Jinja2 with LaTeX-safe delimiters so `{`, `}`, `%` and `#` never collide."""
    env = jinja2.Environment(
        block_start_string="((*",
        block_end_string="*))",
        variable_start_string="(((",
        variable_end_string=")))",
        comment_start_string="((=",
        comment_end_string="=))",
        line_statement_prefix=None,
        line_comment_prefix=None,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,
        undefined=jinja2.StrictUndefined,
        loader=jinja2.FileSystemLoader(str(template_dir)),
    )
    env.filters["tex"] = escape_tex
    env.filters["mmy"] = format_month_year
    env.filters["url"] = url_only
    env.filters["is_url"] = is_url
    return env


# --------------------------------------------------------------------------
# Selection model
# --------------------------------------------------------------------------

class BulletRef(BaseModel):
    """A bullet plus which pre-authored string of it to render."""

    model_config = ConfigDict(extra="forbid")

    id: str
    variant: Literal["text", "short"] = "text"


# A bullet reference is either a bare ID (render its `text`) or an object
# naming a variant. Both resolve to a string already sitting in the bank —
# nothing is generated here.
BulletItem = Union[str, BulletRef]


class EntryRef(BaseModel):
    """An entry plus how to render its content.

    `bullets` picks an explicit subset, in render order. `mode: "one_liner"`
    replaces the entry's content with its single pre-authored `one_liner`,
    overriding `bullets` if both are given.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    bullets: list[BulletItem] | None = None
    mode: Literal["bullets", "one_liner"] = "bullets"


# Sections whose entries carry bullets accept either form:
#   "proj_003"                                             -> all bullets, full text
#   {"id": "proj_003", "bullets": ["proj_003_b1"]}         -> just these, in order
#   {"id": "proj_003", "bullets": [{"id": "proj_003_b1",
#                                   "variant": "short"}]}  -> the short variant
#   {"id": "proj_003", "mode": "one_liner"}                -> the entry's one_liner
EntryItem = Union[str, EntryRef]

BULLET_SECTIONS = ("experience", "projects", "activities")


def ref_id(item: Union[EntryItem, BulletItem]) -> str:
    return item if isinstance(item, str) else item.id


def bullet_variant(item: BulletItem) -> str:
    return "text" if isinstance(item, str) else item.variant


class Selection(BaseModel):
    """Which bank entries to render, in the order they should appear.

    Validated against the bank passed in as validation context, so a typo'd
    or non-existent ID fails loudly here rather than silently vanishing from
    the rendered resume.
    """

    model_config = ConfigDict(extra="forbid")

    education: list[str] = []
    experience: list[EntryItem] = []
    projects: list[EntryItem] = []
    activities: list[EntryItem] = []
    certifications: list[str] = []
    skills: list[str] = []

    @model_validator(mode="after")
    def _resolve_against_bank(self, info: ValidationInfo) -> "Selection":
        bank = (info.context or {}).get("bank")
        if bank is None:
            return self

        problems: list[str] = []

        for section, prefix in SECTION_PREFIX.items():
            entries = bank.get(section, []) or []
            by_id = {e["id"]: e for e in entries}
            available = list(by_id)
            seen: set[str] = set()
            for item in getattr(self, section):
                entry_id = ref_id(item)
                if entry_id in seen:
                    problems.append(
                        f"{section}: '{entry_id}' listed more than once"
                    )
                    continue
                seen.add(entry_id)
                if not entry_id.startswith(prefix):
                    problems.append(
                        f"{section}: '{entry_id}' has the wrong prefix "
                        f"(entries in '{section}' must start with '{prefix}')"
                    )
                    continue
                if entry_id not in by_id:
                    problems.append(
                        f"{section}: '{entry_id}' does not exist in the bank"
                        + _suggest(entry_id, available)
                    )
                    continue
                if isinstance(item, EntryRef):
                    problems.extend(
                        _check_entry(section, item, by_id[entry_id])
                    )

        skill_names = [s["name"] for s in bank.get("skills", []) or []]
        seen_skills: set[str] = set()
        for name in self.skills:
            if name in seen_skills:
                problems.append(f"skills: '{name}' listed more than once")
                continue
            seen_skills.add(name)
            if name not in skill_names:
                problems.append(
                    f"skills: '{name}' is not in the bank's top-level skills array"
                    + _suggest(name, skill_names)
                )

        if problems:
            raise ValueError(
                "selection does not resolve against the bank:\n  - "
                + "\n  - ".join(problems)
            )
        return self


def _check_entry(section: str, item: EntryRef, entry: dict) -> list[str]:
    """Bullet IDs, variants and modes get the same treatment as entry IDs."""
    problems: list[str] = []

    if item.mode == "one_liner":
        if not entry.get("one_liner"):
            problems.append(
                f"{section}: '{item.id}' requests mode 'one_liner' but has no "
                f"'one_liner' field in the bank"
            )
        # mode overrides bullets; no point also validating a list we won't use.
        return problems

    if item.bullets is None:
        return problems
    if not item.bullets:
        problems.append(
            f"{section}: '{item.id}' has an empty 'bullets' list "
            f"(omit the field or use the bare ID string to include all bullets)"
        )
        return problems

    by_id = {b["id"]: b for b in entry.get("bullets", []) or []}
    seen: set[str] = set()
    for bullet in item.bullets:
        bullet_id = ref_id(bullet)
        if bullet_id in seen:
            problems.append(f"{section}: '{bullet_id}' listed more than once")
            continue
        seen.add(bullet_id)
        if not bullet_id.startswith(f"{item.id}_b"):
            problems.append(
                f"{section}: bullet '{bullet_id}' does not belong to '{item.id}' "
                f"(bullets of '{item.id}' must start with '{item.id}_b')"
            )
            continue
        if bullet_id not in by_id:
            problems.append(
                f"{section}: bullet '{bullet_id}' does not exist on '{item.id}' "
                f"(it has {len(by_id)}: {', '.join(by_id)})"
            )
            continue
        variant = bullet_variant(bullet)
        if variant != "text" and not by_id[bullet_id].get(variant):
            problems.append(
                f"{section}: bullet '{bullet_id}' requests variant '{variant}' "
                f"but has no '{variant}' field in the bank"
            )
    return problems


def _suggest(value: str, candidates: list[str]) -> str:
    close = difflib.get_close_matches(value, candidates, n=3, cutoff=0.6)
    return f" (did you mean: {', '.join(close)}?)" if close else ""


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def build_context(bank: dict, selection: Selection) -> dict:
    """Resolve each selected ID to its full bank entry, in selection order.

    When an entry specifies a bullet subset, its bullets are filtered and
    reordered to match. The bank itself is never mutated.
    """
    context: dict = {"profile": bank.get("profile", {})}
    for section in SECTION_PREFIX:
        by_id = {e["id"]: e for e in bank.get(section, []) or []}
        resolved = []
        for item in getattr(selection, section):
            entry = by_id[ref_id(item)]
            if isinstance(item, EntryRef):
                if item.mode == "one_liner":
                    # Substitute a single synthetic bullet so the template's
                    # existing per-bullet loop renders it with no new logic.
                    entry = {**entry, "bullets": [{"text": entry["one_liner"]}]}
                elif item.bullets is not None:
                    bank_bullets = {b["id"]: b for b in entry["bullets"]}
                    chosen = []
                    for bullet in item.bullets:
                        source = bank_bullets[ref_id(bullet)]
                        variant = bullet_variant(bullet)
                        # Swap `text` for the requested pre-authored variant.
                        chosen.append(
                            source if variant == "text"
                            else {**source, "text": source[variant]}
                        )
                    entry = {**entry, "bullets": chosen}
            resolved.append(entry)
        context[section] = resolved
    by_name = {s["name"]: s for s in bank.get("skills", []) or []}
    context["skills"] = [by_name[n] for n in selection.skills]
    return context


def compile_pdf(tex_path: Path) -> bool:
    """Compile to PDF if a LaTeX engine is present. Returns True on success."""
    engine = shutil.which("pdflatex") or shutil.which("xelatex")
    if not engine:
        print(
            f"\nNo LaTeX engine (pdflatex/xelatex) found on PATH.\n"
            f"Wrote {tex_path} only - compile it manually to get a PDF.",
            file=sys.stderr,
        )
        return False

    if Path(engine).stem == "xelatex":
        print(
            "Note: only xelatex was found. This template uses \\pdfgentounicode, "
            "which is a pdflatex primitive; compilation may fail.",
            file=sys.stderr,
        )

    result = subprocess.run(
        [engine, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
        cwd=tex_path.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    pdf_path = tex_path.with_suffix(".pdf")
    if result.returncode != 0 or not pdf_path.exists():
        print(f"\nLaTeX compilation failed ({Path(engine).stem}).", file=sys.stderr)
        tail = (result.stdout or "").strip().splitlines()[-25:]
        print("\n".join(tail), file=sys.stderr)
        print(f"\nThe rendered source is still at {tex_path}.", file=sys.stderr)
        return False

    # The engine reports this itself: "Output written on x.pdf (2 pages, 113176 bytes)."
    pages = None
    match = re.search(r"Output written on .*?\((\d+) pages?,", result.stdout or "")
    if match:
        pages = int(match.group(1))

    # Remove the auxiliary files LaTeX leaves behind.
    for suffix in (".aux", ".log", ".out", ".fls", ".fdb_latexmk"):
        tex_path.with_suffix(suffix).unlink(missing_ok=True)

    if pages is None:
        print(f"Compiled PDF: {pdf_path} (page count not reported by {Path(engine).stem})")
    else:
        print(f"Compiled PDF: {pdf_path} ({pages} page{'s' if pages != 1 else ''})")
        if pages > 1:
            print(
                f"Warning: this selection renders to {pages} pages. "
                f"Drop entries, bullets, or skills to fit one page.",
                file=sys.stderr,
            )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a tailored resume from experience_bank.json (no LLM, no generation).",
    )
    parser.add_argument("--bank", type=Path, default=Path("experience_bank.json"),
                        help="Path to experience_bank.json")
    parser.add_argument("--selection", type=Path, required=True,
                        help="JSON file listing which entry IDs to include, in render order")
    parser.add_argument("--template", type=Path, default=Path("resume_template.tex.jinja"),
                        help="Jinja2 LaTeX template")
    parser.add_argument("--output", type=Path, required=True,
                        help="Path to write the rendered .tex file")
    parser.add_argument("--no-compile", action="store_true",
                        help="Write the .tex only; skip PDF compilation")
    args = parser.parse_args()

    for path, label in ((args.bank, "bank"), (args.selection, "selection"),
                        (args.template, "template")):
        if not path.is_file():
            print(f"Error: {label} file not found: {path}", file=sys.stderr)
            return 1

    # utf-8-sig tolerates a BOM, which Windows editors and PowerShell add.
    bank = json.loads(args.bank.read_text(encoding="utf-8-sig"))
    raw_selection = json.loads(args.selection.read_text(encoding="utf-8-sig"))

    try:
        selection = Selection.model_validate(raw_selection, context={"bank": bank})
    except ValidationError as exc:
        print(f"Error: invalid selection file {args.selection}\n", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 1

    context = build_context(bank, selection)
    env = build_jinja_env(args.template.parent.resolve())
    template = env.get_template(args.template.name)
    rendered = template.render(**context)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Rendered LaTeX: {args.output}")

    counts = ", ".join(
        f"{section}={len(getattr(selection, section))}"
        for section in (*SECTION_PREFIX, "skills")
        if getattr(selection, section)
    )
    n_bullets = sum(len(e["bullets"]) for s in BULLET_SECTIONS for e in context[s])
    print(f"Included: {counts}, bullets={n_bullets}")

    if args.no_compile:
        return 0
    compile_pdf(args.output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
