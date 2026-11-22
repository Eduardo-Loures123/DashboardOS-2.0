"""Executa a suíte; contorna exclusivamente um unittest/main.py vazio no host."""
from pathlib import Path
import sys, types, importlib.util, os

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
if not os.environ.get('DASHBOARD_TEST_WORKER'):
    from scripts.testar_suite_isolada import main
    sys.exit(main())
spec=importlib.util.find_spec('unittest')
main_file=Path(spec.origin).with_name('main.py')
if main_file.exists() and main_file.stat().st_size==0:
    print('Aviso: unittest/main.py vazio no Python instalado. Usando loader e runner padrão diretamente.')
    stub=types.ModuleType('unittest.main')
    def unavailable(*args,**kwargs):
        raise RuntimeError('A CLI unittest desta instalação está incompleta; use scripts/testar.py.')
    stub.TestProgram=stub.main=unavailable
    sys.modules['unittest.main']=stub
import unittest
suite=(unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:]) if len(sys.argv)>1
       else unittest.defaultTestLoader.discover(str(ROOT/'tests'),top_level_dir=str(ROOT)))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
