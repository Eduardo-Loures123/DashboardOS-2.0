"""Run only pure 3A/3B/3C.1 tests; forbid writes, DBs, network and application imports."""
from pathlib import Path
import importlib.util
import os
import sys
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def guard(event, args):
    forbidden = {
        'sqlite3.connect', 'socket.connect', 'socket.connect_ex', 'socket.getaddrinfo',
        'socket.bind', 'socket.sendto', 'smtplib.connect', 'smtplib.send',
        'subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.spawn',
        'os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.link', 'os.symlink',
        'os.truncate', 'os.chmod', 'os.chown', 'os.utime', 'shutil.copyfile',
    }
    if event in forbidden:
        raise AssertionError('Pure test runner forbids: ' + event)
    if event == 'import' and (args[0] == 'app' or args[0] in {
            'services.auth_service', 'services.mail_service', 'services.enterprise_routes'}):
        raise AssertionError('Application/delivery import forbidden: ' + args[0])
    if event == 'open':
        path, mode, flags = args
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        if (mode and any(c in mode for c in 'wax+')) or flags & write_flags:
            raise AssertionError('Filesystem writes forbidden by pure test runner')
        if isinstance(path, (str, bytes, os.PathLike)):
            candidate = Path(os.fsdecode(path)).resolve()
            if candidate.is_relative_to(ROOT / 'dados') or candidate.is_relative_to(ROOT / 'instance'):
                raise AssertionError('Real operational data reads forbidden by pure test runner')


def main():
    # The host's unittest/main.py may be empty. Use the standard loader/runner.
    spec = importlib.util.find_spec('unittest')
    main_file = Path(spec.origin).with_name('main.py')
    if main_file.exists() and main_file.stat().st_size == 0:
        stub = types.ModuleType('unittest.main')
        def unavailable(*args, **kwargs):
            raise RuntimeError('Use scripts/testar_contrato_destinatarios.py')
        stub.TestProgram = stub.main = unavailable
        sys.modules['unittest.main'] = stub
    sys.addaudithook(guard)
    import unittest

    class IsolationGuards(unittest.TestCase):
        def test_write_database_network_and_application_guards(self):
            import sqlite3
            import socket
            with self.assertRaisesRegex(AssertionError, 'writes forbidden'):
                with open(ROOT / 'tests' / 'must-never-be-created.txt', 'w'): pass
            with self.assertRaisesRegex(AssertionError, 'sqlite3.connect'):
                sqlite3.connect(':memory:')
            with self.assertRaisesRegex(AssertionError, 'socket.getaddrinfo'):
                socket.getaddrinfo('example.test', 25)
            with self.assertRaisesRegex(AssertionError, 'Application/delivery import forbidden'):
                __import__('app')

        def test_real_operational_data_cannot_be_read(self):
            for path in (ROOT / 'instance/auth.sqlite3', ROOT / 'dados/dados_dashboard.xlsx'):
                with self.assertRaisesRegex(AssertionError, 'Real operational data reads forbidden'):
                    with open(path, 'rb'): pass

    names = ('tests.test_operational_events', 'tests.test_notification_recipients',
             'tests.test_email_recipient_policy')
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(IsolationGuards)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromNames(names))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
