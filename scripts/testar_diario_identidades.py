"""P2 tests under the existing synthetic-SQLite filesystem/network guard."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.testar_persistencia_destinatarios import main

if __name__ == '__main__':
    raise SystemExit(main(suites=('tests.test_identity_operation_journal',)))
