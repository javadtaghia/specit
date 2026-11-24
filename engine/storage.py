from pathlib import Path
from datetime import datetime, timezone
import json
import re
import difflib


def slug(name: str) -> str:
    return re.sub(r'[^a-z0-9-]+', '-', name.lower()).strip('-')[:65] or 'project'


def normalize_prefix(raw: str, fallback: str = 'PRJ') -> str:
    cleaned = re.sub(r'[^A-Za-z0-9]+', '', (raw or '').upper())[:10]
    return cleaned if len(cleaned) >= 2 else fallback


def workflow_id_for(process_id: str, prefix: str = 'PRJ') -> str:
    """Convert catalogue ID like PRJ-CA-001 into its matching workflow ID PRJ-WF-001."""
    px = normalize_prefix(prefix)
    m = re.search(r'(\d+)$', process_id or '')
    if m:
        return f'{px}-WF-{int(m.group(1)):03d}'
    return f'{px}-WF-{re.sub(r"[^A-Za-z0-9]+", "", process_id or "001").upper()[:8]}'


from .version import default_workspace_root


class Store:
    def __init__(self, root=None):
        self.root = Path(root).resolve() if root is not None else default_workspace_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def project(self, name: str) -> Path:
        p = self.root / slug(name)
        p.mkdir(parents=True, exist_ok=True)
        (p / 'revisions').mkdir(exist_ok=True)
        (p / 'inputs').mkdir(exist_ok=True)
        (p / 'diagrams').mkdir(exist_ok=True)
        (p / 'assets').mkdir(exist_ok=True)
        return p

    def projects(self) -> list[str]:
        return sorted(x.name for x in self.root.iterdir() if x.is_dir())

    def read(self, p: Path, key: str, default=None):
        f = p / f'{key}.json'
        return json.loads(f.read_text(encoding='utf-8')) if f.exists() else default

    def write(self, p: Path, key: str, obj, reason: str = 'updated'):
        f = p / f'{key}.json'
        old = f.read_text(encoding='utf-8') if f.exists() else None
        new = json.dumps(obj, indent=2, ensure_ascii=False)
        if old == new:
            return
        rev = p / 'revisions' / slug(key)
        rev.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        (rev / f'{stamp}.json').write_text(new, encoding='utf-8')
        (rev / f'{stamp}.meta.json').write_text(
            json.dumps({'reason': reason, 'timestamp': stamp}, indent=2),
            encoding='utf-8',
        )
        f.write_text(new, encoding='utf-8')

    def invalidate_from(self, p: Path, stage: str, reason: str):
        """Cascade approval invalidation cleanly from an upstream stage downward."""
        cascade = {
            'sources': ['catalogue_approved', 'artifacts_approved', 'foundation_approved', 'planning_approved'],
            'catalogue': ['catalogue_approved', 'artifacts_approved', 'foundation_approved', 'planning_approved'],
            'artifacts': ['artifacts_approved', 'foundation_approved', 'planning_approved'],
            'foundation': ['foundation_approved', 'planning_approved'],
            'planning': ['planning_approved'],
        }
        for flag in cascade.get(stage, []):
            if self.read(p, flag, False):
                self.write(p, flag, False, reason)

    def revisions(self, p: Path, key: str) -> list[Path]:
        folder = p / 'revisions' / slug(key)
        return (
            sorted([x for x in folder.glob('*.json') if not x.name.endswith('.meta.json')], reverse=True)
            if folder.exists()
            else []
        )

    def revisions_with_meta(self, p: Path, key: str) -> list[dict]:
        out = []
        for rev_file in self.revisions(p, key):
            meta_file = rev_file.with_suffix('.meta.json')
            meta = json.loads(meta_file.read_text(encoding='utf-8')) if meta_file.exists() else {}
            out.append({
                'id': rev_file.stem,
                'filename': rev_file.name,
                'timestamp': meta.get('timestamp', rev_file.stem),
                'reason': meta.get('reason', 'updated'),
            })
        return out

    def read_revision(self, p: Path, key: str, rev_id: str):
        rev_file = p / 'revisions' / slug(key) / f'{rev_id}.json'
        if not rev_file.exists():
            raise FileNotFoundError(rev_id)
        return json.loads(rev_file.read_text(encoding='utf-8'))

    def diff(self, p: Path, key: str, index_a: int = 1, index_b: int = 0) -> str:
        xs = self.revisions(p, key)
        if len(xs) <= max(index_a, index_b):
            return ''
        a = xs[index_a].read_text(encoding='utf-8').splitlines(True)
        b = xs[index_b].read_text(encoding='utf-8').splitlines(True)
        return ''.join(difflib.unified_diff(a, b, fromfile=xs[index_a].name, tofile=xs[index_b].name))

    def diff_by_ids(self, p: Path, key: str, rev_a: str, rev_b: str) -> str:
        fa = p / 'revisions' / slug(key) / f'{rev_a}.json'
        fb = p / 'revisions' / slug(key) / f'{rev_b}.json'
        if not fa.exists() or not fb.exists():
            return ''
        a = fa.read_text(encoding='utf-8').splitlines(True)
        b = fb.read_text(encoding='utf-8').splitlines(True)
        return ''.join(difflib.unified_diff(a, b, fromfile=fa.name, tofile=fb.name))

    def save_upload(self, p: Path, filename: str, data: bytes) -> Path:
        safe = Path(filename).name
        dest = p / 'inputs' / safe
        if dest.exists() and dest.read_bytes() != data:
            dest = p / 'inputs' / f'{datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")}-{safe}'
        dest.write_bytes(data)
        return dest

    def delete_upload(self, p: Path, filename: str) -> bool:
        safe = Path(filename).name
        target = (p / 'inputs' / safe).resolve()
        if target.parent == (p / 'inputs').resolve() and target.exists():
            target.unlink()
            return True
        return False

    def read_diagram(self, p: Path, diagram_key: str) -> str | None:
        f = p / 'diagrams' / f'{slug(diagram_key)}.drawio'
        return f.read_text(encoding='utf-8') if f.exists() else None

    def read_diagram_svg(self, p: Path, diagram_key: str) -> str | None:
        f = p / 'diagrams' / f'{slug(diagram_key)}.svg'
        return f.read_text(encoding='utf-8') if f.exists() else None

    def write_diagram(self, p: Path, diagram_key: str, xml: str, reason: str = 'diagram updated', svg: str | None = None):
        dkey = slug(diagram_key)
        f = p / 'diagrams' / f'{dkey}.drawio'
        if svg is not None and svg.strip():
            (p / 'diagrams' / f'{dkey}.svg').write_text(svg, encoding='utf-8')
        old = f.read_text(encoding='utf-8') if f.exists() else None
        if old == xml:
            return
        rev = p / 'revisions' / f'diagram-{dkey}'
        rev.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        (rev / f'{stamp}.json').write_text(json.dumps({'xml': xml}, indent=2), encoding='utf-8')
        (rev / f'{stamp}.meta.json').write_text(
            json.dumps({'reason': reason, 'timestamp': stamp}, indent=2),
            encoding='utf-8',
        )
        f.write_text(xml, encoding='utf-8')

    def save_asset(self, p: Path, filename: str, data: bytes) -> str:
        allowed = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
        raw_name = Path(filename or 'image.png').name
        ext = Path(raw_name).suffix.lower()
        if ext not in allowed:
            raise ValueError('Supported image formats: PNG, JPG, JPEG, GIF, WEBP, SVG')
        stem = slug(Path(raw_name).stem) or 'image'
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')[:18]
        final_name = f'{stamp}-{stem}{ext}'
        assets_dir = p / 'assets'
        assets_dir.mkdir(exist_ok=True)
        (assets_dir / final_name).write_bytes(data)
        return final_name

    def get_asset_path(self, p: Path, filename: str) -> Path:
        safe = Path(filename).name
        target = (p / 'assets' / safe).resolve()
        if target.parent != (p / 'assets').resolve() or not target.exists():
            raise FileNotFoundError(safe)
        return target

    def get_prefix(self, p: Path) -> str:
        meta = self.read(p, 'project_meta', {}) or {}
        if meta.get('prefix'):
            return normalize_prefix(meta['prefix'])
        # Default clean prefix from first token of project slug, fallback PRJ
        token = (p.name.split('-')[0] or 'PRJ').upper()
        if token in ('MY', 'NEW', 'TEST', 'PROJECT'):
            return 'PRJ'
        return normalize_prefix(token[:6], fallback='PRJ')

    def set_prefix(self, p: Path, prefix: str, renumber_existing: bool = True) -> dict:
        px = normalize_prefix(prefix)
        meta = self.read(p, 'project_meta', {}) or {}
        meta['prefix'] = px
        self.write(p, 'project_meta', meta, f'set project prefix to {px}')

        id_map: dict[str, str] = {}
        if renumber_existing:
            cat = self.read(p, 'catalogue')
            if cat and isinstance(cat.get('processes'), list):
                for idx, proc in enumerate(cat['processes'], 1):
                    old_id = proc.get('id', '')
                    new_id = f'{px}-CA-{idx:03d}'
                    if old_id:
                        id_map[old_id] = new_id
                    proc['id'] = new_id
                    for r_idx, rule in enumerate(proc.get('rules', []), 1):
                        if isinstance(rule, dict):
                            rule['id'] = f'{new_id}-R{r_idx}'
                self.write(p, 'catalogue', cat, f'applied uniform prefix {px}-CA-NNN')

            # Migrate linked artifacts, diagrams, and comments cleanly
            for old_id, new_id in id_map.items():
                if old_id == new_id:
                    continue
                old_art = p / f'artifact_{old_id}.json'
                if old_art.exists():
                    art_data = json.loads(old_art.read_text(encoding='utf-8'))
                    art_data['process_id'] = new_id
                    self.write(p, f'artifact_{new_id}', art_data, f'renamed from {old_id} to {new_id}')
                    old_art.unlink()
                for kind in ('workflow', 'boundaries', 'domain', 'states'):
                    old_d = p / 'diagrams' / f'{slug(f"{old_id}_{kind}")}.drawio'
                    new_d = p / 'diagrams' / f'{slug(f"{new_id}_{kind}")}.drawio'
                    if old_d.exists() and not new_d.exists():
                        old_d.rename(new_d)
                    old_s = p / 'diagrams' / f'{slug(f"{old_id}_{kind}")}.svg'
                    new_s = p / 'diagrams' / f'{slug(f"{new_id}_{kind}")}.svg'
                    if old_s.exists() and not new_s.exists():
                        old_s.rename(new_s)

            if id_map:
                comments = self.read(p, 'comments', [])
                changed = False
                for c in comments:
                    tk = c.get('target_key', '')
                    for old_id, new_id in id_map.items():
                        if f'::{old_id}' in tk:
                            c['target_key'] = tk.replace(f'::{old_id}', f'::{new_id}')
                            changed = True
                if changed:
                    self.write(p, 'comments', comments, f'updated comment scopes for prefix {px}')

        return {'prefix': px, 'renamed': id_map}
