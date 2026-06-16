import importlib.util as _ilu, pathlib as _pl
_f = _pl.Path(__file__).parents[3] / '.agents' / 'sync_erp' / 'sync_erp.py'
_s = _ilu.spec_from_file_location('_agent_sync_erp', _f)
_m = _ilu.module_from_spec(_s); _s.loader.exec_module(_m)
SyncERPAgent = _m.SyncERPAgent
