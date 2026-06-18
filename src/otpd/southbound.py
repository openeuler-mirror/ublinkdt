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

import logging
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Tuple, List, Any, Callable
from .models import PortInfo, OpticalModuleInfo
# Runtime-mode policy and diagnostic context live in runtime.py; re-exported
# here so existing importers (cli.py, __init__.py, tests) keep working.
from .runtime import (
    STUB_MODE_ENV,
    _env_flag,
    is_debug_mode,
    is_stub_mode,
    set_query_context,
    reset_query_context,
    get_query_context,
)
from .schema import (
    OPTICAL_LANE_COUNT,
    PORT_SNR_LANE_COUNT,
    PORT_FIELD_NAMES,
    OPTICAL_FIELD_NAMES,
)

logger = logging.getLogger(__name__)


class SouthboundInterface(ABC):
    """Southbound interface base class."""

    _data_cache: Dict[Tuple[int, int, int, Optional[frozenset]], Tuple[PortInfo, OpticalModuleInfo]] = {}

    @abstractmethod
    def get_port_data(
        self,
        port_id: int,
        chip_id: int,
        die_id: int = 0,
        use_cache: bool = True,
        required_fields: Optional[set] = None,
    ) -> Optional[Tuple[PortInfo, OpticalModuleInfo]]:
        """Get port data (must be implemented by subclass).

        Args:
            port_id: Port ID
            chip_id: Chip ID (0 or 1)
            die_id: Die ID (0 or 1)
            use_cache: Whether to use cache
            required_fields: Optional field names needed by the current query.

        Returns:
            (PortInfo, OpticalModuleInfo) tuple or None
        """
        pass

    def clear_cache(self):
        """Clear cache."""
        self._data_cache.clear()
        logger.info("Data cache cleared")

    def _cache_get_or_compute(
        self,
        port_id: int,
        chip_id: int,
        die_id: int,
        required_fields: Optional[set],
        use_cache: bool,
        compute: Callable[[], Optional[Tuple[PortInfo, OpticalModuleInfo]]],
    ) -> Optional[Tuple[PortInfo, OpticalModuleInfo]]:
        """Return the cached result if present, otherwise call ``compute``.

        ``compute`` produces a ``(PortInfo, OpticalModuleInfo)`` tuple or None.
        None results are never cached, matching the prior per-subclass behavior
        where the cache write only ran on a successful (non-None) assembly.
        Subclasses that skip caching (e.g. ZeroBaselineSouthbound) simply don't
        call this method.
        """
        cache_key = self._make_cache_key(port_id, chip_id, die_id, required_fields)
        if use_cache and cache_key in self._data_cache:
            logger.debug(f"Using cached data for port {port_id} chip {chip_id} die {die_id}")
            return self._data_cache[cache_key]
        result = compute()
        if result is not None:
            self._data_cache[cache_key] = result
        return result

    @staticmethod
    def _make_cache_key(port_id: int, chip_id: int, die_id: int, required_fields: Optional[set]) -> Tuple[int, int, int, Optional[frozenset]]:
        """Build a cache key that distinguishes full and field-filtered queries."""
        field_key = None if required_fields is None else frozenset(required_fields)
        return (port_id, chip_id, die_id, field_key)


class ZeroBaselineSouthbound(SouthboundInterface):
    """Southbound that returns all-zero PortInfo and OpticalModuleInfo."""

    def get_port_data(
        self,
        port_id: int,
        chip_id: int,
        die_id: int = 0,
        use_cache: bool = True,
        required_fields: Optional[set] = None,
    ) -> Optional[Tuple[PortInfo, OpticalModuleInfo]]:
        port_info = PortInfo(port_id=port_id, chip_id=chip_id)
        optical_info = OpticalModuleInfo(port_id=port_id, chip_id=chip_id)
        return (port_info, optical_info)


@dataclass
class CommandEntry:
    """One registered external tool invocation.

    Attributes:
        name: Human-readable identifier for this command.
        command: Command and arguments as a list. Supports template variables
            ``{port_id}`` and ``{chip_id}`` that are substituted at runtime.
        parser: Developer-defined function that takes command stdout and
            returns a dict whose keys match PortInfo/OpticalModuleInfo field names.
            For ``output_mode="text"`` (default), receives ``str``.
            For ``output_mode="binary"``, receives ``bytes``.
            Example: ``{"port_snrlane": [25.0, ...], "cw_fec_cnt": 12345}``
        timeout: Subprocess timeout in seconds.
        enabled: Whether this command is active.
        output_mode: ``"text"`` (default) or ``"binary"``. In binary mode the
            subprocess stdout is captured as raw bytes and passed to parser.
        fields: List of field names this command is expected to produce.
            Used to zero out fields when the command fails or device is absent.
    """
    name: str
    command: List[str]
    parser: Any  # Callable[[str], Dict] for text mode, Callable[[bytes], Dict] for binary mode
    timeout: float = 10.0
    enabled: bool = True
    output_mode: str = "text"
    fields: List[str] = None


class CommandBasedSouthbound(SouthboundInterface):
    """Southbound that retrieves data by executing external commands.

    Developers register CommandEntry instances. Each entry specifies an
    external tool to run and a parser function to convert its text output
    into field values. Multiple commands contribute different fields;
    results are merged and assembled into PortInfo/OpticalModuleInfo.

    See ``docs/southbound_command_guide.md`` for the full developer guide.
    """

    def __init__(self, default_timeout: float = 10.0):
        self._command_registry: Dict[str, CommandEntry] = {}
        self._default_timeout = default_timeout
        self._known_fields: set = set()

    def known_fields(self) -> set:
        """Return field names that registered commands are expected to provide."""
        return self._known_fields

    def has_commands_for(self, required_fields: Optional[set] = None) -> bool:
        """Return whether enabled commands are bound for the requested fields."""
        for entry in self._command_registry.values():
            if not entry.enabled:
                continue
            if required_fields is None:
                return True
            if entry.fields is None or set(entry.fields) & required_fields:
                return True
        return False

    def register_command(self, entry: CommandEntry) -> None:
        """Register a command entry.

        Args:
            entry: CommandEntry instance. ``entry.name`` must be unique.
        """
        self._command_registry[entry.name] = entry
        if entry.fields:
            self._known_fields.update(entry.fields)
        logger.info(f"Registered command '{entry.name}': {entry.command}")

    def unregister_command(self, name: str) -> None:
        """Remove a registered command by name."""
        if name in self._command_registry:
            del self._command_registry[name]
            logger.info(f"Unregistered command '{name}'")

    def get_port_data(
        self,
        port_id: int,
        chip_id: int,
        die_id: int = 0,
        use_cache: bool = True,
        required_fields: Optional[set] = None,
    ) -> Optional[Tuple[PortInfo, OpticalModuleInfo]]:
        """Execute registered commands and return parsed data."""
        return self._cache_get_or_compute(
            port_id, chip_id, die_id, required_fields, use_cache,
            lambda: self._compute_port_data(port_id, chip_id, die_id, required_fields),
        )

    def _compute_port_data(
        self,
        port_id: int,
        chip_id: int,
        die_id: int,
        required_fields: Optional[set],
    ) -> Optional[Tuple[PortInfo, OpticalModuleInfo]]:
        """Run commands and assemble models; returns None when nothing merged."""
        merged, failed_entries = self._execute_all(port_id, chip_id, die_id, required_fields)
        if not merged:
            if is_stub_mode():
                logger.debug(f"No data from any command for port {port_id} chip {chip_id} die {die_id}")
            else:
                self._log_missing_fields(
                    port_id, chip_id, die_id, failed_entries, merged, required_fields
                )
            return None

        port_info = self._assemble_port_info(port_id, chip_id, merged)
        optical_info = self._assemble_optical_info(port_id, chip_id, merged)
        return (port_info, optical_info)

    def get_field_data(self, port_id: int, chip_id: int, die_id: int = 0, required_fields: Optional[set] = None) -> Dict[str, Any]:
        """Execute registered commands and return only fields they supplied.

        Args:
            required_fields: If provided, only execute commands whose ``fields``
                overlap with this set. If None, execute all commands.
        """
        merged, _ = self._execute_all(port_id, chip_id, die_id, required_fields)
        return merged

    def get_field_data_with_failures(self, port_id: int, chip_id: int, die_id: int = 0, required_fields: Optional[set] = None) -> Tuple[Dict[str, Any], List['CommandEntry']]:
        """Execute registered commands, return (fields dict, failed entries list).

        Args:
            required_fields: If provided, only execute commands whose ``fields``
                overlap with this set. If None, execute all commands.
        """
        return self._execute_all(port_id, chip_id, die_id, required_fields)

    def _execute_all(self, port_id: int, chip_id: int, die_id: int = 0, required_fields: Optional[set] = None) -> Tuple[Dict[str, Any], List['CommandEntry']]:
        """Run enabled registered commands and merge their parsed dicts.

        Returns:
            Tuple of (merged dict, list of CommandEntry that returned empty results).
        """
        merged: Dict[str, Any] = {}
        failed_entries: List[CommandEntry] = []
        for entry in self._command_registry.values():
            if not entry.enabled:
                continue
            if required_fields is not None and entry.fields is not None:
                if not set(entry.fields) & required_fields:
                    continue
            result = self._execute_one(entry, port_id, chip_id, die_id)
            if result:
                merged.update(result)
            else:
                failed_entries.append(entry)
        return merged, failed_entries

    def _execute_one(self, entry: CommandEntry, port_id: int, chip_id: int, die_id: int = 0) -> Dict[str, Any]:
        """Execute one command, return its parser's output dict."""
        formatted_cmd = self._format_command(entry.command, port_id, chip_id, die_id)
        binary_mode = (entry.output_mode == "binary")
        try:
            proc = subprocess.run(
                formatted_cmd,
                capture_output=True,
                text=not binary_mode,
                timeout=entry.timeout,
            )
            if proc.returncode != 0:
                stderr = proc.stderr or (b"" if binary_mode else "")
                stderr_info = (
                    repr(stderr[:200]) if binary_mode
                    else str(stderr).strip()
                )
                if is_stub_mode():
                    logger.debug(
                        f"Command '{entry.name}' returned rc={proc.returncode}, "
                        f"stubbing fields [OTPD_STUB_MODE]: stderr={stderr_info}"
                    )
                else:
                    logger.debug(
                        f"Command '{entry.name}' failed (rc={proc.returncode}): "
                        f"stderr={stderr_info}"
                    )
                return {}
        except subprocess.TimeoutExpired:
            if is_stub_mode():
                logger.debug(
                    f"Command '{entry.name}' timed out after {entry.timeout}s, "
                    f"stubbing fields [OTPD_STUB_MODE]"
                )
            else:
                logger.debug(f"Command '{entry.name}' timed out after {entry.timeout}s")
            return {}
        except FileNotFoundError:
            if is_stub_mode():
                logger.debug(
                    f"Command '{entry.name}' not found: {formatted_cmd[0]}, "
                    f"stubbing fields [OTPD_STUB_MODE]"
                )
                return {}
            else:
                self._log_missing_fields(
                    port_id, chip_id, die_id, [entry], {}, set(entry.fields or []),
                    reason=f"command not found: {formatted_cmd[0]}"
                )
                raise
        except Exception as e:
            if is_stub_mode():
                logger.debug(
                    f"Command '{entry.name}' error: {e}, "
                    f"stubbing fields [OTPD_STUB_MODE]"
                )
            else:
                logger.debug(f"Command '{entry.name}' error: {e}")
            return {}

        try:
            result = entry.parser(proc.stdout)
            return result
        except Exception as e:
            if is_stub_mode():
                logger.debug(
                    f"Parser for '{entry.name}' failed: {e}, "
                    f"stubbing fields [OTPD_STUB_MODE]"
                )
            else:
                logger.debug(f"Parser for '{entry.name}' failed: {e}")
            return {}

    @staticmethod
    def _log_missing_fields(
        port_id: int,
        chip_id: int,
        die_id: int,
        failed_entries: List[CommandEntry],
        overlay_fields: Dict[str, Any],
        required_fields: Optional[set],
        reason: str = "no data returned",
    ) -> None:
        """Log one structured diagnostic line per failed southbound command."""
        logged = False
        for entry in failed_entries:
            missing_fields = CommandBasedSouthbound._missing_fields(
                entry, overlay_fields, required_fields
            )
            if not missing_fields:
                continue
            command_text = " ".join(
                CommandBasedSouthbound._format_command(
                    entry.command, port_id, chip_id, die_id
                )
            )
            logger.warning(
                "Southbound fields missing: "
                "ublinkdt_command=%r target=port:%s,chip:%s,die:%s "
                "southbound_command=%r command=%r missing_fields=%s reason=%r",
                get_query_context(),
                port_id,
                chip_id,
                die_id,
                entry.name,
                command_text,
                missing_fields,
                reason,
            )
            logged = True
        if not logged:
            logger.warning(
                "Southbound fields missing: "
                "ublinkdt_command=%r target=port:%s,chip:%s,die:%s "
                "southbound_command=<unknown> command=<unknown> missing_fields=%s reason=%r",
                get_query_context(),
                port_id,
                chip_id,
                die_id,
                sorted(required_fields) if required_fields else [],
                reason,
            )

    @staticmethod
    def _missing_fields(
        entry: CommandEntry,
        overlay_fields: Dict[str, Any],
        required_fields: Optional[set],
    ) -> List[str]:
        """Return the command fields that are still missing from the overlay."""
        if entry.fields is None:
            expected_fields = sorted(required_fields) if required_fields else []
        else:
            expected_fields = list(entry.fields)
            if required_fields is not None:
                expected_fields = [
                    field for field in expected_fields
                    if field in required_fields
                ]
        return [
            field for field in expected_fields
            if field not in overlay_fields
        ]

    @staticmethod
    def _format_command(command: List[str], port_id: int, chip_id: int, die_id: int = 0) -> List[str]:
        """Substitute command template parameters, including simple integer offsets."""
        params = {"port_id": port_id, "chip_id": chip_id, "die_id": die_id}

        def replace(match):
            expr = match.group(1)
            expr_match = re.match(r"^(port_id|chip_id|die_id)([+-]\d+)?$", expr)
            if not expr_match:
                raise KeyError(expr)
            value = params[expr_match.group(1)]
            if expr_match.group(2):
                value += int(expr_match.group(2))
            return str(value)

        return [re.sub(r"\{([^{}]+)\}", replace, arg) for arg in command]

    @staticmethod
    def _assemble_port_info(port_id: int, chip_id: int, merged: Dict[str, Any]) -> PortInfo:
        """Build PortInfo from merged command result dict."""
        port_data = {"port_id": port_id, "chip_id": chip_id}
        for key in PORT_FIELD_NAMES:
            if key in merged:
                port_data[key] = merged[key]
        port_info = PortInfo.from_dict(port_data)
        return port_info

    @staticmethod
    def _assemble_optical_info(port_id: int, chip_id: int, merged: Dict[str, Any]) -> OpticalModuleInfo:
        """Build OpticalModuleInfo from merged command result dict."""
        optical_data = {"port_id": port_id, "chip_id": chip_id}
        for key in OPTICAL_FIELD_NAMES:
            if key in merged:
                optical_data[key] = merged[key]
        return OpticalModuleInfo.from_dict(optical_data)


class CompositeSouthbound(SouthboundInterface):
    """Southbound that overlays command-provided fields on a zero baseline.

    Baseline fields start at zero; command results override individual fields
    as they become available.
    """

    _data_cache: Dict[Tuple[int, int, int, Optional[frozenset]], Tuple[PortInfo, OpticalModuleInfo]] = {}

    def __init__(
        self,
        baseline: SouthboundInterface,
        overlay: CommandBasedSouthbound,
        calculators: Optional[List[Callable[[Dict[str, Any]], None]]] = None,
    ):
        self._baseline = baseline
        self._overlay = overlay
        self._calculators = calculators or []

    def get_port_data(self, port_id: int, chip_id: int, die_id: int = 0, use_cache: bool = True, required_fields: Optional[set] = None) -> Optional[Tuple[PortInfo, OpticalModuleInfo]]:
        """Get baseline data, apply command field overrides, then calculate derived fields."""
        return self._cache_get_or_compute(
            port_id, chip_id, die_id, required_fields, use_cache,
            lambda: self._compute_port_data(port_id, chip_id, die_id, use_cache, required_fields),
        )

    def _compute_port_data(
        self,
        port_id: int,
        chip_id: int,
        die_id: int,
        use_cache: bool,
        required_fields: Optional[set],
    ) -> Optional[Tuple[PortInfo, OpticalModuleInfo]]:
        """Baseline + overlay + derived-field calculation; None when overlay is empty."""
        baseline_data = self._baseline.get_port_data(port_id, chip_id, die_id, use_cache=use_cache)
        if baseline_data is None:
            logger.warning(f"No baseline data for port {port_id} chip {chip_id} die {die_id}")
            return None

        fields = self._models_to_fields(*baseline_data)

        if self._overlay.has_commands_for(required_fields):
            overlay_fields, failed_entries = self._overlay.get_field_data_with_failures(
                port_id, chip_id, die_id, required_fields=required_fields
            )

            if is_stub_mode():
                if not overlay_fields:
                    logger.debug(
                        f"Bound overlay commands returned no data for port {port_id} "
                        f"chip {chip_id} die {die_id}, falling back to stub defaults "
                        f"[OTPD_STUB_MODE]"
                    )
                    executed_field_set = required_fields if required_fields is not None else self._overlay.known_fields()
                    for key in executed_field_set:
                        self._stub_field(fields, key, port_id, chip_id)
                executed_field_set = required_fields if required_fields is not None else self._overlay.known_fields()
                for key in executed_field_set:
                    if key not in overlay_fields:
                        self._stub_field(fields, key, port_id, chip_id)
                fields.update(overlay_fields)
            else:
                if not overlay_fields:
                    CommandBasedSouthbound._log_missing_fields(
                        port_id, chip_id, die_id,
                        failed_entries, overlay_fields, required_fields
                    )
                    return None

                if failed_entries:
                    CommandBasedSouthbound._log_missing_fields(
                        port_id, chip_id, die_id,
                        failed_entries, overlay_fields, required_fields
                    )

                executed_field_set = required_fields if required_fields is not None else self._overlay.known_fields()
                for key in executed_field_set:
                    if key not in overlay_fields:
                        self._zero_field(fields, key)
                fields.update(overlay_fields)

        if required_fields is None or "cw_total_cnt" in required_fields:
            for calculator in self._calculators:
                calculator(fields)

        return self._assemble_from_fields(port_id, chip_id, fields)

    @staticmethod
    def _zero_field(fields: Dict[str, Any], key: str) -> None:
        """Set a field to its zero/default value."""
        if key == "port_snrlane":
            fields[key] = [0.0] * PORT_SNR_LANE_COUNT
        elif key in ("tx_power", "rx_power", "tx_bias", "host_snr", "media_snr"):
            fields[key] = [0.0] * OPTICAL_LANE_COUNT
        elif key in ("optical_sn", "optical_vendor", "optical_type_name", "link_status"):
            fields[key] = ""
        elif isinstance(fields.get(key), str):
            fields[key] = ""
        elif isinstance(fields.get(key), float):
            fields[key] = 0.0
        else:
            fields[key] = 0

    @staticmethod
    def _stub_field(fields: Dict[str, Any], key: str, port_id: int, chip_id: int) -> None:
        """Set a field to its stub-mode default value."""
        if key == "link_status":
            fields[key] = CompositeSouthbound._stub_link_status(port_id, chip_id)
            return
        if key in OPTICAL_FIELD_NAMES:
            fields[key] = CompositeSouthbound._stub_optical_field(key)
            return
        CompositeSouthbound._zero_field(fields, key)

    @staticmethod
    def _stub_optical_field(key: str) -> Any:
        """Return less-empty optical defaults for stub mode."""
        if key in ("optical_sn", "optical_vendor"):
            return "XXXXX"
        if key == "optical_type_name":
            return "XXXXX"
        if key == "lane_count":
            return 8
        if key in ("tx_power", "rx_power", "tx_bias", "host_snr", "media_snr"):
            return [0.0] * OPTICAL_LANE_COUNT
        return 0

    @staticmethod
    def _stub_link_status(port_id: int, chip_id: int) -> str:
        """Return deterministic-enough mock link status text for stub mode."""
        return "\n".join([
            "link status info:",
            f"current_time       : {datetime.now().strftime('%a %b %d %H:%M:%S %Y')}",
            f"link_up_count      : 2",
            "link_down_count    : 1",
            "records:",
            "  Mon Oct 23 10:30:15 2023  LINK UP",
            "  Mon Oct 23 10:25:10 2023  LINK DOWN",
            "  Mon Oct 23 10:22:30 2023  LINK UP",
        ])

    @staticmethod
    def _models_to_fields(port_info: PortInfo, optical_info: OpticalModuleInfo) -> Dict[str, Any]:
        """Convert models to one flat field dict for overlay and calculation."""
        fields = port_info.to_dict()
        fields.update(optical_info.to_dict())
        fields.pop("port_id", None)
        fields.pop("chip_id", None)
        return fields

    @staticmethod
    def _assemble_from_fields(port_id: int, chip_id: int, fields: Dict[str, Any]) -> Tuple[PortInfo, OpticalModuleInfo]:
        """Assemble output models from a merged flat field dict."""
        port_info = CommandBasedSouthbound._assemble_port_info(port_id, chip_id, fields)
        optical_info = CommandBasedSouthbound._assemble_optical_info(port_id, chip_id, fields)
        return (port_info, optical_info)



def get_southbound_interface(source: str = "hybrid", **kwargs) -> SouthboundInterface:
    """Get southbound interface instance.

    Args:
        source: Data source type ("command" or "hybrid")
        **kwargs: Additional arguments passed to the constructor.

    Returns:
        SouthboundInterface instance
    """
    if source == "command":
        return CommandBasedSouthbound(**kwargs)
    elif source == "hybrid":
        from .southbound_commands import build_hybrid_southbound
        return build_hybrid_southbound(**kwargs)
    else:
        raise ValueError(f"Unknown source '{source}'")


southbound = get_southbound_interface()
