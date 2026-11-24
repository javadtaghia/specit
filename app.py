import logging
from pathlib import Path
from typing import Any
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

logger = logging.getLogger('uvicorn.error')

from engine.diagrams import extract_mermaid_blocks, mermaid_to_drawio_xml, process_to_drawio_xml
from engine.export import (
    export_markdown_docx_bytes,
    export_project_docx,
    export_project_zip_bytes,
    export_speckit,
    import_project_zip,
    save_code,
)
from engine.git_sync import commit_project, connect_git, get_git_status, pull_project
from engine.llm import LLMClient, detect_providers
from engine.model import Artifact, Catalogue, CodeBundle, Foundation, Planning
from engine.pipeline import (
    assess,
    extract_catalogue,
    foundation,
    generate_artifact,
    implementation,
    planning,
    quality_checks,
    rerun_single_document,
    rerun_single_process_catalogue,
    review_scoped_item,
    _compact_catalogue_summary,
)
from engine.sources import parse_source
from engine.storage import Store

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / 'web'
EXAMPLES_DIR = BASE_DIR / 'examples'

app = FastAPI(title='SPECiT', version='2.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

if WEB_DIR.exists():
    app.mount('/static', StaticFiles(directory=str(WEB_DIR)), name='static')

store = Store()


class LLMConfig(BaseModel):
    provider: str = 'copilot_cli'
    url: str = ''
    model: str = 'auto'
    api_key: str = ''


class ExtractRequest(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    feedback: str = ''


class SaveCatalogueRequest(BaseModel):
    catalogue: dict[str, Any]
    note: str = 'manual catalogue review'


class ApproveRequest(BaseModel):
    approved: bool = True
    note: str = ''


class GenerateArtifactRequest(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    process_id: str
    feedback: str = ''


class SaveArtifactRequest(BaseModel):
    artifact: dict[str, Any]
    note: str = 'manual document edit'


class SaveDiagramRequest(BaseModel):
    xml: str
    svg: str = ''
    note: str = 'diagram edit'


class AssessRequest(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    feedback: str = ''
    process_ids: list[str] | None = None


class SaveQualityRequest(BaseModel):
    report: dict[str, Any]
    note: str = 'batch QA merged report'


class CommentCreateRequest(BaseModel):
    target_key: str
    text: str
    quote: str = ''
    author: str = 'Reviewer'


class CommentStatusRequest(BaseModel):
    status: str = 'resolved'


class ScopedAIRequest(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    target_key: str
    extra_feedback: str = ''


class GitConnectRequest(BaseModel):
    remote_url: str = ''
    branch: str = 'main'


class GitCommitRequest(BaseModel):
    message: str = 'Update architecture artifacts'
    push: bool = False
    branch: str | None = None


class GitPullRequest(BaseModel):
    branch: str | None = None


class FoundationRequest(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    feedback: str = ''


class SaveFoundationRequest(BaseModel):
    foundation: dict[str, Any]
    note: str = 'manual foundation edit'


class PlanningRequest(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    tech_preferences: str = ''


class SavePlanningRequest(BaseModel):
    planning: dict[str, Any]
    note: str = 'manual planning edit'


class ImplementationRequest(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    task_selection: str


class SaveCodeRequest(BaseModel):
    files: dict[str, str]
    reviewed: bool = False
    overwrite: bool = False


class RestoreRequest(BaseModel):
    revision_id: str


class LoadExampleRequest(BaseModel):
    filename: str = 'sample_document.pdf'


class ExportSingleDocxRequest(BaseModel):
    title: str
    subtitle: str = ''
    markdown: str


def _make_llm(cfg: LLMConfig) -> LLMClient:
    return LLMClient(
        model=cfg.model,
        url=cfg.url,
        provider=cfg.provider,
        api_key=cfg.api_key,
    )


def _get_sources(project: Path) -> list[dict]:
    sources = []
    inputs_dir = project / 'inputs'
    if not inputs_dir.exists():
        return sources
    for p in sorted(inputs_dir.iterdir()):
        if p.is_file() and not p.name.startswith('.'):
            try:
                sources.append(parse_source(p.name, p.read_bytes()))
            except Exception as e:
                sources.append({
                    'source_id': 'error',
                    'filename': p.name,
                    'size': p.stat().st_size,
                    'chunks': [],
                    'error': str(e),
                })
    return sources


def _all_artifacts(project: Path, catalogue: dict | None) -> dict[str, dict]:
    arts = {}
    if catalogue:
        for p in catalogue.get('processes', []):
            pid = p.get('id')
            if pid:
                a = store.read(project, f'artifact_{pid}')
                if a:
                    arts[pid] = a
    for f in sorted(project.glob('artifact_*.json')):
        pid = f.stem[len('artifact_'):]
        if pid not in arts:
            data = store.read(project, f.stem)
            if data:
                arts[pid] = data
    return arts


def _sync_initial_diagrams(project: Path, process_id: str, art_dict: dict, proc_dict: dict | None = None):
    """Create initial Draw.io XML for any diagram kind that does not yet have a custom diagram."""
    field_map = {
        'workflow': 'workflow_md',
        'boundaries': 'boundaries_md',
        'domain': 'domain_md',
        'states': 'states_md',
    }
    for kind, field in field_map.items():
        dkey = f'{process_id}_{kind}'
        if store.read_diagram(project, dkey) is None:
            blocks = extract_mermaid_blocks(art_dict.get(field, ''))
            if blocks:
                xml = mermaid_to_drawio_xml(blocks[0], title=f'{process_id} {kind.title()}', diagram_kind=kind)
            elif proc_dict:
                xml = process_to_drawio_xml(proc_dict, diagram_kind=kind)
            else:
                xml = mermaid_to_drawio_xml('', title=f'{process_id} {kind.title()}', diagram_kind=kind)
            store.write_diagram(project, dkey, xml, 'initial diagram generated from artifact')


@app.get('/')
def index():
    idx = WEB_DIR / 'index.html'
    if not idx.exists():
        raise HTTPException(status_code=500, detail='Frontend index.html missing')
    return FileResponse(str(idx))


@app.get('/api/llm/providers')
def list_llm_providers():
    return {'providers': detect_providers()}


@app.post('/api/llm/test')
def test_llm_provider(cfg: LLMConfig):
    llm = _make_llm(cfg)
    return llm.test_connection()


@app.post('/api/llm/models')
def list_llm_models(cfg: LLMConfig):
    llm = _make_llm(cfg)
    status = llm.test_connection()
    return {'ok': status['ok'], 'models': status['models'], 'message': status['message'], 'error': '' if status['ok'] else status['message']}


@app.get('/api/projects')
def list_projects():
    examples = []
    if EXAMPLES_DIR.exists():
        examples = sorted(
            f.name for f in EXAMPLES_DIR.iterdir()
            if f.is_file() and f.suffix.lower() in {'.docx', '.pdf', '.md', '.txt'}
        )
    return {'projects': store.projects(), 'examples': examples}


@app.get('/api/projects/{project_name}/state')
def get_project_state(project_name: str):
    project = store.project(project_name)
    sources = _get_sources(project)
    catalogue = store.read(project, 'catalogue')
    artifacts = _all_artifacts(project, catalogue)
    quality = store.read(project, 'quality')
    foundation_data = store.read(project, 'foundation')
    planning_data = store.read(project, 'planning')
    code_proposal = store.read(project, 'code_proposal')

    static_checks = []
    if catalogue:
        try:
            cat_obj = Catalogue.model_validate(catalogue)
            valid_sources = [s for s in sources if 'error' not in s]
            static_checks = quality_checks(cat_obj, artifacts, valid_sources)
        except Exception as e:
            static_checks = [f'Catalogue schema validation warning: {e}']

    diagrams_present = sorted(f.stem for f in (project / 'diagrams').glob('*.drawio'))
    diagram_svgs = {
        f.stem: f.read_text(encoding='utf-8')
        for f in sorted((project / 'diagrams').glob('*.svg'))
    }
    revision_keys = ['catalogue', 'quality', 'foundation', 'planning', 'code_proposal']
    revision_keys += [f'artifact_{pid}' for pid in sorted(artifacts)]

    return {
        'project_slug': project.name,
        'workspace_path': str(project),
        'sources': sources,
        'catalogue': catalogue,
        'artifacts': artifacts,
        'diagrams': diagrams_present,
        'diagram_svgs': diagram_svgs,
        'quality': quality,
        'static_checks': static_checks,
        'foundation': foundation_data,
        'planning': planning_data,
        'code_proposal': code_proposal,
        'approvals': {
            'catalogue': bool(store.read(project, 'catalogue_approved', False)),
            'artifacts': bool(store.read(project, 'artifacts_approved', False)),
            'foundation': bool(store.read(project, 'foundation_approved', False)),
            'planning': bool(store.read(project, 'planning_approved', False)),
        },
        'comments': store.read(project, 'comments', []),
        'revision_keys': revision_keys,
    }


@app.post('/api/projects/{project_name}/sources/upload')
async def upload_sources(project_name: str, files: list[UploadFile] = File(...)):
    project = store.project(project_name)
    saved = []
    for f in files:
        raw = await f.read()
        try:
            parse_source(f.filename or 'upload.txt', raw)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f'{f.filename}: {e}')
        dest = store.save_upload(project, f.filename or 'upload.txt', raw)
        saved.append(dest.name)
    store.invalidate_from(project, 'sources', 'new source document uploaded')
    return {'saved': saved}


@app.post('/api/projects/{project_name}/sources/load-example')
def load_example_source(project_name: str, req: LoadExampleRequest):
    safe = Path(req.filename).name
    src = (EXAMPLES_DIR / safe).resolve()
    if not src.exists() or src.parent != EXAMPLES_DIR.resolve():
        raise HTTPException(status_code=404, detail=f'Example not found: {safe}')
    project = store.project(project_name)
    dest = store.save_upload(project, safe, src.read_bytes())
    store.invalidate_from(project, 'sources', f'loaded example source {safe}')
    return {'loaded': dest.name}


@app.delete('/api/projects/{project_name}/sources/{filename}')
def delete_source(project_name: str, filename: str):
    project = store.project(project_name)
    ok = store.delete_upload(project, filename)
    if not ok:
        raise HTTPException(status_code=404, detail='File not found')
    store.invalidate_from(project, 'sources', f'deleted source {filename}')
    return {'deleted': filename}


@app.post('/api/projects/{project_name}/assets/upload')
async def upload_asset(project_name: str, file: UploadFile = File(...)):
    project = store.project(project_name)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail='Empty image file')
    try:
        saved_name = store.save_asset(project, file.filename or 'image.png', raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    url = f'/api/projects/{project.name}/assets/{saved_name}'
    return {'filename': saved_name, 'url': url}


@app.get('/api/projects/{project_name}/assets/{filename}')
def get_asset(project_name: str, filename: str):
    project = store.project(project_name)
    try:
        path = store.get_asset_path(project, filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail='Image asset not found')
    return FileResponse(str(path))


@app.post('/api/projects/{project_name}/extract')
def run_extraction(project_name: str, req: ExtractRequest):
    project = store.project(project_name)
    sources = [s for s in _get_sources(project) if 'error' not in s]
    if not sources:
        raise HTTPException(status_code=400, detail='Upload at least one readable source document first.')
    old = store.read(project, 'catalogue')
    try:
        out = extract_catalogue(_make_llm(req.llm), sources, req.feedback, old)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'{type(e).__name__}: {e}')
    store.write(project, 'catalogue', out.model_dump(), 'extraction' + (f': {req.feedback[:60]}' if req.feedback else ''))
    store.invalidate_from(project, 'catalogue', 'catalogue regenerated')
    return out.model_dump()


@app.put('/api/projects/{project_name}/catalogue')
def update_catalogue(project_name: str, req: SaveCatalogueRequest):
    project = store.project(project_name)
    try:
        parsed = Catalogue.model_validate(req.catalogue)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    store.write(project, 'catalogue', parsed.model_dump(), req.note or 'manual review')
    store.invalidate_from(project, 'catalogue', 'catalogue edited')
    return parsed.model_dump()


@app.post('/api/projects/{project_name}/approve/{stage}')
def set_approval(project_name: str, stage: str, req: ApproveRequest):
    if stage not in {'catalogue', 'artifacts', 'foundation', 'planning'}:
        raise HTTPException(status_code=400, detail='Invalid approval stage')
    project = store.project(project_name)
    flag = f'{stage}_approved'
    reason = req.note or (f'human approved {stage}' if req.approved else f'human revoked {stage}')
    store.write(project, flag, req.approved, reason)
    if not req.approved:
        store.invalidate_from(project, stage, reason)
    return {'stage': stage, 'approved': req.approved}


@app.post('/api/projects/{project_name}/artifacts/generate')
def generate_process_artifact(project_name: str, req: GenerateArtifactRequest):
    project = store.project(project_name)
    cat_data = store.read(project, 'catalogue')
    if not cat_data:
        raise HTTPException(status_code=400, detail='Generate and approve the process catalogue first.')
    if not store.read(project, 'catalogue_approved', False):
        raise HTTPException(status_code=400, detail='Approve the process catalogue in Step 2 first.')
    cat = Catalogue.model_validate(cat_data)
    artkey = f'artifact_{req.process_id}'
    prior = store.read(project, artkey)
    try:
        result = generate_artifact(_make_llm(req.llm), cat, req.process_id, req.feedback, prior)
    except Exception as e:
        logger.exception('Artifact generation failed for %s (%s/%s): %s', req.process_id, req.llm.provider, req.llm.model, e)
        raise HTTPException(status_code=500, detail=f'{type(e).__name__}: {e}')
    art_dict = result.model_dump()
    store.write(project, artkey, art_dict, 'artifact generated' + (f': {req.feedback[:60]}' if req.feedback else ''))
    proc_dict = next((p.model_dump() for p in cat.processes if p.id == req.process_id), None)
    _sync_initial_diagrams(project, req.process_id, art_dict, proc_dict)
    store.invalidate_from(project, 'artifacts', f'artifact {req.process_id} regenerated')
    return art_dict


@app.put('/api/projects/{project_name}/artifacts/{process_id}')
def update_artifact(project_name: str, process_id: str, req: SaveArtifactRequest):
    project = store.project(project_name)
    data = dict(req.artifact)
    data['process_id'] = process_id
    try:
        parsed = Artifact.model_validate(data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    store.write(project, f'artifact_{process_id}', parsed.model_dump(), req.note or 'manual artifact edit')
    store.invalidate_from(project, 'artifacts', f'artifact {process_id} edited')
    return parsed.model_dump()


@app.get('/api/projects/{project_name}/diagrams/{process_id}/{kind}')
def get_diagram(project_name: str, process_id: str, kind: str):
    if kind not in {'workflow', 'boundaries', 'domain', 'states'}:
        raise HTTPException(status_code=400, detail='Invalid diagram kind')
    project = store.project(project_name)
    art = store.read(project, f'artifact_{process_id}') or {}
    blocks = extract_mermaid_blocks(art.get(f'{kind}_md', ''))
    mermaid_code = blocks[0] if blocks else ''
    dkey = f'{process_id}_{kind}'
    saved_xml = store.read_diagram(project, dkey)
    saved_svg = store.read_diagram_svg(project, dkey) or ''
    if saved_xml:
        return {'xml': saved_xml, 'svg': saved_svg, 'mermaid': mermaid_code, 'is_custom': True}
    cat = store.read(project, 'catalogue') or {}
    proc = next((p for p in cat.get('processes', []) if p.get('id') == process_id), None)
    if mermaid_code:
        xml = mermaid_to_drawio_xml(mermaid_code, title=f'{process_id} {kind.title()}', diagram_kind=kind)
    elif proc:
        xml = process_to_drawio_xml(proc, diagram_kind=kind)
    else:
        xml = mermaid_to_drawio_xml('', title=f'{process_id} {kind.title()}', diagram_kind=kind)
    return {'xml': xml, 'svg': saved_svg, 'mermaid': mermaid_code, 'is_custom': False}


@app.put('/api/projects/{project_name}/diagrams/{process_id}/{kind}')
def save_diagram(project_name: str, process_id: str, kind: str, req: SaveDiagramRequest):
    if kind not in {'workflow', 'boundaries', 'domain', 'states'}:
        raise HTTPException(status_code=400, detail='Invalid diagram kind')
    if '<mxfile' not in req.xml and '<mxGraphModel' not in req.xml:
        raise HTTPException(status_code=422, detail='Diagram XML must be valid Draw.io mxfile/mxGraphModel XML')
    project = store.project(project_name)
    store.write_diagram(project, f'{process_id}_{kind}', req.xml, req.note, svg=req.svg or None)
    return {'saved': True}


@app.post('/api/projects/{project_name}/diagrams/{process_id}/{kind}/reset')
def reset_diagram_from_mermaid(project_name: str, process_id: str, kind: str):
    if kind not in {'workflow', 'boundaries', 'domain', 'states'}:
        raise HTTPException(status_code=400, detail='Invalid diagram kind')
    project = store.project(project_name)
    art = store.read(project, f'artifact_{process_id}') or {}
    blocks = extract_mermaid_blocks(art.get(f'{kind}_md', ''))
    cat = store.read(project, 'catalogue') or {}
    proc = next((p for p in cat.get('processes', []) if p.get('id') == process_id), None)
    if blocks:
        xml = mermaid_to_drawio_xml(blocks[0], title=f'{process_id} {kind.title()}', diagram_kind=kind)
    elif proc:
        xml = process_to_drawio_xml(proc, diagram_kind=kind)
    else:
        xml = mermaid_to_drawio_xml('', title=f'{process_id} {kind.title()}', diagram_kind=kind)
    # Remove stale SVG snapshot so Word view re-renders fresh from new XML/Mermaid
    svg_path = project / 'diagrams' / f'{process_id.lower()}_{kind}.svg'
    if svg_path.exists():
        svg_path.unlink()
    store.write_diagram(project, f'{process_id}_{kind}', xml, 'reset diagram from Mermaid source')
    return {'xml': xml}


@app.get('/api/projects/{project_name}/diagrams/{process_id}/{kind}/download')
def download_diagram(project_name: str, process_id: str, kind: str):
    res = get_diagram(project_name, process_id, kind)
    return Response(
        content=res['xml'].encode('utf-8'),
        media_type='application/xml',
        headers={'Content-Disposition': f'attachment; filename="{process_id}-{kind}.drawio"'},
    )


@app.post('/api/projects/{project_name}/assess')
def run_assessment(project_name: str, req: AssessRequest):
    project = store.project(project_name)
    cat_data = store.read(project, 'catalogue')
    if not cat_data:
        raise HTTPException(status_code=400, detail='No catalogue found.')
    cat = Catalogue.model_validate(cat_data)
    all_arts = _all_artifacts(project, cat_data)
    if req.process_ids:
        arts = {pid: all_arts[pid] for pid in req.process_ids if pid in all_arts}
    else:
        arts = all_arts
    if not arts:
        raise HTTPException(status_code=400, detail='Generate at least one process artifact before quality review.')
    sources = [s for s in _get_sources(project) if 'error' not in s]
    try:
        report = assess(_make_llm(req.llm), cat, arts, req.feedback, sources)
    except Exception as e:
        logger.exception('Quality assessment failed: %s', e)
        raise HTTPException(status_code=500, detail=f'{type(e).__name__}: {e}')
    if not req.process_ids:
        store.write(project, 'quality', report.model_dump(), 'QA assessment')
    return report.model_dump()


@app.put('/api/projects/{project_name}/quality')
def save_quality_report(project_name: str, req: SaveQualityRequest):
    project = store.project(project_name)
    store.write(project, 'quality', req.report, req.note)
    return req.report


def _resolve_scoped_target(project: Path, target_key: str):
    """Return (kind, label, content_str, extra_dict) for a scoped comment/review/rerun target."""
    parts = target_key.split('::')
    cat = store.read(project, 'catalogue') or {}
    ctx = _compact_catalogue_summary(cat)

    if len(parts) == 3 and parts[0] == 'catalogue' and parts[1] == 'process':
        pid = parts[2]
        proc = next((p for p in cat.get('processes', []) if p.get('id') == pid), None)
        if not proc:
            raise HTTPException(status_code=404, detail=f'Process {pid} not found in catalogue')
        import json as _json_mod
        return ('catalogue_process', f'Catalogue Process {pid} ({proc.get("name", "")})', _json_mod.dumps(proc, indent=2), {'pid': pid, 'proc': proc, 'ctx': ctx})

    if len(parts) == 3 and parts[0] == 'artifact':
        pid, field = parts[1], parts[2]
        art = store.read(project, f'artifact_{pid}')
        if not art or field not in {'workflow_md', 'boundaries_md', 'domain_md', 'states_md'}:
            raise HTTPException(status_code=404, detail=f'Artifact {pid}/{field} not found')
        return ('artifact_doc', f'{pid} — {field}', art.get(field, ''), {'pid': pid, 'field': field, 'art': art, 'ctx': ctx})

    if len(parts) == 2 and parts[0] == 'foundation':
        field = parts[1]
        found = store.read(project, 'foundation')
        if not found or field not in {'constitution_md', 'specification_md', 'clarification_md'}:
            raise HTTPException(status_code=404, detail=f'Foundation {field} not found')
        return ('foundation_doc', f'Foundation — {field}', found.get(field, ''), {'field': field, 'found': found, 'ctx': ctx})

    if len(parts) == 2 and parts[0] == 'planning':
        field = parts[1]
        plan = store.read(project, 'planning')
        if not plan or field not in {'plan_md', 'tasks_md'}:
            raise HTTPException(status_code=404, detail=f'Planning {field} not found')
        return ('planning_doc', f'Planning — {field}', plan.get(field, ''), {'field': field, 'plan': plan, 'ctx': ctx})

    raise HTTPException(status_code=400, detail=f'Unsupported target_key: {target_key}')


@app.post('/api/projects/{project_name}/comments')
def add_comment(project_name: str, req: CommentCreateRequest):
    from datetime import datetime, timezone
    import uuid

    if not req.text.strip():
        raise HTTPException(status_code=400, detail='Comment text cannot be empty')
    project = store.project(project_name)
    comments = list(store.read(project, 'comments', []))
    item = {
        'id': uuid.uuid4().hex[:10],
        'target_key': req.target_key,
        'quote': req.quote.strip()[:400],
        'text': req.text.strip(),
        'author': req.author or 'Reviewer',
        'status': 'open',
        'created_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
    }
    comments.append(item)
    store.write(project, 'comments', comments, f'comment on {req.target_key}')
    return item


@app.patch('/api/projects/{project_name}/comments/{comment_id}')
def update_comment_status(project_name: str, comment_id: str, req: CommentStatusRequest):
    project = store.project(project_name)
    comments = list(store.read(project, 'comments', []))
    for c in comments:
        if c.get('id') == comment_id:
            c['status'] = 'resolved' if req.status == 'resolved' else 'open'
            store.write(project, 'comments', comments, f'comment {comment_id} -> {c["status"]}')
            return c
    raise HTTPException(status_code=404, detail='Comment not found')


@app.delete('/api/projects/{project_name}/comments/{comment_id}')
def delete_comment(project_name: str, comment_id: str):
    project = store.project(project_name)
    comments = [c for c in store.read(project, 'comments', []) if c.get('id') != comment_id]
    store.write(project, 'comments', comments, f'deleted comment {comment_id}')
    return {'deleted': comment_id}


@app.post('/api/projects/{project_name}/review-item')
def ai_review_item(project_name: str, req: ScopedAIRequest):
    from datetime import datetime, timezone
    import uuid

    project = store.project(project_name)
    _, label, content, meta = _resolve_scoped_target(project, req.target_key)
    all_comments = list(store.read(project, 'comments', []))
    scoped = [c for c in all_comments if c.get('target_key') == req.target_key and c.get('status') == 'open']
    if req.extra_feedback.strip():
        scoped.append({'status': 'open', 'quote': '', 'text': req.extra_feedback.strip()})
    try:
        review = review_scoped_item(_make_llm(req.llm), label, content, scoped, meta['ctx'])
    except Exception as e:
        logger.exception('Scoped AI review failed for %s: %s', req.target_key, e)
        raise HTTPException(status_code=500, detail=f'{type(e).__name__}: {e}')

    lines = [f'Verdict: {review.verdict.upper()} — {review.summary}']
    if review.issues:
        lines.append('Issues:\n' + '\n'.join(f'• {x}' for x in review.issues))
    if review.suggestions:
        lines.append('Suggestions:\n' + '\n'.join(f'• {x}' for x in review.suggestions))

    ai_comment = {
        'id': uuid.uuid4().hex[:10],
        'target_key': req.target_key,
        'quote': '',
        'text': '\n\n'.join(lines),
        'author': 'AI Review',
        'status': 'open',
        'created_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
    }
    all_comments.append(ai_comment)
    store.write(project, 'comments', all_comments, f'AI review on {req.target_key}')
    return {'review': review.model_dump(), 'comment': ai_comment}


@app.post('/api/projects/{project_name}/rerun-item')
def ai_rerun_item(project_name: str, req: ScopedAIRequest):
    project = store.project(project_name)
    kind, label, content, meta = _resolve_scoped_target(project, req.target_key)
    all_comments = list(store.read(project, 'comments', []))
    scoped = [c for c in all_comments if c.get('target_key') == req.target_key and c.get('status') == 'open']
    if req.extra_feedback.strip():
        scoped.append({'quote': '', 'text': req.extra_feedback.strip()})
    if not scoped:
        raise HTTPException(status_code=400, detail='Add at least one open comment or review note before rerunning this item.')

    try:
        llm = _make_llm(req.llm)
        if kind == 'catalogue_process':
            updated_proc = rerun_single_process_catalogue(llm, meta['proc'], scoped, meta['ctx'])
            cat = store.read(project, 'catalogue')
            cat['processes'] = [
                updated_proc.model_dump() if p.get('id') == meta['pid'] else p
                for p in cat.get('processes', [])
            ]
            store.write(project, 'catalogue', cat, f'scoped AI rerun of {meta["pid"]}')
            store.invalidate_from(project, 'catalogue', f'scoped rerun of {meta["pid"]}')
            summary = f'Updated catalogue process {updated_proc.id}'
        elif kind == 'artifact_doc':
            upd = rerun_single_document(llm, label, content, scoped, meta['ctx'])
            art = dict(meta['art'])
            art[meta['field']] = upd.markdown
            store.write(project, f'artifact_{meta["pid"]}', art, f'scoped AI rerun: {upd.change_summary[:60] or meta["field"]}')
            store.invalidate_from(project, 'artifacts', f'scoped rerun of {meta["pid"]} {meta["field"]}')
            summary = upd.change_summary or f'Updated {label}'
        elif kind == 'foundation_doc':
            upd = rerun_single_document(llm, label, content, scoped, meta['ctx'])
            found = dict(meta['found'])
            found[meta['field']] = upd.markdown
            store.write(project, 'foundation', found, f'scoped AI rerun: {meta["field"]}')
            store.invalidate_from(project, 'foundation', f'scoped rerun of {meta["field"]}')
            summary = upd.change_summary or f'Updated {label}'
        else:
            upd = rerun_single_document(llm, label, content, scoped, meta['ctx'])
            plan = dict(meta['plan'])
            plan[meta['field']] = upd.markdown
            store.write(project, 'planning', plan, f'scoped AI rerun: {meta["field"]}')
            store.invalidate_from(project, 'planning', f'scoped rerun of {meta["field"]}')
            summary = upd.change_summary or f'Updated {label}'
    except Exception as e:
        logger.exception('Scoped AI rerun failed for %s: %s', req.target_key, e)
        raise HTTPException(status_code=500, detail=f'{type(e).__name__}: {e}')

    # Mark applied open comments as resolved
    for c in all_comments:
        if c.get('target_key') == req.target_key and c.get('status') == 'open':
            c['status'] = 'resolved'
    store.write(project, 'comments', all_comments, f'resolved comments after rerun of {req.target_key}')
    return {'ok': True, 'summary': summary}


@app.post('/api/projects/{project_name}/foundation/generate')
def generate_foundation(project_name: str, req: FoundationRequest):
    project = store.project(project_name)
    if not store.read(project, 'artifacts_approved', False):
        raise HTTPException(status_code=400, detail='Approve architecture artifacts in Step 4 first.')
    cat_data = store.read(project, 'catalogue')
    cat = Catalogue.model_validate(cat_data)
    arts = _all_artifacts(project, cat_data)
    try:
        result = foundation(_make_llm(req.llm), cat, arts, req.feedback)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'{type(e).__name__}: {e}')
    store.write(project, 'foundation', result.model_dump(), 'Spec Kit phase 1 generated')
    store.invalidate_from(project, 'foundation', 'foundation regenerated')
    return result.model_dump()


@app.put('/api/projects/{project_name}/foundation')
def update_foundation(project_name: str, req: SaveFoundationRequest):
    project = store.project(project_name)
    try:
        parsed = Foundation.model_validate(req.foundation)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    store.write(project, 'foundation', parsed.model_dump(), req.note or 'manual foundation edit')
    store.invalidate_from(project, 'foundation', 'foundation edited')
    return parsed.model_dump()


@app.post('/api/projects/{project_name}/planning/generate')
def generate_planning(project_name: str, req: PlanningRequest):
    project = store.project(project_name)
    if not store.read(project, 'foundation_approved', False):
        raise HTTPException(status_code=400, detail='Approve Spec Kit foundation in Step 5 first.')
    cat = Catalogue.model_validate(store.read(project, 'catalogue'))
    found = store.read(project, 'foundation')
    try:
        result = planning(_make_llm(req.llm), cat, found, req.tech_preferences)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'{type(e).__name__}: {e}')
    store.write(project, 'planning', result.model_dump(), 'Spec Kit phase 2 planning')
    store.invalidate_from(project, 'planning', 'planning regenerated')
    return result.model_dump()


@app.put('/api/projects/{project_name}/planning')
def update_planning(project_name: str, req: SavePlanningRequest):
    project = store.project(project_name)
    try:
        parsed = Planning.model_validate(req.planning)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    store.write(project, 'planning', parsed.model_dump(), req.note or 'manual planning edit')
    store.invalidate_from(project, 'planning', 'planning edited')
    return parsed.model_dump()


@app.post('/api/projects/{project_name}/implementation/generate')
def generate_implementation(project_name: str, req: ImplementationRequest):
    project = store.project(project_name)
    if not store.read(project, 'planning_approved', False):
        raise HTTPException(status_code=400, detail='Approve plan and tasks before generating code proposals.')
    if not req.task_selection.strip():
        raise HTTPException(status_code=400, detail='Specify a task ID or vertical slice to implement.')
    found = store.read(project, 'foundation')
    plan = store.read(project, 'planning')
    try:
        result = implementation(_make_llm(req.llm), found, plan, req.task_selection)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'{type(e).__name__}: {e}')
    store.write(project, 'code_proposal', result.model_dump(), f'code proposal: {req.task_selection[:60]}')
    return result.model_dump()


@app.post('/api/projects/{project_name}/implementation/save')
def save_implementation_files(project_name: str, req: SaveCodeRequest):
    if not req.reviewed:
        raise HTTPException(status_code=400, detail='Confirm you reviewed all file contents and paths before saving.')
    project = store.project(project_name)
    try:
        dest = save_code(project, req.files, overwrite=req.overwrite)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {'saved_dir': str(dest), 'count': len(req.files)}


@app.get('/api/projects/{project_name}/revisions/{key}')
def get_revisions(project_name: str, key: str):
    project = store.project(project_name)
    return {'key': key, 'revisions': store.revisions_with_meta(project, key)}


@app.get('/api/projects/{project_name}/diff/{key}')
def get_diff(project_name: str, key: str, rev_a: str | None = None, rev_b: str | None = None):
    project = store.project(project_name)
    if rev_a and rev_b:
        diff_text = store.diff_by_ids(project, key, rev_a, rev_b)
    else:
        diff_text = store.diff(project, key)
    return {'key': key, 'diff': diff_text}


@app.post('/api/projects/{project_name}/revisions/{key}/restore')
def restore_revision(project_name: str, key: str, req: RestoreRequest):
    project = store.project(project_name)
    try:
        obj = store.read_revision(project, key, req.revision_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail='Revision not found')
    store.write(project, key, obj, f'restored revision {req.revision_id}')
    if key == 'catalogue':
        store.invalidate_from(project, 'catalogue', 'restored historical catalogue')
    elif key.startswith('artifact_'):
        store.invalidate_from(project, 'artifacts', f'restored historical {key}')
    elif key == 'foundation':
        store.invalidate_from(project, 'foundation', 'restored historical foundation')
    elif key == 'planning':
        store.invalidate_from(project, 'planning', 'restored historical planning')
    return {'restored': req.revision_id}


@app.post('/api/projects/{project_name}/export/docx-single')
def export_single_docx(project_name: str, req: ExportSingleDocxRequest):
    project = store.project(project_name)
    data = export_markdown_docx_bytes(req.title, req.markdown, req.subtitle, project_dir=project)
    safe_name = ''.join(c if c.isalnum() or c in '-_' else '-' for c in req.title).strip('-') or 'document'
    return Response(
        content=data,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition': f'attachment; filename="{safe_name}.docx"'},
    )


@app.get('/api/projects/{project_name}/export/docx')
def export_full_docx(project_name: str):
    project = store.project(project_name)
    catalogue = store.read(project, 'catalogue')
    artifacts = _all_artifacts(project, catalogue)
    found = store.read(project, 'foundation')
    plan = store.read(project, 'planning')
    out = export_project_docx(project, catalogue=catalogue, artifacts=artifacts, foundation=found, planning=plan)
    return FileResponse(
        str(out),
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        filename=out.name,
    )


@app.get('/api/projects/{project_name}/export/zip')
def export_full_project_zip(project_name: str):
    project = store.project(project_name)
    data = export_project_zip_bytes(project)
    return Response(
        content=data,
        media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{project.name}-project.zip"'},
    )


@app.post('/api/projects/import-zip')
async def import_full_project_zip(file: UploadFile = File(...), project_name: str = ''):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail='Empty ZIP file')
    try:
        fallback_name = project_name.strip() or Path(file.filename or '').stem.replace('-project', '')
        res = import_project_zip(store, raw, project_name=project_name.strip() or fallback_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception('Project ZIP import failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))
    return res


@app.get('/api/projects/{project_name}/export/speckit')
def export_speckit_zip(project_name: str):
    project = store.project(project_name)
    found = store.read(project, 'foundation')
    if not found:
        raise HTTPException(status_code=400, detail='Generate Spec Kit Foundation in Step 5 before exporting.')
    catalogue = store.read(project, 'catalogue')
    artifacts = _all_artifacts(project, catalogue)
    plan = store.read(project, 'planning')
    out = export_speckit(project, found, planning=plan, catalogue=catalogue, artifacts=artifacts)
    return FileResponse(str(out), media_type='application/zip', filename=out.name)


@app.get('/api/projects/{project_name}/git/status')
def git_status_endpoint(project_name: str):
    project = store.project(project_name)
    try:
        return get_git_status(project)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/projects/{project_name}/git/connect')
def git_connect_endpoint(project_name: str, req: GitConnectRequest):
    project = store.project(project_name)
    try:
        return connect_git(project, req.remote_url, req.branch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception('Git connect failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/projects/{project_name}/git/commit')
def git_commit_endpoint(project_name: str, req: GitCommitRequest):
    project = store.project(project_name)
    try:
        return commit_project(project, req.message, push=req.push, branch=req.branch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception('Git commit/push failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/projects/{project_name}/git/pull')
def git_pull_endpoint(project_name: str, req: GitPullRequest):
    project = store.project(project_name)
    try:
        return pull_project(project, branch=req.branch)
    except Exception as e:
        logger.exception('Git pull failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('app:app', host='127.0.0.1', port=8501, reload=False)
