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

import subprocess
import sys
from pathlib import Path

import src


def test_package_version_is_release_version():
    """The package metadata and importable version stay in sync for release."""
    setup_py = Path(__file__).resolve().parents[1] / "setup.py"
    setup_text = setup_py.read_text(encoding="utf-8")

    assert "version='1.0.0'" in setup_text
    assert src.__version__ == "1.0.0"


def test_python_requires_matches_dataclass_usage():
    """The package uses stdlib dataclasses, so Python 3.7+ is required."""
    setup_py = Path(__file__).resolve().parents[1] / "setup.py"

    assert "python_requires='>=3.7'" in setup_py.read_text(encoding="utf-8")


def test_console_entry_point_uses_required_src_package_layout():
    """The published CLI follows the required src/otpd package layout."""
    setup_py = Path(__file__).resolve().parents[1] / "setup.py"
    setup_text = setup_py.read_text(encoding="utf-8")

    assert "find_packages(exclude=['tests', 'tests.*'])" in setup_text
    assert "package_dir={'': 'src'}" not in setup_text
    assert "find_packages(where='src'" not in setup_text
    assert "'ublinkdt=src.otpd.cli:main'" in setup_text
    assert "src.otpd.cli:main" in setup_text


def test_default_install_has_no_runtime_dependencies_and_debug_extra_has_tests():
    """Delivery installs stay dependency-free; debug installs add test tools."""
    setup_py = Path(__file__).resolve().parents[1] / "setup.py"
    setup_text = setup_py.read_text(encoding="utf-8")

    assert "install_requires=[]" in setup_text
    assert "'debug':" in setup_text
    assert "'pytest>=6.2.5'" in setup_text
    assert "'pytest-cov>=3.0.0'" in setup_text


def test_requirements_file_contains_build_tooling_only():
    """requirements.txt is for build tooling, not runtime or test imports."""
    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(
        encoding="utf-8"
    )

    assert "Runtime dependencies: none" in requirements
    assert "build>=0.10.0" in requirements
    assert "setuptools>=40.8.0" in requirements
    assert "wheel>=0.37.0" in requirements
    assert "pytest" not in requirements
    assert "pytest-cov" not in requirements


def test_build_mode_marker_defaults_to_delivery_and_can_be_debug(tmp_path):
    """Build output records whether the artifact is delivery or debug mode."""
    repo_root = Path(__file__).resolve().parents[1]

    delivery_build = tmp_path / "delivery"
    subprocess.run(
        [
            sys.executable,
            "setup.py",
            "build_py",
            "--build-lib",
            str(delivery_build),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    delivery_marker = delivery_build / "src" / "otpd" / "_runtime_mode.py"
    assert delivery_marker.read_text(encoding="utf-8") == "DEBUG_BUILD = False\n"

    debug_flag_build = tmp_path / "debug-flag"
    subprocess.run(
        [
            sys.executable,
            "setup.py",
            "build",
            "--debug-build",
            "--build-lib",
            str(debug_flag_build),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    debug_flag_marker = debug_flag_build / "src" / "otpd" / "_runtime_mode.py"
    assert debug_flag_marker.read_text(encoding="utf-8") == "DEBUG_BUILD = True\n"
