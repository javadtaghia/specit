from pathlib import Path
BASE=Path(__file__).resolve().parent.parent/'prompts'
def load(name):return (BASE/f'{name}.md').read_text(encoding='utf-8')
