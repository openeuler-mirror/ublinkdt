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

"""Runtime-mode policy and southbound diagnostic context.

Holds the orthogonal concerns that were previously embedded in southbound.py:
the debug/stub build policy and the per-query diagnostic ContextVar that lets
southbound log lines attribute themselves to the originating northbound CLI
command. ``southbound`` re-exports these names for backward compatibility.
"""

import contextvars
import os

from ._runtime_mode import DEBUG_BUILD

STUB_MODE_ENV = "OTPD_STUB_MODE"

# Per-query diagnostic context: the northbound CLI command currently in flight.
# Set/reset around each command execution so southbound logs can attribute
# field-loss warnings to the user-facing command that triggered them.
_query_context = contextvars.ContextVar("otpd_query_context", default="")


def set_query_context(ublinkdt_command: str):
    """Set the current northbound CLI command for southbound diagnostics."""
    return _query_context.set(ublinkdt_command)


def reset_query_context(token) -> None:
    """Reset the current northbound CLI command context."""
    _query_context.reset(token)


def get_query_context() -> str:
    """Return the current northbound CLI command for diagnostics."""
    return _query_context.get() or "<unknown>"


def _env_flag(name: str) -> bool:
    """Return True when an environment flag is explicitly enabled."""
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


def is_debug_mode() -> bool:
    """Return True when this installed package was built in debug mode."""
    return DEBUG_BUILD


def is_stub_mode() -> bool:
    """Return True if stub mode is enabled for debug/integration testing.

    Delivery builds are the default: OTPD_STUB_MODE is ignored unless the
    installed package was built in debug mode first. This keeps delivered
    installs from accidentally returning stubbed data because of a stray
    environment value.
    """
    return is_debug_mode() and _env_flag(STUB_MODE_ENV)
