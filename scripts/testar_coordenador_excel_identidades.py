"""P4 synthetic XLSX/SQLite/anchor tests under the existing isolation guard."""
from pathlib import Path
from contextlib import redirect_stderr
import os
import sys
# openpyxl can import optional NumPy/OpenBLAS. Keep this synthetic runner small.
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.testar_persistencia_destinatarios import main

if __name__ == '__main__':
    with redirect_stderr(sys.stdout):
        raise SystemExit(main(suites=('tests.test_identity_excel_coordinator', 'tests.test_identity_excel_recovery')))
