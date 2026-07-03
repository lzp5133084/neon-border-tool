import os
import sys

block_cipher = None

base_path = os.path.dirname(os.path.abspath(__file__))
frontend_path = os.path.join(base_path, '../frontend')
data_path = os.path.join(base_path, '../data')

a = Analysis(
    ['app.py'],
    pathex=[base_path],
    binaries=[],
    datas=[
        (frontend_path, '../frontend'),
        (data_path, '../data'),
        ('.env', '.'),
    ],
    hiddenimports=[
        'flask',
        'flask_cors',
        'sqlite3',
        'requests',
        'json',
        'base64',
        'threading',
        'datetime',
        'os',
        'sys',
        'time',
        'io',
        'oss2',
        'volcengine',
        'dotenv',
        'jinja2',
        'markupsafe',
        'werkzeug',
        'click',
        'itsdangerous',
        'blinker',
        'urllib3',
        'certifi',
        'charset_normalizer',
        'idna',
        'crcmod',
        'pycryptodome',
        'aliyun_python_sdk_core',
        'aliyun_python_sdk_kms',
        'protobuf',
        'google',
        'beautifulsoup4',
        'soupsieve',
        'pytz',
        'six',
        'jmespath',
        'cryptography',
        'cffi',
        'pycparser',
        'typing_extensions',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='霓虹边框凸显工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
