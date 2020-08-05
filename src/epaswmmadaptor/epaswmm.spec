# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['epaswmm.py'],
             pathex=['C:\\Users\\pbishop\\Documents\\0_WORKING\\30900_DelftFEWsPilot\\epa-swmm-adaptor\\src\\epaswmmadaptor'],
             binaries=[],
             datas=[('C:\\Users\\pbishop\\.conda\\envs\\epaswmm\\Lib\\site-packages\\xarray', '.\\xarray'),
			 ('C:\\Users\\pbishop\\.conda\\envs\\epaswmm\\Lib\\site-packages\\setuptools', '.\\setuptools')],
             hiddenimports=['xarray', 'setuptools', 'pkg_resources.py2_warn'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='epaswmm',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=True )
