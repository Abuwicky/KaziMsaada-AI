"""Small, dependency-free DOCX export for the CV builder.

Word documents are ZIP packages of XML parts. This module writes the minimum
parts needed for a clean, editable document so the app does not need an extra
third-party package.
"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

from .cv import build_cv_document

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

_CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{title}</dc:title>
  <dc:creator>KaziMsaada AI</dc:creator>
  <cp:lastModifiedBy>KaziMsaada AI</cp:lastModifiedBy>
</cp:coreProperties>"""

_APP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>KaziMsaada AI</Application>
</Properties>"""

_NAMESPACES = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)


def _text(value) -> str:
    return escape(str(value or ""), {'"': "&quot;"})


def _run(text: str, *, bold: bool = False, size: int = 20, color: str = "222222") -> str:
    bold_xml = "<w:b/>" if bold else ""
    return (
        "<w:r><w:rPr>"
        f"{bold_xml}<w:color w:val=\"{color}\"/><w:sz w:val=\"{size}\"/><w:szCs w:val=\"{size}\"/>"
        f"</w:rPr><w:t xml:space=\"preserve\">{_text(text)}</w:t></w:r>"
    )


def _paragraph(
    text: str,
    *,
    bold: bool = False,
    size: int = 20,
    color: str = "222222",
    align: str | None = None,
    space_after: int = 80,
    bullet: bool = False,
    heading_rule: bool = False,
) -> str:
    align_xml = f'<w:jc w:val="{align}"/>' if align else ""
    border_xml = (
        '<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="B8C2CC"/></w:pBdr>'
        if heading_rule
        else ""
    )
    indent_xml = '<w:ind w:left="360" w:hanging="220"/>' if bullet else ""
    prefix = "• " if bullet else ""
    return (
        "<w:p><w:pPr>"
        f"{align_xml}{border_xml}{indent_xml}"
        f'<w:spacing w:after="{space_after}"/>'
        "</w:pPr>"
        + _run(prefix + text, bold=bold, size=size, color=color)
        + "</w:p>"
    )


def _section(title: str) -> str:
    return _paragraph(title.upper(), bold=True, size=23, color="17365D", heading_rule=True, space_after=80)


def _document_xml(document: dict, accent: str) -> str:
    parts: list[str] = [
        _paragraph(
            document.get("name") or "Your Name",
            bold=True,
            size=40,
            color=accent,
            align="center",
            space_after=40,
        )
    ]
    if document.get("target_role"):
        parts.append(
            _paragraph(
                document["target_role"],
                bold=True,
                size=22,
                color="425466",
                align="center",
                space_after=40,
            )
        )
    contact = " | ".join(
        value
        for value in (
            document.get("location"),
            document.get("phone"),
            document.get("email"),
        )
        if value
    )
    if contact:
        parts.append(_paragraph(contact, size=19, color="526273", align="center"))

    def add_section(title: str, items: list[str]) -> None:
        if items:
            parts.append(_section(title))
            for item in items:
                parts.append(_paragraph(item, bullet=True))

    if document.get("summary"):
        parts.append(_section("Professional Summary"))
        parts.append(_paragraph(document["summary"]))

    add_section("Education", document.get("education", []))

    experience = document.get("experience", [])
    if experience:
        parts.append(_section("Work Experience"))
        for entry in experience:
            title = entry.get("job_title") or entry.get("organisation") or "Experience"
            parts.append(_paragraph(title, bold=True, size=21))
            details = " | ".join(
                value
                for value in (
                    entry.get("organisation"),
                    entry.get("location"),
                    " - ".join(
                        value
                        for value in (entry.get("start_date"), entry.get("end_date"))
                        if value
                    ),
                )
                if value
            )
            if details:
                parts.append(_paragraph(details, size=19, color="526273", space_after=50))
            for item in entry.get("responsibilities", []):
                parts.append(_paragraph(item, bullet=True))

    add_section("Projects and Practical Experience", document.get("projects", []))
    add_section("Volunteering", document.get("volunteering", []))
    add_section("Skills", document.get("skills", []))
    add_section("Certifications and Training", document.get("certifications", []))
    add_section("Languages", document.get("languages", []))
    add_section("Referees", document.get("referees", []))

    parts.append(
        _paragraph(
            "Created with KaziMsaada AI",
            size=15,
            color="8A97A6",
            space_after=0,
        )
    )

    section_properties = (
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="720" w:right="900" w:bottom="720" w:left="900" '
        'w:header="360" w:footer="360" w:gutter="0"/>'
        "</w:sectPr>"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {_NAMESPACES}><w:body>"
        + "".join(parts)
        + section_properties
        + "</w:body></w:document>"
    )


def generate_cv_docx(
    profile: dict,
    cv_data: dict | None = None,
    accent: str | None = None,
) -> bytes:
    """Return an editable DOCX file generated from the same CV data as the PDF."""

    document = build_cv_document(profile, cv_data)
    colour = str(accent or "#17365D").lstrip("#").upper()
    if len(colour) != 6 or any(ch not in "0123456789ABCDEF" for ch in colour):
        colour = "17365D"

    title = document.get("name") or "Professional CV"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", _CONTENT_TYPES)
        package.writestr("_rels/.rels", _ROOT_RELS)
        package.writestr("word/document.xml", _document_xml(document, colour))
        package.writestr("docProps/core.xml", _CORE.format(title=_text(title)))
        package.writestr("docProps/app.xml", _APP)
    return buffer.getvalue()


__all__ = ["generate_cv_docx"]
