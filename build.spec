# Antigravity Terminal - Build Configuration for PyInstaller
# This creates a standalone Windows executable

block_cipher = None

a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('.env', '.'),
    ],
    hiddenimports=[
        'flask',
        'webview',
        'psycopg2',
        'ccxt',
        'pandas',
        'numpy',
        'sklearn',
        'database',
        'dashboard_server',
        'liquidation_predictor',
        'signal_generator',
        'institutional_monitor',
        'market_impact',
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
    name='AntigravityTerminal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon='icon.ico' if you have one
)
