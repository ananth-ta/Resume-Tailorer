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

Output is LaTeX (+ PDF) when pdflatex/xelatex is installed, otherwise a Word
.docx next to the requested path. Force one with --format latex|docx.
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


def find_latex_engine(explicit: Path | None = None) -> str | None:
    """An explicit engine path (from .claude/format.local) wins over PATH."""
    if explicit is not None:
        return str(explicit) if explicit.is_file() else None
    return shutil.which("pdflatex") or shutil.which("xelatex")


# --------------------------------------------------------------------------
# Word (.docx) fallback
# --------------------------------------------------------------------------

# Mirrors the LaTeX template's content and section order. Layout uses tab
# stops and real list bullets (no tables, text boxes or images) so the file
# stays ATS-parsable. Only the *content* is shared with the .tex path; every
# string still comes verbatim from the resolved bank entries.
DOCX_FONT = "Times New Roman"
DOCX_BODY_PT = 10
DOCX_TEXT_WIDTH_IN = 7.5  # letter paper, 0.5in margins


def render_docx(context: dict, output: Path) -> None:
    """Build the resume as a Word document from the resolved context."""
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.opc.constants import RELATIONSHIP_TYPE
        from docx.shared import Inches, Pt
    except ImportError:
        raise SystemExit(
            "Error: python-docx is required for Word output but is not installed.\n"
            "Install it with: <python> -m pip install -r requirements.txt"
        )

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.left_margin = section.right_margin = Inches(0.5)
    section.top_margin = section.bottom_margin = Inches(0.5)

    normal = doc.styles["Normal"]
    normal.font.name = DOCX_FONT
    normal.font.size = Pt(DOCX_BODY_PT)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), DOCX_FONT)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1.0

    def paragraph(align=None, before=0, after=0, keep_with_next=False):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(before)
        p.paragraph_format.space_after = Pt(after)
        p.paragraph_format.keep_with_next = keep_with_next
        if align is not None:
            p.alignment = align
        return p

    def run(p, text, bold=False, italic=False, size=None, small_caps=False,
            underline=False):
        r = p.add_run(text)
        r.bold, r.italic, r.underline = bold, italic, underline
        r.font.small_caps = small_caps
        if size:
            r.font.size = Pt(size)
        return r

    def hyperlink(p, url, text, size=None):
        r_id = p.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
        link = OxmlElement("w:hyperlink")
        link.set(qn("r:id"), r_id)
        r = run(p, text, underline=True, size=size)
        p._p.remove(r._r)
        link.append(r._r)
        p._p.append(link)

    def tab_stops(p, *stops):
        for inches, alignment in stops:
            p.paragraph_format.tab_stops.add_tab_stop(Inches(inches), alignment)

    right = (DOCX_TEXT_WIDTH_IN, WD_TAB_ALIGNMENT.RIGHT)

    def heading(text):
        p = paragraph(before=6, after=3, keep_with_next=True)
        run(p, text, size=12, small_caps=True)
        borders = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        for key, value in (("val", "single"), ("sz", "6"), ("space", "1"),
                           ("color", "000000")):
            bottom.set(qn(f"w:{key}"), value)
        borders.append(bottom)
        p._p.get_or_add_pPr().append(borders)

    def line(left_parts, right_text="", size=None, before=0):
        """One line: left runs, then a right-aligned tab and right_text.

        left_parts is a list of (text, bold, italic) tuples.
        """
        p = paragraph(before=before, keep_with_next=True)
        tab_stops(p, right)
        for text, bold, italic in left_parts:
            run(p, text, bold=bold, italic=italic, size=size)
        if right_text:
            run(p, "\t" + right_text, size=size)
        return p

    def bullets(items):
        for i, b in enumerate(items):
            p = paragraph(keep_with_next=i < len(items) - 1)
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.first_line_indent = Inches(-0.17)
            tab_stops(p, (0.25, WD_TAB_ALIGNMENT.LEFT))
            run(p, "•\t" + b["text"], size=DOCX_BODY_PT - 0.5)

    def dates(e):
        return f"{format_month_year(e.get('start'))} – {format_month_year(e.get('end'))}"

    profile = context["profile"]

    # Header
    p = paragraph(WD_ALIGN_PARAGRAPH.CENTER)
    run(p, profile.get("preferred_name", ""), bold=True, size=22, small_caps=True)
    p = paragraph(WD_ALIGN_PARAGRAPH.CENTER, after=2)
    sep = "  |  "
    run(p, f"{profile.get('location', '')}{sep}{profile.get('phone', '')}{sep}", size=9.5)
    hyperlink(p, f"mailto:{url_only(profile.get('email'))}", profile.get("email", ""), 9.5)
    for key in ("linkedin", "github"):
        run(p, sep, size=9.5)
        hyperlink(p, f"https://{url_only(profile.get(key))}", profile.get(key, ""), 9.5)

    if context["education"]:
        heading("Education")
        for e in context["education"]:
            line([(e["institution"], True, False)], e.get("location") or "")
            line([(e["degree"], False, True)], dates(e), size=9.5)
            if e.get("coursework") or e.get("gpa"):
                # coursework_extra is deliberately not printed; same rule as the .tex template.
                line([(e.get("coursework") or "", False, False)],
                     f"GPA: {e['gpa']}" if e.get("gpa") else "", size=9.5)

    if context["experience"]:
        heading("Experience")
        for e in context["experience"]:
            line([(e["title"], True, False)], dates(e), before=2)
            left = [(e["org"], False, True)]
            if e.get("location"):
                left.append(("    " + e["location"], True, False))
            line(left, size=9.5)
            bullets(e["bullets"])

    if context["projects"]:
        heading("Projects")
        for e in context["projects"]:
            left = [(e["title"], True, False)]
            if e.get("tech"):
                left += [("  |  ", False, False), (e["tech"], False, True)]
            line(left, dates(e), size=9.5, before=2)
            bullets(e["bullets"])

    if context["activities"]:
        heading("Activities")
        for e in context["activities"]:
            line([(e["org"], True, False), ("  |  ", False, False),
                  (e["title"], False, True)], dates(e), size=9.5, before=2)
            bullets(e["bullets"])

    if context["skills"]:
        heading("Technical Skills")
        categories: list[str] = []
        for s in context["skills"]:
            if s["category"] not in categories:
                categories.append(s["category"])
        for c in categories:
            names = ", ".join(s["name"] for s in context["skills"] if s["category"] == c)
            p = paragraph()
            run(p, c, bold=True, size=DOCX_BODY_PT - 0.5)
            run(p, f": {names}", size=DOCX_BODY_PT - 0.5)

    if context["certifications"]:
        heading("Certifications")
        for c in context["certifications"]:
            p = paragraph()
            tab_stops(p, (3.5, WD_TAB_ALIGNMENT.LEFT), right)
            run(p, c["name"], bold=True, size=DOCX_BODY_PT - 0.5)
            run(p, "\t" + format_month_year(c.get("date")), size=DOCX_BODY_PT - 0.5)
            cred = c.get("credential_id")
            if cred:
                run(p, "\t", size=DOCX_BODY_PT - 0.5)
                if is_url(cred):
                    hyperlink(p, f"https://{url_only(cred)}", cred, DOCX_BODY_PT - 0.5)
                else:
                    run(p, f"ID: {cred}", size=DOCX_BODY_PT - 0.5)

    doc.core_properties.author = profile.get("preferred_name", "")
    doc.core_properties.title = f"{profile.get('preferred_name', '')} - Resume".strip(" -")
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)


def compile_pdf(tex_path: Path, engine_path: Path | None = None) -> bool:
    """Compile to PDF if a LaTeX engine is present. Returns True on success."""
    engine = find_latex_engine(engine_path)
    if not engine:
        print(
            f"\nNo LaTeX engine found ({engine_path or 'pdflatex/xelatex on PATH'}).\n"
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
                        help="Output path. The extension is set by the format: "
                             ".tex (+ .pdf) for latex, .docx for docx")
    parser.add_argument("--format", choices=("auto", "latex", "docx"), default="auto",
                        help="auto (default) renders LaTeX when pdflatex/xelatex is "
                             "on PATH and falls back to a Word .docx otherwise")
    parser.add_argument("--latex-engine", type=Path, default=None,
                        help="Path to a pdflatex/xelatex executable that is not on PATH")
    parser.add_argument("--no-compile", action="store_true",
                        help="Write the .tex only; skip PDF compilation "
                             "(under --format auto this also selects latex)")
    args = parser.parse_args()

    fmt = args.format
    if fmt == "auto":
        if args.no_compile or find_latex_engine(args.latex_engine):
            fmt = "latex"
        else:
            fmt = "docx"
            print("No LaTeX engine (pdflatex/xelatex) found on PATH - "
                  "building a Word .docx instead.", file=sys.stderr)

    required = [(args.bank, "bank"), (args.selection, "selection")]
    if fmt == "latex":
        required.append((args.template, "template"))
    for path, label in required:
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

    if fmt == "docx":
        output = args.output.with_suffix(".docx")
        render_docx(context, output)
        print(f"Rendered Word document: {output}")
    else:
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

    if fmt == "docx":
        print(
            "Page count not verified: Word documents can't be paginated here. "
            "Open the file and confirm it fits one page.",
            file=sys.stderr,
        )
        return 0
    if args.no_compile:
        return 0
    compile_pdf(args.output.resolve(), args.latex_engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())
