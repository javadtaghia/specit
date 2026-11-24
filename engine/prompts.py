from .version import resource_root

BASE = resource_root() / 'prompts'


def load(name: str) -> str:
    return (BASE / f'{name}.md').read_text(encoding='utf-8')
