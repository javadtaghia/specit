"""Mermaid extraction, validation, and Draw.io (mxfile XML) conversion utilities.
Supports flowchart/graph (LR & TB/TD), subgraphs/frames, classDiagram, and stateDiagram-v2.
"""
import html
import re


MERMAID_BLOCK_RE = re.compile(r'```mermaid\s*\n(.*?)```', flags=re.DOTALL | re.IGNORECASE)
VALID_STARTS = (
    'flowchart', 'graph', 'sequencediagram', 'classdiagram',
    'statediagram', 'statediagram-v2', 'erdiagram', 'gantt', 'pie', 'mindmap',
)


def extract_mermaid_blocks(markdown_text: str) -> list[str]:
    if not markdown_text:
        return []
    return [m.group(1).strip() for m in MERMAID_BLOCK_RE.finditer(markdown_text) if m.group(1).strip()]


def validate_mermaid_syntax(code: str) -> list[str]:
    """Lightweight deterministic syntax checks for Mermaid code blocks."""
    issues = []
    lines = [ln.strip() for ln in code.splitlines() if ln.strip() and not ln.strip().startswith('%%')]
    if not lines:
        return ['Empty Mermaid diagram block']
    first = lines[0].split()[0].lower()
    if not any(first.startswith(s) for s in VALID_STARTS):
        issues.append(f'Unrecognized Mermaid diagram header: "{lines[0][:40]}"')
    if len(lines) < 2:
        issues.append('Mermaid diagram has no nodes or transitions')
    if code.count('{') != code.count('}'):
        issues.append('Unbalanced curly braces in Mermaid diagram')
    return issues


def _escape_xml(value: str) -> str:
    return html.escape(str(value or ''), quote=True)


def _mxfile_wrap(cells_xml: list[str], diagram_name: str = 'Architecture Diagram') -> str:
    body = '\n        '.join(cells_xml)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mxfile host="specit" agent="SPECiTSketch" version="24.0.0">\n'
        f'  <diagram id="diag-1" name="{_escape_xml(diagram_name)}">\n'
        '    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1169" pageHeight="827">\n'
        '      <root>\n'
        '        <mxCell id="0"/>\n'
        '        <mxCell id="1" parent="0"/>\n'
        f'        {body}\n'
        '      </root>\n'
        '    </mxGraphModel>\n'
        '  </diagram>\n'
        '</mxfile>'
    )


def _parse_mermaid(code: str) -> dict:
    """Parse Mermaid flowchart/graph/class/state diagrams preserving direction, subgraphs, and labels."""
    nodes: dict[str, dict] = {}
    edges: list[tuple[str, str, str]] = []
    subgraphs: list[dict] = []  # [{'id': ..., 'title': ..., 'members': set()}]
    sg_stack: list[dict] = []
    horizontal = False
    is_state = False
    in_class: str | None = None
    class_attrs: dict[str, list[str]] = {}

    def register_node(raw: str, is_target: bool = False) -> str:
        token = raw.strip().rstrip(';')
        if token == '[*]':
            nid = 'END_STATE' if is_target else 'START_STATE'
            lbl = 'End' if is_target else 'Start'
            nodes.setdefault(nid, {'label': lbl, 'shape': 'oval'})
            if sg_stack:
                sg_stack[-1]['members'].add(nid)
            return nid

        # Handle shapes: A[(Label)], A[Label], A(Label), A((Label)), A{Label}
        patterns = [
            (r'^([A-Za-z0-9_.-]+)\s*\[\(\"?(.*?)\"?\)\]$', 'rect'),
            (r'^([A-Za-z0-9_.-]+)\s*\(\(\"?(.*?)\"?\)\)$', 'oval'),
            (r'^([A-Za-z0-9_.-]+)\s*\{\"?(.*?)\"?\}$', 'decision'),
            (r'^([A-Za-z0-9_.-]+)\s*\[\"?(.*?)\"?\]$', 'rect'),
            (r'^([A-Za-z0-9_.-]+)\s*\(\"?(.*?)\"?\)$', 'oval' if is_state else 'rect'),
            (r'^([A-Za-z0-9_.-]+)$', 'oval' if is_state else 'rect'),
        ]
        for pat, shape in patterns:
            m = re.match(pat, token)
            if m:
                nid = m.group(1)
                lbl = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else nid
                if nid not in nodes:
                    nodes[nid] = {'label': lbl, 'shape': shape}
                elif nodes[nid]['label'] == nid and lbl != nid:
                    nodes[nid]['label'] = lbl
                    nodes[nid]['shape'] = shape
                if sg_stack:
                    sg_stack[-1]['members'].add(nid)
                return nid

        safe = re.sub(r'[^A-Za-z0-9_]+', '_', token).strip('_') or f'N{len(nodes) + 1}'
        nodes.setdefault(safe, {'label': token, 'shape': 'rect'})
        if sg_stack:
            sg_stack[-1]['members'].add(safe)
        return safe

    edge_patterns = [
        # A -->|label| B  or  A -.->|label| B
        ('pipe', re.compile(r'^(.+?)\s*(?:--+>|==+>|-\.+->)\s*\|([^|]+)\|\s*(.+)$')),
        # A -- label --> B
        ('mid', re.compile(r'^(.+?)\s*--\s+([^->]+?)\s+-->\s*(.+)$')),
        # classDiagram cardinality: A "1" --> "0..*" B : label
        ('class_rel', re.compile(r'^([A-Za-z0-9_.-]+)\s*(?:"([^"]*)")?\s*(?:--+>|\.\.+>|<\|--|--\*|--o|<-->)\s*(?:"([^"]*)")?\s*([A-Za-z0-9_.-]+)\s*(?::\s*(.+))?$')),
        # State / sequence: A --> B : label
        ('colon', re.compile(r'^(.+?)\s*(?:--+>|==+>|-\.+->|->>|-->>)\s*(.+?)\s*:\s*(.+)$')),
        # Plain arrow: A --> B
        ('plain', re.compile(r'^(.+?)\s*(?:--+>|==+>|-\.+->|->>|-->>)\s*(.+)$')),
    ]

    for raw_line in (code or '').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('%%'):
            continue
        low = line.lower()

        if low.startswith(('flowchart ', 'graph ')):
            if re.search(r'\b(lr|rl)\b', low):
                horizontal = True
            continue
        if low.startswith('direction '):
            if re.search(r'\b(lr|rl)\b', low):
                horizontal = True
            continue
        if low.startswith('statediagram'):
            is_state = True
            continue
        if low.startswith(('classdiagram', 'sequencediagram')):
            continue

        # Inside class { ... } block
        if in_class is not None:
            if line == '}':
                in_class = None
            else:
                clean_attr = line.strip()
                if clean_attr and not clean_attr.startswith('<<'):
                    class_attrs.setdefault(in_class, []).append(clean_attr)
            continue

        # class Foo {
        cm = re.match(r'^class\s+([A-Za-z0-9_.-]+)\s*\{?$', line)
        if cm:
            cid = cm.group(1)
            nodes.setdefault(cid, {'label': cid, 'shape': 'rect'})
            if line.endswith('{'):
                in_class = cid
            continue

        # subgraph Id[Title]  or  subgraph Title
        if low.startswith('subgraph '):
            rest = line[len('subgraph '):].strip()
            sm = re.match(r'^([A-Za-z0-9_.-]+)\s*\[\"?(.*?)\"?\]$', rest)
            if sm:
                sg = {'id': sm.group(1), 'title': sm.group(2).strip(), 'members': set()}
            else:
                sg = {'id': f'SG_{len(subgraphs) + 1}', 'title': rest.strip('"'), 'members': set()}
            subgraphs.append(sg)
            sg_stack.append(sg)
            continue
        if low == 'end':
            if sg_stack:
                sg_stack.pop()
            continue
        if any(low.startswith(k) for k in ('style ', 'classdef ', 'linkstyle ', 'click ')):
            continue
        pm = re.match(r'^(?:participant|actor)\s+([A-Za-z0-9_.-]+)(?:\s+as\s+(.+))?$', line, flags=re.IGNORECASE)
        if pm:
            nodes[pm.group(1)] = {'label': (pm.group(2) or pm.group(1)).strip(), 'shape': 'rect'}
            continue

        matched = False
        for kind, pat in edge_patterns:
            m = pat.match(line)
            if not m:
                continue
            if kind in ('pipe', 'mid'):
                s_id = register_node(m.group(1), False)
                lbl = m.group(2).strip()
                d_id = register_node(m.group(3), True)
            elif kind == 'class_rel':
                s_id = register_node(m.group(1), False)
                d_id = register_node(m.group(4), True)
                c1, c2, rel = (m.group(2) or '').strip(), (m.group(3) or '').strip(), (m.group(5) or '').strip()
                card = f'{c1}..{c2}' if (c1 and c2) else (c1 or c2)
                lbl = f'{rel} ({card})'.strip() if (rel and card) else (rel or card)
            elif kind == 'colon':
                s_id = register_node(m.group(1), False)
                d_id = register_node(m.group(2), True)
                lbl = m.group(3).strip()
            else:
                s_id = register_node(m.group(1), False)
                d_id = register_node(m.group(2), True)
                lbl = ''
            edges.append((s_id, d_id, lbl))
            matched = True
            break

        if not matched:
            register_node(line, False)

    # Append concise attribute subtitles to classDiagram nodes
    for cid, attrs in class_attrs.items():
        if cid in nodes and attrs:
            preview = ' · '.join(attrs[:3]) + ('…' if len(attrs) > 3 else '')
            nodes[cid]['label'] = f"{nodes[cid]['label']} | {preview}"

    return {'nodes': nodes, 'edges': edges, 'subgraphs': subgraphs, 'horizontal': horizontal}


def mermaid_to_drawio_xml(mermaid_code: str, title: str = 'Diagram', diagram_kind: str = 'workflow') -> str:
    """Convert Mermaid syntax into a clean, editable Draw.io mxfile XML diagram preserving LR/TB & subgraphs."""
    parsed = _parse_mermaid(mermaid_code or '')
    node_map: dict[str, dict] = parsed['nodes']
    edges: list[tuple[str, str, str]] = parsed['edges']
    subgraphs: list[dict] = parsed['subgraphs']
    horizontal: bool = parsed['horizontal']

    if not node_map:
        node_map = {'NODE_1': {'label': f'{title} (edit diagram)', 'shape': 'rect'}}

    palette = {
        'workflow': ('#fef9d7', '#1e1e1e'),
        'boundaries': ('#eaf4fe', '#1e1e1e'),
        'domain': ('#f0edfe', '#1e1e1e'),
        'states': ('#fef0f2', '#1e1e1e'),
    }
    fill, stroke = palette.get(diagram_kind, ('#fef9d7', '#1e1e1e'))

    # Compute layered layout via BFS (ignoring self-loops for level depth)
    node_ids = list(node_map.keys())
    indegree = {nid: 0 for nid in node_ids}
    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for s, d, _ in edges:
        if s != d and s in adj and d in indegree:
            adj[s].append(d)
            indegree[d] += 1

    levels: dict[str, int] = {}
    queue = [nid for nid in node_ids if indegree[nid] == 0] or [node_ids[0]]
    for nid in queue:
        levels[nid] = 0
    qi = 0
    while qi < len(queue):
        cur = queue[qi]
        qi += 1
        for nxt in adj.get(cur, []):
            if nxt not in levels:
                levels[nxt] = levels[cur] + 1
                queue.append(nxt)
    for nid in node_ids:
        levels.setdefault(nid, 0)

    # Group subgraph members contiguously within each level so external nodes NEVER sit inside a subgraph frame!
    sg_index = {}
    for idx, sg in enumerate(subgraphs, 1):
        for m in sg['members']:
            sg_index.setdefault(m, idx)

    by_level: dict[int, list[str]] = {}
    for nid in node_ids:
        by_level.setdefault(levels[nid], []).append(nid)
    for lvl in by_level:
        by_level[lvl].sort(key=lambda nid: (sg_index.get(nid, 999), node_ids.index(nid)))

    box_w, box_h = 220, 70
    coords: dict[str, tuple[int, int, int, int]] = {}
    start_x, start_y = 70, 80

    if horizontal:
        gap_x, gap_y = 170, 74
        for lvl in sorted(by_level):
            col = by_level[lvl]
            y_cursor = start_y
            prev_sg = None
            for nid in col:
                cur_sg = sg_index.get(nid, 0)
                if prev_sg is not None and cur_sg != prev_sg:
                    y_cursor += 54  # Extra gap separating subgraph from external nodes
                w = 130 if nid in ('START_STATE', 'END_STATE') else box_w
                h = 54 if nid in ('START_STATE', 'END_STATE') else box_h
                x = start_x + lvl * (box_w + gap_x)
                coords[nid] = (x, y_cursor, w, h)
                y_cursor += h + gap_y
                prev_sg = cur_sg
    else:
        gap_x, gap_y = 80, 96
        for lvl in sorted(by_level):
            row = by_level[lvl]
            x_cursor = start_x
            prev_sg = None
            for nid in row:
                cur_sg = sg_index.get(nid, 0)
                if prev_sg is not None and cur_sg != prev_sg:
                    x_cursor += 70  # Extra gap separating subgraph from external nodes
                w = 130 if nid in ('START_STATE', 'END_STATE') else box_w
                h = 54 if nid in ('START_STATE', 'END_STATE') else box_h
                y = start_y + lvl * (box_h + gap_y)
                coords[nid] = (x_cursor, y, w, h)
                x_cursor += w + gap_x
                prev_sg = cur_sg

    cells = []
    cell_id_map: dict[str, str] = {}
    next_id = 2

    # Emit outer subgraph container frames FIRST so they sit cleanly behind member nodes
    for sg in subgraphs:
        members = [m for m in sg['members'] if m in coords]
        if not members:
            continue
        pad_x, pad_top, pad_bot = 32, 54, 34
        # Leave extra right space if any member has a self-loop
        has_self_loop = any(s == d and s in members for s, d, _ in edges)
        extra_right = 155 if has_self_loop else 0
        min_x = min(coords[m][0] for m in members) - pad_x
        min_y = min(coords[m][1] for m in members) - pad_top
        max_x = max(coords[m][0] + coords[m][2] for m in members) + pad_x + extra_right
        max_y = max(coords[m][1] + coords[m][3] for m in members) + pad_bot
        cid = str(next_id)
        next_id += 1
        style = f'rounded=1;container=1;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor={stroke};strokeWidth=2;fontFamily=Architects Daughter;fontSize=14;'
        cells.append(
            f'<mxCell id="{cid}" value="{_escape_xml(sg["title"])}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{min_x}" y="{min_y}" width="{max_x - min_x}" height="{max_y - min_y}" as="geometry"/>'
            '</mxCell>'
        )

    # Emit nodes
    for nid in node_ids:
        info = node_map[nid]
        x, y, w, h = coords[nid]
        cid = str(next_id)
        next_id += 1
        cell_id_map[nid] = cid
        shape = info.get('shape', 'rect')
        shape_prefix = 'rhombus;' if shape == 'decision' else 'ellipse;' if shape == 'oval' else 'rounded=1;'
        node_fill = '#fef0f2' if nid in ('START_STATE', 'END_STATE') else fill
        style = f'{shape_prefix}whiteSpace=wrap;html=1;fillColor={node_fill};strokeColor={stroke};strokeWidth=2;fontFamily=Architects Daughter;fontSize=14;'
        cells.append(
            f'<mxCell id="{cid}" value="{_escape_xml(info["label"])}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
            '</mxCell>'
        )

    # Emit edges
    for s, d, lbl in edges:
        if s in cell_id_map and d in cell_id_map:
            cid = str(next_id)
            next_id += 1
            style = f'edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;strokeColor={stroke};strokeWidth=1.8;endArrow=open;fontFamily=Architects Daughter;fontSize=12;'
            cells.append(
                f'<mxCell id="{cid}" value="{_escape_xml(lbl)}" style="{style}" edge="1" parent="1" source="{cell_id_map[s]}" target="{cell_id_map[d]}">'
                '<mxGeometry relative="1" as="geometry"/>'
                '</mxCell>'
            )

    return _mxfile_wrap(cells, diagram_name=title)


def process_to_drawio_xml(process: dict, diagram_kind: str = 'workflow') -> str:
    """Fallback Draw.io XML generator directly from structured Process fields."""
    name = process.get('name', process.get('id', 'Process'))
    steps = process.get('steps') or []
    if steps:
        lines = ['flowchart LR']
        for i, step in enumerate(steps, 1):
            clean = step.replace('"', "'").replace('[', '(').replace(']', ')')[:80]
            lines.append(f'  S{i}["{i}. {clean}"]')
            if i > 1:
                lines.append(f'  S{i - 1} --> S{i}')
        return mermaid_to_drawio_xml('\n'.join(lines), title=name, diagram_kind=diagram_kind)
    return mermaid_to_drawio_xml('', title=name, diagram_kind=diagram_kind)
