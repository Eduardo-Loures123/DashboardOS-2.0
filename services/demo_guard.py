"""Process-wide restrictions for the standalone P5-A launcher; never installed by app.py."""
import os
from pathlib import Path
import sys


def install_demo_guard(directory, project, port):
    directory, project = Path(directory).resolve(), Path(project).resolve()
    forbidden = [project / name for name in ('instance', 'dados', '.aws', '.git')]

    def inside(path, parent):
        return path == parent or parent in path.parents

    def guard(event, args):
        if event in {'subprocess.Popen', 'os.system', 'os.posix_spawn', 'smtplib.connect',
                     'smtplib.send', 'socket.connect', 'socket.connect_ex', 'socket.sendto',
                     'sqlite3.load_extension'}:
            raise PermissionError('P5-A: rede externa, SMTP e processos bloqueados.')
        if event == 'socket.getaddrinfo' and args[0] != '127.0.0.1':
            raise PermissionError('P5-A: DNS externo bloqueado.')
        if event == 'socket.bind' and args[1] != ('127.0.0.1', port):
            raise PermissionError('P5-A: somente servidor local na porta autorizada.')
        if event == 'sqlite3.connect':
            value = str(args[0])
            if value.startswith('file:') or not inside(Path(value).resolve(), directory):
                raise PermissionError('P5-A: banco fora da demonstração bloqueado.')
        if event == 'open':
            value, mode, flags = args
            if not isinstance(value, (str, bytes, os.PathLike)):
                return
            path = Path(os.fsdecode(value)).resolve()
            if any(inside(path, p) for p in forbidden) or '.aws' in path.parts or path.name == '.env':
                raise PermissionError('P5-A: dados e credenciais reais bloqueados.')
            writing = bool(mode and any(c in mode for c in 'wax+')) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing and not inside(path, directory):
                raise PermissionError('P5-A: escrita fora da demonstração bloqueada.')
        if event in {'os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod', 'os.utime', 'os.truncate'}:
            if not inside(Path(args[0]).resolve(), directory):
                raise PermissionError('P5-A: alteração fora da demonstração bloqueada.')
        if event in {'os.rename', 'os.link', 'os.symlink', 'shutil.copyfile'}:
            if any(not inside(Path(p).resolve(), directory) for p in args[:2]):
                raise PermissionError('P5-A: movimentação fora da demonstração bloqueada.')

    sys.addaudithook(guard)
