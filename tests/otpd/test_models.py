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
from src.otpd.models import PortInfo, OpticalModuleInfo


class TestPortInfo:
    """Test cases for PortInfo data model."""

    def test_normal_initialization(self):
        """Test PortInfo normal initialization with valid parameters."""
        port_info = PortInfo(
            port_id=0,
            chip_id=0,
            port_snrlane=[25.0, 26.3, 27.1, 25.8],
            cw_fec_cnt=1234567890,
            cw_uncorrect_cnt=1234,
            cw_total_cnt=1234567890 + 1234 * 1000
        )
        assert port_info.port_id == 0
        assert port_info.chip_id == 0
        assert len(port_info.port_snrlane) == 4
        assert port_info.cw_fec_cnt == 1234567890
        assert port_info.cw_uncorrect_cnt == 1234
        assert port_info.validate() is True

    def test_default_initialization(self):
        """Test PortInfo default initialization with only port_id and chip_id."""
        port_info = PortInfo(port_id=0, chip_id=0)
        assert port_info.port_id == 0
        assert port_info.chip_id == 0
        assert len(port_info.port_snrlane) == 4
        assert all(snr == 0.0 for snr in port_info.port_snrlane)
        assert port_info.cw_fec_cnt == 0
        assert port_info.cw_uncorrect_cnt == 0
        assert port_info.validate() is True

    def test_negative_port_id_validation(self):
        """Test PortInfo validation with negative port_id."""
        port_info = PortInfo(port_id=-1, chip_id=0)
        assert port_info.validate() is False

    def test_invalid_chip_id_validation(self):
        """Test PortInfo validation with invalid chip_id."""
        port_info = PortInfo(port_id=0, chip_id=2)
        assert port_info.validate() is False

    def test_wrong_lane_count_correction(self):
        """Test that __post_init__ corrects wrong lane count."""
        port_info = PortInfo(port_id=0, chip_id=0, port_snrlane=[1.0, 2.0, 3.0])
        assert len(port_info.port_snrlane) == 4

    @pytest.mark.parametrize("data", [
        {'port_id': 0, 'chip_id': 0, 'port_snrlane': [25.0] * 4, 'cw_fec_cnt': 1234567890, 'cw_uncorrect_cnt': 1234, 'cw_total_cnt': 1234567890 + 1234 * 1000, 'link_status': ''},
    ])
    def test_serialization_roundtrip(self, data):
        """Test PortInfo serialization and deserialization."""
        port_info = PortInfo.from_dict(data)
        assert port_info.port_id == data['port_id']
        assert port_info.chip_id == data['chip_id']
        assert port_info.cw_fec_cnt == data['cw_fec_cnt']
        result = port_info.to_dict()
        assert result['port_id'] == data['port_id']
        assert result['chip_id'] == data['chip_id']
        assert result['cw_fec_cnt'] == data['cw_fec_cnt']

    @pytest.mark.parametrize("cw_fec_cnt,cw_uncorrect_cnt", [
        (0, 0),
        (2**64 - 1, 2**64 - 1),
    ])
    def test_boundary_values(self, cw_fec_cnt, cw_uncorrect_cnt):
        """Test PortInfo with boundary values."""
        port_info = PortInfo(port_id=0, chip_id=0, cw_fec_cnt=cw_fec_cnt, cw_uncorrect_cnt=cw_uncorrect_cnt)
        assert port_info.cw_total_cnt >= 0


class TestOpticalModuleInfo:
    """Test cases for OpticalModuleInfo data model."""

    def test_normal_initialization(self):
        """Test OpticalModuleInfo normal initialization."""
        optical_info = OpticalModuleInfo(
            port_id=0,
            chip_id=0,
            optical_sn='OEO-2024-1234',
            optical_vendor='HuaweiOptic',
            optical_state=1,
            optical_type=2,
            interface_code=3,
            tx_los_flag=1,
            rx_los_flag=0,
            tx_lol_flag=0,
            rx_lol_flag=0,
            vcc=3300,
            temp=35
        )
        assert optical_info.port_id == 0
        assert optical_info.chip_id == 0
        assert optical_info.optical_sn == 'OEO-2024-1234'
        assert optical_info.optical_vendor == 'HuaweiOptic'
        assert optical_info.interface_code == 3
        assert optical_info.validate() is True

    def test_16_channel_data_processing(self):
        """Test OpticalModuleInfo with all 16 channels."""
        optical_info = OpticalModuleInfo(
            port_id=0,
            chip_id=0,
            interface_code=0x10,
            tx_power=[-3.0 + i * 0.1 for i in range(16)],
            rx_power=[-8.0 + i * 0.1 for i in range(16)],
            tx_bias=[45.0 + i * 1.0 for i in range(16)],
            host_snr=[2.5 + i * 0.1 for i in range(16)],
            media_snr=[2.8 + i * 0.1 for i in range(16)]
        )
        assert len(optical_info.tx_power) == 16
        assert optical_info.validate() is True

    def test_serialization_roundtrip(self):
        """Test OpticalModuleInfo serialization and deserialization."""
        data = {
            'port_id': 0,
            'chip_id': 0,
            'optical_sn': 'OEO-2024-1234',
            'optical_vendor': 'HuaweiOptic',
            'optical_state': 1,
            'optical_type': 2,
            'interface_code': 3,
            'tx_los_flag': 1,
            'rx_los_flag': 0,
            'tx_lol_flag': 0,
            'rx_lol_flag': 0,
            'tx_power': [-3.0] * 16,
            'rx_power': [-8.0] * 16,
            'vcc': 3300,
            'temp': 35,
            'tx_bias': [45.0] * 16,
            'host_snr': [2.5] * 16,
            'media_snr': [2.8] * 16
        }
        optical_info = OpticalModuleInfo.from_dict(data)
        assert optical_info.port_id == 0
        assert optical_info.chip_id == 0
        assert optical_info.optical_sn == 'OEO-2024-1234'
        result = optical_info.to_dict()
        assert result['port_id'] == 0
        assert result['chip_id'] == 0
        assert result['interface_code'] == 3
