"""Pacote de código por lista explícita; nunca inclui dados persistentes."""
from pathlib import Path
import hashlib
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT.parent / ('DashboardOS_2.0_' + (ROOT/'VERSION').read_text().strip() + '_codigo.tar.gz')
TOP = 'DashboardOS_2.0'
DIRECTORIES = {'services': {'.py'}, 'templates': {'.html'}, 'static': {'.css', '.js', '.svg', '.png', '.webmanifest'}}
DEPLOYMENT = {
    'dashboardos.env.example', 'requirements.txt', 'gunicorn.conf.py',
    'build_package.py', 'preflight_existente.py', 'backup_existente.py', 'ATUALIZAR_EXISTENTE.md',
}
EXCLUDED_SERVICES = {
    'demo_guard', 'demo_notifications', 'demo_web', 'email_recipient_policy',
    'email_recipient_repository', 'email_recipient_schema', 'notification_recipients',
    'continuity_anchor', 'identity_recovery', 'identity_planner', 'identity_operation_schema',
    'identity_operation_journal', 'identity_excel_recovery', 'identity_excel_coordinator',
}



def selected_files():
    files = [ROOT/'app.py', ROOT/'requirements.txt', ROOT/'VERSION', ROOT/'CHANGELOG.md', ROOT/'RELATORIO_PREPARACAO_EC2.md']
    for folder, extensions in DIRECTORIES.items():
        for path in sorted((ROOT/folder).rglob('*')):
            if (path.is_file() and path.suffix in extensions and '__pycache__' not in path.parts
                    and path.stem not in EXCLUDED_SERVICES and not path.stem.startswith(('demo_', 'demo-'))):
                files.append(path)
    files += [ROOT/'deployment/aws'/name for name in sorted(DEPLOYMENT)]
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f'Arquivo ausente ou link não permitido: {path}')
        if not path.resolve().is_relative_to(ROOT):
            raise RuntimeError('Arquivo fora do projeto')
    return files


def build():
    if OUTPUT.exists():
        raise RuntimeError('Pacote ja existe; preserve-o antes de gerar novamente.')
    files = selected_files()
    with tarfile.open(OUTPUT, 'w:gz') as archive:
        for path in files:
            name = TOP + '/' + path.relative_to(ROOT).as_posix()
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mode = 0o755 if path.suffix == '.sh' else 0o644
            with path.open('rb') as stream:
                archive.addfile(info, stream)
    with tarfile.open(OUTPUT, 'r:gz') as archive:
        names = archive.getnames()
        expected = {TOP + '/' + p.relative_to(ROOT).as_posix() for p in files}
        assert len(names) == len(expected) and set(names) == expected
        for member in archive.getmembers():
            assert member.isfile() and not member.name.startswith('/')
            assert '..' not in Path(member.name).parts
            assert member.name.endswith('.env.example') or '/.env' not in member.name
            assert not set(Path(member.name).parts) & {'.git', '.venv', 'node_modules', '__pycache__', 'dados', 'instance'}
            assert Path(member.name).suffix.lower() not in {'.xlsx', '.xls', '.sqlite3', '.db', '.pem', '.key', '.pyc'}
            relative = Path(member.name).relative_to(TOP)
            assert archive.extractfile(member).read() == (ROOT/relative).read_bytes()
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    OUTPUT.with_suffix(OUTPUT.suffix+'.sha256').write_text(digest+'  '+OUTPUT.name+'\n', encoding='ascii')
    print(f'{OUTPUT}\n{len(files)} arquivos; {OUTPUT.stat().st_size} bytes\nSHA256: {digest}')


if __name__ == '__main__':
    build()
