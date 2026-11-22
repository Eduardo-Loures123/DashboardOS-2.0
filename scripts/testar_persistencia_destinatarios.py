"""3C.2A: SQLite/files confined to a disposable synthetic root; no app or network."""
from pathlib import Path
import importlib.util
import os
import sqlite3
import sys
import tempfile
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(*, suites=None):
    spec = importlib.util.find_spec('unittest')
    main_file = Path(spec.origin).with_name('main.py')
    if main_file.exists() and main_file.stat().st_size == 0:
        stub = types.ModuleType('unittest.main')
        def unavailable(*args, **kwargs): raise RuntimeError('Use this isolated runner')
        stub.TestProgram = stub.main = unavailable
        sys.modules['unittest.main'] = stub
    import unittest
    # Only this empty synthetic directory is created before installing guards.
    with tempfile.TemporaryDirectory(prefix='dashboardos-3c2a-synthetic-') as temporary:
        isolated = Path(temporary).resolve()
        previous_tempdir = tempfile.tempdir
        tempfile.tempdir = str(isolated)

        def inside(value):
            if not isinstance(value, (str, bytes, os.PathLike)):
                return False
            return Path(os.fsdecode(value)).resolve().is_relative_to(isolated)

        def guard(event, args):
            if event in {'socket.connect', 'socket.getaddrinfo', 'socket.bind', 'socket.sendto',
                         'smtplib.connect', 'smtplib.send', 'subprocess.Popen', 'os.system',
                         'os.posix_spawn', 'os.spawn', 'os.exec', 'os.startfile'}:
                raise AssertionError('Network/process forbidden: ' + event)
            if event == 'import' and args[0] in {'app', 'flask', 'services.auth_service', 'services.mail_service',
                                                'services.excel_service', 'services.import_routes',
                                                'services.enterprise_routes', 'services.import_coordinator'}:
                raise AssertionError('Operational import forbidden: ' + args[0])
            if event == 'sqlite3.connect' and not inside(args[0]):
                raise AssertionError('Database outside synthetic root forbidden')
            if event == 'open':
                path, mode, flags = args
                writing = bool(mode and any(c in mode for c in 'wax+')) or flags & (
                    os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
                if writing and not inside(path):
                    raise AssertionError('Write outside synthetic root forbidden')
                if isinstance(path, (str, bytes, os.PathLike)):
                    candidate = Path(os.fsdecode(path)).resolve()
                    if any(candidate.is_relative_to(ROOT / directory) for directory in ('instance', 'dados')):
                        raise AssertionError('Real data access forbidden')
            if event in {'os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod', 'os.chown', 'os.utime', 'os.truncate'}:
                if not inside(args[0]): raise AssertionError('Mutation outside synthetic root forbidden')
            if event in {'os.rename', 'os.link', 'os.symlink', 'shutil.copyfile'}:
                if not inside(args[0]) or not inside(args[1]):
                    raise AssertionError('Move/copy outside synthetic root forbidden')

        original_connect = sqlite3.connect
        def connect(*args, **kwargs):
            if not inside(args[0] if args else kwargs.get('database')):
                raise AssertionError('Database outside synthetic root forbidden')
            db = original_connect(*args, **kwargs)
            db.enable_load_extension(False)
            def authorize(action, first, second, database, source):
                if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH): return sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_FUNCTION and second == 'load_extension': return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            db.set_authorizer(authorize)
            return db

        sys.addaudithook(guard)
        sqlite3.connect = connect
        try:
            class IsolationGuards(unittest.TestCase):
                def test_real_database_read_write_import_and_network_blocked(self):
                    import socket
                    for path in (ROOT / 'instance/auth.sqlite3', ROOT / 'dados/dados_dashboard.xlsx'):
                        with self.assertRaisesRegex(AssertionError, 'Real data access'):
                            with open(path, 'rb'): pass
                    with self.assertRaisesRegex(AssertionError, 'Database outside'):
                        sqlite3.connect(ROOT / 'instance/auth.sqlite3')
                    with self.assertRaisesRegex(AssertionError, 'Write outside'):
                        with open(ROOT / 'tests/never-created-3c2a.txt', 'w'): pass
                    with self.assertRaisesRegex(AssertionError, 'Operational import'):
                        __import__('app')
                    with self.assertRaisesRegex(AssertionError, 'Operational import'):
                        __import__('services.excel_service')
                    with self.assertRaisesRegex(AssertionError, 'Network/process'):
                        socket.getaddrinfo('example.test', 25)

                def test_attach_and_extension_are_blocked(self):
                    db = sqlite3.connect(isolated / 'guard-test.sqlite3')
                    try:
                        with self.assertRaises(sqlite3.DatabaseError):
                            db.execute("ATTACH DATABASE ':memory:' AS forbidden")
                        with self.assertRaises(sqlite3.DatabaseError):
                            db.execute("SELECT load_extension('nonexistent')")
                    finally: db.close()

            suite = unittest.defaultTestLoader.loadTestsFromTestCase(IsolationGuards)
            suite.addTests(unittest.defaultTestLoader.loadTestsFromNames(suites if suites is not None else (
                'tests.test_operational_events', 'tests.test_notification_recipients',
                'tests.test_email_recipient_policy', 'tests.test_email_recipient_persistence')))
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            return 0 if result.wasSuccessful() else 1
        finally:
            sqlite3.connect = original_connect
            tempfile.tempdir = previous_tempdir


if __name__ == '__main__':
    raise SystemExit(main())
