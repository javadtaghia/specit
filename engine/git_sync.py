"""Per-project independent Git repository for archiving project artifacts (completely isolated from SPECiT's own repo)."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .version import resource_root


DEFAULT_GITIGNORE = """.DS_Store
*.zip
speckit-handoff/
__pycache__/
*.pyc
"""


def _assert_isolated_project_dir(project: Path) -> Path:
    proj = project.resolve()
    app_root = resource_root().resolve()
    if proj == app_root:
        raise ValueError('Refusing to run artifact Git sync on the SPECiT application source directory.')
    return proj


def _validate_remote_url(url: str) -> str:
    u = (url or '').strip()
    if not u:
        return ''
    if u.startswith('-') or any(ch in u for ch in ('\n', '\r', '\0')):
        raise ValueError('Invalid Git remote URL')
    # Allow https://, http://, ssh://, git@host:org/repo, or local filesystem path for bare repos
    if not re.match(r'^(https?://|ssh://|git@[\w.-]+:|file://|/)', u):
        raise ValueError('Git remote must start with https://, ssh://, git@host:..., or an absolute path')
    return u


def _validate_branch(branch: str) -> str:
    b = (branch or 'main').strip()
    if not re.match(r'^[A-Za-z0-9._/-]+$', b) or b.startswith('-') or '..' in b:
        raise ValueError(f'Invalid Git branch name: {branch}')
    return b


def _run_git(project: Path, args: list[str], timeout: int = 60, *, allow_uninitialized: bool = False) -> subprocess.CompletedProcess:
    proj = _assert_isolated_project_dir(project)
    git_bin = shutil.which('git') or '/usr/bin/git'
    env = dict(os.environ)
    env['GIT_TERMINAL_PROMPT'] = '0'
    # Hard isolation: never inherit or walk up into SPECiT's own dashboard/source-code Git repository
    for k in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_OBJECT_DIRECTORY'):
        env.pop(k, None)
    env['GIT_CEILING_DIRECTORIES'] = str(proj.parent)

    git_dir = proj / '.git'
    if not allow_uninitialized:
        if not git_dir.is_dir():
            raise RuntimeError('Project artifact Git repository is not initialized yet.')
        env['GIT_DIR'] = str(git_dir)
        env['GIT_WORK_TREE'] = str(proj)

    return subprocess.run(
        [git_bin, *args],
        cwd=str(proj),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def sync_readable_docs(project: Path) -> list[str]:
    """Mirror structured JSON artifacts into clean, browsable Markdown docs/ inside the project Git repo."""
    written: list[str] = []
    docs_dir = project / 'docs'
    docs_dir.mkdir(exist_ok=True)

    cat_file = project / 'catalogue.json'
    cat = json.loads(cat_file.read_text(encoding='utf-8')) if cat_file.exists() else None
    if cat:
        lines = [
            f"# {cat.get('project_name') or project.name}",
            '',
            cat.get('project_summary') or '',
            '',
            '## Process Inventory',
            '',
            '| ID | Process | Actors | Confidence |',
            '| --- | --- | --- | --- |',
        ]
        for p in cat.get('processes', []):
            lines.append(
                f"| {p.get('id', '')} | {p.get('name', '')} | {', '.join(p.get('actors', []))} | {p.get('confidence', '')} |"
            )
        if cat.get('open_questions'):
            lines.extend(['', '## Open Questions', ''])
            for q in cat['open_questions']:
                lines.append(f'- {q}')
        readme = project / 'README.md'
        readme.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        written.append('README.md')

    for art_file in sorted(project.glob('artifact_*.json')):
        pid = art_file.stem[len('artifact_'):]
        art = json.loads(art_file.read_text(encoding='utf-8'))
        pdir = docs_dir / 'architecture' / pid
        pdir.mkdir(parents=True, exist_ok=True)
        for fname, field in [
            ('workflow.md', 'workflow_md'),
            ('boundaries.md', 'boundaries_md'),
            ('domain.md', 'domain_md'),
            ('states.md', 'states_md'),
        ]:
            if art.get(field):
                out = pdir / fname
                out.write_text(art[field], encoding='utf-8')
                written.append(str(out.relative_to(project)))

    found_file = project / 'foundation.json'
    if found_file.exists():
        found = json.loads(found_file.read_text(encoding='utf-8'))
        sdir = docs_dir / 'speckit'
        sdir.mkdir(parents=True, exist_ok=True)
        for fname, field in [
            ('constitution.md', 'constitution_md'),
            ('spec.md', 'specification_md'),
            ('clarification.md', 'clarification_md'),
        ]:
            if found.get(field):
                out = sdir / fname
                out.write_text(found[field], encoding='utf-8')
                written.append(str(out.relative_to(project)))

    plan_file = project / 'planning.json'
    if plan_file.exists():
        plan = json.loads(plan_file.read_text(encoding='utf-8'))
        sdir = docs_dir / 'speckit'
        sdir.mkdir(parents=True, exist_ok=True)
        for fname, field in [('plan.md', 'plan_md'), ('tasks.md', 'tasks_md')]:
            if plan.get(field):
                out = sdir / fname
                out.write_text(plan[field], encoding='utf-8')
                written.append(str(out.relative_to(project)))

    return written


def get_git_status(project: Path) -> dict:
    proj = _assert_isolated_project_dir(project)
    git_dir = proj / '.git'
    if not git_dir.is_dir():
        return {
            'initialized': False,
            'independent_repo': True,
            'remote_url': '',
            'branch': 'main',
            'changed_files': [],
            'recent_commits': [],
            'local_path': str(proj),
            'git_dir': str(git_dir),
        }

    br = _run_git(proj, ['rev-parse', '--abbrev-ref', 'HEAD'])
    branch = br.stdout.strip() if br.returncode == 0 and br.stdout.strip() != 'HEAD' else 'main'

    rem = _run_git(proj, ['remote', 'get-url', 'origin'])
    remote_url = rem.stdout.strip() if rem.returncode == 0 else ''

    st = _run_git(proj, ['status', '--porcelain'])
    changed = []
    if st.returncode == 0:
        for line in st.stdout.splitlines():
            if len(line) >= 4:
                changed.append({'status': line[:2].strip() or '?', 'path': line[3:].strip()})

    lg = _run_git(proj, ['log', '-n', '10', '--pretty=format:%h|%ad|%an|%s', '--date=short'])
    commits = []
    if lg.returncode == 0 and lg.stdout.strip():
        for line in lg.stdout.splitlines():
            parts = line.split('|', 3)
            if len(parts) == 4:
                commits.append({'hash': parts[0], 'date': parts[1], 'author': parts[2], 'message': parts[3]})

    return {
        'initialized': True,
        'independent_repo': True,
        'remote_url': remote_url,
        'branch': branch,
        'changed_files': changed,
        'recent_commits': commits,
        'local_path': str(proj),
        'git_dir': str(git_dir),
    }


def connect_git(project: Path, remote_url: str = '', branch: str = 'main') -> dict:
    proj = _assert_isolated_project_dir(project)
    url = _validate_remote_url(remote_url)
    br = _validate_branch(branch)

    if not (proj / '.git').is_dir():
        r = _run_git(proj, ['init', '-b', br], allow_uninitialized=True)
        if r.returncode != 0:
            # Fallback for older git versions without -b
            r2 = _run_git(proj, ['init'], allow_uninitialized=True)
            if r2.returncode != 0:
                raise RuntimeError(r2.stderr or r2.stdout or 'git init failed')
            _run_git(proj, ['checkout', '-B', br])
    else:
        # Ensure current branch matches requested branch if repo has commits or unborn HEAD
        _run_git(proj, ['checkout', '-B', br])

    gi = proj / '.gitignore'
    if not gi.exists():
        gi.write_text(DEFAULT_GITIGNORE, encoding='utf-8')

    if url:
        cur = _run_git(proj, ['remote', 'get-url', 'origin'])
        if cur.returncode == 0:
            r = _run_git(proj, ['remote', 'set-url', 'origin', url])
        else:
            r = _run_git(proj, ['remote', 'add', 'origin', url])
        if r.returncode != 0:
            raise RuntimeError(r.stderr or r.stdout or 'Failed to configure remote origin')

    sync_readable_docs(proj)
    return get_git_status(proj)


def commit_project(project: Path, message: str = 'Update project artifacts', push: bool = False, branch: str | None = None) -> dict:
    proj = _assert_isolated_project_dir(project)
    if not (proj / '.git').is_dir():
        connect_git(proj, '', branch or 'main')

    sync_readable_docs(proj)
    add_res = _run_git(proj, ['add', '-A'])
    if add_res.returncode != 0:
        raise RuntimeError(add_res.stderr or add_res.stdout or 'git add failed')

    status_before = _run_git(proj, ['status', '--porcelain'])
    committed = False
    commit_out = ''
    if status_before.stdout.strip():
        msg = (message or 'Update project artifacts').strip()
        c_res = _run_git(proj, ['commit', '-m', msg])
        if c_res.returncode != 0:
            # Ensure local repo has fallback user.name/email if global git config is unset
            if 'user.name' in (c_res.stderr or '') or 'Please tell me who you are' in (c_res.stderr or ''):
                _run_git(proj, ['config', 'user.name', 'SPECiT'])
                _run_git(proj, ['config', 'user.email', 'specit@local'])
                c_res = _run_git(proj, ['commit', '-m', msg])
            if c_res.returncode != 0:
                raise RuntimeError((c_res.stderr or c_res.stdout or 'git commit failed').strip())
        committed = True
        commit_out = c_res.stdout.strip()

    pushed = False
    push_out = ''
    if push:
        st = get_git_status(proj)
        if not st['remote_url']:
            raise RuntimeError('No Git remote URL connected yet. Add a remote URL and click Connect first.')
        target_branch = _validate_branch(branch or st['branch'])
        p_res = _run_git(proj, ['push', '-u', 'origin', target_branch], timeout=120)
        if p_res.returncode != 0:
            raise RuntimeError((p_res.stderr or p_res.stdout or 'git push failed').strip())
        pushed = True
        push_out = (p_res.stdout or p_res.stderr or 'Pushed successfully').strip()

    return {
        'committed': committed,
        'pushed': pushed,
        'commit_output': commit_out,
        'push_output': push_out,
        'status': get_git_status(proj),
    }


def pull_project(project: Path, branch: str | None = None) -> dict:
    proj = _assert_isolated_project_dir(project)
    if not (proj / '.git').is_dir():
        raise RuntimeError('Initialize and connect the project artifacts Git repository first.')
    st = get_git_status(proj)
    if not st['remote_url']:
        raise RuntimeError('No Git remote URL connected yet.')
    target_branch = _validate_branch(branch or st['branch'])
    res = _run_git(proj, ['pull', '--rebase', 'origin', target_branch], timeout=120)
    if res.returncode != 0:
        raise RuntimeError((res.stderr or res.stdout or 'git pull failed').strip())
    return {
        'pulled': True,
        'output': (res.stdout or res.stderr or 'Up to date').strip(),
        'status': get_git_status(proj),
    }
