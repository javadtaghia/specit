from pathlib import Path
from io import BytesIO
import hashlib

SUPPORTED = {'.docx', '.pdf', '.md', '.txt'}


def _format_table_md(rows: list[list[str | None]]) -> str:
    cleaned = []
    for row in rows:
        if not row:
            continue
        cells = [' '.join((c or '').split()) for c in row]
        if any(cells):
            cleaned.append(cells)
    if not cleaned:
        return ''
    width = max(len(r) for r in cleaned)
    norm = [r + [''] * (width - len(r)) for r in cleaned]
    header = '| ' + ' | '.join(norm[0]) + ' |'
    sep = '| ' + ' | '.join(['---'] * width) + ' |'
    body = ['| ' + ' | '.join(r) + ' |' for r in norm[1:]]
    return '\n'.join([header, sep, *body])


def _parse_pdf(raw: bytes) -> list[dict]:
    chunks = []
    try:
        import pdfplumber

        with pdfplumber.open(BytesIO(raw)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                tables = page.find_tables() or []
                table_bboxes = [t.bbox for t in tables]

                def not_in_table(obj):
                    if not table_bboxes:
                        return True
                    x0 = obj.get('x0', 0)
                    top = obj.get('top', 0)
                    x1 = obj.get('x1', x0)
                    bottom = obj.get('bottom', top)
                    cx = (x0 + x1) / 2
                    cy = (top + bottom) / 2
                    for bx0, btop, bx1, bbottom in table_bboxes:
                        if bx0 - 1 <= cx <= bx1 + 1 and btop - 1 <= cy <= bbottom + 1:
                            return False
                    return True

                filtered = page.filter(not_in_table)
                prose = (filtered.extract_text() or '').strip()
                md_tables = []
                for t in tables:
                    extracted = t.extract()
                    md = _format_table_md(extracted or [])
                    if md:
                        md_tables.append(md)

                parts = [p for p in [prose, *md_tables] if p]
                txt = '\n\n'.join(parts).strip()
                if not txt:
                    txt = (page.extract_text() or '').strip()
                if txt:
                    chunks.append({'locator': f'page {i}', 'text': txt, 'has_tables': bool(md_tables)})
        return chunks
    except Exception:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(raw))
        for i, page in enumerate(reader.pages, 1):
            txt = (page.extract_text() or '').strip()
            if txt:
                chunks.append({'locator': f'page {i}', 'text': txt, 'has_tables': False})
        return chunks


def parse_source(filename: str, raw: bytes) -> dict:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError('Supported: DOCX, PDF, MD, TXT')
    source_id = hashlib.sha256(raw).hexdigest()[:12]
    chunks = []
    if suffix == '.docx':
        from docx import Document

        doc = Document(BytesIO(raw))
        for i, block in enumerate(doc.iter_inner_content(), 1):
            if hasattr(block, 'text'):
                txt = block.text.strip()
                has_tables = False
            else:
                rows = [[c.text for c in row.cells] for row in block.rows]
                txt = _format_table_md(rows)
                has_tables = True
            if txt:
                chunks.append({'locator': f'block {i}', 'text': txt, 'has_tables': has_tables})
    elif suffix == '.pdf':
        chunks = _parse_pdf(raw)
    else:
        data = raw.decode('utf-8-sig', errors='replace')
        lines = data.splitlines()
        for i in range(0, len(lines), 50):
            txt = '\n'.join(lines[i:i + 50]).strip()
            if txt:
                chunks.append({'locator': f'lines {i + 1}-{min(i + 50, len(lines))}', 'text': txt, 'has_tables': False})
    return {
        'source_id': source_id,
        'filename': filename,
        'size': len(raw),
        'chunks': chunks,
        'sha256': hashlib.sha256(raw).hexdigest(),
    }


def pack_chunks(sources, max_chars=12000):
    buffer = []
    chars = 0
    for src in sources:
        for ch in src['chunks']:
            header = f"[source_id={src['source_id']} | file={src['filename']} | locator={ch['locator']}]\n"
            text = ch['text']
            step = max(500, max_chars - 300)
            for idx in range(0, len(text), step):
                part = header + text[idx:idx + step]
                if buffer and chars + len(part) > max_chars:
                    yield '\n\n'.join(buffer)
                    buffer = []
                    chars = 0
                buffer.append(part)
                chars += len(part)
    if buffer:
        yield '\n\n'.join(buffer)


def index_sources(sources: list[dict]) -> dict[str, dict[str, str]]:
    """Build lookup {source_id: {normalized_locator: text}} accepting both 'page 2' and '<filename> page 2'."""
    idx: dict[str, dict[str, str]] = {}
    for src in sources:
        sid = src['source_id']
        fname = (src.get('filename') or '').lower()
        loc_map: dict[str, str] = {}
        for ch in src.get('chunks', []):
            loc = ch['locator'].strip().lower()
            loc_map[loc] = ch['text']
            if fname:
                loc_map[f'{fname} {loc}'] = ch['text']
                loc_map[f'{fname}, {loc}'] = ch['text']
                loc_map[f'{fname}: {loc}'] = ch['text']
        idx[sid] = loc_map
    return idx
