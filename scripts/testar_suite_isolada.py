"""Complete Python suite in separate processes, with synthetic disposable data.

Never imports app in the controller or reads the operational workbook. The runtime
temporary root is a sibling of the code copy: project paths remain non-runtime
paths even when the checkout copy itself is under the OS temporary directory.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]

BOOTSTRAP = r'''
from pathlib import Path
import os, sys, tempfile, platform, runpy
platform.uname()
root = Path.cwd().resolve()
sys.path.insert(0, str(root))
tempfile.tempdir = os.environ['DASHBOARD_TEST_RUNTIME']
original = Path(os.environ['DASHBOARD_TEST_ORIGINAL']).resolve()
def guard(event, args):
    if event in {'socket.connect', 'socket.connect_ex', 'socket.getaddrinfo',
                 'socket.sendto', 'smtplib.connect', 'smtplib.send',
                 'subprocess.Popen', 'os.system'}:
        raise AssertionError('Test forbids network and child processes')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0])).resolve()
        if any(path.is_relative_to(original / name) for name in ('dados', 'instance', '.aws')):
            raise AssertionError('Original operational data forbidden')
    if event == 'sqlite3.connect':
        from urllib.parse import urlsplit
        from urllib.request import url2pathname
        value = str(args[0])
        if value == ':memory:': return
        if value.startswith('file:'):
            uri = urlsplit(value)
            if uri.netloc: raise AssertionError('Remote database forbidden')
            value = url2pathname(uri.path)
        path = Path(value).resolve()
        if not (path.is_relative_to(root) or path.is_relative_to(Path(tempfile.gettempdir()))):
            raise AssertionError('Non-test database forbidden')
sys.addaudithook(guard)
sys.argv = [str(root / 'scripts/review_worker.py'), *sys.argv[1:]]
runpy.run_path(sys.argv[0], run_name='__main__')
'''


def protected():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for name in ('dados', 'instance') for p in (ROOT / name).rglob('*') if p.is_file()}


def prepare(destination, revision=None):
    destination.mkdir()
    if revision:
        archive = subprocess.check_output(['git', 'archive', revision], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            for member in source.getmembers():
                target = (destination / member.name).resolve()
                if not target.is_relative_to(destination.resolve()) or not member.isfile():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.extractfile(member).read())
    else:
        source_extensions = {'.py', '.cjs', '.js', '.html', '.css', '.svg', '.png',
                             '.webmanifest', '.md', '.txt', '.example', '.sh',
                             '.service', '.timer', '.conf'}
        def source_only(folder, names):
            return [name for name in names
                    if name in {'__pycache__', 'fixtures', 'instance', 'dados', '.aws', '.git'}
                    or (Path(folder, name).is_file()
                        and Path(name).suffix.lower() not in source_extensions)]
        for name in ('services', 'scripts', 'tests', 'static', 'templates', 'deployment'):
            shutil.copytree(ROOT / name, destination / name,
                            ignore=source_only)
        for name in ('app.py', 'VERSION', 'requirements.txt'):
            shutil.copy2(ROOT / name, destination / name)
    # Use the existing generator, writing exclusively fictional data in the copy.
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    subprocess.run([sys.executable, '-c',
                    "from scripts.gerar_dados import gerar; from pathlib import Path; "
                    "Path('dados').mkdir(exist_ok=True); gerar(Path('dados/dados_dashboard.xlsx'))"],
                   cwd=destination, env=env, check=True, stdout=subprocess.DEVNULL)
    (destination / 'scripts/review_worker.py').write_text(
        (ROOT / 'scripts/testar.py').read_text(encoding='utf-8'), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('names', nargs='*', help='Fully qualified unittest modules or methods')
    parser.add_argument('--revision', help='Read-only Git snapshot, for baseline comparison')
    parser.add_argument('--individual-failures', type=Path, help='Run each unique recorded failing method separately')
    args = parser.parse_args(argv)
    before = protected()
    directory = Path(tempfile.mkdtemp(prefix='dashboardos-python-review-')).resolve()
    code = directory / 'code'
    prepare(code, args.revision)
    # Historical application/test files stay unchanged. The same selector-aware
    # harness is injected into the disposable copy for comparable revision runs.
    bootstrap = directory / 'worker.py'
    bootstrap.write_text(BOOTSTRAP, encoding='utf-8')
    names = args.names or ['tests.' + p.stem for p in sorted((code / 'tests').glob('test_*.py'))]
    if args.individual_failures:
        names = sorted({entry['id'] for entry in json.loads(args.individual_failures.read_text(encoding='utf-8'))})
    outcomes = {}
    print('Artifacts:', directory, flush=True)
    try:
        for index, name in enumerate(names):
            runtime = directory / ('runtime-' + str(index)); runtime.mkdir()
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith('DASHBOARD_') and k != 'SECRET_KEY'}
            env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
                       DASHBOARD_ENV='development', DASHBOARD_MAIL_ENABLED='false',
                       DASHBOARD_EMAIL_SUSPENDED='true', DASHBOARD_TEST_WORKER='1',
                       DASHBOARD_TEST_RUNTIME=str(runtime), DASHBOARD_TEST_ORIGINAL=str(ROOT),
                       TMP=str(runtime), TEMP=str(runtime))
            # Isolate global app construction as well as individual test stores.
            with (directory / (name + '.log')).open('w', encoding='utf-8') as log:
                result = subprocess.run([sys.executable, '-B', str(bootstrap), name],
                                        cwd=code, env=env, stdout=log, stderr=subprocess.STDOUT)
            outcomes[name] = result.returncode
            print(name, 'PASS' if result.returncode == 0 else 'FAIL', flush=True)
    finally:
        unchanged = before == protected()
        (directory / 'result.json').write_text(json.dumps(dict(outcomes=outcomes,
            protected_unchanged=unchanged, protected_files=len(before)), indent=2), encoding='utf-8')
        print('Protected unchanged:', unchanged, flush=True)
    return 0 if unchanged and outcomes and all(value == 0 for value in outcomes.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
