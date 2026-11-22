"""Offline notifications tests. Never import the Flask app with its real database."""
from pathlib import Path
import argparse
from contextlib import redirect_stderr
import importlib.util
import os
import runpy
import shutil
import sys
import tempfile
import types
from urllib.parse import urlsplit
from urllib.request import url2pathname

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--completo', action='store_true', help='Run the full Python suite, also offline.')
    parser.add_argument('--suite', help='Run one named unittest module under the same isolation.')
    parser.add_argument('--frontend-fixtures', action='store_true', help='Generate DOM fixtures in isolation.')
    args = parser.parse_args()
    # Work around the incomplete unittest.main in this host installation.
    spec = importlib.util.find_spec('unittest')
    main_file = Path(spec.origin).with_name('main.py')
    if main_file.exists() and main_file.stat().st_size == 0:
        stub = types.ModuleType('unittest.main')
        def unavailable(*a, **kw): raise RuntimeError('Use scripts/testar_notificacoes.py.')
        stub.TestProgram = stub.main = unavailable
        sys.modules['unittest.main'] = stub
    import unittest
    from unittest.mock import patch

    with tempfile.TemporaryDirectory(prefix='dashboardos-offline-bootstrap-') as temp:
        temporary_root = Path(temp).resolve()
        # Deny actual networking, including SMTP, before importing application code.
        def guard(event, arguments):
            if event in ('socket.connect', 'socket.getaddrinfo', 'smtplib.send'):
                raise AssertionError('Network forbidden by offline test runner')
            if event == 'sqlite3.connect':
                location = str(arguments[0])
                if location == ':memory:': return
                # All test databases must be under the OS temporary directory.
                if location.startswith('file:'):
                    uri=urlsplit(location)
                    if uri.netloc: raise AssertionError('Remote database URI forbidden')
                    location=url2pathname(uri.path)
                if not Path(location).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
                    raise AssertionError('Database outside temporary test directory forbidden')
        sys.addaudithook(guard)
        # Legacy tests copy the main Excel by convention. Redirect that source to
        # a freshly generated fictional workbook; never import principal records.
        from scripts.gerar_dados import gerar
        fictional_book = temporary_root / 'fictional-source.xlsx'
        gerar(fictional_book)
        principal_book = (ROOT / 'dados/dados_dashboard.xlsx').resolve()
        original_copy = shutil.copy2
        def isolated_copy(source, destination, *a, **kw):
            if Path(source).resolve() == principal_book:
                source = fictional_book
            return original_copy(source, destination, *a, **kw)
        previous = {key: os.environ.get(key) for key in ('DASHBOARD_AUTH_DIRECTORY', 'DASHBOARD_EXCEL_PATH', 'DASHBOARD_ENV', 'DASHBOARD_MAIL_ENABLED')}
        try:
            os.environ.update(DASHBOARD_AUTH_DIRECTORY=str(temporary_root / 'instance'),
                              DASHBOARD_EXCEL_PATH=str(temporary_root / 'bootstrap.xlsx'),
                              DASHBOARD_ENV='development', DASHBOARD_MAIL_ENABLED='false')
            import app  # Its global app now initializes only an empty temporary DB.
            del os.environ['DASHBOARD_AUTH_DIRECTORY']
            del os.environ['DASHBOARD_EXCEL_PATH']
            with patch('shutil.copy2', isolated_copy):
                if args.frontend_fixtures:
                    runpy.run_path(str(ROOT / 'scripts/preparar_testes_frontend.py'), run_name='__main__')
                    return 0
                if args.suite:
                    suite = unittest.defaultTestLoader.loadTestsFromName(args.suite)
                elif args.completo:
                    with redirect_stderr(sys.stdout):
                        runpy.run_path(str(ROOT / 'scripts/testar.py'), run_name='__main__')
                else:
                    suite = unittest.defaultTestLoader.loadTestsFromNames([
                        'tests.test_profile_redesign', 'tests.test_notification_recipients', 'tests.test_operational_events',
                        'tests.test_notification_pipeline', 'tests.test_smtp_transport'])
                result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
                return 0 if result.wasSuccessful() else 1
        finally:
            for key, value in previous.items():
                if value is None: os.environ.pop(key, None)
                else: os.environ[key] = value


if __name__ == '__main__':
    raise SystemExit(main())
