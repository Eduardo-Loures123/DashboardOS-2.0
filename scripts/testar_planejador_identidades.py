"""P1: in-memory tests; no filesystem writes, database, network or operational imports."""
from pathlib import Path
import importlib.util
import sys
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    # Same host workaround used by the existing isolated test runner.
    spec = importlib.util.find_spec('unittest')
    path = Path(spec.origin).with_name('main.py')
    if path.exists() and path.stat().st_size == 0:
        stub = types.ModuleType('unittest.main')
        def unavailable(*args, **kwargs): raise RuntimeError('Use this isolated runner')
        stub.TestProgram = stub.main = unavailable
        sys.modules['unittest.main'] = stub
    from scripts.testar_contrato_destinatarios import guard

    def pure_guard(event, args):
        guard(event, args)
        if event == 'import' and (args[0] in {
            'flask', 'services.excel_service', 'services.import_coordinator',
            'services.enterprise_service', 'services.email_recipient_repository',
            'services.email_recipient_schema', 'services.import_routes',
        } or args[0].startswith('flask.')):
            raise AssertionError('Operational import forbidden: ' + args[0])

    sys.addaudithook(pure_guard)
    import unittest

    class IsolationGuards(unittest.TestCase):
        def test_real_reads_writes_databases_and_network_blocked(self):
            import sqlite3
            import socket
            for path in (ROOT / 'dados/dados_dashboard.xlsx', ROOT / 'instance/auth.sqlite3'):
                with self.assertRaisesRegex(AssertionError, 'Real operational data reads'):
                    with open(path, 'rb'): pass
            with self.assertRaisesRegex(AssertionError, 'Filesystem writes forbidden'):
                with open(ROOT / 'tests/never-created-p1.txt', 'w'): pass
            with self.assertRaisesRegex(AssertionError, 'sqlite3.connect'):
                sqlite3.connect(':memory:')
            with self.assertRaisesRegex(AssertionError, 'socket.getaddrinfo'):
                socket.getaddrinfo('example.test', 25)

        def test_app_and_operational_services_cannot_be_imported(self):
            for module in ('app', 'flask', 'services.auth_service', 'services.excel_service',
                           'services.import_coordinator', 'services.enterprise_service',
                           'services.email_recipient_repository', 'services.mail_service'):
                with self.subTest(module=module), self.assertRaises(AssertionError):
                    __import__(module)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(IsolationGuards)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromName('tests.test_identity_planner'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
