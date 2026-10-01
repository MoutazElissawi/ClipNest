"""Stage a private CPython runtime and compile Inno Setup on Windows x64."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.5.1'
PUBLIC_FILES = ('main.py', 'bootstrap.py', 'Launch_ClipNest.pyw', 'Launch_ClipNest.vbs',
                'Start_ClipNest.bat', 'requirements.txt', 'LICENSE.txt', 'THIRD_PARTY.md', 'README.md')


def copy_public(destination, *, build_sources=True):
    destination.mkdir(parents=True, exist_ok=True)
    for name in PUBLIC_FILES:
        shutil.copy2(ROOT / name, destination / name)
    shutil.copytree(ROOT / 'clipnest', destination / 'clipnest',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    if build_sources:
        shutil.copytree(ROOT / 'packaging', destination / 'packaging',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copy2(ROOT / 'Build_Installer.bat', destination)


def copy_runtime(base, destination):
    required = [base / name for name in ('python.exe', 'pythonw.exe', 'Lib/os.py', 'DLLs', 'LICENSE.txt')]
    if not all(p.exists() for p in required) or not list(base.glob('python3*.dll')):
        raise RuntimeError('Use a full python.org Windows x64 installation (3.11–3.13), not Store/embedded Python.')
    destination.mkdir(parents=True)
    for name in ('python.exe', 'pythonw.exe', 'LICENSE.txt'):
        shutil.copy2(base / name, destination / name)
    for pattern in ('python3*.dll', 'vcruntime*.dll'):
        for file in base.glob(pattern):
            shutil.copy2(file, destination / file.name)
    # Never copy the builder's installed packages, user settings, or venv.
    shutil.copytree(base / 'Lib', destination / 'Lib',
                    ignore=shutil.ignore_patterns('site-packages', '__pycache__', '*.pyc', 'test', 'idlelib'))
    shutil.copytree(base / 'DLLs', destination / 'DLLs')


def find_compiler(explicit=None):
    candidates = [explicit, shutil.which('ISCC.exe')]
    for env in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
        if os.environ.get(env):
            base = Path(os.environ[env])
            for version in ('6', '7'):
                candidates += [str(base / f'Inno Setup {version}' / 'ISCC.exe'),
                               str(base / 'Programs' / f'Inno Setup {version}' / 'ISCC.exe')]
    return next((Path(p) for p in candidates if p and Path(p).is_file()), None)


def copy_ffmpeg(source, target):
    """Accept a complete redistribution folder, not an arbitrary EXE from PATH."""
    source = source.resolve()
    if not all((source / n).is_file() for n in ('ffmpeg.exe', 'ffprobe.exe', 'REDISTRIBUTION.md')):
        raise RuntimeError('FFmpeg folder must contain ffmpeg.exe, ffprobe.exe and REDISTRIBUTION.md. See packaging/BUILD.md.')
    if not any(p.is_file() and ('license' in p.name.lower() or 'copying' in p.name.lower()) for p in source.rglob('*')):
        raise RuntimeError('Keep FFmpeg distribution license files in the supplied folder.')
    if not (source / 'REDISTRIBUTION.md').read_text(encoding='utf-8').strip():
        raise RuntimeError('FFmpeg REDISTRIBUTION.md must identify its build and corresponding source.')
    shutil.copytree(source, target)


def build(args):
    if sys.platform != 'win32' or struct.calcsize('P') != 8 or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise RuntimeError('Build on Windows x64 using 64-bit Python 3.11–3.13.')
    if not (3, 11) <= sys.version_info[:2] <= (3, 13):
        raise RuntimeError('Use Python 3.11, 3.12 or 3.13 for this build recipe.')
    compiler = find_compiler(args.iscc)
    if not args.stage_only and not compiler:
        raise RuntimeError('Install Inno Setup 6.3+ from https://jrsoftware.org/isdl.php, then retry; or supply --iscc PATH.')
    payload = ROOT / 'build' / 'installer-payload'
    # Only this disposable, fixed build directory is removed.
    if payload.exists():
        shutil.rmtree(payload)
    copy_public(payload)
    runtime = payload / 'runtime'
    copy_runtime(Path(sys.base_prefix), runtime)
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--isolated', '--only-binary=:all:',
                    '--ignore-installed', '--no-compile', '--target', str(runtime / 'Lib/site-packages'),
                    '-r', str(ROOT / 'requirements.txt')], check=True)
    env = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH', 'PYTHONSTARTUP'):
        env.pop(key, None)
    env['PYTHONNOUSERSITE'] = '1'
    # Exercise the copied interpreter and Qt without the build machine's packages.
    check = ('import sys, ssl, ctypes, PySide6, psutil, numpy; from pathlib import Path; '
             'from PySide6 import QtWidgets, QtMultimedia; '
             'assert all(Path(m.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()) '
             'for m in (PySide6, psutil, numpy)); print(sys.prefix)')
    subprocess.run([str(runtime / 'python.exe'), '-s', '-E', '-c', check], cwd=payload, env=env, check=True)
    # Check the recorder's relocated interpreter without touching user runtime data.
    with tempfile.TemporaryDirectory(prefix='clipnest-host-check-') as temp:
        host_dir = Path(temp)
        shutil.copy2(runtime / 'python.exe', host_dir / 'clipnest-host.exe')
        for dll in runtime.glob('*.dll'):
            shutil.copy2(dll, host_dir / dll.name)
        host_env = env.copy()
        host_env['PYTHONHOME'] = str(runtime)
        host_env['PYTHONPATH'] = str(payload)
        subprocess.run([str(host_dir / 'clipnest-host.exe'), '-s', '-c',
                        'import ssl, ctypes, clipnest.native_host; print("Recorder host imports OK")'],
                       cwd=payload, env=host_env, check=True)
    if args.ffmpeg_dir:
        copy_ffmpeg(args.ffmpeg_dir, payload / 'tools/ffmpeg')
        for name in ('ffmpeg', 'ffprobe'):
            subprocess.run([str(payload / f'tools/ffmpeg/{name}.exe'), '-version'], check=True, env=env)
    deps = subprocess.check_output([str(runtime / 'python.exe'), '-s', '-E', '-c',
        'import importlib.metadata as m,json; print(json.dumps({d.metadata["Name"]:d.version for d in m.distributions()}))'], env=env, text=True)
    (payload / 'BUILD-INFO.json').write_text(json.dumps(dict(version=VERSION, python=platform.python_version(),
        dependencies=json.loads(deps), bundled_ffmpeg=bool(args.ffmpeg_dir)), indent=2), encoding='utf-8')
    print(f'Staged: {payload}')
    if args.stage_only:
        return
    subprocess.run([str(compiler), f'/DPayloadDir={payload}', f'/DAppVersion={VERSION}',
                    str(ROOT / 'packaging/ClipNest.iss')], check=True)
    result = ROOT / f'dist/ClipNest-Setup-{VERSION}-x64.exe'
    digest = hashlib.sha256(result.read_bytes()).hexdigest()
    result.with_suffix('.exe.sha256').write_text(f'{digest}  {result.name}\n', encoding='ascii')
    print(f'Installer ready: {result}')
    print('Windows acceptance tests in TESTCASES.md must pass before publishing.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iscc', help='Full path to ISCC.exe')
    parser.add_argument('--ffmpeg-dir', type=Path, help='Prepared FFmpeg redistribution folder')
    parser.add_argument('--stage-only', action='store_true', help='Prepare and check payload without compiling')
    args = parser.parse_args()
    try:
        build(args)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'Build failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
