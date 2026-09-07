"""
Rendering engine for the MemSOC Technical Design and Architecture
Document. Academic report style: one serif font throughout, black text
only, plain bordered tables with no color fill, page numbers, and
keep-together rules so headings and figure captions are never orphaned.
"""

from pathlib import Path

from docx import Document
from docx.shared import Pt, Inches, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

FONT = "Cambria"
BLACK = RGBColor(0x00, 0x00, 0x00)


def _add_field(paragraph, instr_text):
    run = paragraph.add_run()
    r = run._r
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instr_text
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    txt = OxmlElement("w:t")
    txt.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for el in (begin, instr, sep, txt, end):
        r.append(el)


def setup_styles(doc):
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(11.5)
    normal.font.color.rgb = BLACK
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.line_spacing = 1.25
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    heading_sizes = {1: 17, 2: 13.5, 3: 12}
    for level, size in heading_sizes.items():
        style = doc.styles[f"Heading {level}"]
        style.font.name = FONT
        style.font.size = Pt(size)
        style.font.color.rgb = BLACK
        style.font.bold = True
        style.font.italic = False
        style.paragraph_format.space_before = Pt(20 if level == 1 else 14)
        style.paragraph_format.space_after = Pt(8 if level == 1 else 6)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT


def setup_header_footer(doc, title):
    section = doc.sections[0]
    header_p = section.header.paragraphs[0]
    header_p.text = ""
    run = header_p.add_run(title)
    run.font.name = FONT
    run.font.size = Pt(9)
    run.font.color.rgb = BLACK
    run.font.italic = True
    header_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    footer_p = section.footer.paragraphs[0]
    footer_p.text = ""
    footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_field(footer_p, "PAGE")
    for run in footer_p.runs:
        run.font.name = FONT
        run.font.size = Pt(9.5)
        run.font.color.rgb = BLACK


def add_cover_page(doc, title, subtitle, meta_lines):
    for _ in range(5):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(title)
    run.font.name = FONT
    run.font.size = Pt(30)
    run.font.bold = True
    run.font.color.rgb = BLACK

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(subtitle)
    run.font.name = FONT
    run.font.size = Pt(15)
    run.font.italic = True
    run.font.color.rgb = BLACK

    for _ in range(7):
        doc.add_paragraph()

    for line in meta_lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(line)
        run.font.name = FONT
        run.font.size = Pt(11)
        run.font.color.rgb = BLACK

    doc.add_page_break()


def add_toc_page(doc):
    doc.add_heading("Table of Contents", level=1)
    p = doc.add_paragraph()
    _add_field(p, 'TOC \\o "1-3" \\h \\z \\u')
    for run in p.runs:
        run.font.name = FONT
        run.font.color.rgb = BLACK
    note = doc.add_paragraph()
    run = note.add_run(
        "(In Word, right-click this area and choose “Update Field” to populate "
        "the table of contents and page numbers.)"
    )
    run.font.italic = True
    run.font.size = Pt(9)
    run.font.color.rgb = BLACK
    doc.add_page_break()


def set_landscape(section):
    section.orientation = WD_ORIENT.LANDSCAPE
    w, h = section.page_width, section.page_height
    section.page_width, section.page_height = h, w
    section.left_margin = section.right_margin = Cm(1.5)
    section.top_margin = section.bottom_margin = Cm(1.5)


def add_figure(doc, image_path, caption, width_in, landscape=False):
    if landscape:
        new_section = doc.add_section()
        set_landscape(new_section)

    pic_par = doc.add_paragraph()
    pic_par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pic_par.paragraph_format.keep_with_next = True
    run = pic_par.add_run()
    run.add_picture(str(image_path), width=Inches(width_in))

    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.keep_with_next = False
    cap.paragraph_format.space_after = Pt(14)
    run = cap.add_run(caption)
    run.font.name = FONT
    run.font.italic = True
    run.font.size = Pt(10)
    run.font.color.rgb = BLACK

    if landscape:
        back_section = doc.add_section()
        back_section.orientation = WD_ORIENT.PORTRAIT
        w2, h2 = back_section.page_width, back_section.page_height
        if w2 > h2:
            back_section.page_width, back_section.page_height = h2, w2


def add_table(doc, headers, rows, caption=None, col_widths=None):
    if caption:
        cap = doc.add_paragraph()
        cap.paragraph_format.keep_with_next = True
        cap.paragraph_format.space_after = Pt(4)
        run = cap.add_run(caption)
        run.font.name = FONT
        run.font.bold = True
        run.font.size = Pt(10.5)
        run.font.color.rgb = BLACK

    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = ""
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(h)
        run.font.name = FONT
        run.font.bold = True
        run.font.size = Pt(10)
        run.font.color.rgb = BLACK

    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(str(val))
            run.font.name = FONT
            run.font.size = Pt(10)
            run.font.color.rgb = BLACK

    if col_widths:
        table.autofit = False
        for row_ in table.rows:
            for i, w in enumerate(col_widths):
                if i < len(row_.cells):
                    row_.cells[i].width = Inches(w)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)


def add_bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if isinstance(item, tuple):
            lead, rest = item
            r1 = p.add_run(lead + " -- ")
            r1.bold = True
            r1.font.name = FONT
            r1.font.color.rgb = BLACK
            r2 = p.add_run(rest)
            r2.font.name = FONT
            r2.font.color.rgb = BLACK
        else:
            run = p.add_run(item)
            run.font.name = FONT
            run.font.color.rgb = BLACK


def add_para(doc, text, bold=False, italic=False, size=None):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run(text)
    run.font.name = FONT
    run.font.color.rgb = BLACK
    run.bold = bold
    run.italic = italic
    if size:
        run.font.size = Pt(size)
    return p


def build_document(sections, assets_dir, out_path, cover, running_header):
    doc = Document()
    setup_styles(doc)

    section0 = doc.sections[0]
    section0.left_margin = section0.right_margin = Cm(2.2)
    section0.top_margin = section0.bottom_margin = Cm(2.0)

    setup_header_footer(doc, running_header)

    add_cover_page(doc, **cover)
    add_toc_page(doc)

    for sec in sections:
        heading_text = f"{sec['number']}  {sec['title']}"
        doc.add_heading(heading_text, level=1)

        for block in sec.get("blocks", []):
            render_block(doc, block, assets_dir)

        for sub in sec.get("subsections", []):
            doc.add_heading(f"{sub['number']}  {sub['title']}", level=2)
            for block in sub.get("blocks", []):
                render_block(doc, block, assets_dir)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    return out_path


def render_block(doc, block, assets_dir):
    kind = block["type"]

    if kind == "para":
        add_para(doc, block["text"], bold=block.get("bold", False), italic=block.get("italic", False))

    elif kind == "heading3":
        doc.add_heading(block["text"], level=3)

    elif kind == "bullets":
        add_bullets(doc, block["items"])

    elif kind == "figure":
        path = Path(assets_dir) / block["file"]
        add_figure(doc, path, block["caption"], width_in=block["width_in"],
                   landscape=block.get("landscape", False))

    elif kind == "table":
        add_table(doc, block["headers"], block["rows"], caption=block.get("caption"),
                   col_widths=block.get("col_widths"))

    elif kind == "pagebreak":
        doc.add_page_break()

    else:
        raise ValueError(f"unknown block type: {kind}")
