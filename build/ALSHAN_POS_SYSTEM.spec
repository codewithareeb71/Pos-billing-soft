# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['../run.py'],
    pathex=['C:/xampp/htdocs/Areeb pos sfotware'],
    binaries=[],
    datas=[],
    hiddenimports=['barcode', 'barcode.writer', 'app.services', 'app.ui.pages', 'app.ui.pages.customers_page', 'app.ui.pages.dashboard', 'app.ui.pages.expenses_page', 'app.ui.pages.inventory_page', 'app.ui.pages.pos_page', 'app.ui.pages.products_page', 'app.ui.pages.purchases_page', 'app.ui.pages.reports_page', 'app.ui.pages.returns_page', 'app.ui.pages.sales_page', 'app.ui.pages.settings_page', 'app.ui.pages.suppliers_page', 'app.ui.pages.users_page'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ALSHAN_POS_SYSTEM',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/xampp/htdocs/Areeb pos sfotware/assets/alshan_pos.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ALSHAN_POS_SYSTEM',
)
