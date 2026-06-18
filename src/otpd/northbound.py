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
from typing import Optional, Tuple, Set
from .southbound import southbound
from .system_interface import system_interface
from .models import get_optical_type_name
from .models import OpticalModuleInfo, PortInfo
from .format import format_port_snr_output, format_stat_output, format_optical_output

logger = logging.getLogger(__name__)


CollectedPortData = Tuple[PortInfo, OpticalModuleInfo]


def collect_port_data(port_id: int, chip_id: int, die_id: int = 0, required_fields: Optional[Set[str]] = None) -> Optional[CollectedPortData]:
    """Collect fresh southbound data for one port/chip/die query.

    Args:
        required_fields: If provided, only execute commands that can contribute
            these fields. Avoids running unrelated commands.
    """
    kwargs = {}
    if required_fields is not None:
        kwargs["required_fields"] = required_fields
    return southbound.get_port_data(port_id, chip_id, die_id, use_cache=False, **kwargs)


def format_port_snr_from_data(port_id: int, chip_id: int, data: Optional[CollectedPortData]) -> Optional[str]:
    """Format port SNR information from collected data."""
    if data is None:
        logger.error(f"No data for port {port_id} chip {chip_id}")
        return None

    port_info, _ = data
    return format_port_snr_output(port_id, chip_id, port_info.port_snrlane)


def get_port_snr(port_id: int, chip_id: int, die_id: int = 0) -> Optional[str]:
    """Collect and format port SNR information."""
    data = collect_port_data(port_id, chip_id, die_id, required_fields={"port_snrlane"})
    return format_port_snr_from_data(port_id, chip_id, data)


def format_statistics_from_data(port_id: int, chip_id: int, data: Optional[CollectedPortData]) -> Optional[str]:
    """Format error codeword statistics from collected data."""
    if data is None:
        logger.error(f"No data for port {port_id} chip {chip_id}")
        return None

    port_info, _ = data
    return format_stat_output(
        port_id,
        chip_id,
        port_info.cw_total_cnt,
        port_info.cw_fec_cnt,
        port_info.cw_uncorrect_cnt
    )


def get_statistics(port_id: int, chip_id: int, die_id: int = 0) -> Optional[str]:
    """Collect and format error codeword statistics."""
    data = collect_port_data(
        port_id,
        chip_id,
        die_id,
        required_fields={
            "sds_rate_bps", "tx_lane_num",
            "cw_fec_cnt", "cw_uncorrect_cnt", "cw_total_cnt",
        },
    )
    return format_statistics_from_data(port_id, chip_id, data)


def format_optical_info_from_data(port_id: int, chip_id: int, data: Optional[CollectedPortData]) -> Optional[str]:
    """Format optical module information from collected data."""
    if data is None:
        logger.error(f"No data for port {port_id} chip {chip_id}")
        return None

    _, optical_info = data
    lane_count = optical_info.lane_count
    optical_type = optical_info.optical_type_name or get_optical_type_name(optical_info.optical_type)

    return format_optical_output(
        port_id,
        chip_id,
        optical_info.optical_sn,
        optical_info.optical_vendor,
        optical_info.optical_state,
        optical_type,
        lane_count,
        optical_info.temp,
        optical_info.vcc,
        optical_info.tx_power,
        optical_info.rx_power,
        optical_info.tx_bias,
        optical_info.host_snr,
        optical_info.media_snr,
        optical_info.tx_los_flag,
        optical_info.rx_los_flag,
        optical_info.tx_lol_flag,
        optical_info.rx_lol_flag
    )


def get_optical_info(port_id: int, chip_id: int, die_id: int = 0) -> Optional[str]:
    """Collect and format optical module information."""
    data = collect_port_data(port_id, chip_id, die_id, required_fields={
        "optical_sn", "optical_vendor", "optical_state", "optical_type",
        "optical_type_name", "interface_code", "lane_count",
        "tx_los_flag", "rx_los_flag", "tx_lol_flag", "rx_lol_flag",
        "tx_power", "rx_power", "vcc", "temp", "tx_bias", "host_snr", "media_snr",
    })
    return format_optical_info_from_data(port_id, chip_id, data)


def get_ip_address(port_id: int, chip_id: int, inet6: bool = False) -> Optional[str]:
    """Get IP address for port."""
    address = system_interface.get_ip_address(port_id, chip_id, inet6)
    if address is None:
        return None

    lines = ["ip info:"]
    for ip in address.split('\n'):
        lines.append(f"{'ipv6_address':<20}: {ip}")
    return '\n'.join(lines)


def format_link_status_from_data(port_id: int, chip_id: int, data: Optional[CollectedPortData]) -> Optional[str]:
    """Format link status information from collected data."""
    if data is None:
        logger.error(f"No data for port {port_id} chip {chip_id}")
        return None

    port_info, _ = data
    return port_info.link_status if port_info.link_status else None


def get_link_status(port_id: int, chip_id: int, die_id: int = 0) -> Optional[str]:
    """Collect and format link status information."""
    data = collect_port_data(port_id, chip_id, die_id, required_fields={"link_status"})
    return format_link_status_from_data(port_id, chip_id, data)


# Maps a northbound command name to its data-driven formatter. Each formatter
# takes (port_id, chip_id, collected_data); ``process_command`` supplies the
# collected data (fetching it on demand). ``ip`` is handled separately because
# it takes ``inet6`` instead of collected data.
_COMMAND_FORMATTERS = {
    'port_snr': format_port_snr_from_data,
    'stat': format_statistics_from_data,
    'optical': format_optical_info_from_data,
    'link_stat': format_link_status_from_data,
}


def process_command(
    port_id: int,
    chip_id: int,
    die_id: int = 0,
    command: str = '',
    inet6: bool = False,
    data: Optional[CollectedPortData] = None,
) -> Optional[str]:
    """Process a northbound command."""
    if command == 'ip':
        return get_ip_address(port_id, chip_id, inet6)

    formatter = _COMMAND_FORMATTERS.get(command)
    if formatter is None:
        logger.warning(f"Unknown command: {command}")
        return None
    return formatter(port_id, chip_id, data or collect_port_data(port_id, chip_id, die_id))
