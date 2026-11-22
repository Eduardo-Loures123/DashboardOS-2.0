"""P5-A standalone launcher. No operational application, worker or real data."""
import argparse
import os
import platform
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=5095)
    parser.add_argument('--retomar',type=Path,help='Retoma somente um diretório temporário P5-A existente.')
    args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('Use uma porta entre 1024 e 65535.')
    directory=args.retomar.resolve() if args.retomar else Path(tempfile.mkdtemp(prefix='dashboardos-p5a-'))
    # Validate before installing process restrictions or importing application libraries.
    if (not directory.is_relative_to(Path(tempfile.gettempdir()).resolve())
            or not directory.name.startswith('dashboardos-p5a-') or not directory.is_dir()
            or any(p.is_symlink() for p in (directory,*directory.parents))):
        parser.error('A retomada exige um diretório temporário P5-A, sem links.')
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    os.environ['DASHBOARD_MAIL_ENABLED']='false'
    os.environ['OPENBLAS_NUM_THREADS']='1'
    # Cache read-only OS identification before the process guard (pandas uses it).
    platform.uname()
    # openpyxl uses NamedTemporaryFile internally; confine those files as well.
    os.environ['TMP']=str(directory);os.environ['TEMP']=str(directory)
    tempfile.tempdir=str(directory)
    from services.demo_guard import install_demo_guard
    install_demo_guard(directory,ROOT,args.port)
    from services.demo_notifications import DemoNotifications
    if not args.retomar:DemoNotifications(directory).initialize()
    elif not (directory/'demo.sqlite3').is_file() or not (directory/'witness.json').is_file():
        parser.error('Provas incompletas; não será feita reinicialização automática.')
    from services.demo_web import create_demo_app
    app=create_demo_app(directory)
    print('AMBIENTE DE DEMONSTRAÇÃO — fictício, isolado, sem SMTP ou AWS',flush=True)
    print('Diretório para retomada:',directory,flush=True)
    print(f'Acesse http://127.0.0.1:{args.port} • Ctrl+C para encerrar.',flush=True)
    app.run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False,threaded=True)


if __name__=='__main__':main()
