from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = 'SPECiT'
APP_SHORT = 'Si'
APP_VERSION = '0.1.0-beta'
APP_STAGE = 'Beta'
APP_LICENSE = 'MIT'
APP_REPO_URL = 'https://github.com/javadtaghia/specit'


def is_frozen() -> bool:
    return bool(getattr(sys, 'frozen', False))


def resource_root() -> Path:
    """Return the root directory containing bundled read-only assets (web/, prompts/, examples/)."""
    if is_frozen() and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def default_workspace_root() -> Path:
    """Return the writable workspace root directory."""
    env_override = os.environ.get('SPECIT_WORKSPACE', '').strip()
    if env_override:
        return Path(env_override).expanduser().resolve()
    if is_frozen():
        return (Path.home() / 'Documents' / 'SPECiT' / 'workspace').resolve()
    return Path('workspace').resolve()
