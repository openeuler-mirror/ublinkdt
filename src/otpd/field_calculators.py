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
from typing import Any, Dict, Callable, Optional


logger = logging.getLogger(__name__)


FieldCalculator = Callable[[Dict[str, Any]], None]


def calculate_cw_total_cnt(fields: Dict[str, Any], collection_window: Optional[float] = None) -> None:
    """Recalculate cw_total_cnt from currently available fields.

    Use current scan data from the port_info command:
    single lane rate * collection window * lane count.
    """
    rate_bps = fields.get("sds_rate_bps")
    lane_count = fields.get("tx_lane_num")
    window = collection_window if collection_window is not None else fields.get("collection_window")
    if rate_bps is not None and lane_count is not None and window is not None:
        fields["cw_total_cnt"] = int(float(rate_bps) * float(window) * int(lane_count))
        return

    fields["cw_total_cnt"] = 0
    missing = []
    if rate_bps is None:
        missing.append("sds_rate_bps")
    if lane_count is None:
        missing.append("tx_lane_num")
    if window is None:
        missing.append("collection_window")
    logger.warning("Cannot calculate cw_total_cnt: missing %s", ", ".join(missing))


def calculate_derived_fields(fields: Dict[str, Any]) -> None:
    """Run the default production-safe derived field calculations."""
    calculate_cw_total_cnt(fields)


def make_derived_fields_calculator(collection_window: float) -> FieldCalculator:
    """Create a calculator bound to a cw_total_cnt collection window."""
    def calculator(fields: Dict[str, Any]) -> None:
        calculate_cw_total_cnt(fields, collection_window=collection_window)

    return calculator
