"""CV content building, preview rendering, and PDF generation.

The same structured CV data powers both the HTML live preview and the
downloadable PDF. PDF rendering preserves the original ReportLab templates
used by the command-line application.
"""

from __future__ import annotations

import html
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer
from xml.sax.saxutils import escape

from .config import CV_DIR
from .profiles import normalize_skills

TEMPLATES = {
    "classic": {
        "name": "Classic Professional",
        "description": "A clean, traditional, single-column layout.",
        "accent": "#17365D",
        "muted": "#526273",
    },
    "modern": {
        "name": "Modern Professional",
        "description": "A contemporary layout with a strong colour accent.",
        "accent": "#087E8B",
        "muted": "#425466",
    },
    "graduate": {
        "name": "Graduate and Early-Career",
        "description": "Highlights education, skills, and practical projects.",
        "accent": "#315C42",
        "muted": "#52665A",
    },
}

DEFAULT_TEMPLATE = "classic"

_EMAIL_LOCAL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$")
_EMAIL_DOMAIN_LABEL_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


def _clean_items(value) -> list[str]:
    """Return a clean list from a list-like value or multiline text.

    Older drafts and CLI callers may pass a single string where the newer UI
    passes a list. Handling both here keeps the CV data contract backward
    compatible without duplicating logic in the interface.
    """

    if value is None:
        return []

    if isinstance(value, str):
        raw_items: Iterable = value.replace(";", "\n").splitlines()
    elif isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = [value]

    return [str(item).strip() for item in raw_items if str(item).strip()]


def is_valid_email(value: str) -> bool:
    """Apply practical email checks without rejecting normal business addresses."""

    text = str(value or "").strip()
    if len(text) > 254 or text.count("@") != 1:
        return False

    local, domain = text.rsplit("@", 1)
    if not local or not domain or len(local) > 64:
        return False
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    if not _EMAIL_LOCAL_RE.fullmatch(local):
        return False

    labels = domain.split(".")
    if len(labels) < 2 or any(not label for label in labels):
        return False
    if any(not _EMAIL_DOMAIN_LABEL_RE.fullmatch(label) for label in labels):
        return False

    # A one-character top-level domain is not a usable public address.
    return len(labels[-1]) >= 2


def phone_digit_count(value: str) -> int:
    """Count digits so spaces, plus signs and hyphens do not affect validation."""

    return sum(1 for character in str(value or "") if character.isdigit())


def is_valid_phone(value: str) -> bool:
    return phone_digit_count(value) >= 7


def validate_cv_contact_details(
    target_role: str,
    email: str,
    phone: str,
) -> dict[str, str]:
    """Return field-specific messages for the CV download/save requirements."""

    errors: dict[str, str] = {}
    if not str(target_role or "").strip():
        errors["target_role"] = "Enter the target job position."

    if not is_valid_email(email):
        errors["email"] = (
            "Enter a complete email address with @ and a dot after it, "
            "for example name@example.com."
        )

    if not is_valid_phone(phone):
        errors["phone"] = "Enter a phone number with at least 7 digits."

    return errors


def add_cv_section(lines: list[str], heading: str, items: Iterable[str]) -> None:
    """Append a bulleted CV section when information is available."""

    items = _clean_items(items)
    if not items:
        return

    lines.append("")
    lines.append(heading.upper())
    lines.append("-" * 55)

    for item in items:
        lines.append(f"- {item}")


def add_work_experience_section(
    lines: list[str],
    experiences: Iterable[dict],
) -> None:
    """Append structured work experience using the original CLI format."""

    experiences = list(experiences)
    if not experiences:
        return

    lines.extend(["", "WORK EXPERIENCE", "-" * 55])

    for experience in experiences:
        lines.append("")
        lines.append(str(experience.get("job_title", "")).upper())
        lines.append(str(experience.get("organisation", "")))

        if experience.get("location"):
            lines.append(str(experience["location"]))

        date_range = (
            f"{experience.get('start_date', '')} - "
            f"{experience.get('end_date', '')}"
        ).strip(" -")

        if date_range:
            lines.append(date_range)

        for responsibility in _clean_items(experience.get("responsibilities", [])):
            lines.append(f"- {responsibility}")


def build_cv_content(profile: dict, cv_data: dict | None = None) -> str:
    """Build the canonical CV text used by the CLI and PDF generator."""

    cv_data = cv_data or {}

    name = str(profile.get("name", "")).strip()
    location = str(profile.get("location", "")).strip()
    phone = str(cv_data.get("phone", "")).strip()
    email = str(cv_data.get("email", "")).strip()
    target_role = str(cv_data.get("target_role", "")).strip()
    summary = str(cv_data.get("summary", "")).strip()

    education = _clean_items(cv_data.get("education", []))
    experience = [
        item
        for item in cv_data.get("experience", [])
        if isinstance(item, dict)
        and (
            str(item.get("job_title", "")).strip()
            or str(item.get("organisation", "")).strip()
        )
    ]
    projects = _clean_items(cv_data.get("projects", []))
    volunteering = _clean_items(cv_data.get("volunteering", []))
    certifications = _clean_items(cv_data.get("certifications", []))
    languages = _clean_items(cv_data.get("languages", []))
    referees = _clean_items(cv_data.get("referees", []))

    skills = cv_data.get("skills")
    if skills is None:
        skills = profile.get("skills", [])
    skills = normalize_skills(skills)

    lines: list[str] = []

    lines.append("=" * 60)
    lines.append(name.upper())
    lines.append("=" * 60)

    lines.append(f"Location: {location}")
    lines.append(f"Phone: {phone}")
    lines.append(f"Email: {email}")
    lines.append(f"Target Position: {target_role}")

    if summary:
        lines.extend(["", "PROFESSIONAL SUMMARY", "-" * 55, summary])

    lines.extend(["", "EDUCATION", "-" * 55, str(profile.get("education", ""))])

    for item in education:
        lines.append(f"- {item}")

    add_work_experience_section(lines, experience)
    add_cv_section(lines, "Projects and Practical Experience", projects)
    add_cv_section(lines, "Volunteering", volunteering)
    add_cv_section(lines, "Skills", skills)
    add_cv_section(lines, "Certifications and Training", certifications)
    add_cv_section(lines, "Languages", languages)
    add_cv_section(lines, "Referees", referees)

    lines.extend(
        ["", "=" * 60, "CV CREATED WITH KAZIMSAADA AI", "=" * 60]
    )

    return "\n".join(lines)


def _date_range(experience: dict) -> str:
    return (
        f"{experience.get('start_date', '')} - "
        f"{experience.get('end_date', '')}"
    ).strip(" -")


def _bullets(items: Iterable[str]) -> str:
    items = _clean_items(items)
    if not items:
        return ""
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"


def build_cv_html(
    profile: dict,
    cv_data: dict | None = None,
    template: str = DEFAULT_TEMPLATE,
) -> str:
    """Render a self-contained HTML preview from the same CV data."""

    cv_data = cv_data or {}
    if template not in TEMPLATES:
        template = DEFAULT_TEMPLATE

    palette = TEMPLATES[template]
    accent = palette["accent"]
    muted = palette["muted"]

    name = html.escape(str(profile.get("name", "")).strip())
    location = html.escape(str(profile.get("location", "")).strip())
    phone = html.escape(str(cv_data.get("phone", "")).strip())
    email = html.escape(str(cv_data.get("email", "")).strip())
    target_role = html.escape(str(cv_data.get("target_role", "")).strip())
    summary = html.escape(str(cv_data.get("summary", "")).strip())

    education = _clean_items(cv_data.get("education", []))
    experience = [
        item
        for item in cv_data.get("experience", [])
        if isinstance(item, dict)
        and (
            str(item.get("job_title", "")).strip()
            or str(item.get("organisation", "")).strip()
        )
    ]

    skills = cv_data.get("skills")
    if skills is None:
        skills = profile.get("skills", [])
    skills = normalize_skills(skills)

    sections: list[str] = []

    if summary:
        sections.append(
            f'<section><h2>Professional Summary</h2><p>{summary}</p></section>'
        )

    education_body = f'<p>{html.escape(str(profile.get("education", "")))}</p>'
    education_body += _bullets(education)
    sections.append(
        f"<section><h2>Education</h2>{education_body}</section>"
    )

    if experience:
        blocks = []
        for item in experience:
            title = html.escape(str(item.get("job_title", "")).strip())
            organisation = html.escape(str(item.get("organisation", "")).strip())
            place = html.escape(str(item.get("location", "")).strip())
            dates = html.escape(_date_range(item))
            responsibilities = _clean_items(item.get("responsibilities", []))

            meta = " · ".join(part for part in (place, dates) if part)
            block = ['<div class="entry">']
            if title:
                block.append(f'<div class="entry-title">{title}</div>')
            if organisation:
                block.append(f'<div class="entry-org">{organisation}</div>')
            if meta:
                block.append(f'<div class="entry-meta">{meta}</div>')
            block.append(_bullets(responsibilities))
            block.append("</div>")
            blocks.append("".join(block))

        sections.append(
            "<section><h2>Work Experience</h2>" + "".join(blocks) + "</section>"
        )

    list_sections = (
        ("Projects and Practical Experience", cv_data.get("projects", [])),
        ("Volunteering", cv_data.get("volunteering", [])),
        ("Skills", skills),
        ("Certifications and Training", cv_data.get("certifications", [])),
        ("Languages", cv_data.get("languages", [])),
        ("Referees", cv_data.get("referees", [])),
    )

    for heading, items in list_sections:
        body = _bullets(items)
        if body:
            sections.append(f"<section><h2>{heading}</h2>{body}</section>")

    contact_parts = [
        part
        for part in (
            location,
            phone,
            email,
            f"Target: {target_role}" if target_role else "",
        )
        if part
    ]
    contact = " &nbsp;|&nbsp; ".join(contact_parts)

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 14px; background: #eef2f7; font-family: "Segoe UI", Arial, sans-serif; }}
  .cv-shell {{
    width: 100%; min-height: 720px; background: #ffffff; color: #222222;
    padding: 40px 44px 36px; box-shadow: 0 10px 30px rgba(11,31,58,.14);
    border-top: 6px solid {accent};
  }}
  .cv-classic {{ text-align: left; }}
  .cv-classic header {{ text-align: center; border-bottom: 1.5px solid {accent}; padding-bottom: 12px; }}
  .cv-modern header {{ text-align: left; border-bottom: 2px solid {accent}; padding-bottom: 12px; }}
  .cv-graduate header {{ text-align: center; border-bottom: 1.5px solid {accent}; padding-bottom: 12px; }}
  h1 {{ margin: 0; font-size: 25px; letter-spacing: .6px; color: {accent}; }}
  .cv-modern h1 {{ font-size: 27px; }}
  .contact {{ margin-top: 7px; font-size: 12px; color: {muted}; line-height: 1.6; }}
  h2 {{
    margin: 22px 0 7px; padding-bottom: 3px; font-size: 12.5px; letter-spacing: .8px;
    text-transform: uppercase; color: {accent}; border-bottom: 1px solid #d8dfe8;
  }}
  .cv-modern h2 {{ border-bottom: 1px solid {accent}; }}
  p {{ margin: 5px 0; font-size: 13px; line-height: 1.55; }}
  ul {{ margin: 5px 0 8px; padding-left: 19px; }}
  li {{ margin: 3px 0; font-size: 13px; line-height: 1.5; }}
  .entry {{ margin-bottom: 12px; }}
  .entry-title {{ font-weight: 700; font-size: 13.5px; color: #1c2b3a; text-transform: uppercase; letter-spacing: .3px; }}
  .entry-org {{ font-size: 13px; font-weight: 600; color: #33475b; }}
  .entry-meta {{ font-size: 12px; color: {muted}; margin: 2px 0 4px; }}
  .empty-note {{ color: #8a97a6; font-style: italic; }}
</style>
</head>
<body>
  <div class="cv-shell cv-{template}">
    <header>
      <h1>{name or "Your Name"}</h1>
      <div class="contact">{contact or "Location &nbsp;|&nbsp; Phone &nbsp;|&nbsp; Email"}</div>
    </header>
    {''.join(sections) if sections else '<p class="empty-note" style="margin-top:26px">Start filling in the form and your CV preview will appear here.</p>'}
  </div>
</body>
</html>
"""


def generate_cv_pdf(
    cv_content: str,
    pdf_path,
    template: str = DEFAULT_TEMPLATE,
) -> None:
    """Render CV content using one of the built-in PDF templates.

    ``pdf_path`` may be a filesystem path or a writable binary buffer.
    """

    palettes = {
        "classic": {
            "accent": "#17365D",
            "muted": "#526273",
            "title_alignment": TA_CENTER,
            "top_margin": 19 * mm,
        },
        "modern": {
            "accent": "#087E8B",
            "muted": "#425466",
            "title_alignment": 0,
            "top_margin": 16 * mm,
        },
        "graduate": {
            "accent": "#315C42",
            "muted": "#52665A",
            "title_alignment": TA_CENTER,
            "top_margin": 18 * mm,
        },
    }

    if template not in palettes:
        template = DEFAULT_TEMPLATE

    palette = palettes[template]
    accent = colors.HexColor(palette["accent"])
    muted = colors.HexColor(palette["muted"])

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CVTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22 if template == "modern" else 20,
        leading=26,
        textColor=accent,
        alignment=palette["title_alignment"],
        spaceAfter=7,
    )

    heading_style = ParagraphStyle(
        "CVHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=14,
        textColor=accent,
        spaceBefore=11,
        spaceAfter=4,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "CVBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#222222"),
        spaceAfter=4,
    )

    bullet_style = ParagraphStyle(
        "CVBullet",
        parent=body_style,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=3,
    )

    contact_style = ParagraphStyle(
        "CVContact",
        parent=body_style,
        alignment=TA_CENTER if template != "modern" else 0,
        fontSize=8.8,
        leading=12,
        textColor=muted,
        spaceAfter=2,
    )

    target = (
        str(pdf_path)
        if isinstance(pdf_path, (str, Path))
        else pdf_path
    )

    document = SimpleDocTemplate(
        target,
        pagesize=A4,
        rightMargin=19 * mm,
        leftMargin=19 * mm,
        topMargin=palette["top_margin"],
        bottomMargin=19 * mm,
        title="Professional CV",
        author="KaziMsaada AI",
    )

    clean_lines = [
        line.strip()
        for line in cv_content.splitlines()
        if line.strip() and set(line.strip()) not in ({"="}, {"-"})
    ]

    story = []
    title_added = False

    for line in clean_lines:
        if not title_added:
            story.append(Paragraph(escape(line), title_style))
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=1.5 if template == "modern" else 1,
                    color=accent,
                    spaceBefore=2,
                    spaceAfter=9,
                )
            )
            title_added = True
            continue

        if line.startswith(("Location:", "Phone:", "Email:", "Target Position:")):
            story.append(Paragraph(escape(line), contact_style))
            continue

        if line.isupper() and len(line) <= 45:
            story.append(Paragraph(escape(line), heading_style))
            if template == "modern":
                story.append(
                    HRFlowable(
                        width="100%",
                        thickness=0.7,
                        color=accent,
                        spaceAfter=4,
                    )
                )
            continue

        if line.startswith("- "):
            story.append(
                Paragraph(f"&bull; {escape(line[2:])}", bullet_style)
            )
        else:
            story.append(Paragraph(escape(line), body_style))

    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(19 * mm, 11 * mm, "KaziMsaada AI")
        canvas.drawRightString(
            A4[0] - 19 * mm, 11 * mm, f"Page {doc.page}"
        )
        canvas.restoreState()

    document.build(
        story,
        onFirstPage=add_page_number,
        onLaterPages=add_page_number,
    )


def save_cv_bundle(
    profile: dict,
    cv_data: dict | None = None,
    template: str = DEFAULT_TEMPLATE,
    cv_dir: str | Path | None = None,
) -> dict:
    """Write text and PDF versions of a CV and return their details."""

    if template not in TEMPLATES:
        template = DEFAULT_TEMPLATE

    directory = Path(cv_dir) if cv_dir is not None else CV_DIR
    directory.mkdir(parents=True, exist_ok=True)

    cv_content = build_cv_content(profile, cv_data)

    profile_id = str(profile.get("profile_id", "unknown"))
    profile_token = "".join(
        character
        if character.isalnum() or character in ("-", "_")
        else "_"
        for character in profile_id
    )[:8] or "unknown"
    filename = (
        f"CV_{profile_token}_{template}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    )

    txt_path = directory / f"{filename}.txt"
    pdf_path = directory / f"{filename}.pdf"

    # Generate the PDF before writing either file so a PDF failure does not
    # leave an orphaned text CV behind. Remove a partial pair if a disk write
    # fails after generation.
    pdf_buffer = io.BytesIO()
    generate_cv_pdf(cv_content, pdf_buffer, template=template)
    pdf_bytes = pdf_buffer.getvalue()

    try:
        txt_path.write_text(cv_content, encoding="utf-8")
        pdf_path.write_bytes(pdf_bytes)
    except OSError:
        txt_path.unlink(missing_ok=True)
        pdf_path.unlink(missing_ok=True)
        raise

    return {
        "filename": filename,
        "template": template,
        "template_name": TEMPLATES[template]["name"],
        "txt_path": txt_path,
        "pdf_path": pdf_path,
        "content": cv_content,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def list_saved_cvs(cv_dir: str | Path | None = None) -> list[dict]:
    """List generated PDF CVs, newest first, for real dashboard metrics."""

    directory = Path(cv_dir) if cv_dir is not None else CV_DIR
    if not directory.exists():
        return []

    records = []
    for pdf_path in directory.glob("*.pdf"):
        try:
            stat = pdf_path.stat()
        except OSError:
            continue

        records.append(
            {
                "name": pdf_path.name,
                "path": pdf_path,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "text_path": pdf_path.with_suffix(".txt"),
            }
        )

    records.sort(key=lambda item: item["modified"], reverse=True)
    return records


def count_saved_cvs(cv_dir: str | Path | None = None) -> int:
    return len(list_saved_cvs(cv_dir))
