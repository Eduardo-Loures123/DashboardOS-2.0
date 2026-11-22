"""Run P5-A integration tests without operational app or actual network access."""
import importlib.util
import platform
from pathlib import Path
import sys
import tempfile
import types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True


def main():
    platform.uname()
    spec=importlib.util.find_spec('unittest')
    if Path(spec.origin).with_name('main.py').stat().st_size==0:
        stub=types.ModuleType('unittest.main');stub.TestProgram=stub.main=lambda *a,**k:None
        sys.modules['unittest.main']=stub
    def guard(event,args):
        if event in {'socket.connect','socket.connect_ex','socket.sendto','socket.getaddrinfo',
                     'smtplib.connect','smtplib.send','subprocess.Popen','os.system'}:
            raise AssertionError('P5-A tests forbid network/processes')
        if event=='import' and args[0]=='app':raise AssertionError('Operational app import forbidden')
        if event=='sqlite3.connect':
            if not Path(str(args[0])).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
                raise AssertionError('Database outside temporary directory forbidden')
        if event=='open' and isinstance(args[0],(str,bytes)):
            p=Path(args[0]).resolve()
            if any(p.is_relative_to(ROOT/name) for name in ('dados','instance','.aws')):
                raise AssertionError('Real data access forbidden')
    sys.addaudithook(guard)
    import unittest
    suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_demo_notifications')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
