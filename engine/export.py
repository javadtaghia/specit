from pathlib import Path
from io import BytesIO
import json
import re
import zipfile
from docx import Document
from docx.shared import Inches, Pt, RGBColor

from .git_sync import sync_readable_docs
from .storage import Store, slug


def _add_markdown_to_docx(doc: Document, md_text: str, project_dir: Path | None = None):
    """Render common Markdown (headings, bullets, numbered lists, tables, code/mermaid blocks) into MS Word."""
    if not md_text:
        return
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Fenced code / Mermaid blocks
        if stripped.startswith('```'):
            lang = stripped[3:].strip() or 'code'
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1
            label = 'Diagram (Mermaid source)' if lang.lower() == 'mermaid' else f'Code ({lang})'
            p_lbl = doc.add_paragraph()
            run_lbl = p_lbl.add_run(label)
            run_lbl.bold = True
            run_lbl.font.size = Pt(9)
            run_lbl.font.color.rgb = RGBColor(0x3B, 0x59, 0x98)
            p_code = doc.add_paragraph('\n'.join(code_lines))
            for r in p_code.runs:
                r.font.name = 'Courier New'
                r.font.size = Pt(8.5)
            continue

        # Markdown table
        if '|' in stripped and i + 1 < len(lines) and re.match(r'^\|?[\s:-]+\|[\s|:-]*$', lines[i + 1].strip()):
            table_rows = []
            while i < len(lines) and '|' in lines[i].strip():
                raw_cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                table_rows.append(raw_cells)
                i += 1
            # Remove separator row
            if len(table_rows) >= 2:
                header = table_rows[0]
                body = table_rows[2:]
                cols = max(len(header), *(len(r) for r in body)) if body else len(header)
                tbl = doc.add_table(rows=1 + len(body), cols=cols)
                tbl.style = 'Table Grid'
                for ci, val in enumerate(header):
                    cell = tbl.rows[0].cells[ci]
                    cell.text = val
                    for p in cell.paragraphs:
                        for r in p.runs:
                            r.bold = True
                for ri, row in enumerate(body, 1):
                    for ci, val in enumerate(row[:cols]):
                        tbl.rows[ri].cells[ci].text = val
                doc.add_paragraph('')
            continue

        # Headings
        hm = re.match(r'^(#{1,4})\s+(.*)$', stripped)
        if hm:
            level = min(len(hm.group(1)), 4)
            doc.add_heading(hm.group(2).strip(), level=level)
            i += 1
            continue

        # Bullet list
        bm = re.match(r'^[-*+]\s+(.*)$', stripped)
        if bm:
            doc.add_paragraph(bm.group(1).strip(), style='List Bullet')
            i += 1
            continue

        # Numbered list
        nm = re.match(r'^\d+[.)]\s+(.*)$', stripped)
        if nm:
            doc.add_paragraph(nm.group(1).strip(), style='List Number')
            i += 1
            continue

        # Embedded Markdown image: ![caption](url_or_path)
        im = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', stripped)
        if im:
            alt, target = im.group(1).strip(), im.group(2).strip()
            img_file = None
            if project_dir:
                fname = Path(target.split('?')[0]).name
                cand = (project_dir / 'assets' / fname).resolve()
                if cand.parent == (project_dir / 'assets').resolve() and cand.exists() and cand.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif'}:
                    img_file = cand
            if img_file:
                try:
                    doc.add_picture(str(img_file), width=Inches(5.8))
                    if alt:
                        cap = doc.add_paragraph(alt)
                        for r in cap.runs:
                            r.italic = True
                            r.font.size = Pt(9)
                except Exception:
                    doc.add_paragraph(f'[Image: {alt or img_file.name}]')
            else:
                doc.add_paragraph(f'[Image: {alt or target}]')
            i += 1
            continue

        # Blockquote
        if stripped.startswith('>'):
            p = doc.add_paragraph(stripped.lstrip('> ').strip())
            for r in p.runs:
                r.italic = True
            i += 1
            continue

        # Normal paragraph
        if stripped:
            p = doc.add_paragraph()
            # Simple inline **bold** support
            tokens = re.split(r'(\*\*.*?\*\*)', stripped)
            for tok in tokens:
                if tok.startswith('**') and tok.endswith('**') and len(tok) > 4:
                    run = p.add_run(tok[2:-2])
                    run.bold = True
                else:
                    p.add_run(tok)
        i += 1


def export_markdown_docx_bytes(title: str, markdown_text: str, subtitle: str = '', project_dir: Path | None = None) -> bytes:
    """Export a single Markdown document to a styled MS Word (.docx) byte buffer."""
    doc = Document()
    doc.add_heading(title, level=0)
    if subtitle:
        p = doc.add_paragraph(subtitle)
        for r in p.runs:
            r.italic = True
            r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    _add_markdown_to_docx(doc, markdown_text, project_dir=project_dir)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def export_project_docx(
    project: Path,
    catalogue: dict | None = None,
    artifacts: dict | None = None,
    foundation: dict | None = None,
    planning: dict | None = None,
) -> Path:
    """Compile the full project Architecture Design Document into a Microsoft Word (.docx) file."""
    doc = Document()
    name = (catalogue or {}).get('project_name') or project.name
    doc.add_heading(f'{name} — Software Architecture & Specification', level=0)
    if catalogue and catalogue.get('project_summary'):
        doc.add_paragraph(catalogue['project_summary'])

    if catalogue:
        doc.add_heading('1. Process Catalogue & System Overview', level=1)
        if catalogue.get('systems'):
            doc.add_heading('Systems & Responsibilities', level=2)
            tbl = doc.add_table(rows=1 + len(catalogue['systems']), cols=3)
            tbl.style = 'Table Grid'
            for ci, h in enumerate(['System', 'Responsibility', 'Ownership']):
                tbl.rows[0].cells[ci].text = h
            for ri, s in enumerate(catalogue['systems'], 1):
                tbl.rows[ri].cells[0].text = s.get('name', '')
                tbl.rows[ri].cells[1].text = s.get('responsibility', '')
                tbl.rows[ri].cells[2].text = s.get('ownership', '')

        procs = catalogue.get('processes', [])
        if procs:
            doc.add_heading('Process Inventory', level=2)
            tbl = doc.add_table(rows=1 + len(procs), cols=4)
            tbl.style = 'Table Grid'
            for ci, h in enumerate(['ID', 'Process', 'Actors', 'Confidence']):
                tbl.rows[0].cells[ci].text = h
            for ri, p in enumerate(procs, 1):
                tbl.rows[ri].cells[0].text = p.get('id', '')
                tbl.rows[ri].cells[1].text = p.get('name', '')
                tbl.rows[ri].cells[2].text = ', '.join(p.get('actors', []))
                tbl.rows[ri].cells[3].text = p.get('confidence', '')

        if catalogue.get('open_questions'):
            doc.add_heading('Open Questions', level=2)
            for q in catalogue['open_questions']:
                doc.add_paragraph(str(q), style='List Bullet')

    if artifacts:
        doc.add_page_break()
        doc.add_heading('2. Architecture Artifacts by Process', level=1)
        for pid, art in artifacts.items():
            doc.add_heading(f'Process {pid}', level=2)
            for label, field in [
                ('Operational Workflow', 'workflow_md'),
                ('System Boundaries', 'boundaries_md'),
                ('Domain Model', 'domain_md'),
                ('State Machine', 'states_md'),
            ]:
                if art.get(field):
                    doc.add_heading(f'{pid} — {label}', level=3)
                    _add_markdown_to_docx(doc, art[field], project_dir=project)

    if foundation:
        doc.add_page_break()
        doc.add_heading('3. Spec Kit Foundation', level=1)
        for label, field in [
            ('Constitution', 'constitution_md'),
            ('Specification', 'specification_md'),
            ('Clarification & Open Decisions', 'clarification_md'),
        ]:
            if foundation.get(field):
                doc.add_heading(label, level=2)
                _add_markdown_to_docx(doc, foundation[field], project_dir=project)

    if planning:
        doc.add_page_break()
        doc.add_heading('4. Implementation Plan & Tasks', level=1)
        if planning.get('plan_md'):
            doc.add_heading('Technical Plan', level=2)
            _add_markdown_to_docx(doc, planning['plan_md'], project_dir=project)
        if planning.get('tasks_md'):
            doc.add_heading('Task Breakdown', level=2)
            _add_markdown_to_docx(doc, planning['tasks_md'], project_dir=project)

    out = project / f'{project.name}-architecture.docx'
    doc.save(out)
    return out


def export_speckit(
    project: Path,
    foundation: dict,
    planning: dict | None = None,
    catalogue: dict | None = None,
    artifacts: dict | None = None,
) -> Path:
    """Export Spec Kit-compatible handoff plus architecture artifacts, diagrams, and MS Word SAD."""
    target = project / 'speckit-handoff'
    (target / '.specify' / 'memory').mkdir(parents=True, exist_ok=True)
    feat = target / 'specs' / '001-project-foundation'
    feat.mkdir(parents=True, exist_ok=True)

    (target / '.specify' / 'memory' / 'constitution.md').write_text(foundation['constitution_md'], encoding='utf-8')
    (feat / 'spec.md').write_text(foundation['specification_md'], encoding='utf-8')
    (feat / 'clarification.md').write_text(foundation['clarification_md'], encoding='utf-8')

    if planning:
        (feat / 'plan.md').write_text(planning['plan_md'], encoding='utf-8')
        (feat / 'tasks.md').write_text(planning['tasks_md'], encoding='utf-8')

    if artifacts:
        arch_dir = target / 'architecture'
        arch_dir.mkdir(exist_ok=True)
        for pid, art in artifacts.items():
            pdir = arch_dir / pid
            pdir.mkdir(exist_ok=True)
            for fname, field in [
                ('workflow.md', 'workflow_md'),
                ('boundaries.md', 'boundaries_md'),
                ('domain.md', 'domain_md'),
                ('states.md', 'states_md'),
            ]:
                if art.get(field):
                    (pdir / fname).write_text(art[field], encoding='utf-8')

    diagrams_dir = project / 'diagrams'
    if diagrams_dir.exists():
        out_diag = target / 'diagrams'
        out_diag.mkdir(exist_ok=True)
        for df in diagrams_dir.glob('*.drawio'):
            (out_diag / df.name).write_text(df.read_text(encoding='utf-8'), encoding='utf-8')

    # Include compiled MS Word document inside the handoff
    docx_path = export_project_docx(project, catalogue=catalogue, artifacts=artifacts, foundation=foundation, planning=planning)
    (target / docx_path.name).write_bytes(docx_path.read_bytes())

    (target / 'README.md').write_text(
        '# Spec Kit & Architecture Handoff\n\n'
        'Generated by SPECiT (human-reviewed).\n\n'
        'Contents:\n'
        '- `.specify/memory/constitution.md` — Project principles and gates\n'
        '- `specs/001-project-foundation/` — Specification, Clarification, Plan, Tasks\n'
        '- `architecture/` — Per-process workflow, boundary, domain, and state Markdown\n'
        '- `diagrams/` — Editable `.drawio` architecture diagrams\n'
        f'- `{docx_path.name}` — Compiled Microsoft Word Architecture Document\n\n'
        'Official Spec Kit guidance: https://github.com/github/spec-kit\n',
        encoding='utf-8',
    )

    out = project / 'speckit-handoff.zip'
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for file in target.rglob('*'):
            if file.is_file():
                z.write(file, file.relative_to(target))
    return out


def save_code(project: Path, files: dict[str, str], overwrite: bool = False) -> Path:
    base = (project / 'generated-code').resolve()
    base.mkdir(exist_ok=True)
    for name, content in files.items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0].startswith('.'):
            raise ValueError(f'Unsafe path: {name}')
        dest = (base / path).resolve()
        if not dest.is_relative_to(base):
            raise ValueError(f'Unsafe resolved path: {name}')
        if dest.exists() and not overwrite:
            raise ValueError(f'Cannot overwrite existing generated file: {name}')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding='utf-8')
    return base


def export_project_zip_bytes(project: Path) -> bytes:
    """Package the entire project workspace (sources, catalogue, artifacts, diagrams, assets, comments, revisions, docs) into a portable ZIP."""
    sync_readable_docs(project)
    buf = BytesIO()
    skip_dirs = {'.git', '__pycache__', 'speckit-handoff'}
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        manifest = {
            'format': 'specit-project',
            'version': 1,
            'project_slug': project.name,
        }
        z.writestr('project-bundle.json', json.dumps(manifest, indent=2))
        for file in sorted(project.rglob('*')):
            if not file.is_file():
                continue
            rel = file.relative_to(project)
            if any(part in skip_dirs for part in rel.parts):
                continue
            if file.name == '.DS_Store' or file.suffix.lower() == '.zip':
                continue
            z.write(file, str(rel))
    return buf.getvalue()


def import_project_zip(store: Store, raw_zip: bytes, project_name: str = '') -> dict:
    """Safely import a portable Architecture Engine project ZIP into a workspace folder."""
    try:
        zf = zipfile.ZipFile(BytesIO(raw_zip))
    except zipfile.BadZipFile as e:
        raise ValueError('Uploaded file is not a valid ZIP archive') from e

    with zf:
        names = zf.namelist()
        if not names:
            raise ValueError('ZIP archive is empty')

        base_slug = slug(project_name) if project_name.strip() else ''
        if not base_slug and 'project-bundle.json' in names:
            try:
                manifest = json.loads(zf.read('project-bundle.json').decode('utf-8'))
                base_slug = slug(manifest.get('project_slug') or '')
            except Exception:
                pass
        if not base_slug:
            base_slug = 'imported-project'

        # Avoid clobbering an existing non-empty project
        target_slug = base_slug
        n = 2
        while (store.root / target_slug).exists() and any((store.root / target_slug).iterdir()):
            target_slug = f'{base_slug}-{n}'
            n += 1

        dest_root = store.project(target_slug).resolve()
        extracted = 0
        for info in zf.infolist():
            if info.is_dir():
                continue
            rel = Path(info.filename)
            if rel.is_absolute() or '..' in rel.parts or not rel.parts:
                raise ValueError(f'Unsafe path inside ZIP: {info.filename}')
            if any(part == '.git' for part in rel.parts) or rel.name == '.DS_Store':
                continue
            target = (dest_root / rel).resolve()
            if not target.is_relative_to(dest_root):
                raise ValueError(f'Unsafe resolved path inside ZIP: {info.filename}')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info))
            extracted += 1

    return {'project_slug': target_slug, 'files_imported': extracted}
