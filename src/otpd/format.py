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
from typing import List, Optional

from .schema import PORT_SNR_LANE_COUNT

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def _format_int_or_na(value: Optional[int], width: int = 8) -> str:
    """Format optional integer value."""
    if value is None:
        return f"{'N/A':>{width}}"
    return f"{value:>{width}}"


def _format_float_or_na(value: Optional[float], unit: str) -> str:
    """Format optional float value with unit."""
    if value is None:
        return f"{'N/A':>10} {unit}"
    return f"{value: .4f} {unit}"


def _format_flag_or_na(value: Optional[int]) -> str:
    """Format optional flag value."""
    if value is None:
        return f"{'N/A':>10}"
    return f"{value:>10}"


def format_port_snr_output(port_id: int, chip_id: int, snr_lanes: List[float]) -> str:
    """Format port SNR output with aligned colon and 4 decimal places.

    Port SNR southbound output is fixed to 4 lanes.

    Args:
        port_id: Port ID
        chip_id: Chip ID (0 or 1)
        snr_lanes: List of 4 SNR values

    Returns:
        Formatted string
    """
    lines = ["port SNR info:"]
    for i in range(PORT_SNR_LANE_COUNT):
        label = f"port SNR Lane{i}"
        lines.append(f"{label:<18}: {snr_lanes[i]: .4f} dB")
    return '\n'.join(lines)


def format_stat_output(port_id: int, chip_id: int, cw_total_cnt: int, cw_before_correct_cnt: int,
                     cw_uncorrect_cnt: int) -> str:
    """Format statistics output with aligned colon.

    Args:
        port_id: Port ID
        chip_id: Chip ID (0 or 1)
        cw_total_cnt: Total codeword count
        cw_before_correct_cnt: Codeword count before correction
        cw_uncorrect_cnt: Uncorrectable codeword count

    Returns:
        Formatted string
    """
    lines = ["error codeword statistics info:"]
    lines.append(f"{'cw_total_cnt':<22}: {cw_total_cnt:>15}")
    lines.append(f"{'cw_before_correct_cnt':<22}: {cw_before_correct_cnt:>15}")
    lines.append(f"{'cw_uncorrect_cnt':<22}: {cw_uncorrect_cnt:>15}")
    return '\n'.join(lines)


def format_optical_output(port_id: int, chip_id: int, sn: str, vendor: str,
                         state: int, optical_type: str, lane_count: int,
                         temp: Optional[int], vcc: Optional[int],
                         tx_power: List[Optional[float]], rx_power: List[Optional[float]],
                         tx_bias: List[Optional[float]], host_snr: List[Optional[float]],
                         media_snr: List[Optional[float]], tx_los: Optional[int], rx_los: Optional[int],
                         tx_lol: Optional[int], rx_lol: Optional[int]) -> str:
    """Format optical module information with aligned colon and 4 decimal places.

    Args:
        port_id: Port ID
        chip_id: Chip ID (0 or 1)
        sn: Serial number
        vendor: Vendor name
        state: Optical module state (0 or 1)
        optical_type: Optical type name string
        lane_count: Number of active lanes
        temp: Temperature
        vcc: Voltage
        tx_power: TX power list (16 elements, display based on lane_count)
        rx_power: RX power list (16 elements, display based on lane_count)
        tx_bias: TX bias list (16 elements, display based on lane_count)
        host_snr: Host SNR list (16 elements, display based on lane_count)
        media_snr: Media SNR list (16 elements, display based on lane_count)
        tx_los: TX LOS flag
        rx_los: RX LOS flag
        tx_lol: TX LoL flag
        rx_lol: RX LoL flag

    Returns:
        Formatted string
    """
    lines = ["optical info:"]

    lines.append(f"{'SN':<18}: {sn}")
    lines.append(f"{'temperature':<18}: {_format_int_or_na(temp)} C")
    lines.append(f"{'Vcc':<18}: {_format_int_or_na(vcc)} mV")

    for i in range(lane_count):
        label = f"TX Power{i}"
        lines.append(f"{label:<18}: {_format_float_or_na(tx_power[i], 'dBm')}")
        label = f"RX Power{i}"
        lines.append(f"{label:<18}: {_format_float_or_na(rx_power[i], 'dBm')}")

    for i in range(lane_count):
        label = f"TX Bias{i}"
        lines.append(f"{label:<18}: {_format_float_or_na(tx_bias[i], 'mA')}")

    lines.append(f"{'TX Los Flag':<18}: {_format_flag_or_na(tx_los)}")
    lines.append(f"{'RX Los Flag':<18}: {_format_flag_or_na(rx_los)}")
    lines.append(f"{'TX LoL Flag':<18}: {_format_flag_or_na(tx_lol)}")
    lines.append(f"{'RX LoL Flag':<18}: {_format_flag_or_na(rx_lol)}")

    for i in range(lane_count):
        label = f"Host SNR Lane{i}"
        lines.append(f"{label:<18}: {_format_float_or_na(host_snr[i], 'dB')}")

    for i in range(lane_count):
        label = f"Media SNR Lane{i}"
        lines.append(f"{label:<18}: {_format_float_or_na(media_snr[i], 'dB')}")
    lines.append(f"{'Vendor':<18}: {vendor}")
    lines.append(f"{'State':<18}: {state}")
    lines.append(f"{'Type':<18}: {optical_type}")
    lines.append(f"{'Lane Count':<18}: {lane_count}")
    return '\n'.join(lines)
