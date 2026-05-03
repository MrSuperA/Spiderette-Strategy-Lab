# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Spiderette Strategy Lab（单文件模式）
# 用法: pyinstaller spiderette.spec --noconfirm

import os
import sys

base_dir = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    ['main.py'],
    pathex=[base_dir],
    binaries=[],
    datas=[
        ('src/ui/static', 'src/ui/static'),
    ],
    hiddenimports=[
        # 核心模块
        'src', 'src.core', 'src.core.types', 'src.core.rules', 'src.core.session',
        'src.core.info_set', 'src.core.exceptions',
        'src.envs', 'src.envs.generator', 'src.envs.simulator',
        'src.strategy', 'src.strategy.mcts', 'src.strategy.heuristics',
        'src.strategy.compose', 'src.strategy.neural', 'src.strategy.registry',
        'src.search', 'src.search.is_mcts', 'src.search.puct',
        'src.search.determinization',
        'src.network', 'src.network.feature_v2',
        'src.rl', 'src.rl.environment', 'src.rl.self_play', 'src.rl.curriculum',
        'src.iteration', 'src.iteration.engine',
        'src.utils', 'src.utils.paths',
        'src.analysis', 'src.analysis.metrics', 'src.analysis.report',
        'src.analysis.runner', 'src.analysis.batch', 'src.analysis.profile',
        'src.analysis.exporter', 'src.analysis.compare', 'src.analysis.genetic',
        'src.analysis.tuning', 'src.analysis.tournament', 'src.analysis.weakness',
        'src.analysis.factor', 'src.analysis.pattern', 'src.analysis.scenario',
        'src.analysis.utils',
        'src.ui', 'src.ui.server', 'src.ui.window',
        # 第三方依赖
        'flask', 'flask.json', 'jinja2', 'markupsafe', 'werkzeug', 'werkzeug.serving',
        'numpy',
        'webview', 'webview.platforms', 'webview.platforms.edgechromium',
        'waitress', 'psutil', 'GPUtil',
        'multiprocessing', 'multiprocessing.pool',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', '_tkinter',
        'matplotlib', 'scipy', 'pandas',
        'PIL', 'cv2', 'torch', 'tensorflow',
        'IPython', 'jupyter', 'notebook',
        'test', 'tests', 'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

# 单文件模式：所有内容打包进一个 exe
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SpideretteStrategyLab',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,    # 使用默认临时目录
    console=False,          # 无控制台黑窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=None,
)
