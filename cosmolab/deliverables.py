"""
CosmoLab client deliverables: turn a Markdown result (article, synthesis,
gap report, matrix) into a Word and/or PDF document with the firm's letterhead.

Every deliverable gets a cover page (firm, title, client, date), a header and
footer with page numbers, and a closing note that names the human reviewer.
Delivery is refused while the citation check still has open findings, or while
a cited claim is not backed by the paper it cites, unless the reviewer
explicitly accepts them.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path

from markdown_it import MarkdownIt

from . import config
from . import entail
from . import verify

MONTHS_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
             "Agustus", "September", "Oktober", "November", "Desember"]


class DeliveryBlocked(Exception):
    """Raised when the citation check has open findings."""

    def __init__(self, report: "verify.VerificationReport"):
        self.report = report
        super().__init__(f"{len(report.blocking)} sitasi belum terverifikasi")


class ClaimsBlocked(Exception):
    """Raised when cited claims are not backed by their paper, or could not be checked."""

    def __init__(self, claims_report: dict):
        self.claims_report = claims_report
        self.problems = entail.blocking_claims(claims_report)
        self.skipped = claims_report.get("skipped", 0)
        msg = f"{len(self.problems)} klaim tidak didukung sumber atau belum bisa dicek"
        if self.skipped:
            msg += f", {self.skipped} klaim melewati batas pemeriksaan"
        super().__init__(msg)


# Cited sentences checked before delivery. Beyond this the rest are counted as not checked.
DELIVERY_MAX_CLAIMS = 100


@dataclass
class DeliverableMeta:
    title: str
    reviewer: str
    client: str = ""
    project: str = ""
    date: datetime = field(default_factory=datetime.now)
    firm_name: str = ""
    firm_tagline: str = ""
    firm_address: str = ""
    firm_contact: str = ""
    firm_logo: Path | None = None
    citation_note: str = ""

    @property
    def date_text(self) -> str:
        return f"{self.date.day} {MONTHS_ID[self.date.month - 1]} {self.date.year}"

    @property
    def disclosure(self) -> str:
        return (
            f"Catatan penyusunan: dokumen ini disusun oleh {self.firm_name} dengan bantuan "
            f"perangkat analisis berbasis AI, lalu diperiksa dan disetujui oleh {self.reviewer}. "
            f"{self.citation_note}"
        ).strip()


def citation_note(report: "verify.VerificationReport") -> str:
    """Closing sentence about the citation check, stating only what was done."""
    if not report.references and not report.citations:
        return ""
    where = "koleksi riset proyek dan basis data Crossref" if report.online else "koleksi riset proyek"
    if report.ok:
        return f"Seluruh rujukan telah diverifikasi otomatis terhadap {where}."
    return (
        f"Rujukan diperiksa otomatis terhadap {where}; "
        f"{len(report.blocking)} rujukan yang tidak dapat diverifikasi otomatis diperiksa manual oleh peneliti."
    )


def default_meta(title: str, reviewer: str) -> DeliverableMeta:
    info = config.project_info()
    return DeliverableMeta(
        title=title,
        reviewer=reviewer,
        client=info.get("client", ""),
        project=config.PROJECT or "",
        firm_name=config.FIRM_NAME,
        firm_tagline=config.FIRM_TAGLINE,
        firm_address=config.FIRM_ADDRESS,
        firm_contact=config.FIRM_CONTACT,
        firm_logo=config.FIRM_LOGO if config.FIRM_LOGO and config.FIRM_LOGO.exists() else None,
    )


def split_title(md: str) -> tuple[str, str]:
    """Return (first H1 text, markdown without that H1)."""
    lines = md.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^#\s+(.+)", line)
        if m:
            title = re.sub(r"[*_`]", "", m.group(1)).strip()
            return title, "\n".join(lines[:i] + lines[i + 1:]).strip()
        if line.strip():
            break
    return "", md.strip()


def _md() -> MarkdownIt:
    return MarkdownIt("commonmark", {"html": False}).enable("table")


# ---------------------------------------------------------------------------
# Word (.docx)
# ---------------------------------------------------------------------------

def _add_page_number(paragraph):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    run = paragraph.add_run()
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)


def _add_inline(paragraph, children):
    """Write markdown-it inline tokens into a python-docx paragraph."""
    bold = italic = False
    link_href = None
    for tok in children or []:
        t = tok.type
        if t == "strong_open":
            bold = True
        elif t == "strong_close":
            bold = False
        elif t == "em_open":
            italic = True
        elif t == "em_close":
            italic = False
        elif t == "link_open":
            link_href = tok.attrs.get("href")
        elif t == "link_close":
            if link_href and link_href.startswith("http"):
                r = paragraph.add_run(f" ({link_href})")
                r.italic = True
            link_href = None
        elif t in ("softbreak",):
            paragraph.add_run(" ")
        elif t == "hardbreak":
            paragraph.add_run().add_break()
        elif t == "code_inline":
            r = paragraph.add_run(tok.content)
            r.font.name = "Consolas"
        elif t == "text":
            r = paragraph.add_run(tok.content)
            r.bold = bold or None
            r.italic = italic or None
        elif t == "image":
            paragraph.add_run(f"[Gambar: {tok.content}]")


def build_docx(body_md: str, meta: DeliverableMeta, out_path: Path) -> Path:
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.shared import Cm, Pt, RGBColor
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    doc = Document()
    styles = doc.styles
    styles["Normal"].font.name = "Calibri"
    styles["Normal"].font.size = Pt(10.5)
    styles["Normal"].paragraph_format.line_spacing = 1.15
    styles["Normal"].paragraph_format.space_after = Pt(4)
    accent = RGBColor(0x1E, 0x3A, 0x8A)
    dark_slate = RGBColor(0x0F, 0x17, 0x2A)

    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    for side in ("left_margin", "right_margin"):
        setattr(sec, side, Cm(2.54))
    sec.top_margin, sec.bottom_margin = Cm(2.54), Cm(2.2)
    sec.different_first_page_header_footer = True

    # Cover page - Executive Firm Letterhead
    if meta.firm_logo:
        doc.add_picture(str(meta.firm_logo), width=Cm(3.5))
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(meta.firm_name)
    r.bold, r.font.size, r.font.color.rgb = True, Pt(17), accent
    if meta.firm_tagline:
        p_tag = doc.add_paragraph()
        p_tag.paragraph_format.space_after = Pt(0)
        tr = p_tag.add_run(meta.firm_tagline.upper())
        tr.font.size, tr.font.color.rgb = Pt(9), RGBColor(0x64, 0x74, 0x8B)

    # Spacing before title
    p_space = doc.add_paragraph()
    p_space.paragraph_format.space_before = Pt(90)

    p_doctype = doc.add_paragraph()
    p_doctype.paragraph_format.space_after = Pt(4)
    dt_run = p_doctype.add_run("LAPORAN TELAAH EKSEKUTIF & STRATEGIS")
    dt_run.bold, dt_run.font.size, dt_run.font.color.rgb = True, Pt(9.5), RGBColor(0x64, 0x74, 0x8B)

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(16)
    r = p.add_run(meta.title)
    r.bold, r.font.size, r.font.color.rgb = True, Pt(22), dark_slate

    # Metadata card as a subtle single-cell box
    meta_items = [
        (label, value) for label, value in (
            ("Disusun untuk", meta.client),
            ("Kode proyek", meta.project),
            ("Tanggal", meta.date_text),
            ("Penelaah Resmi", meta.reviewer),
        ) if value
    ]
    if meta_items:
        meta_table = doc.add_table(rows=len(meta_items), cols=2)
        meta_table.style = "Normal Table"
        for idx, (label, val) in enumerate(meta_items):
            c0, c1 = meta_table.cell(idx, 0), meta_table.cell(idx, 1)
            c0.width, c1.width = Cm(3.8), Cm(12.2)

            p0 = c0.paragraphs[0]
            p0.paragraph_format.space_before = Pt(2)
            p0.paragraph_format.space_after = Pt(2)
            r0 = p0.add_run(f"{label}:")
            r0.bold = True
            r0.font.size = Pt(9.5)
            r0.font.color.rgb = dark_slate

            p1 = c1.paragraphs[0]
            p1.paragraph_format.space_before = Pt(2)
            p1.paragraph_format.space_after = Pt(2)
            r1 = p1.add_run(val)
            r1.font.size = Pt(9.5)

    p_space2 = doc.add_paragraph()
    p_space2.paragraph_format.space_before = Pt(80)

    for line in (meta.firm_address, meta.firm_contact):
        if line:
            p_addr = doc.add_paragraph()
            p_addr.paragraph_format.space_after = Pt(1)
            ar = p_addr.add_run(line)
            ar.font.size, ar.font.color.rgb = Pt(8.5), RGBColor(0x94, 0xA3, 0xB8)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # Header and footer for the body pages
    header = sec.header.paragraphs[0]
    header.text = f"{meta.firm_name}  |  {meta.title}"
    header.runs[0].font.size = Pt(8)
    header.runs[0].font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    fr = footer.add_run(f"Dokumen Telaah Resmi, untuk {meta.client}  ·  Halaman " if meta.client else "Halaman ")
    fr.font.size = Pt(8)
    _add_page_number(footer)

    # Body
    tokens = _md().parse(body_md)
    list_stack = []  # "bullet" / "ordered"
    in_quote = False
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        t = tok.type
        if t == "heading_open":
            level = min(int(tok.tag[1]), 4)
            h = doc.add_heading(level=level)
            h.paragraph_format.keep_with_next = True
            h.paragraph_format.space_before = Pt(14)
            h.paragraph_format.space_after = Pt(4)
            _add_inline(h, tokens[i + 1].children)
            for run in h.runs:
                if level == 1:
                    run.font.color.rgb = dark_slate
                    run.font.size = Pt(16)
                elif level == 2:
                    run.font.color.rgb = accent
                    run.font.size = Pt(13)
                elif level == 3:
                    run.font.color.rgb = dark_slate
                    run.font.size = Pt(11)
                else:
                    run.font.color.rgb = RGBColor(0x33, 0x41, 0x55)
                    run.font.size = Pt(10)
            i += 3
            continue
        if t == "bullet_list_open":
            list_stack.append("bullet")
        elif t == "ordered_list_open":
            list_stack.append("ordered")
        elif t in ("bullet_list_close", "ordered_list_close"):
            list_stack.pop()
        elif t == "blockquote_open":
            in_quote = True
        elif t == "blockquote_close":
            in_quote = False
        elif t == "paragraph_open":
            inline = tokens[i + 1]
            if list_stack:
                depth = min(len(list_stack), 3)
                base = "List Bullet" if list_stack[-1] == "bullet" else "List Number"
                style = base if depth == 1 else f"{base} {depth}"
                para = doc.add_paragraph(style=style)
            elif in_quote:
                para = doc.add_paragraph(style="Quote")
                para.paragraph_format.space_before = Pt(3)
                para.paragraph_format.space_after = Pt(4)
            else:
                para = doc.add_paragraph()
            _add_inline(para, inline.children)
            i += 3
            continue
        elif t in ("fence", "code_block"):
            para = doc.add_paragraph()
            r = para.add_run(tok.content.rstrip())
            r.font.name, r.font.size = "Consolas", Pt(9)
        elif t == "hr":
            doc.add_paragraph()
        elif t == "table_open":
            rows, j = [], i + 1
            current = None
            while tokens[j].type != "table_close":
                tt = tokens[j]
                if tt.type == "tr_open":
                    current = []
                elif tt.type == "tr_close":
                    rows.append(current)
                elif tt.type == "inline":
                    current.append(tt.children)
                j += 1
            if rows:
                ncols = max(len(r) for r in rows)
                table = doc.add_table(rows=len(rows), cols=ncols)
                table.style = "Table Grid"
                for ri, row in enumerate(rows):
                    for ci, cell_children in enumerate(row):
                        cell = table.cell(ri, ci)
                        if ncols == 2:
                            cell.width = Cm(4.8) if ci == 0 else Cm(11.2)
                        cell_p = cell.paragraphs[0]
                        cell_p.paragraph_format.space_before = Pt(3)
                        cell_p.paragraph_format.space_after = Pt(3)
                        cell_p.paragraph_format.line_spacing = 1.15
                        _add_inline(cell_p, cell_children)
                        if ri == 0:
                            shading_xml = parse_xml(r'<w:shd {} w:fill="F1F5F9"/>'.format(nsdecls('w')))
                            cell._tc.get_or_add_tcPr().append(shading_xml)
                            for run in cell_p.runs:
                                run.bold = True
                                run.font.color.rgb = dark_slate
                        elif ri % 2 == 1:
                            shading_xml = parse_xml(r'<w:shd {} w:fill="F8FAFC"/>'.format(nsdecls('w')))
                            cell._tc.get_or_add_tcPr().append(shading_xml)
                doc.add_paragraph()
            i = j + 1
            continue
        i += 1

    # Reviewer note
    doc.add_paragraph()
    note = doc.add_paragraph()
    nr = note.add_run(meta.disclosure)
    nr.italic, nr.font.size = True, Pt(8.5)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

PDF_CSS = """
* { font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif; }
body { font-size: 10pt; line-height: 1.55; color: #1E293B; }
h1 { font-size: 18pt; font-weight: 700; color: #0F172A; margin-top: 18pt; margin-bottom: 8pt; border-bottom: 1.5pt solid #E2E8F0; padding-bottom: 4pt; }
h2 { font-size: 13.5pt; font-weight: 700; color: #1E3A8A; margin-top: 16pt; margin-bottom: 6pt; border-bottom: 1pt solid #E2E8F0; padding-bottom: 3pt; }
h3 { font-size: 11.5pt; font-weight: 600; color: #1E293B; margin-top: 12pt; margin-bottom: 4pt; }
h4 { font-size: 10.5pt; font-weight: 600; color: #334155; margin-top: 10pt; margin-bottom: 3pt; }
p { margin-bottom: 6pt; text-align: justify; }
ul, ol { margin-top: 3pt; margin-bottom: 8pt; padding-left: 18pt; }
li { margin-bottom: 3pt; }
blockquote { margin: 8pt 0 10pt 0; padding: 6pt 12pt; background-color: #F8FAFC; border-left: 3.5pt solid #1E3A8A; color: #334155; font-style: italic; }
table { border-collapse: collapse; width: 100%; margin-top: 6pt; margin-bottom: 12pt; font-size: 9pt; }
th, td { border: 1pt solid #CBD5E1; padding: 5pt 7pt; text-align: left; vertical-align: top; }
th { background-color: #F1F5F9; color: #0F172A; font-weight: 700; }
tr:nth-child(even) td { background-color: #F8FAFC; }
code { font-family: Consolas, monospace; font-size: 8.5pt; background: #F1F5F9; padding: 1pt 3pt; border-radius: 2pt; }
pre { font-family: Consolas, monospace; font-size: 8.5pt; background: #F1F5F9; padding: 6pt; }
.note { font-size: 8pt; color: #64748B; font-style: italic; margin-top: 20pt; border-top: 1pt solid #E2E8F0; padding-top: 8pt; }
"""

COVER_CSS = """
* { font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif; }
.firm { font-size: 17pt; font-weight: 800; color: #1E3A8A; letter-spacing: 0.5px; }
.tagline { font-size: 9.5pt; color: #64748B; text-transform: uppercase; letter-spacing: 1px; margin-top: 2pt; }
.accent-bar { width: 50px; height: 3.5px; background-color: #1E3A8A; margin-top: 110pt; margin-bottom: 16pt; }
.doc-type { font-size: 10pt; font-weight: 600; text-transform: uppercase; letter-spacing: 1.5px; color: #64748B; margin-bottom: 8pt; }
.title { font-size: 22pt; font-weight: 800; line-height: 1.25; color: #0F172A; margin-bottom: 24pt; }
.meta-box { margin-top: 16pt; padding: 10pt 14pt; background-color: #F8FAFC; border-left: 3pt solid #1E3A8A; font-size: 9.5pt; }
.meta-row { margin-bottom: 4pt; color: #334155; }
.meta-label { font-weight: 600; color: #0F172A; display: inline-block; width: 120px; }
.contact { font-size: 8.5pt; color: #94A3B8; margin-top: 80pt; line-height: 1.4; border-top: 1pt solid #E2E8F0; padding-top: 10pt; }
"""


def _cover_html(meta: DeliverableMeta) -> str:
    parts = []
    if meta.firm_logo:
        parts.append(f'<img src="{escape(meta.firm_logo.name)}" width="100"/>')
    parts.append(f'<div class="firm">{escape(meta.firm_name)}</div>')
    if meta.firm_tagline:
        parts.append(f'<div class="tagline">{escape(meta.firm_tagline)}</div>')
    parts.append('<div class="accent-bar"></div>')
    parts.append('<div class="doc-type">Laporan Telaah Eksekutif & Celah Riset</div>')
    parts.append(f'<div class="title">{escape(meta.title)}</div>')
    meta_rows = []
    for label, value in (("Disusun untuk", meta.client), ("Kode proyek", meta.project),
                         ("Tanggal", meta.date_text), ("Diperiksa oleh", meta.reviewer)):
        if value:
            meta_rows.append(f'<div class="meta-row"><span class="meta-label">{escape(label)}:</span> {escape(value)}</div>')
    if meta_rows:
        parts.append(f'<div class="meta-box">{"".join(meta_rows)}</div>')
    contact = "<br/>".join(escape(x) for x in (meta.firm_address, meta.firm_contact) if x)
    if contact:
        parts.append(f'<div class="contact">{contact}</div>')
    return "\n".join(parts)


def build_pdf(body_md: str, meta: DeliverableMeta, out_path: Path) -> Path:
    import pymupdf

    out_path.parent.mkdir(parents=True, exist_ok=True)
    page_rect = pymupdf.paper_rect("a4")
    margin_x, margin_top, margin_bottom = 64, 72, 64
    content = pymupdf.Rect(margin_x, margin_top, page_rect.width - margin_x, page_rect.height - margin_bottom)

    body_html = _md().render(body_md)
    body_html += f'<p class="note">{escape(meta.disclosure)}</p>'
    archive = pymupdf.Archive(str(meta.firm_logo.parent)) if meta.firm_logo else None

    writer = pymupdf.DocumentWriter(str(out_path))
    for html, css in ((_cover_html(meta), COVER_CSS), (body_html, PDF_CSS)):
        story = pymupdf.Story(html=html, user_css=css, archive=archive)
        more = 1
        while more:
            device = writer.begin_page(page_rect)
            more, _ = story.place(content)
            story.draw(device)
            writer.end_page()
    writer.close()

    # Header and footer on every page except the cover.
    pdf = pymupdf.open(str(out_path))
    total = pdf.page_count
    grey = "color:#64748B; font-size:7.5pt; font-family:sans-serif;"
    for n, page in enumerate(pdf, start=1):
        if n == 1:
            continue
        page.insert_htmlbox(
            pymupdf.Rect(margin_x, 28, page_rect.width - margin_x, 50),
            f'<p style="{grey}">{escape(meta.firm_name)} &nbsp;|&nbsp; {escape(meta.title)}</p>',
        )
        conf = f"Rahasia, untuk {escape(meta.client)} &nbsp;·&nbsp; " if meta.client else ""
        page.insert_htmlbox(
            pymupdf.Rect(margin_x, page_rect.height - 44, page_rect.width - margin_x, page_rect.height - 24),
            f'<p style="{grey} text-align:right;">{conf}Halaman {n - 1} dari {total - 1}</p>',
        )
    pdf.saveIncr()
    pdf.close()
    return out_path


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def resolve_source(path_text: str) -> Path:
    """Find a markdown file: as given, or inside the active project's output folders."""
    p = Path(path_text)
    candidates = [p] if p.is_absolute() else [
        Path.cwd() / p, config.ROOT / p,
        *(config.ROOT / sub / p for sub in ("articles", "synthesis", "gaps", "matrices", "inspections")),
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    raise FileNotFoundError(f"File tidak ditemukan: {path_text}")


def deliver(
    source: Path,
    reviewer: str,
    formats: tuple = ("docx", "pdf"),
    title: str | None = None,
    online: bool = True,
    allow_unverified: bool = False,
    allow_unsupported_claims: bool = False,
    claims_report: dict | None = None,
) -> dict:
    """Check citations and cited claims, then write the client files to <project>/deliverables/.

    Returns {"report": VerificationReport, "qa_report": Path, "files": [Path, ...],
    "claims": claim report or None}.
    Raises DeliveryBlocked when citations are not verified and allow_unverified is False.
    Raises ClaimsBlocked when a cited claim is not supported, its source is missing, or it
    could not be judged, and allow_unsupported_claims is False. `claims_report` reuses a
    check already run, so accepting the findings does not run the LLM again.
    """
    reviewer = (reviewer or "").strip()
    if not reviewer:
        raise ValueError("Nama peneliti pemeriksa wajib diisi sebelum dokumen dikirim ke klien.")

    md = Path(source).read_text(encoding="utf-8")
    report = verify.verify_markdown(md, source=str(source), online=online)
    qa_path = verify.save_report(report)
    if not report.ok and not allow_unverified:
        raise DeliveryBlocked(report)

    # Every cited sentence is judged against the paper it cites (the paper's own text only).
    if claims_report is None and not allow_unsupported_claims:
        body_only, _ = verify.split_reference_section(md)
        claims_report = entail.check_answer(body_only, max_claims=DELIVERY_MAX_CLAIMS)
    if claims_report is not None and not allow_unsupported_claims:
        if entail.blocking_claims(claims_report) or claims_report.get("skipped"):
            raise ClaimsBlocked(claims_report)

    h1, body = split_title(md)
    meta = default_meta(title or h1 or Path(source).stem.replace("_", " "), reviewer)
    meta.citation_note = citation_note(report)

    out_dir = config.ROOT / "deliverables"
    stem = f"{meta.date.strftime('%Y%m%d')}_{re.sub(r'[^A-Za-z0-9]+', '_', meta.title).strip('_')[:70]}"
    files = []
    if "docx" in formats:
        files.append(build_docx(body, meta, out_dir / f"{stem}.docx"))
    if "pdf" in formats:
        files.append(build_pdf(body, meta, out_dir / f"{stem}.pdf"))
    return {"report": report, "qa_report": qa_path, "files": files, "claims": claims_report}
