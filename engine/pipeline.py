from .model import (
    Artifact,
    Catalogue,
    CodeBundle,
    Foundation,
    Planning,
    Process,
    QualityReport,
    ScopedReview,
    SingleDocUpdate,
)
from .prompts import load
from .sources import pack_chunks, index_sources
from .storage import normalize_prefix, workflow_id_for
from .diagrams import extract_mermaid_blocks, validate_mermaid_syntax
import json
import re

MAX_PROCESSES_PER_PASS = 15


def _json(x) -> str:
    return json.dumps(x, indent=2, ensure_ascii=False)


def _compact_catalogue_summary(cat_dict: dict) -> dict:
    """Produce a valid, compact JSON representation of the catalogue (never sliced mid-JSON)."""
    if not cat_dict:
        return {}
    return {
        'project_name': cat_dict.get('project_name', ''),
        'project_summary': cat_dict.get('project_summary', ''),
        'shared_actors': cat_dict.get('shared_actors', []),
        'systems': cat_dict.get('systems', []),
        'glossary': cat_dict.get('glossary', []),
        'nfrs': cat_dict.get('nfrs', []),
        'exclusions': cat_dict.get('exclusions', []),
        'open_questions': cat_dict.get('open_questions', []),
        'processes': [
            {
                'id': p.get('id'),
                'name': p.get('name'),
                'description': p.get('description', ''),
                'actors': p.get('actors', []),
                'trigger': p.get('trigger', ''),
                'messages': p.get('messages', []),
                'entities': p.get('entities', []),
                'exceptions': p.get('exceptions', []),
                'open_questions': p.get('open_questions', []),
            }
            for p in cat_dict.get('processes', [])
        ],
    }


def _compact_artifacts_bundle(artifacts: dict, max_field_chars: int = 3500) -> dict:
    """Keep all processes represented in valid JSON without mid-JSON string slicing."""
    out = {}
    for pid, a in artifacts.items():
        data = a.model_dump() if hasattr(a, 'model_dump') else dict(a)
        item = {'process_id': pid, 'findings': data.get('findings', [])}
        for field in ('workflow_md', 'boundaries_md', 'domain_md', 'states_md'):
            txt = data.get(field, '') or ''
            if len(txt) > max_field_chars:
                txt = txt[:max_field_chars] + '\n...[section trimmed for context budget]...'
            item[field] = txt
        out[pid] = item
    return out


def _next_unique_id(base_id: str, used: set[str]) -> str:
    if base_id not in used:
        return base_id
    m = re.match(r'^([A-Za-z_-]+?)(\d+)$', base_id)
    if m:
        prefix, num_str = m.group(1), m.group(2)
        width = len(num_str)
        n = int(num_str) + 1
        while f'{prefix}{n:0{width}d}' in used:
            n += 1
        return f'{prefix}{n:0{width}d}'
    n = 2
    while f'{base_id}-{n}' in used:
        n += 1
    return f'{base_id}-{n}'


def _merge_process_into(target, incoming):
    target.evidence.extend(e for e in incoming.evidence if e not in target.evidence)
    for attr in ('steps', 'actors', 'messages', 'exceptions', 'open_questions', 'entities', 'inputs', 'outputs'):
        arr = getattr(target, attr)
        for val in getattr(incoming, attr):
            if val not in arr:
                arr.append(val)
    existing_stmts = {r.statement.strip().lower() for r in target.rules}
    for r in incoming.rules:
        if r.statement.strip().lower() not in existing_stmts:
            target.rules.append(r)
            existing_stmts.add(r.statement.strip().lower())


def extract_catalogue(llm, sources, feedback: str = '', prior=None, prefix: str = 'PRJ') -> Catalogue:
    parts = list(pack_chunks(sources))
    if not parts:
        raise ValueError('No readable text in input documents. Scanned PDFs require OCR outside this starter.')

    px = normalize_prefix(prefix)
    merged = []
    summaries = []
    running_context = _compact_catalogue_summary(prior) if prior else {'processes': []}

    for idx, part in enumerate(parts, 1):
        prompt = (
            f'Source segment {idx}/{len(parts)}. Extract only what is supported by this segment. '
            f'Up to {MAX_PROCESSES_PER_PASS} processes. '
            f'STRICT ID CONVENTION: Every process ID MUST use the single project catalogue prefix `{px}-CA-001`, `{px}-CA-002`, `{px}-CA-003`, etc. '
            'Do NOT invent category abbreviations like LO, MO, EQ, RPT, MEM, OVD, etc. '
            f'Rule IDs MUST use `{px}-CA-001-R1`, `{px}-CA-001-R2`, etc. '
            'IMPORTANT: If a process in this segment continues or elaborates a process already listed in '
            'EXISTING PROCESSES SO FAR, reuse its EXACT id and name so they merge cleanly. '
            'For evidence.locator, use ONLY the locator value from `locator=...` (e.g. `page 2`, `block 5`), without repeating the filename. '
            'Also capture systems/responsibilities, glossary abbreviations, non-functional requirements (nfrs), '
            'exclusions (out-of-scope items), shared_actors, and open_questions when present in this segment.\n\n'
            f'{part}\n\nUSER FEEDBACK:\n{feedback}\n\nEXISTING PROCESSES SO FAR / PRIOR CATALOGUE:\n{_json(running_context)}'
        )
        result = llm.ask(load('system'), load('extract_catalogue') + '\n' + prompt, Catalogue)
        merged.extend(result.processes)
        summaries.append(result)

        # Feed newly discovered process IDs/names into subsequent chunks to prevent ID collisions and duplicates
        existing_by_key = {
            re.sub(r'[^a-z0-9]', '', (p.get('name') or '').lower()): p
            for p in running_context.get('processes', [])
        }
        for p in result.processes:
            k = re.sub(r'[^a-z0-9]', '', p.name.lower())
            if k not in existing_by_key:
                entry = {'id': p.id, 'name': p.name, 'description': p.description}
                running_context.setdefault('processes', []).append(entry)
                existing_by_key[k] = entry

    # Deduplicate processes by normalized name while preserving rules and source evidence.
    seen = {}
    for p in merged:
        key = re.sub(r'[^a-z0-9]', '', p.name.lower())
        if key not in seen:
            seen[key] = p
        else:
            _merge_process_into(seen[key], p)

    # Deterministically enforce uniform `{PREFIX}-CA-001`, `{PREFIX}-CA-002`, ... IDs (no arbitrary LO/MO/RPT prefixes)
    final_processes = []
    for idx, p in enumerate(seen.values(), 1):
        p.id = f'{px}-CA-{idx:03d}'
        for r_idx, rule in enumerate(p.rules, 1):
            rule.id = f'{p.id}-R{r_idx}'
        final_processes.append(p)

    first = summaries[0]
    systems_map = {}
    for r in summaries:
        for s in r.systems:
            k = s.name.strip().lower()
            if k not in systems_map:
                systems_map[k] = s
    glossary_map = {}
    for r in summaries:
        for g in r.glossary:
            k = g.term.strip().lower()
            if k not in glossary_map:
                glossary_map[k] = g

    return Catalogue(
        project_name=first.project_name,
        project_summary=' '.join(dict.fromkeys(r.project_summary.strip() for r in summaries if r.project_summary.strip())),
        processes=final_processes,
        shared_actors=sorted(set(v for r in summaries for v in r.shared_actors)),
        systems=list(systems_map.values()),
        glossary=list(glossary_map.values()),
        nfrs=list(dict.fromkeys(v for r in summaries for v in r.nfrs)),
        exclusions=list(dict.fromkeys(v for r in summaries for v in r.exclusions)),
        open_questions=list(dict.fromkeys(v for r in summaries for v in r.open_questions)),
    )


def generate_artifact(llm, catalogue: Catalogue, process_id: str, feedback: str = '', previous=None, prefix: str = 'PRJ') -> Artifact:
    p = next((x for x in catalogue.processes if x.id == process_id), None)
    if not p:
        raise KeyError(process_id)
    px = normalize_prefix(prefix)
    wf_id = workflow_id_for(process_id, px)
    cat_summary = _compact_catalogue_summary(catalogue.model_dump())
    prev_compact = _compact_artifacts_bundle({process_id: previous}, max_field_chars=5000).get(process_id, {}) if previous else {}
    prompt = (
        f'ID CONVENTION: Label this workflow `{wf_id}` traced back to catalogue item `{process_id}`. '
        'Do NOT invent unfamiliar acronyms or extra prefix codes.\n\n'
        f'CATALOGUE CONTEXT:\n{_json(cat_summary)}\n\n'
        f'TARGET PROCESS (FULL):\n{_json(p.model_dump())}\n\n'
        f'PREVIOUS ARTIFACT (optional):\n{_json(prev_compact)}\n\n'
        f'REVIEW FEEDBACK:\n{feedback}'
    )
    result = llm.ask(load('system'), load('generate_artifact') + '\n' + prompt, Artifact)
    result.process_id = process_id
    return result


def quality_checks(catalogue: Catalogue, artifacts: dict, sources: list[dict] | None = None) -> list[str]:
    findings = []
    ids = [p.id for p in catalogue.processes]
    dupes = sorted({pid for pid in ids if ids.count(pid) > 1})
    if dupes:
        findings.append(f'Duplicate process IDs in catalogue: {", ".join(dupes)}')

    src_index = index_sources(sources) if sources else {}

    for p in catalogue.processes:
        if not p.evidence:
            findings.append(f'{p.id}: no source evidence')
        elif src_index:
            for ev in p.evidence:
                if ev.source_id not in src_index:
                    findings.append(f'{p.id}: evidence references unknown source_id "{ev.source_id}"')
                else:
                    loc = ev.locator.strip().lower()
                    loc_clean = re.sub(r'^locator\s*=\s*', '', loc)
                    if loc not in src_index[ev.source_id] and loc_clean not in src_index[ev.source_id]:
                        findings.append(f'{p.id}: evidence locator "{ev.locator}" not found in source {ev.source_id}')
        if not p.steps:
            findings.append(f'{p.id}: no workflow steps')
        if not p.actors:
            findings.append(f'{p.id}: no actors')

    for pid, a in artifacts.items():
        if pid not in ids:
            findings.append(f'{pid}: artifact is not linked to a catalogue process')
        for name in ('workflow_md', 'boundaries_md', 'domain_md', 'states_md'):
            text = getattr(a, name, '') if not isinstance(a, dict) else a.get(name, '')
            if len((text or '').strip()) < 100:
                findings.append(f'{pid}: {name} is unexpectedly short')
            blocks = extract_mermaid_blocks(text or '')
            if not blocks:
                findings.append(f'{pid}: {name} is missing a Mermaid diagram block')
            else:
                for b in blocks:
                    for merr in validate_mermaid_syntax(b):
                        findings.append(f'{pid}: {name} diagram issue — {merr}')

    return findings


def assess(llm, catalogue: Catalogue, artifacts: dict, feedback: str = '', sources: list[dict] | None = None) -> QualityReport:
    static = quality_checks(catalogue, artifacts, sources)
    cat_summary = _compact_catalogue_summary(catalogue.model_dump())
    budget = max(1400, min(3600, 28000 // max(1, len(artifacts) * 4)))
    arts_compact = _compact_artifacts_bundle(artifacts, max_field_chars=budget)
    prompt = (
        f'CATALOGUE:\n{_json(cat_summary)}\n\n'
        f'ARTIFACTS ({len(artifacts)} of {len(catalogue.processes)} processes):\n{_json(arts_compact)}\n\n'
        f'DETERMINISTIC FAILURES:\n{_json(static)}\n\n'
        f'REVIEW FEEDBACK:\n{feedback}'
    )
    result = llm.ask(load('system'), load('assess') + '\n' + prompt, QualityReport)
    result.critical = list(dict.fromkeys(static + result.critical))
    if static:
        result.score = min(result.score, 79)
    return result


def foundation(llm, catalogue: Catalogue, artifacts: dict, feedback: str = '') -> Foundation:
    cat_full = catalogue.model_dump()
    budget = max(1200, min(3200, 26000 // max(1, len(artifacts) * 4)))
    arts_compact = _compact_artifacts_bundle(artifacts, max_field_chars=budget)
    payload = (
        f'APPROVED CATALOGUE:\n{_json(cat_full)}\n\n'
        f'APPROVED ARTIFACTS ({len(artifacts)} processes):\n{_json(arts_compact)}\n\n'
        f'FEEDBACK:\n{feedback}'
    )
    return llm.ask(load('system'), load('foundation') + '\n' + payload, Foundation)


def planning(llm, catalogue: Catalogue, foundation_data: dict, tech_preferences: str = '', prefix: str = 'PRJ') -> Planning:
    px = normalize_prefix(prefix)
    payload = (
        f'PROJECT:\n{catalogue.project_name}\n\n'
        f'STRICT TASK ID CONVENTION: Number every task `{px}-SC-001`, `{px}-SC-002`, `{px}-SC-003`, etc. '
        f'(tracing back to `{px}-CA-...` and `{px}-WF-...`). Do NOT invent unfamiliar acronyms.\n\n'
        f'CATALOGUE OVERVIEW:\n{_json(_compact_catalogue_summary(catalogue.model_dump()))}\n\n'
        f'FOUNDATION:\n{_json(foundation_data)}\n\n'
        f'TECH PREFERENCES:\n{tech_preferences}'
    )
    return llm.ask(load('system'), load('planning') + '\n' + payload, Planning)


def implementation(llm, foundation_data: dict, planning_data: dict, task_selection: str = '') -> CodeBundle:
    payload = (
        f'FOUNDATION:\n{_json(foundation_data)}\n\n'
        f'PLAN AND TASKS:\n{_json(planning_data)}\n\n'
        f'SELECTED TASKS:\n{task_selection}'
    )
    return llm.ask(load('system'), load('implementation') + '\n' + payload, CodeBundle)


def review_scoped_item(llm, item_label: str, item_content: str, comments: list[dict], context_summary: dict | None = None) -> ScopedReview:
    """Run a focused AI architectural review on a single catalogue item or document."""
    comments_txt = '\n'.join(
        f"- [{c.get('status', 'open')}]"
        + (f" (on \"{c['quote']}\")" if c.get('quote') else '')
        + f" {c.get('text', '')}"
        for c in comments
    ) or '(no user comments yet)'
    prompt = (
        f'TASK: PERFORM A FOCUSED ARCHITECTURAL REVIEW of ONLY this item: {item_label}.\n'
        'Be concrete, concise, and strict about source grounding (SOURCE_DEFINED vs DESIGN_PROPOSED vs UNRESOLVED), '
        'missing exceptions, state/boundary clarity, and directly address any user review comments.\n\n'
        f'PROJECT CONTEXT:\n{_json(context_summary or {})}\n\n'
        f'USER REVIEW COMMENTS:\n{comments_txt}\n\n'
        f'ITEM CONTENT TO REVIEW:\n{item_content}'
    )
    return llm.ask(load('system'), prompt, ScopedReview)


def rerun_single_document(llm, item_label: str, current_md: str, comments: list[dict], context_summary: dict | None = None) -> SingleDocUpdate:
    """Regenerate ONLY a single Markdown architecture/Spec Kit document incorporating open review comments."""
    comments_txt = '\n'.join(
        f"- " + (f"(quote: \"{c['quote']}\") " if c.get('quote') else '') + c.get('text', '')
        for c in comments
    )
    prompt = (
        f'TASK: REVISE ONLY THIS SINGLE DOCUMENT ({item_label}) to resolve all review comments below.\n'
        'Preserve existing valid sections, source citations, SOURCE_DEFINED vs DESIGN_PROPOSED vs UNRESOLVED tags, '
        'and Mermaid diagram blocks unless a comment specifically asks to change them.\n\n'
        f'PROJECT CONTEXT:\n{_json(context_summary or {})}\n\n'
        f'REVIEW COMMENTS TO APPLY:\n{comments_txt}\n\n'
        f'CURRENT DOCUMENT MARKDOWN:\n{current_md}'
    )
    return llm.ask(load('system'), prompt, SingleDocUpdate)


def rerun_single_process_catalogue(llm, process_dict: dict, comments: list[dict], context_summary: dict | None = None) -> Process:
    """Revise ONLY a single Process item in the catalogue based on open comments."""
    comments_txt = '\n'.join(
        f"- " + (f"(quote: \"{c['quote']}\") " if c.get('quote') else '') + c.get('text', '')
        for c in comments
    )
    prompt = (
        f"TASK: REVISE ONLY THIS SINGLE CATALOGUE PROCESS ({process_dict.get('id')} — {process_dict.get('name')}) "
        'based on the reviewer comments below. Keep its ID stable unless asked to change it, preserve valid source citations, '
        'and never fabricate unsupported source facts.\n\n'
        f'PROJECT CONTEXT:\n{_json(context_summary or {})}\n\n'
        f'REVIEW COMMENTS TO APPLY:\n{comments_txt}\n\n'
        f'CURRENT PROCESS JSON:\n{_json(process_dict)}'
    )
    return llm.ask(load('system'), prompt, Process)
