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

from typing import Iterable, Optional

from .command_parsers import (
    parse_bit_err_stats,
    parse_hikptool_serdes_info,
    parse_link_status,
    parse_optical_dom,
    parse_port_info_stats,
)
from .field_calculators import make_derived_fields_calculator
from .southbound import (
    CommandBasedSouthbound,
    CommandEntry,
    CompositeSouthbound,
    SouthboundInterface,
    ZeroBaselineSouthbound,
)


DEFAULT_COLLECTION_WINDOW = 60.0


def default_stat_command_entries() -> Iterable[CommandEntry]:
    """Return default ubctl commands that provide --stat fields."""
    return [
        CommandEntry(
            name="ubctl_port_info_stats",
            command=[
                "ubctl", "-c", "{chip_id}", "-p", "{port_id}",
                "-d", "{die_id}", "-m", "port_info",
            ],
            parser=parse_port_info_stats,
            fields=["sds_rate_bps", "tx_lane_num"],
        ),
        CommandEntry(
            name="ubctl_bit_err_stats",
            command=[
                "ubctl", "-c", "{chip_id}", "-p", "{port_id}",
                "-d", "{die_id}", "-m", "dl", "-f", "bit_err",
            ],
            parser=parse_bit_err_stats,
            fields=["cw_fec_cnt", "cw_uncorrect_cnt"],
        ),
        CommandEntry(
            name="hikptool_serdes_info_port_snr",
            command=[
                "hikptool", "serdes_info",
                "-i", "{chip_id}", "-s", "m{port_id+10}d0", "-n", "4", "-k",
            ],
            parser=parse_hikptool_serdes_info,
            fields=["port_snrlane"],
        ),
        CommandEntry(
            name="ubctl_port_link",
            command=[
                "ubctl", "-c", "{chip_id}", "-d", "{die_id}",
                "-p", "{port_id}", "-m", "port_link",
            ],
            parser=parse_link_status,
            fields=["link_status"],
        ),
        CommandEntry(
            name="hikptool_optical_dom",
            command=[
                "hikptool", "optical_dom",
                "-c", "{chip_id}", "-d", "{die_id}", "-p", "{port_id}",
            ],
            parser=parse_optical_dom,
            fields=[
                "optical_sn", "optical_vendor", "optical_state",
                "optical_type", "optical_type_name", "interface_code",
                "lane_count", "tx_los_flag", "rx_los_flag",
                "tx_lol_flag", "rx_lol_flag", "tx_power", "rx_power",
                "vcc", "temp", "tx_bias", "host_snr", "media_snr",
            ],
        ),
    ]


def build_command_southbound(entries: Optional[Iterable[CommandEntry]] = None) -> CommandBasedSouthbound:
    """Build a command-based southbound source from registered command entries."""
    southbound = CommandBasedSouthbound()
    for entry in default_stat_command_entries() if entries is None else entries:
        southbound.register_command(entry)
    return southbound


def build_hybrid_southbound(
    entries: Optional[Iterable[CommandEntry]] = None,
    baseline: SouthboundInterface = None,
    collection_window: float = DEFAULT_COLLECTION_WINDOW,
) -> CompositeSouthbound:
    """Build zero-baseline + command-overlay southbound."""
    baseline = baseline or ZeroBaselineSouthbound()
    overlay = build_command_southbound(entries)
    return CompositeSouthbound(
        baseline=baseline,
        overlay=overlay,
        calculators=[make_derived_fields_calculator(collection_window)],
    )
