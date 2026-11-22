"""Exercise the actual P5-A process guard; all forbidden actions stop before I/O."""
from pathlib import Path
import platform
import sys
import tempfile
import types
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True


def main():
    platform.uname()
    spec=importlib.util.find_spec('unittest')
    if Path(spec.origin).with_name('main.py').stat().st_size==0:
        stub=types.ModuleType('unittest.main');stub.TestProgram=stub.main=lambda *a,**k:None
        sys.modules['unittest.main']=stub
    import unittest
    import socket
    import sqlite3
    import subprocess
    from services.demo_guard import install_demo_guard
    with tempfile.TemporaryDirectory(prefix='dashboardos-p5a-') as temporary:
        directory=Path(temporary)
        install_demo_guard(directory,ROOT,5095)
        class Guards(unittest.TestCase):
            def test_actual_data_and_aws_credentials_cannot_be_read(self):
                for path in (ROOT/'instance/auth.sqlite3',ROOT/'dados/dados_dashboard.xlsx',
                             ROOT/'.aws/credentials',ROOT/'.env'):
                    with self.assertRaises(PermissionError):path.read_bytes()

            def test_sqlite_cannot_open_principal_or_uri(self):
                for path in (ROOT/'instance/auth.sqlite3','file:demo.sqlite3?mode=ro'):
                    with self.assertRaises(PermissionError):sqlite3.connect(path)

            def test_outgoing_network_and_external_dns_are_blocked(self):
                with self.assertRaises(PermissionError):socket.getaddrinfo('example.test',587)
                with socket.socket() as sock:
                    with self.assertRaises(PermissionError):sock.connect(('127.0.0.1',587))
                    with self.assertRaises(PermissionError):sock.bind(('0.0.0.0',5095))

            def test_writes_and_subprocesses_cannot_escape(self):
                with self.assertRaises(PermissionError):(ROOT/'never-created-p5a.txt').write_text('blocked')
                with self.assertRaises(PermissionError):subprocess.run([sys.executable,'-c','pass'])

            def test_temporary_database_is_allowed_and_closed(self):
                db=sqlite3.connect(directory/'guard-test.sqlite3')
                try:db.execute('CREATE TABLE synthetic(id INTEGER)');db.commit()
                finally:db.close()
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Guards))
        return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
