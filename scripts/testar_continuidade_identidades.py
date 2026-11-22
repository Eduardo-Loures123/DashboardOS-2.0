"""P3 contract/failure tests under the synthetic-only SQLite/filesystem guard."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.testar_persistencia_destinatarios import main

if __name__ == '__main__':
    raise SystemExit(main(suites=('tests.test_continuity_anchor', 'tests.test_identity_recovery')))
