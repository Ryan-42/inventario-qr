import importlib.util as _ilu, pathlib as _pl
_f = _pl.Path(__file__).parents[3] / '.agents' / 'plano_acao' / 'plano_acao.py'
_s = _ilu.spec_from_file_location('_agent_plano_acao', _f)
_m = _ilu.module_from_spec(_s); _s.loader.exec_module(_m)
PlanoAcaoAgent = _m.PlanoAcaoAgent
