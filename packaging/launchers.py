"""Build in-process branded entry points using Windows' .NET Framework compiler."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def find_csc():
    root = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'Microsoft.NET'
    for platform in ('Framework64', 'Framework'):
        path = root / platform / 'v4.0.30319/csc.exe'
        if path.is_file():
            return path
    raise RuntimeError('The .NET Framework 4.x C# compiler is missing. Repair/enable .NET Framework 4.8, then rebuild ClipNest.')


def build_launchers(payload, version, compiler=None):
    compiler = Path(compiler) if compiler else find_csc()
    runtime = payload / 'runtime'
    dll = f'python{sys.version_info.major}{sys.version_info.minor}.dll'
    if not (runtime / dll).is_file():
        raise RuntimeError(f'Bundled Python DLL is missing: {dll}')
    parts = version.split('.')
    if len(parts) != 3 or not all(p.isdigit() and 0 <= int(p) < 65535 for p in parts):
        raise ValueError('Launcher version must be three numeric components')
    icon = payload / 'clipnest/assets/clipnest.ico'
    source = Path(__file__).with_name('Launcher.cs')
    with tempfile.TemporaryDirectory(prefix='clipnest-launcher-') as temp:
        metadata = Path(temp) / 'BuildInfo.cs'
        for recorder, destination, title in (
            (False, payload / 'ClipNest.exe', 'ClipNest'),
            (True, runtime / 'ClipNestRecorder.exe', 'ClipNest Recorder'),
        ):
            metadata.write_text(
                'using System.Reflection;\n'
                f'[assembly: AssemblyTitle("{title}")]\n'
                f'[assembly: AssemblyDescription("{title}")]\n'
                '[assembly: AssemblyProduct("ClipNest")]\n'
                '[assembly: AssemblyCompany("ClipNest")]\n'
                f'[assembly: AssemblyVersion("{version}.0")]\n'
                f'[assembly: AssemblyFileVersion("{version}.0")]\n'
                f'internal static class BuildInfo {{ public const string PythonDll = "{dll}"; }}\n', encoding='utf-8')
            command = [str(compiler), '/nologo', '/optimize+', '/platform:x64',
                       '/target:exe' if recorder else '/target:winexe',
                       '/win32icon:' + str(icon), '/out:' + str(destination)]
            if recorder:
                command.append('/define:RECORDER')
            subprocess.run(command + [str(source), str(metadata)], check=True)


def check_launcher(payload, env):
    with tempfile.TemporaryDirectory(prefix='clipnest-launcher-check-') as temp:
        report = Path(temp) / 'report.json'
        subprocess.run([str(payload / 'ClipNest.exe'), '--check-runtime', str(report)],
                       cwd=temp, env=env, check=True, timeout=60)
        result = json.loads(report.read_text(encoding='utf-8'))
        if Path(result['executable']).resolve() != (payload / 'ClipNest.exe').resolve():
            raise RuntimeError('Branded launcher did not remain the running executable')
        if Path(result['prefix']).resolve() != (payload / 'runtime').resolve():
            raise RuntimeError('Branded launcher loaded the wrong Python runtime')
