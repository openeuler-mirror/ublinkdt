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

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Dict, Optional

from .schema import OPTICAL_LANE_COUNT, PORT_SNR_LANE_COUNT


UNSET_VALUES = {"", "UNSET"}


def parse_key_value_lines(stdout: str, key_map: Dict[str, str], value_parsers: Dict[str, Callable[[str], Any]] = None) -> Dict[str, Any]:
    """Parse KEY=VALUE text into model field names.

    Args:
        stdout: Command stdout text.
        key_map: Maps command output keys to PortInfo/OpticalModuleInfo fields.
        value_parsers: Optional field-specific converters keyed by output key.
    """
    value_parsers = value_parsers or {}
    result: Dict[str, Any] = {}

    for line in stdout.strip().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in key_map:
            continue
        parser = value_parsers.get(key, str)
        result[key_map[key]] = parser(value.strip())

    return result


def parse_rate_to_bps(value: str) -> int:
    """Parse rate text such as 112G into bits per second."""
    normalized = value.strip().upper()
    if normalized in UNSET_VALUES:
        return 0
    multipliers = {
        "G": 1024 * 1024 * 1024,
        "M": 1024 * 1024,
        "K": 1024,
    }
    suffix = normalized[-1:]
    if suffix in multipliers:
        return int(float(normalized[:-1]) * multipliers[suffix])
    return int(float(normalized))


def parse_lane_count(value: str) -> int:
    """Parse lane count text such as X4 into an integer."""
    normalized = value.strip().upper()
    if normalized in UNSET_VALUES:
        return 0
    if normalized.startswith("X"):
        normalized = normalized[1:]
    return int(normalized)


def parse_hex_or_unset(value: str) -> int:
    """Parse a hex value, treating UNSET as zero."""
    normalized = value.strip().upper()
    if normalized in UNSET_VALUES:
        return 0
    return int(normalized, 16)


def _parse_float_or_none(value: str) -> Optional[float]:
    """Parse a float value, returning None for failed reads."""
    normalized = value.strip().upper()
    if normalized in UNSET_VALUES or normalized in {"N/A", "NA", "-"}:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def _parse_int_or_none(value: str) -> Optional[int]:
    """Parse an integer value, returning None for failed reads."""
    normalized = value.strip().upper()
    if normalized in UNSET_VALUES or normalized in {"N/A", "NA", "-"}:
        return None
    try:
        return int(normalized)
    except ValueError:
        return None


def _parse_rounded_int_or_none(value: str) -> Optional[int]:
    """Parse a decimal value and round half up to integer."""
    normalized = value.strip().lower().replace("c", "").strip()
    if normalized.upper() in UNSET_VALUES or normalized.upper() in {"N/A", "NA", "-"}:
        return None
    try:
        return int(Decimal(normalized).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def _parse_voltage_mv_or_none(value: str) -> Optional[int]:
    """Parse voltage text in volts and return millivolts."""
    normalized = value.strip().lower().replace("v", "").strip()
    if normalized.upper() in UNSET_VALUES or normalized.upper() in {"N/A", "NA", "-"}:
        return None
    try:
        return int((Decimal(normalized) * Decimal("1000")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def _parse_hex_or_none(value: str) -> Optional[int]:
    """Parse a hex value, returning None for failed reads."""
    normalized = value.strip().upper()
    if normalized in UNSET_VALUES or normalized in {"N/A", "NA", "-"}:
        return None
    if not re.match(r"^0X[0-9A-F]+$", normalized):
        return None
    try:
        return int(normalized, 16)
    except ValueError:
        return None


def _absent_optical_fields() -> Dict[str, Any]:
    """Return zero values for a not-present optical module."""
    return {
        "optical_sn": "",
        "optical_vendor": "",
        "optical_state": 0,
        "optical_type": 0,
        "optical_type_name": "",
        "interface_code": 0,
        "lane_count": 0,
        "tx_los_flag": 0,
        "rx_los_flag": 0,
        "tx_lol_flag": 0,
        "rx_lol_flag": 0,
        "tx_power": [0.0] * OPTICAL_LANE_COUNT,
        "rx_power": [0.0] * OPTICAL_LANE_COUNT,
        "vcc": 0,
        "temp": 0,
        "tx_bias": [0.0] * OPTICAL_LANE_COUNT,
        "host_snr": [0.0] * OPTICAL_LANE_COUNT,
        "media_snr": [0.0] * OPTICAL_LANE_COUNT,
    }


def parse_port_info_stats(stdout: str) -> Dict[str, Any]:
    """Parse ubctl port_info output fields needed by --stat."""
    result: Dict[str, Any] = {}
    for line in stdout.strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "sds_rate":
            result["sds_rate_bps"] = parse_rate_to_bps(value)
        elif key == "cur_tx_lane_num":
            result["tx_lane_num"] = parse_lane_count(value)
    return result


def parse_bit_err_stats(stdout: str) -> Dict[str, Any]:
    """Parse ubctl bit_err output fields needed by --stat."""
    result: Dict[str, Any] = {}
    for line in stdout.strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "st_fec_decoding_fail_num":
            result["cw_fec_cnt"] = parse_hex_or_unset(value)
        elif key == "st_fec_err_bit_num":
            result["cw_uncorrect_cnt"] = parse_hex_or_unset(value)
    return result


def parse_hikptool_serdes_info(stdout: str) -> Dict[str, Any]:
    """Parse hikptool serdes_info output fields needed by --port-snr."""
    port_snr = [0.0] * PORT_SNR_LANE_COUNT
    parsed_count = 0

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        lane_match = re.search(r"\bds(\d+)\b", line)
        if not lane_match:
            continue

        bracket_groups = re.findall(r"\[([^\]]*)\]", line)
        if not bracket_groups:
            continue

        value_match = re.search(r"-?\d+(?:\.\d+)?", bracket_groups[-1])
        if not value_match:
            continue

        lane = int(lane_match.group(1))
        if 0 <= lane < len(port_snr):
            port_snr[lane] = float(value_match.group(0))
            parsed_count += 1

    if parsed_count == 0:
        return {}
    return {"port_snrlane": port_snr}


def _extract_optical_kv_fields(line: str, result: Dict[str, Any]) -> int:
    """Parse a ``key: value`` optical header line into ``result``.

    Returns the number of fields populated (0 when the line is not a known
    header or the value is empty/unset).
    """
    if ":" not in line:
        return 0
    key, value = line.split(":", 1)
    key = key.strip()
    value = value.strip()

    if key == "Media Type":
        result["optical_type_name"] = value
        return 1 if value else 0
    if key == "Host Lane Count":
        # parse_lane_count already maps UNSET -> 0, so no pre-check needed.
        try:
            lane_count = parse_lane_count(value)
        except ValueError:
            lane_count = 0
        result["lane_count"] = lane_count
        return 1 if lane_count else 0
    if key == "Vendor Name":
        result["optical_vendor"] = value
        return 1 if value else 0
    if key == "Vendor SN":
        result["optical_sn"] = value
        return 1 if value else 0
    if key == "Temperature":
        temp = _parse_rounded_int_or_none(value)
        result["temp"] = temp
        return 1 if temp is not None else 0
    if key == "Voltage":
        vcc = _parse_voltage_mv_or_none(value)
        result["vcc"] = vcc
        return 1 if vcc is not None else 0
    return 0


def _extract_optical_lane_row(line: str, result: Dict[str, Any]) -> int:
    """Parse a numeric ``N: tx rx bias host_snr media_snr`` lane row.

    Writes the five per-lane values into ``result`` and returns how many
    parsed to a non-None float. Returns 0 for non-matching lines or out-of-range lanes.
    """
    lane_match = re.match(
        r"^(\d+)\s*:\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$",
        line,
    )
    if not lane_match:
        return 0
    lane = int(lane_match.group(1))
    if not (0 <= lane < OPTICAL_LANE_COUNT):
        return 0
    fields = [
        ("tx_power", lane_match.group(2)),
        ("rx_power", lane_match.group(3)),
        ("tx_bias", lane_match.group(4)),
        ("host_snr", lane_match.group(5)),
        ("media_snr", lane_match.group(6)),
    ]
    parsed_count = 0
    for field_name, raw_value in fields:
        parsed = _parse_float_or_none(raw_value)
        result[field_name][lane] = parsed
        parsed_count += 1 if parsed is not None else 0
    return parsed_count


def _extract_optical_los_lol(line: str, result: Dict[str, Any]) -> int:
    """Parse the inline ``RX/TX LOS/LOL`` flag line into ``result``.

    Returns the number of flag fields populated (0 when the line is not the
    combined LOS/LOL line).
    """
    if not ("RX LOS" in line and "TX LOS" in line and "RX LOL" in line and "TX LOL" in line):
        return 0
    parsed_count = 0
    for label, field_name in (
        ("RX LOS", "rx_los_flag"),
        ("TX LOS", "tx_los_flag"),
        ("RX LOL", "rx_lol_flag"),
        ("TX LOL", "tx_lol_flag"),
    ):
        match = re.search(rf"{label}\s*:\s*(\S+)", line)
        if match:
            parsed = _parse_hex_or_none(match.group(1))
            result[field_name] = parsed
            parsed_count += 1 if parsed is not None else 0
    return parsed_count


def parse_optical_dom(stdout: str) -> Dict[str, Any]:
    """Parse hikptool optical_dom output for --optical fields."""
    if "no optical module present on" in stdout.lower():
        return _absent_optical_fields()

    result: Dict[str, Any] = {
        "tx_power": [0.0] * OPTICAL_LANE_COUNT,
        "rx_power": [0.0] * OPTICAL_LANE_COUNT,
        "tx_bias": [0.0] * OPTICAL_LANE_COUNT,
        "host_snr": [0.0] * OPTICAL_LANE_COUNT,
        "media_snr": [0.0] * OPTICAL_LANE_COUNT,
        "optical_state": 1,
    }
    valid_count = 0

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or line == "...":
            continue
        valid_count += _extract_optical_kv_fields(line, result)
        valid_count += _extract_optical_lane_row(line, result)
        valid_count += _extract_optical_los_lol(line, result)

    if valid_count == 0:
        return _absent_optical_fields()
    return result


def parse_link_status(stdout: str) -> Dict[str, Any]:
    """Parse ubctl port_link output and return raw stdout as-is."""
    return {"link_status": stdout}
