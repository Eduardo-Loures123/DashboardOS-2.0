"""Executa a suíte; contorna exclusivamente um unittest/main.py vazio no host."""
from pathlib import Path
import sys, types, importlib.util

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
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
suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),top_level_dir=str(ROOT))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
