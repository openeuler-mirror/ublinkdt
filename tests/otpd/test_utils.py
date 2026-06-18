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

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.otpd.format import (
    format_port_snr_output,
    format_stat_output,
    format_optical_output,
)


class TestFormattingFunctions:
    """Test formatting functions."""

    def test_format_port_snr_output_fixed_4_lanes(self):
        """Test format_port_snr_output always displays 4 lanes."""
        snr_lanes = [25.0, 26.3, 27.1, 25.8, 26.0, 27.5, 25.2, 26.8]
        result = format_port_snr_output(0, 0, snr_lanes)
        lines = result.strip().split('\n')
        assert "port SNR info" in result
        assert "port SNR Lane0" in result
        assert "port SNR Lane3" in result
        assert "port SNR Lane4" not in result
        assert len(lines) == 5

    def test_format_port_snr_output_last_4_zero(self):
        """Test format_port_snr_output when last 4 lanes are exactly zero."""
        snr_lanes = [25.0, 26.3, 27.1, 25.8, 0.0, 0.0, 0.0, 0.0]
        result = format_port_snr_output(0, 0, snr_lanes)
        lines = result.strip().split('\n')
        assert "port SNR Lane4" not in result
        assert len(lines) == 5

    def test_format_stat_output(self):
        """Test format_stat_output formatting."""
        result = format_stat_output(0, 0, 1234567890, 1234567890, 1234)
        assert "error codeword statistics info" in result
        assert "cw_total_cnt" in result
        assert "cw_before_correct_cnt" in result
        assert "cw_uncorrect_cnt" in result

    @pytest.mark.parametrize("lane_count", [2, 4, 8, 16])
    def test_format_optical_output_different_lanes(self, lane_count):
        """Test format_optical_output with different lane counts."""
        tx_power = [-3.0 + i * 0.1 if i < lane_count else 0.0 for i in range(16)]
        rx_power = [-8.0 + i * 0.1 if i < lane_count else 0.0 for i in range(16)]
        tx_bias = [45.0 + i * 1.0 if i < lane_count else 0.0 for i in range(16)]
        host_snr = [2.5 + i * 0.1 if i < lane_count else 0.0 for i in range(16)]
        media_snr = [2.8 + i * 0.1 if i < lane_count else 0.0 for i in range(16)]

        result = format_optical_output(
            port_id=0,
            chip_id=0,
            sn='OEO-2024-TEST',
            vendor='HuaweiOptic',
            state=1,
            optical_type='SMF',
            lane_count=lane_count,
            temp=35,
            vcc=3300,
            tx_power=tx_power,
            rx_power=rx_power,
            tx_bias=tx_bias,
            host_snr=host_snr,
            media_snr=media_snr,
            tx_los=0,
            rx_los=0,
            tx_lol=0,
            rx_lol=0
        )
        assert "SN" in result
        assert "Vendor" in result
        assert "State" in result
        assert "Type" in result
        assert "Lane Count" in result
        assert "Lane0" in result
        assert f"Lane{lane_count - 1}" in result
