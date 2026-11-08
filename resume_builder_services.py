"""
resume_builder.py
=================
ATS-Friendly Resume Builder
Reads a resume.json file and generates a polished Word (.docx) document.

Usage:
    python resume_builder.py resume.json
    python resume_builder.py resume.json -o MyResume.docx
"""

import json
import argparse
import os
from datetime import datetime

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml


# ──────────────────────────────────────────────
#  DESIGN SYSTEM
# ──────────────────────────────────────────────

FONT_NAME = "Calibri"
NAME_SIZE = Pt(18)
TITLE_SIZE = Pt(12)
CONTACT_SIZE = Pt(10)
SECTION_HEADING_SIZE = Pt(11)
BODY_SIZE = Pt(10.5)
SMALL_SIZE = Pt(10)
MARGIN_INCHES = 0.6
LINE_SPACING = 1.0

COLOR_BLACK = RGBColor(0x00, 0x00, 0x00)
COLOR_DARK_GRAY = RGBColor(0x33, 0x33, 0x33)
COLOR_MEDIUM_GRAY = RGBColor(0x55, 0x55, 0x55)
COLOR_BORDER = RGBColor(0x2E, 0x74, 0xB5)  # Professional blue for section borders


# ──────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────

def load_resume(path: str) -> dict:
    """Load and return the resume JSON data."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def set_margins(doc: Document, inches: float):
    """Set all page margins to the given value in inches."""
    for section in doc.sections:
        section.top_margin = Inches(inches)
        section.bottom_margin = Inches(inches)
        section.left_margin = Inches(inches)
        section.right_margin = Inches(inches)


def set_run_font(run, size=BODY_SIZE, bold=False, italic=False, color=COLOR_BLACK, font_name=FONT_NAME):
    """Apply font styling to a run."""
    run.font.name = font_name
    run.font.size = size
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    # Ensure Calibri is used for East Asian text too
    r = run._element
    rPr = r.find(qn("w:rPr"))
    if rPr is None:
        rPr = parse_xml(f"<w:rPr {nsdecls('w')}/>")
        r.insert(0, rPr)
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = parse_xml(f'<w:rFonts {nsdecls("w")} w:ascii="{font_name}" w:hAnsi="{font_name}" w:eastAsia="{font_name}" w:cs="{font_name}"/>')
        rPr.insert(0, rFonts)


def set_paragraph_spacing(paragraph, before=0, after=0, line_spacing=LINE_SPACING):
    """Set paragraph spacing."""
    pf = paragraph.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line_spacing


def add_section_heading(doc: Document, title: str):
    """
    Add an ATS-friendly section heading:
    ALL CAPS, bold, with a thin bottom border line.
    """
    paragraph = doc.add_paragraph()
    set_paragraph_spacing(paragraph, before=10, after=4)

    run = paragraph.add_run(title.upper())
    set_run_font(run, size=SECTION_HEADING_SIZE, bold=True, color=COLOR_DARK_GRAY)

    # Add bottom border to the paragraph
    pPr = paragraph._element.get_or_add_pPr()
    pBdr = parse_xml(
        f'<w:pBdr {nsdecls("w")}>'
        f'  <w:bottom w:val="single" w:sz="6" w:space="1" w:color="2E74B5"/>'
        f'</w:pBdr>'
    )
    pPr.append(pBdr)

    return paragraph


def add_bullet(doc: Document, text: str):
    """Add a bullet point paragraph."""
    paragraph = doc.add_paragraph()
    set_paragraph_spacing(paragraph, before=1, after=1)

    # Bullet character
    bullet_run = paragraph.add_run("•  ")
    set_run_font(bullet_run, size=BODY_SIZE, color=COLOR_DARK_GRAY)

    text_run = paragraph.add_run(text)
    set_run_font(text_run, size=BODY_SIZE, color=COLOR_DARK_GRAY)

    # Indent the bullet
    pf = paragraph.paragraph_format
    pf.left_indent = Inches(0.25)

    return paragraph


def format_date(date_str: str) -> str:
    """
    Convert date strings:
      '2019-06' → 'Jun 2019'
      'Present' → 'Present'
      '2016'   → '2016'
    """
    if not date_str or date_str.lower() == "present":
        return "Present"

    # Handle YYYY-MM format
    if "-" in date_str and len(date_str) == 7:
        try:
            dt = datetime.strptime(date_str, "%Y-%m")
            return dt.strftime("%b %Y")
        except ValueError:
            pass

    # Handle YYYY format
    if len(date_str) == 4 and date_str.isdigit():
        return date_str

    return date_str


# ──────────────────────────────────────────────
#  SECTION RENDERERS
# ──────────────────────────────────────────────

def render_header(doc: Document, basics: dict):
    """Render the name, title, and contact information at the top."""

    # ── Full Name ──
    name_para = doc.add_paragraph()
    name_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(name_para, before=0, after=0)
    name_run = name_para.add_run(basics.get("full_name", "").upper())
    set_run_font(name_run, size=NAME_SIZE, bold=True, color=COLOR_BLACK)

    # ── Title ──
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(title_para, before=0, after=2)
    title_run = title_para.add_run(basics.get("title", ""))
    set_run_font(title_run, size=TITLE_SIZE, color=COLOR_MEDIUM_GRAY)

    # ── Contact Line ──
    contact_parts = []
    if basics.get("email"):
        contact_parts.append(basics["email"])
    if basics.get("phone"):
        contact_parts.append(basics["phone"])
    if basics.get("location"):
        contact_parts.append(basics["location"])
    if basics.get("linkedin"):
        contact_parts.append(basics["linkedin"])
    if basics.get("website"):
        contact_parts.append(basics["website"])
    if basics.get("portfolio"):
        contact_parts.append(basics["portfolio"])

    if contact_parts:
        contact_para = doc.add_paragraph()
        contact_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_paragraph_spacing(contact_para, before=0, after=6)

        separator = "  |  "
        contact_text = separator.join(contact_parts)
        contact_run = contact_para.add_run(contact_text)
        set_run_font(contact_run, size=CONTACT_SIZE, color=COLOR_MEDIUM_GRAY)


def render_summary(doc: Document, summary: str):
    """Render the Professional Summary section."""
    if not summary:
        return

    add_section_heading(doc, "Professional Summary")

    para = doc.add_paragraph()
    set_paragraph_spacing(para, before=2, after=4)
    run = para.add_run(summary)
    set_run_font(run, size=BODY_SIZE, color=COLOR_DARK_GRAY)


def render_skills(doc: Document, skills: list):
    """Render the Technical Skills section."""
    if not skills:
        return

    add_section_heading(doc, "Technical Skills")

    for skill_group in skills:
        category = skill_group.get("category", "")
        items = skill_group.get("items", [])

        para = doc.add_paragraph()
        set_paragraph_spacing(para, before=1, after=1)

        # Bold category label
        cat_run = para.add_run(f"{category}: ")
        set_run_font(cat_run, size=BODY_SIZE, bold=True, color=COLOR_DARK_GRAY)

        # Comma-separated items
        items_run = para.add_run(", ".join(items))
        set_run_font(items_run, size=BODY_SIZE, color=COLOR_DARK_GRAY)


def render_experience(doc: Document, experience: list):
    """Render the Professional Experience section."""
    if not experience:
        return

    add_section_heading(doc, "Professional Experience")

    for i, job in enumerate(experience):
        role = job.get("role", "")
        company = job.get("company", "")
        location = job.get("location", "")
        start = format_date(job.get("start_date", ""))
        end = format_date(job.get("end_date", ""))

        # ── Role & Company line ──
        role_para = doc.add_paragraph()
        set_paragraph_spacing(role_para, before=6 if i > 0 else 2, after=0)

        role_run = role_para.add_run(role)
        set_run_font(role_run, size=BODY_SIZE, bold=True, color=COLOR_BLACK)

        sep_run = role_para.add_run("  —  ")
        set_run_font(sep_run, size=BODY_SIZE, color=COLOR_DARK_GRAY)

        company_run = role_para.add_run(company)
        set_run_font(company_run, size=BODY_SIZE, color=COLOR_DARK_GRAY)

        # ── Location & Date line ──
        meta_para = doc.add_paragraph()
        set_paragraph_spacing(meta_para, before=0, after=2)

        location_run = meta_para.add_run(location)
        set_run_font(location_run, size=SMALL_SIZE, italic=True, color=COLOR_MEDIUM_GRAY)

        date_run = meta_para.add_run(f"  |  {start} – {end}")
        set_run_font(date_run, size=SMALL_SIZE, color=COLOR_MEDIUM_GRAY)

        # ── Highlights (bullets) ──
        for highlight in job.get("highlights", []):
            add_bullet(doc, highlight)


def render_projects(doc: Document, projects: list):
    """Render the Projects section."""
    if not projects:
        return

    add_section_heading(doc, "Projects")

    for i, project in enumerate(projects):
        name = project.get("name", "")
        description = project.get("description", "")
        tech_stack = project.get("tech_stack", [])
        link = project.get("link", "")

        # ── Project Name ──
        name_para = doc.add_paragraph()
        set_paragraph_spacing(name_para, before=6 if i > 0 else 2, after=1)

        name_run = name_para.add_run(name)
        set_run_font(name_run, size=BODY_SIZE, bold=True, color=COLOR_BLACK)

        # ── Description ──
        if description:
            desc_para = doc.add_paragraph()
            set_paragraph_spacing(desc_para, before=0, after=1)
            desc_run = desc_para.add_run(description)
            set_run_font(desc_run, size=BODY_SIZE, color=COLOR_DARK_GRAY)

        # ── Tech Stack ──
        if tech_stack:
            tech_para = doc.add_paragraph()
            set_paragraph_spacing(tech_para, before=0, after=1)

            tech_label = tech_para.add_run("Tech Stack: ")
            set_run_font(tech_label, size=SMALL_SIZE, bold=True, color=COLOR_DARK_GRAY)

            tech_items = tech_para.add_run(", ".join(tech_stack))
            set_run_font(tech_items, size=SMALL_SIZE, color=COLOR_DARK_GRAY)

        # ── Link ──
        if link:
            link_para = doc.add_paragraph()
            set_paragraph_spacing(link_para, before=0, after=1)

            link_label = link_para.add_run("Link: ")
            set_run_font(link_label, size=SMALL_SIZE, bold=True, color=COLOR_DARK_GRAY)

            link_value = link_para.add_run(link)
            set_run_font(link_value, size=SMALL_SIZE, color=COLOR_BORDER)


def render_education(doc: Document, education: list):
    """Render the Education section."""
    if not education:
        return

    add_section_heading(doc, "Education")

    for i, edu in enumerate(education):
        institution = edu.get("institution", "")
        degree = edu.get("degree", "")
        field = edu.get("field", "")
        start_year = edu.get("start_year", "")
        end_year = edu.get("end_year", "")

        para = doc.add_paragraph()
        set_paragraph_spacing(para, before=4 if i > 0 else 2, after=1)

        # Degree in Field
        degree_text = f"{degree} in {field}" if field else degree
        degree_run = para.add_run(degree_text)
        set_run_font(degree_run, size=BODY_SIZE, bold=True, color=COLOR_BLACK)

        # Em dash + Institution
        inst_run = para.add_run(f"  —  {institution}")
        set_run_font(inst_run, size=BODY_SIZE, color=COLOR_DARK_GRAY)

        # Year range
        if start_year or end_year:
            year_text = f"  ({start_year} – {end_year})" if start_year and end_year else f"  ({start_year or end_year})"
            year_run = para.add_run(year_text)
            set_run_font(year_run, size=SMALL_SIZE, color=COLOR_MEDIUM_GRAY)


def render_certifications(doc: Document, certifications: list):
    """Render the Certifications section."""
    if not certifications:
        return

    add_section_heading(doc, "Certifications")

    for i, cert in enumerate(certifications):
        name = cert.get("name", "")
        issuer = cert.get("issuer", "")
        year = cert.get("year", "")

        para = doc.add_paragraph()
        set_paragraph_spacing(para, before=4 if i > 0 else 2, after=1)

        # Cert name
        name_run = para.add_run(name)
        set_run_font(name_run, size=BODY_SIZE, bold=True, color=COLOR_BLACK)

        # Issuer
        if issuer:
            issuer_run = para.add_run(f"  —  {issuer}")
            set_run_font(issuer_run, size=BODY_SIZE, color=COLOR_DARK_GRAY)

        # Year
        if year:
            year_run = para.add_run(f"  ({year})")
            set_run_font(year_run, size=SMALL_SIZE, color=COLOR_MEDIUM_GRAY)


# ──────────────────────────────────────────────
#  GENERIC / DYNAMIC SECTION RENDERER
# ──────────────────────────────────────────────

def prettify_section_name(key: str) -> str:
    """
    Convert a JSON key like 'volunteer_work' or 'awards'
    into a human-readable heading like 'Volunteer Work' or 'Awards'.
    """
    return key.replace("_", " ").replace("-", " ").title()


def render_generic_section(doc: Document, section_name: str, section_data):
    """
    Dynamically render ANY section based on its data shape.
    Handles:
      - str              → single paragraph
      - list[str]        → bullet list
      - list[dict]       → each dict rendered as a styled entry
      - dict             → key-value pairs
      - other            → str() fallback
    """
    if not section_data:
        return

    heading_text = prettify_section_name(section_name)
    add_section_heading(doc, heading_text)

    # ── Case 1: Plain string ──
    if isinstance(section_data, str):
        para = doc.add_paragraph()
        set_paragraph_spacing(para, before=2, after=4)
        run = para.add_run(section_data)
        set_run_font(run, size=BODY_SIZE, color=COLOR_DARK_GRAY)
        return

    # ── Case 2: List ──
    if isinstance(section_data, list):
        for i, item in enumerate(section_data):

            # Case 2a: List of strings → bullet points
            if isinstance(item, str):
                add_bullet(doc, item)

            # Case 2b: List of dicts → structured entries
            elif isinstance(item, dict):
                _render_generic_dict_entry(doc, item, is_first=(i == 0))

            # Case 2c: Anything else → toString
            else:
                add_bullet(doc, str(item))
        return

    # ── Case 3: Single dict ──
    if isinstance(section_data, dict):
        _render_generic_dict_entry(doc, section_data, is_first=True)
        return

    # ── Fallback ──
    para = doc.add_paragraph()
    set_paragraph_spacing(para, before=2, after=4)
    run = para.add_run(str(section_data))
    set_run_font(run, size=BODY_SIZE, color=COLOR_DARK_GRAY)


def _render_generic_dict_entry(doc: Document, entry: dict, is_first: bool = False):
    """
    Render a single dict entry smartly by detecting common field patterns:
      - 'name'/'title'/'role'/'organization' → bold heading
      - 'description'/'summary'              → paragraph
      - 'highlights'/'items'/'details'        → bullet list
      - date fields                           → formatted inline
      - everything else                       → "Key: value" line
    """
    # Fields we look for as the "title" of the entry
    TITLE_KEYS = ["name", "title", "role", "organization", "award", "language", "label"]
    # Fields we look for as a subtitle / secondary info
    SUBTITLE_KEYS = ["company", "institution", "issuer", "organization", "publisher", "awarder"]
    # Fields that become paragraphs
    PARAGRAPH_KEYS = ["description", "summary", "detail", "overview"]
    # Fields that become bullet lists
    LIST_KEYS = ["highlights", "items", "details", "courses", "keywords", "responsibilities"]
    # Date-related fields
    DATE_KEYS = ["start_date", "end_date", "start_year", "end_year", "date", "year"]
    # Fields to render as links
    LINK_KEYS = ["link", "url", "website", "href"]
    # Fields to render as comma-separated tags
    TAG_KEYS = ["tech_stack", "technologies", "tools", "skills", "tags"]

    rendered_keys = set()

    # ── Find and render the title ──
    title_text = None
    for key in TITLE_KEYS:
        if key in entry and entry[key]:
            title_text = str(entry[key])
            rendered_keys.add(key)
            break

    # ── Find subtitle ──
    subtitle_text = None
    for key in SUBTITLE_KEYS:
        if key in entry and entry[key] and key not in rendered_keys:
            subtitle_text = str(entry[key])
            rendered_keys.add(key)
            break

    # ── Find date info ──
    date_parts = []
    for key in DATE_KEYS:
        if key in entry and entry[key]:
            date_parts.append(format_date(str(entry[key])))
            rendered_keys.add(key)
    date_text = " - ".join(date_parts) if date_parts else None

    # ── Find location ──
    location_text = entry.get("location", "")
    if location_text:
        rendered_keys.add("location")

    # ── Render title line ──
    if title_text:
        title_para = doc.add_paragraph()
        set_paragraph_spacing(title_para, before=6 if not is_first else 2, after=0)

        title_run = title_para.add_run(title_text)
        set_run_font(title_run, size=BODY_SIZE, bold=True, color=COLOR_BLACK)

        if subtitle_text:
            sep_run = title_para.add_run("  --  ")
            set_run_font(sep_run, size=BODY_SIZE, color=COLOR_DARK_GRAY)
            sub_run = title_para.add_run(subtitle_text)
            set_run_font(sub_run, size=BODY_SIZE, color=COLOR_DARK_GRAY)

    # ── Render location & date line ──
    if location_text or date_text:
        meta_para = doc.add_paragraph()
        set_paragraph_spacing(meta_para, before=0, after=2)

        parts = []
        if location_text:
            parts.append(location_text)
        if date_text:
            parts.append(date_text)

        meta_run = meta_para.add_run("  |  ".join(parts))
        set_run_font(meta_run, size=SMALL_SIZE, italic=True, color=COLOR_MEDIUM_GRAY)

    # ── Render paragraph fields ──
    for key in PARAGRAPH_KEYS:
        if key in entry and entry[key] and key not in rendered_keys:
            rendered_keys.add(key)
            para = doc.add_paragraph()
            set_paragraph_spacing(para, before=1, after=1)
            run = para.add_run(str(entry[key]))
            set_run_font(run, size=BODY_SIZE, color=COLOR_DARK_GRAY)

    # ── Render tag/tech fields ──
    for key in TAG_KEYS:
        if key in entry and entry[key] and key not in rendered_keys:
            rendered_keys.add(key)
            items = entry[key]
            if isinstance(items, list):
                tag_para = doc.add_paragraph()
                set_paragraph_spacing(tag_para, before=0, after=1)
                label_run = tag_para.add_run(f"{prettify_section_name(key)}: ")
                set_run_font(label_run, size=SMALL_SIZE, bold=True, color=COLOR_DARK_GRAY)
                items_run = tag_para.add_run(", ".join(str(t) for t in items))
                set_run_font(items_run, size=SMALL_SIZE, color=COLOR_DARK_GRAY)

    # ── Render list/bullet fields ──
    for key in LIST_KEYS:
        if key in entry and entry[key] and key not in rendered_keys:
            rendered_keys.add(key)
            items = entry[key]
            if isinstance(items, list):
                for item in items:
                    add_bullet(doc, str(item))

    # ── Render link fields ──
    for key in LINK_KEYS:
        if key in entry and entry[key] and key not in rendered_keys:
            rendered_keys.add(key)
            link_para = doc.add_paragraph()
            set_paragraph_spacing(link_para, before=0, after=1)
            link_label = link_para.add_run(f"{prettify_section_name(key)}: ")
            set_run_font(link_label, size=SMALL_SIZE, bold=True, color=COLOR_DARK_GRAY)
            link_value = link_para.add_run(str(entry[key]))
            set_run_font(link_value, size=SMALL_SIZE, color=COLOR_BORDER)

    # ── Render any remaining unknown fields as "Key: value" ──
    for key, value in entry.items():
        if key in rendered_keys:
            continue
        if not value:
            continue

        para = doc.add_paragraph()
        set_paragraph_spacing(para, before=1, after=1)

        label_run = para.add_run(f"{prettify_section_name(key)}: ")
        set_run_font(label_run, size=BODY_SIZE, bold=True, color=COLOR_DARK_GRAY)

        if isinstance(value, list):
            value_text = ", ".join(str(v) for v in value)
        else:
            value_text = str(value)

        value_run = para.add_run(value_text)
        set_run_font(value_run, size=BODY_SIZE, color=COLOR_DARK_GRAY)


# ──────────────────────────────────────────────
#  SECTION REGISTRY & ORDERING
# ──────────────────────────────────────────────

# Maps JSON key → specialized renderer function.
# "basics" and "summary" are handled separately in the header.
SECTION_REGISTRY = {
    "skills":         lambda doc, data: render_skills(doc, data),
    "experience":     lambda doc, data: render_experience(doc, data),
    "projects":       lambda doc, data: render_projects(doc, data),
    "education":      lambda doc, data: render_education(doc, data),
    "certifications": lambda doc, data: render_certifications(doc, data),
}

# Preferred ordering for known sections. Unknown sections appear after these.
SECTION_ORDER = [
    "skills",
    "experience",
    "projects",
    "education",
    "certifications",
]

# Keys that are NOT rendered as standalone sections
# (they are consumed by render_header or are metadata)
SKIPPED_KEYS = {"basics"}


# ──────────────────────────────────────────────
#  MAIN ORCHESTRATOR
# ──────────────────────────────────────────────

def build_resume(json_path: str, output_path: str = None):
    """
    Build the resume Word document from a JSON file.
    Dynamically discovers all sections in the JSON — known sections
    use specialized renderers, unknown sections use the generic renderer.

    Args:
        json_path:   Path to the resume.json file.
        output_path: Optional output path for the .docx file.
                     Defaults to <full_name>_Resume.docx in the same directory.
    """
    # 1. Load JSON
    data = load_resume(json_path)
    basics = data.get("basics", {})
    full_name = basics.get("full_name", "Resume")

    # 2. Determine output path
    if not output_path:
        safe_name = full_name.replace(" ", "_")
        output_dir = os.path.dirname(os.path.abspath(json_path))
        output_path = os.path.join(output_dir, f"{safe_name}_Resume.docx")

    # 3. Create document & set margins
    doc = Document()
    set_margins(doc, MARGIN_INCHES)

    # Set default font for the document
    style = doc.styles["Normal"]
    style.font.name = FONT_NAME
    style.font.size = BODY_SIZE
    style.font.color.rgb = COLOR_DARK_GRAY
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.line_spacing = LINE_SPACING

    # 4. Render header (always first — uses basics)
    render_header(doc, basics)
    render_summary(doc, basics.get("summary", ""))

    # 5. Build ordered list of sections to render
    all_section_keys = [k for k in data.keys() if k not in SKIPPED_KEYS]

    # Ordered sections first, then any unknown sections in their JSON order
    ordered_sections = []
    for key in SECTION_ORDER:
        if key in all_section_keys:
            ordered_sections.append(key)

    # Append any sections NOT in SECTION_ORDER (new/unknown ones)
    for key in all_section_keys:
        if key not in ordered_sections:
            ordered_sections.append(key)

    # 6. Render each section
    for section_key in ordered_sections:
        section_data = data[section_key]
        if not section_data:
            continue

        if section_key in SECTION_REGISTRY:
            # Use specialized renderer
            SECTION_REGISTRY[section_key](doc, section_data)
        else:
            # Use generic renderer for unknown sections
            render_generic_section(doc, section_key, section_data)

    # 7. Save
    doc.save(output_path)
    print(f"[SUCCESS] Resume generated successfully: {output_path}")
    return output_path


# ──────────────────────────────────────────────
#  CLI ENTRY POINT
# ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ATS-Friendly Resume Builder — Generate a Word document from resume.json"
    )
    parser.add_argument(
        "json_file",
        help="Path to the resume JSON file"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output .docx file path (default: <full_name>_Resume.docx)",
        default=None
    )

    args = parser.parse_args()
    build_resume(args.json_file, args.output)
