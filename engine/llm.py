"""Unified LLM client supporting paid subscriptions (Copilot, Claude, Gemini, OpenAI Codex CLIs)
and direct API providers (OpenAI, Anthropic, Google Gemini, GitHub Models).
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests
from pydantic import BaseModel, ValidationError


PROVIDER_CATALOG = [
    {
        'id': 'copilot_cli',
        'label': 'GitHub Copilot Subscription (CLI)',
        'kind': 'subscription',
        'binary': 'copilot',
        'default_model': 'auto',
        'models': ['auto', 'claude-sonnet-4.6', 'claude-opus-4.6', 'gpt-5.4', 'gpt-4.1', 'gemini-2.5-pro'],
        'needs_key': False,
        'needs_url': False,
        'help': 'Uses your authenticated `copilot` CLI subscription (run `copilot login` if needed).',
    },
    {
        'id': 'claude_cli',
        'label': 'Claude Pro / Max Subscription (Claude Code CLI)',
        'kind': 'subscription',
        'binary': 'claude',
        'default_model': 'sonnet',
        'models': ['sonnet', 'opus', 'haiku'],
        'needs_key': False,
        'needs_url': False,
        'help': 'Uses your authenticated `claude` CLI subscription with native --json-schema structured output.',
    },
    {
        'id': 'gemini_cli',
        'label': 'Google Gemini Subscription (Gemini CLI)',
        'kind': 'subscription',
        'binary': 'gemini',
        'default_model': 'auto',
        'models': ['auto', 'gemini-2.5-pro', 'gemini-2.5-flash'],
        'needs_key': False,
        'needs_url': False,
        'help': 'Uses your authenticated `gemini` CLI subscription.',
    },
    {
        'id': 'codex_cli',
        'label': 'OpenAI / ChatGPT Subscription (Codex CLI)',
        'kind': 'subscription',
        'binary': 'codex',
        'default_model': 'default',
        'models': ['default', 'gpt-5.4', 'gpt-5.3-codex', 'o3', 'gpt-4.1'],
        'needs_key': False,
        'needs_url': False,
        'help': 'Uses your authenticated `codex` CLI subscription (`codex exec --ephemeral -s read-only`).',
    },
    {
        'id': 'openai_api',
        'label': 'OpenAI API (API Key)',
        'kind': 'api',
        'env_key': 'OPENAI_API_KEY',
        'default_url': 'https://api.openai.com',
        'default_model': 'gpt-4.1',
        'models': ['gpt-4.1', 'gpt-4.1-mini', 'gpt-4o', 'o3-mini'],
        'needs_key': True,
        'needs_url': True,
        'help': 'Uses OPENAI_API_KEY environment variable or API key entered below.',
    },
    {
        'id': 'anthropic_api',
        'label': 'Anthropic Claude API (API Key)',
        'kind': 'api',
        'env_key': 'ANTHROPIC_API_KEY',
        'default_url': 'https://api.anthropic.com',
        'default_model': 'claude-sonnet-4-20250514',
        'models': ['claude-sonnet-4-20250514', 'claude-opus-4-20250514', 'claude-3-7-sonnet-latest'],
        'needs_key': True,
        'needs_url': True,
        'help': 'Uses ANTHROPIC_API_KEY environment variable or API key entered below.',
    },
    {
        'id': 'gemini_api',
        'label': 'Google Gemini API (API Key)',
        'kind': 'api',
        'env_key': 'GEMINI_API_KEY',
        'default_url': 'https://generativelanguage.googleapis.com',
        'default_model': 'gemini-2.5-pro',
        'models': ['gemini-2.5-pro', 'gemini-2.5-flash'],
        'needs_key': True,
        'needs_url': True,
        'help': 'Uses GEMINI_API_KEY environment variable or API key entered below.',
    },
    {
        'id': 'github_models',
        'label': 'GitHub Models API (GitHub Token / gh auth)',
        'kind': 'api',
        'env_key': 'GITHUB_TOKEN',
        'default_url': 'https://models.inference.ai.azure.com',
        'default_model': 'gpt-4.1',
        'models': ['gpt-4.1', 'gpt-4o', 'o3-mini', 'DeepSeek-R1'],
        'needs_key': False,
        'needs_url': True,
        'help': 'Uses GITHUB_TOKEN, entered token, or automatically reads `gh auth token` from your GitHub login.',
    },
]


def _check_cli_usable(binary: str) -> tuple[bool, str]:
    path = shutil.which(binary)
    if not path:
        return False, ''
    # Verify shims actually resolve to a real executable
    try:
        r = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=5)
        out = (r.stdout or r.stderr or '').strip()
        if r.returncode != 0 and 'not found in PATH' in out:
            return False, ''
        return True, path
    except Exception:
        return True, path


def _read_json_safe(path: Path) -> dict:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8', errors='ignore'))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _discover_local_models(provider_id: str, fallback_default: str, fallback_models: list[str]) -> tuple[str, list[str]]:
    """Discover the user's real configured model and cached available models from local CLI config files (never reads secrets)."""
    home = Path.home()
    found_default = ''
    found_models: list[str] = []

    if provider_id == 'codex_cli':
        cfg = home / '.codex' / 'config.toml'
        if cfg.exists():
            try:
                txt = cfg.read_text(encoding='utf-8', errors='ignore')
                m = re.search(r'^\s*model\s*=\s*["\']([^"\']+)["\']', txt, flags=re.MULTILINE)
                if m:
                    found_default = m.group(1).strip()
            except Exception:
                pass
        cache = _read_json_safe(home / '.codex' / 'models_cache.json')
        raw_models = cache.get('models', [])
        if isinstance(raw_models, list):
            for item in raw_models:
                slug = item.get('slug') if isinstance(item, dict) else (item if isinstance(item, str) else '')
                if slug and slug not in found_models:
                    found_models.append(slug)

    elif provider_id == 'claude_cli':
        settings = _read_json_safe(home / '.claude' / 'settings.json')
        m = settings.get('model')
        if isinstance(m, str) and m.strip():
            found_default = m.strip()
        found_models = ['opus', 'sonnet', 'haiku']

    elif provider_id == 'copilot_cli':
        cfg = _read_json_safe(home / '.copilot' / 'config.json')
        m = cfg.get('model')
        if isinstance(m, str) and m.strip():
            found_default = m.strip()
        found_models = list(fallback_models)

    elif provider_id == 'gemini_cli':
        settings = _read_json_safe(home / '.gemini' / 'settings.json')
        m = settings.get('model')
        if isinstance(m, dict):
            m = m.get('name') or m.get('default')
        if isinstance(m, str) and m.strip():
            found_default = m.strip()
        found_models = list(fallback_models)

    models = list(dict.fromkeys(([found_default] if found_default else []) + found_models + fallback_models))
    # Never advertise placeholder "default" when real models are discovered
    if len(models) > 1:
        models = [x for x in models if x != 'default']
    default_model = found_default or (models[0] if models else fallback_default)
    return default_model, models


def detect_providers() -> list[dict]:
    """Return provider catalogue annotated with local availability and live discovered models."""
    out = []
    gh_available = bool(shutil.which('gh'))
    for item in PROVIDER_CATALOG:
        entry = dict(item)
        if item['kind'] == 'subscription':
            ok, path = _check_cli_usable(item['binary'])
            entry['available'] = ok
            entry['detected_detail'] = path if ok else f"`{item['binary']}` CLI not found in PATH"
            if ok:
                cur_default, cur_models = _discover_local_models(item['id'], item['default_model'], list(item['models']))
                entry['default_model'] = cur_default
                entry['models'] = cur_models
        else:
            env_name = item.get('env_key', '')
            has_env = bool(os.environ.get(env_name))
            if item['id'] == 'github_models' and not has_env and gh_available:
                entry['available'] = True
                entry['detected_detail'] = 'GitHub CLI (`gh auth token`) available'
            else:
                entry['available'] = has_env
                entry['detected_detail'] = f'{env_name} set' if has_env else f'Provide key or set {env_name}'
        out.append(entry)
    return out


def _to_strict_openai_schema(schema: dict) -> dict | None:
    """Convert Pydantic JSON Schema to OpenAI strict subset, or None if open dict maps exist."""
    import copy

    s = copy.deepcopy(schema)

    def walk(node):
        if not isinstance(node, dict):
            return True
        if node.get('type') == 'object':
            if 'additionalProperties' in node and node['additionalProperties'] is not False:
                return False  # Open map (e.g. dict[str, str]) not allowed in strict mode
            props = node.get('properties', {})
            node['additionalProperties'] = False
            node['required'] = list(props.keys())
            for v in props.values():
                if not walk(v):
                    return False
        if 'items' in node and not walk(node['items']):
            return False
        for key in ('$defs', 'definitions'):
            if key in node and isinstance(node[key], dict):
                for v in node[key].values():
                    if not walk(v):
                        return False
        for key in ('anyOf', 'oneOf', 'allOf'):
            if key in node and isinstance(node[key], list):
                for v in node[key]:
                    if not walk(v):
                        return False
        return True

    return s if walk(s) else None


def _strip_outer_fences(text: str) -> str:
    """Strip ONLY an outer markdown code fence wrapping the entire response (never match inner ```mermaid blocks!)."""
    s = (text or '').strip()
    m = re.match(r'^```(?:json)?\s*\r?\n(.*)\r?\n```\s*$', s, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return s


def _unwrap_cli_envelope(parsed: dict) -> str | None:
    if 'structured_output' in parsed and isinstance(parsed['structured_output'], dict):
        return json.dumps(parsed['structured_output'], ensure_ascii=False)
    if 'result' in parsed and isinstance(parsed['result'], str):
        inner = extract_json_payload(parsed['result'])
        if inner:
            return inner
    if 'response' in parsed and isinstance(parsed['response'], str) and 'session_id' in parsed:
        inner = extract_json_payload(parsed['response'])
        if inner:
            return inner
    return None


def _parse_json_lenient(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text, strict=False)


def _extract_copilot_jsonl(raw_text: str) -> str | None:
    """Extract the final assistant message content from `copilot --output-format json` JSONL output."""
    last_content = None
    for line in (raw_text or '').splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(evt, dict) and evt.get('type') == 'assistant.message':
            content = (evt.get('data') or {}).get('content')
            if isinstance(content, str) and content.strip():
                last_content = content
    return last_content


def extract_json_payload(raw_text: str) -> str:
    """Extract the target JSON object from raw LLM or CLI envelope output without breaking embedded ```mermaid blocks."""
    raw = (raw_text or '').strip()
    if not raw:
        return ''

    # 0. Unwrap Copilot JSONL event stream if present
    copilot_content = _extract_copilot_jsonl(raw)
    if copilot_content is not None:
        raw = copilot_content.strip()

    # 1. Try direct JSON parse BEFORE touching any markdown fences (protects embedded ```mermaid blocks)
    for candidate in (raw, _strip_outer_fences(raw)):
        try:
            parsed = _parse_json_lenient(candidate)
            if isinstance(parsed, dict):
                unwrapped = _unwrap_cli_envelope(parsed)
                if unwrapped is not None:
                    return unwrapped
            return json.dumps(parsed, ensure_ascii=False)
        except json.JSONDecodeError:
            pass

    # 2. Find outermost balanced JSON object in prose-wrapped output (respecting JSON string escapes)
    cleaned = _strip_outer_fences(raw)
    pos = 0
    while True:
        start = cleaned.find('{', pos)
        if start == -1:
            break
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = cleaned[start:i + 1]
                        try:
                            parsed = _parse_json_lenient(candidate)
                            if isinstance(parsed, dict):
                                unwrapped = _unwrap_cli_envelope(parsed)
                                if unwrapped is not None:
                                    return unwrapped
                            return json.dumps(parsed, ensure_ascii=False)
                        except json.JSONDecodeError:
                            break
        pos = start + 1
    return cleaned


class LLMClient:
    def __init__(
        self,
        model: str = 'auto',
        url: str = '',
        timeout: int = 900,
        provider: str = 'copilot_cli',
        api_key: str = '',
        max_retries: int = 2,
    ):
        self.model = (model or '').strip()
        self.url = (url or '').rstrip('/')
        self.timeout = timeout
        self.provider = provider or 'copilot_cli'
        self.api_key = (api_key or '').strip()
        self.max_retries = max_retries

    def _resolve_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        env_map = {
            'openai_api': 'OPENAI_API_KEY',
            'anthropic_api': 'ANTHROPIC_API_KEY',
            'gemini_api': 'GEMINI_API_KEY',
            'github_models': 'GITHUB_TOKEN',
        }
        env_var = env_map.get(self.provider)
        if env_var and os.environ.get(env_var):
            return os.environ[env_var].strip()
        if self.provider == 'github_models' and shutil.which('gh'):
            r = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, timeout=8)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        return ''

    def test_connection(self) -> dict:
        meta = next((p for p in PROVIDER_CATALOG if p['id'] == self.provider), None)
        if not meta:
            return {'ok': False, 'message': f'Unknown provider: {self.provider}', 'models': []}

        if meta['kind'] == 'subscription':
            ok, path = _check_cli_usable(meta['binary'])
            cur_default, cur_models = _discover_local_models(meta['id'], meta['default_model'], list(meta['models']))
            if not ok:
                return {
                    'ok': False,
                    'message': f"`{meta['binary']}` CLI not found or not runnable in PATH.",
                    'default_model': cur_default,
                    'models': cur_models,
                }
            return {
                'ok': True,
                'message': f"Ready via subscription CLI (current model: {cur_default}).",
                'default_model': cur_default,
                'models': cur_models,
            }

        key = self._resolve_api_key()
        if not key:
            return {
                'ok': False,
                'message': f"Missing API key/token (enter one in Settings or set {meta.get('env_key', 'API key')}).",
                'default_model': meta['default_model'],
                'models': meta['models'],
            }
        live_models = list(meta['models'])
        try:
            if self.provider == 'openai_api':
                r = requests.get(f"{self.url or 'https://api.openai.com'}/v1/models", headers={'Authorization': f'Bearer {key}'}, timeout=8)
                if r.ok:
                    ids = sorted(x['id'] for x in r.json().get('data', []) if isinstance(x, dict) and x.get('id'))
                    if ids:
                        live_models = ids
            elif self.provider == 'gemini_api':
                r = requests.get(f"{self.url or 'https://generativelanguage.googleapis.com'}/v1beta/models?key={key}", timeout=8)
                if r.ok:
                    ids = [x['name'].replace('models/', '') for x in r.json().get('models', []) if isinstance(x, dict) and x.get('name')]
                    if ids:
                        live_models = ids
        except Exception:
            pass
        return {
            'ok': True,
            'message': f"Connected to {meta['label']} ({len(live_models)} models).",
            'default_model': live_models[0] if live_models else meta['default_model'],
            'models': live_models,
        }

    def models(self) -> list[str]:
        meta = next((p for p in PROVIDER_CATALOG if p['id'] == self.provider), None)
        return list(meta['models']) if meta else []

    def _run_cli(self, cmd: list[str], stdin_text: str) -> str:
        proc = subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or '').strip()[:1000]
            raise RuntimeError(f'CLI `{cmd[0]}` failed (exit {proc.returncode}): {err}')
        return proc.stdout

    def _call_provider(self, system: str, user: str, schema: dict) -> str:
        schema_str = json.dumps(schema, ensure_ascii=False)
        combined_prompt = (
            f'SYSTEM INSTRUCTIONS:\n{system}\n\n'
            f'REQUIRED JSON SCHEMA:\n{schema_str}\n\n'
            'CRITICAL: Return ONLY a single valid raw JSON object matching the schema above. '
            'No prose, no markdown fences, no tool calls.\n\n'
            f'TASK INPUT:\n{user}'
        )

        if self.provider == 'claude_cli':
            binary = shutil.which('claude')
            if not binary:
                raise RuntimeError('`claude` CLI not found. Install Claude Code and sign in with your Claude subscription.')
            cmd = [
                binary,
                '-p',
                '--output-format', 'json',
                '--json-schema', schema_str,
                '--system-prompt', system,
                '--tools', '',
                '--no-session-persistence',
            ]
            if self.model and self.model not in ('default', 'auto'):
                cmd.extend(['--model', self.model])
            return self._run_cli(cmd, user)

        if self.provider == 'copilot_cli':
            binary = shutil.which('copilot')
            if not binary:
                raise RuntimeError('`copilot` CLI not found. Install GitHub Copilot CLI and run `copilot login`.')
            # Use --output-format json (JSONL) so Copilot emits lossless assistant.message content without terminal line-wrapping
            cmd = [
                binary,
                '--output-format', 'json',
                '--silent',
                '--stream', 'off',
                '--no-ask-user',
                '--disable-builtin-mcps',
            ]
            if self.model and self.model not in ('default',):
                cmd.extend(['--model', self.model])
            return self._run_cli(cmd, combined_prompt)

        if self.provider == 'gemini_cli':
            binary = shutil.which('gemini')
            if not binary:
                raise RuntimeError('`gemini` CLI not found. Install Gemini CLI and authenticate with your Google account.')
            # Omit -p so Gemini CLI reads the full prompt cleanly from stdin; --skip-trust for headless mode
            cmd = [
                binary,
                '-o', 'json',
                '--skip-trust',
            ]
            if self.model and self.model not in ('default', 'auto'):
                cmd.extend(['-m', self.model])
            return self._run_cli(cmd, combined_prompt)

        if self.provider == 'codex_cli':
            ok, binary = _check_cli_usable('codex')
            if not ok:
                raise RuntimeError('`codex` CLI is not installed in PATH. Install OpenAI Codex CLI (`npm i -g @openai/codex`) and sign in with your ChatGPT subscription.')
            with tempfile.TemporaryDirectory() as tmp:
                out_file = Path(tmp) / 'output.json'
                cmd = [
                    binary,
                    'exec',
                    '--ephemeral',
                    '--skip-git-repo-check',
                    '-s', 'read-only',
                    '-o', str(out_file),
                ]
                strict_schema = _to_strict_openai_schema(schema)
                if strict_schema is not None:
                    schema_file = Path(tmp) / 'schema.json'
                    schema_file.write_text(json.dumps(strict_schema, ensure_ascii=False), encoding='utf-8')
                    cmd.extend(['--output-schema', str(schema_file)])
                if self.model and self.model not in ('default', 'auto'):
                    cmd.extend(['-m', self.model])
                cmd.append('-')
                stdout = self._run_cli(cmd, combined_prompt)
                return out_file.read_text(encoding='utf-8') if out_file.exists() else stdout

        if self.provider in ('openai_api', 'github_models'):
            key = self._resolve_api_key()
            if not key:
                raise RuntimeError(f'Missing API key/token for {self.provider}.')
            default_url = 'https://models.inference.ai.azure.com' if self.provider == 'github_models' else 'https://api.openai.com'
            base = self.url or default_url
            endpoint = f'{base}/chat/completions' if base.endswith('/v1') or 'inference.ai.azure.com' in base else f'{base}/v1/chat/completions'
            payload = {
                'model': self.model or 'gpt-4.1',
                'temperature': 0.1,
                'response_format': {'type': 'json_object'},
                'messages': [
                    {'role': 'system', 'content': system + f'\n\nReturn ONLY raw JSON matching this schema:\n{schema_str}'},
                    {'role': 'user', 'content': user},
                ],
            }
            r = requests.post(
                endpoint,
                headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json()['choices'][0]['message']['content']

        if self.provider == 'anthropic_api':
            key = self._resolve_api_key()
            if not key:
                raise RuntimeError('Missing ANTHROPIC_API_KEY.')
            base = self.url or 'https://api.anthropic.com'
            payload = {
                'model': self.model or 'claude-sonnet-4-20250514',
                'max_tokens': 8192,
                'temperature': 0.1,
                'system': system + f'\n\nReturn ONLY raw valid JSON matching this JSON Schema:\n{schema_str}',
                'messages': [{'role': 'user', 'content': user}],
            }
            r = requests.post(
                f'{base}/v1/messages',
                headers={
                    'x-api-key': key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            blocks = r.json().get('content', [])
            return '\n'.join(b.get('text', '') for b in blocks if b.get('type') == 'text')

        if self.provider == 'gemini_api':
            key = self._resolve_api_key()
            if not key:
                raise RuntimeError('Missing GEMINI_API_KEY.')
            base = self.url or 'https://generativelanguage.googleapis.com'
            model = self.model or 'gemini-2.5-pro'
            endpoint = f'{base}/v1beta/models/{model}:generateContent?key={key}'
            payload = {
                'systemInstruction': {'parts': [{'text': system + f'\n\nReturn ONLY raw valid JSON matching this JSON Schema:\n{schema_str}'}]},
                'contents': [{'role': 'user', 'parts': [{'text': user}]}],
                'generationConfig': {'temperature': 0.1, 'responseMimeType': 'application/json'},
            }
            r = requests.post(endpoint, json=payload, timeout=self.timeout)
            r.raise_for_status()
            parts = r.json()['candidates'][0]['content']['parts']
            return '\n'.join(p.get('text', '') for p in parts if 'text' in p)

        raise ValueError(f'Unsupported provider: {self.provider}')

    def ask(self, system: str, user: str, cls: type[BaseModel]):
        schema = cls.model_json_schema()
        current_user = user
        last_error = None
        last_raw = ''

        for attempt in range(self.max_retries + 1):
            raw = self._call_provider(system, current_user, schema)
            cleaned = extract_json_payload(raw)
            last_raw = cleaned
            try:
                return cls.model_validate_json(cleaned)
            except ValidationError as e:
                last_error = e
                if attempt < self.max_retries:
                    current_user = (
                        f'{user}\n\n'
                        f'CORRECTION REQUIRED: Your previous JSON failed schema validation:\n{e}\n'
                        f'Previous output excerpt:\n{cleaned[:2500]}\n'
                        'Return ONLY a valid raw JSON object conforming strictly to the schema.'
                    )

        raise ValueError(f'Model output failed schema validation: {last_error}\nRaw: {last_raw[:1500]}') from last_error


# Backward-compatible alias
LocalLLM = LLMClient
