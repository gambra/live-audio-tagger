# Portable single-executable build. Audio I/O uses buffers, not NumPy.
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / 'flac_tagger.py')],
    pathex=[str(root)],
    binaries=[], datas=[(str(root / 'assets' / 'live_audio_tagger.png'), 'assets')], hiddenimports=[], hookspath=[], hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'pytest', 'unittest', 'tkinter',
              'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtOpenGL',
              'PySide6.QtPdf', 'PySide6.QtSvg', 'PySide6.QtVirtualKeyboard'],
    noarchive=False, optimize=1,
)

# Keep only plugins used by this raster widgets interface and its smoke test.
qt_dlls = {'qt6core.dll', 'qt6gui.dll', 'qt6widgets.dll', 'qt6network.dll'}
plugins = {'platforms/qwindows.dll', 'platforms/qoffscreen.dll',
           'styles/qmodernwindowsstyle.dll', 'imageformats/qico.dll'}

def needed(entry):
    name = entry[0].replace('\\', '/').lower()
    if name.startswith('pyside6/plugins/'):
        return name.removeprefix('pyside6/plugins/') in plugins
    leaf = name.rsplit('/', 1)[-1]
    if name.startswith('pyside6/') and leaf.startswith('qt6') and leaf.endswith('.dll'):
        return leaf in qt_dlls
    return leaf != 'opengl32sw.dll'

a.binaries = [entry for entry in a.binaries if needed(entry)]
a.datas = [entry for entry in a.datas
           if not entry[0].replace('\\', '/').lower().startswith('pyside6/translations/')]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='LiveAudioTagger',
          icon=str(root / 'assets' / 'live_audio_tagger.ico'),
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
