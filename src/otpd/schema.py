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

"""Data-shape constants shared across the otpd package.

Lane widths and the field-name vocabulary used to shuttle data between
southbound parsers, the models, and formatters. Centralizing them here means
a future product with a different optical lane count (or a new field) changes
one place instead of being hunted across models.py, command_parsers.py,
southbound.py, and format.py.

This module depends on nothing else in the package (plain constants only), so
it is safe to import from any otpd module without risking a cycle.
"""

# Port SNR is reported per host lane (4 lanes).
PORT_SNR_LANE_COUNT = 4

# Optical module metrics are reported per media lane (up to 16 lanes).
OPTICAL_LANE_COUNT = 16

# PortInfo field names contributed by southbound commands.
PORT_FIELD_NAMES = {
    "port_snrlane", "cw_fec_cnt", "cw_uncorrect_cnt", "cw_total_cnt",
    "link_status",
}

# OpticalModuleInfo field names contributed by southbound commands.
OPTICAL_FIELD_NAMES = {
    "optical_sn", "optical_vendor", "optical_state", "optical_type",
    "optical_type_name", "interface_code", "lane_count",
    "tx_los_flag", "rx_los_flag", "tx_lol_flag",
    "rx_lol_flag", "tx_power", "rx_power", "vcc", "temp", "tx_bias",
    "host_snr", "media_snr",
}

# Optical type code -> human-readable name (hikptool optical_dom convention).
OPTICAL_TYPE_MAP = {
    0: "undefined",
    1: "MMF",
    2: "SMF",
    3: "Passive Cu",
    4: "Active Cables",
    5: "BASE-T",
}
