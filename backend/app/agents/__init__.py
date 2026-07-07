"""
Carrega agentes de .agents/{nome}/{nome}.py via importlib e os registra
em sys.modules como app.agents.{nome} — sem arquivos duplicados aqui.
"""
import importlib.util
import pathlib
import sys

# .agents/ fica DENTRO de backend/ para entrar no build context do Docker
# (dockerContext: ./backend). __file__ = backend/app/agents/__init__.py →
# parents[2] = backend/ → backend/.agents. No container: /app/.agents.
_AGENTS_ROOT = pathlib.Path(__file__).parents[2] / '.agents'
_SKIP = {'skills'}


def _load(name: str):
    f = _AGENTS_ROOT / name / f'{name}.py'
    if not f.exists():
        return
    full = f'app.agents.{name}'
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, f)
    mod = importlib.util.module_from_spec(spec)
    try:
        sys.modules[full] = mod
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(full, None)
        raise
    return mod


if _AGENTS_ROOT.is_dir():
    for _d in sorted(_AGENTS_ROOT.iterdir()):
        if _d.is_dir() and not _d.name.startswith('.') and _d.name not in _SKIP:
            _load(_d.name)
