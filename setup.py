"""
Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved
[Software Name] is licensed under Mulan PSL v2.
You can use this software according to the terms and conditions of the Mulan PSL v2.
You may obtain a copy of Mulan PSL v2 at:
         http://license.coscl.org.cn/MulanPSL2
THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
See the Mulan PSL v2 for more details.
"""
import sys
from pathlib import Path

from setuptools import setup, find_packages
from setuptools.command.build_py import build_py as _build_py

_DEBUG_BUILD = False


def _consume_debug_build_flag() -> None:
    """Accept --debug-build as a setup.py build/install option."""
    global _DEBUG_BUILD
    while '--debug-build' in sys.argv:
        sys.argv.remove('--debug-build')
        _DEBUG_BUILD = True


def _is_debug_build() -> bool:
    return _DEBUG_BUILD


class build_py(_build_py):
    """Generate the runtime mode marker into the build output."""

    def run(self):
        super().run()
        target = Path(self.build_lib) / 'ublinkdt' / 'otpd' / '_runtime_mode.py'
        target.write_text(
            'DEBUG_BUILD = {}\n'.format('True' if _is_debug_build() else 'False'),
            encoding='utf-8',
        )


_consume_debug_build_flag()


setup(
    name='ublinkdt',
    version='1.0.0',
    description='UBLink-DT (Unified Bus Link Diagnostic Tool)',
    author='liusiyu60@huawei.com',
    package_dir={"ublinkdt": "src"},
    packages=[
        "ublinkdt",
        "ublinkdt.otpd",
        "ublinkdt.utils"
    ],
    install_requires=[],
    extras_require={
        'debug': [
            'pytest>=6.2.5',
            'pytest-cov>=3.0.0',
        ],
    },
    cmdclass={
        'build_py': build_py,
    },
    entry_points={
        'console_scripts': [
            'ublinkdt=ublinkdt.otpd.cli:main',
        ],
    },
    python_requires='>=3.7',
)

