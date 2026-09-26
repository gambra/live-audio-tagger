"""Build the compact Windows release: EXE, editable template, README and licences."""
from pathlib import Path
from importlib.metadata import distribution
import hashlib
import os
import shutil
import subprocess
import sys
import argparse

ROOT = Path(__file__).resolve().parent


def write_notices(target):
    sections = ['Live Audio Tagger - bundled third-party components\n\n'
                'These libraries retain their own licences. Licence texts and project\n'
                'links are included below. The application source is maintained separately.\n']
    seen = set()
    for name in ('PySide6', 'PySide6_Essentials', 'shiboken6', 'soundfile',
                 'mutagen', 'Jinja2', 'MarkupSafe', 'cffi', 'pycparser', 'pyinstaller'):
        dist = distribution(name)
        sections.append(f"{name} {dist.version}\nLicence: {dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'See text below'}\n"
                        + '\n'.join(dist.metadata.get_all('Project-URL') or []))
        for file in dist.files or []:
            if any(word in file.name.lower() for word in ('license', 'licence', 'copying', 'notice')):
                path = Path(dist.locate_file(file))
                if path.is_file() and '..' not in file.parts:
                    data = path.read_bytes()
                    digest = hashlib.sha256(data).digest()
                    if digest not in seen:
                        sections.append(f'{name}: {file.name}\n\n' + data.decode('utf-8', errors='replace'))
                        seen.add(digest)
    sections.append('Python ' + sys.version + '\n\n' + (Path(sys.base_prefix) / 'LICENSE.txt').read_text(encoding='utf-8'))
    target.write_text(('\n\n' + '=' * 72 + '\n\n').join(sections), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-name', default='LiveAudioTagger-Windows-x64', help='New folder name inside distribution')
    args = parser.parse_args()
    if not args.output_name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.output_name):
        parser.error('Use letters, digits, hyphens or underscores for the output name.')
    if sys.platform != 'win32':
        raise SystemExit('Build the Windows executable on Windows.')
    destination = ROOT / 'distribution' / args.output_name
    if destination.exists():
        raise SystemExit(f'{destination} already exists. Choose another --output-name to preserve that release.')
    environment = os.environ.copy()
    system = Path(environment.get('SystemRoot', r'C:\Windows'))
    environment['PATH'] = os.pathsep.join(map(str, [Path(sys.executable).parent,
                                                   Path(sys.base_prefix), system / 'System32', system]))
    environment.pop('PYTHONPATH', None)
    environment.pop('PYTHONHOME', None)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--distpath', str(destination), '--workpath', str(ROOT / 'build' / 'compact'),
                    str(ROOT / 'FLACTagger-Compact.spec')], cwd=ROOT, env=environment, check=True)
    shutil.copy2(ROOT / 'DISTRIBUTION_README.txt', destination / 'README.txt')
    shutil.copy2(ROOT / 'template_example.txt', destination / 'template_example.txt')
    write_notices(destination / 'THIRD_PARTY_LICENSES.txt')
    print(f'Compact release created: {destination}')


if __name__ == '__main__':
    main()
