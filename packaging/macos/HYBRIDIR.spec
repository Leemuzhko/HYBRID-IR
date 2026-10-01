# Native single-architecture onedir .app. Do not use argv_emulation with Tk.
import importlib.metadata
import json
import os
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root=Path(os.environ['HYBRIDIR_PUBLIC_ROOT'])
info=Path(os.environ['HYBRIDIR_BUILD_METADATA'])
metadata=json.loads(info.read_text())
manifest=json.loads((root/'PUBLICATION_MANIFEST.json').read_text())
datas=[]
for row in manifest['files']:
    name=row['path']
    if name.startswith('hybridir_sdk/templates/') and Path(name).name not in ('HIR3A.ZDL','HIR3A.template.json'):
        continue
    selected=(name.startswith(('hybridir_sdk/','licenses/')) or name in (
        'irbq_lab/irbq/translations.json','irbq_lab/irbq/stock_ids.json',
        'LICENSE','THIRD_PARTY_NOTICES.md','THIRD_PARTY_NOTICES.uk.md'))
    if name.startswith('packaging/macos/licenses/'):
        datas.append((str(root/name), 'licenses/macos'))
    elif selected:
        datas.append((str(root/name), str(Path(name).parent)))
datas.append((str(info), '.'))
for distribution in metadata['dependencies']:
    datas += copy_metadata(distribution)

a=Analysis([str(root/'packaging/macos/launch_macos.py')],
    pathex=[str(root),str(root/'hybridir_sdk/build')],
    binaries=[], datas=datas,
    hiddenimports=['screen_image','zdl','linker','PIL._tkinter_finder'],
    hookspath=[], runtime_hooks=[],
    excludes=['pytest','IPython','notebook','tkinter.test'],
    hooksconfig={'matplotlib':{'backends':['TkAgg']}},
    noarchive=False, optimize=0)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='HYBRID IR',
    debug=False,bootloader_ignore_signals=False,strip=False,upx=False,
    console=False,argv_emulation=False,target_arch=metadata['architecture'],
    codesign_identity=None,entitlements_file=None)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='HYBRID IR')
app=BUNDLE(coll,name='HYBRID IR.app',icon=os.environ['HYBRIDIR_MAC_ICON'],
    bundle_identifier='com.leemuzhko.hybridir' + ('.compat12' if metadata.get('packaging_profile') == 'compat12' else ''),version=metadata['version'],
    info_plist={'CFBundleDisplayName':'HYBRID IR','LSMinimumSystemVersion':metadata['minimum_macos'],
        'NSHighResolutionCapable':True,
        'CFBundleDocumentTypes':[{'CFBundleTypeName':'HYBRID IR project',
            'CFBundleTypeExtensions':['irbq','hybridbank'],
            'CFBundleTypeRole':'Editor','LSHandlerRank':'Alternate'}]})
