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

from unittest.mock import patch

import pytest

from src.otpd.models import OpticalModuleInfo, PortInfo
from src.otpd.system_interface import SystemInterface
import src.otpd.northbound as northbound_module
from src.otpd.northbound import (
    collect_port_data,
    format_port_snr_from_data,
    format_statistics_from_data,
    format_optical_info_from_data,
    get_port_snr,
    get_statistics,
    get_optical_info,
    get_ip_address,
    get_link_status,
    process_command,
)


class FakeSystemInterface(SystemInterface):
    def get_ip_address(self, port_id: int, chip_id: int, inet6: bool = False):
        if inet6:
            return "2001:0db8:0000:0000:0000:0000:0000:0001"
        return "192.0.2.1"


class TestNorthboundFunctions:
    """Test northbound interface functions."""

    def setup_method(self):
        self._original_system_interface = northbound_module.system_interface
        northbound_module.system_interface = FakeSystemInterface()

    def teardown_method(self):
        northbound_module.system_interface = self._original_system_interface

    @staticmethod
    def _collected_data(link_status="port 0 link UP"):
        return (
            PortInfo(
                port_id=0,
                chip_id=0,
                port_snrlane=[25.0] * 4,
                cw_fec_cnt=10,
                cw_uncorrect_cnt=1,
                cw_total_cnt=1010,
                link_status=link_status,
            ),
            OpticalModuleInfo(
                port_id=0,
                chip_id=0,
                optical_sn="LIVE-SN",
                optical_vendor="LIVE-VENDOR",
                optical_type_name="SMF Optical",
                temp=35,
                vcc=3300,
                tx_power=[1.0] * 16,
                rx_power=[2.0] * 16,
                interface_code=2,
                lane_count=4,
            ),
        )

    def test_collect_port_data_queries_southbound_without_cache(self):
        data = self._collected_data()
        with patch.object(northbound_module.southbound, 'get_port_data', return_value=data) as mock_get_port_data:
            result = collect_port_data(0, 1, 1)

        assert result == data
        mock_get_port_data.assert_called_once_with(0, 1, 1, use_cache=False)

    @pytest.mark.parametrize("port_id,chip_id,expected_contains", [
        (0, 0, "port SNR info"),
        (0, 0, "port SNR Lane"),
    ])
    def test_get_port_snr_normal_return(self, port_id, chip_id, expected_contains):
        with patch.object(northbound_module.southbound, 'get_port_data', return_value=self._collected_data()):
            result = get_port_snr(port_id, chip_id)

        assert result is not None
        assert expected_contains in result

    def test_get_port_snr_port_not_exist(self):
        with patch.object(northbound_module.southbound, 'get_port_data', return_value=None):
            result = get_port_snr(99999, 0)

        assert result is None

    def test_format_port_snr_from_collected_data(self):
        result = format_port_snr_from_data(0, 0, self._collected_data())

        assert result is not None
        assert "25.0000" in result

    @pytest.mark.parametrize("port_id,chip_id,expected_contains", [
        (0, 0, "error codeword statistics info"),
        (0, 0, "cw_total_cnt"),
        (0, 0, "cw_before_correct_cnt"),
        (0, 0, "cw_uncorrect_cnt"),
    ])
    def test_get_statistics_normal_return(self, port_id, chip_id, expected_contains):
        with patch.object(northbound_module.southbound, 'get_port_data', return_value=self._collected_data()):
            result = get_statistics(port_id, chip_id)

        assert result is not None
        assert expected_contains in result

    def test_get_statistics_port_not_exist(self):
        with patch.object(northbound_module.southbound, 'get_port_data', return_value=None):
            result = get_statistics(99999, 0)

        assert result is None

    def test_get_statistics_requests_cw_total_input_fields(self):
        data = self._collected_data()
        with patch.object(northbound_module.southbound, 'get_port_data', return_value=data) as mock_get_port_data:
            result = get_statistics(0, 0, 1)

        assert result is not None
        _, kwargs = mock_get_port_data.call_args
        assert kwargs["required_fields"] == {
            "sds_rate_bps", "tx_lane_num",
            "cw_fec_cnt", "cw_uncorrect_cnt", "cw_total_cnt",
        }

    def test_format_statistics_from_collected_data(self):
        result = format_statistics_from_data(0, 0, self._collected_data())

        assert result is not None
        assert "1010" in result

    @pytest.mark.parametrize("port_id,chip_id,expected_contains", [
        (0, 0, "optical info"),
        (0, 0, "SN"),
        (0, 0, "temperature"),
        (0, 0, "Vcc"),
        (0, 0, "TX Power"),
        (0, 0, "RX Power"),
    ])
    def test_get_optical_info_normal_return(self, port_id, chip_id, expected_contains):
        with patch.object(northbound_module.southbound, 'get_port_data', return_value=self._collected_data()):
            result = get_optical_info(port_id, chip_id)

        assert result is not None
        assert expected_contains in result

    def test_get_optical_info_port_not_exist(self):
        with patch.object(northbound_module.southbound, 'get_port_data', return_value=None):
            result = get_optical_info(99999, 0)

        assert result is None

    def test_get_optical_info_uses_real_type_and_lane_count_fields(self):
        data = (
            PortInfo(port_id=0, chip_id=0),
            OpticalModuleInfo(
                port_id=0,
                chip_id=0,
                optical_sn="LIVE-SN",
                optical_vendor="LIVE-VENDOR",
                optical_type_name="SMF Optical",
                lane_count=8,
                tx_power=[0.0] * 16,
                rx_power=[0.0] * 16,
                tx_bias=[0.0] * 16,
                host_snr=[0.0] * 16,
                media_snr=[0.0] * 16,
            ),
        )

        result = format_optical_info_from_data(0, 0, data)

        assert result is not None
        assert "Type              : SMF Optical" in result
        assert "Lane Count        : 8" in result

    def test_get_optical_info_prints_stub_zero_values_for_8_lanes(self):
        data = (
            PortInfo(port_id=0, chip_id=0),
            OpticalModuleInfo(
                port_id=0,
                chip_id=0,
                optical_sn="XXXXX",
                optical_vendor="XXXXX",
                optical_type_name="XXXXX",
                lane_count=8,
                temp=0,
                vcc=0,
                tx_power=[0.0] * 16,
                rx_power=[0.0] * 16,
                tx_bias=[0.0] * 16,
                host_snr=[0.0] * 16,
                media_snr=[0.0] * 16,
            ),
        )

        result = format_optical_info_from_data(0, 0, data)

        assert result is not None
        assert "SN                : XXXXX" in result
        assert "Vendor            : XXXXX" in result
        assert "Type              : XXXXX" in result
        assert "Lane Count        : 8" in result
        assert "temperature       :        0 C" in result
        assert "Vcc               :        0 mV" in result
        assert "TX Power7         :  0.0000 dBm" in result
        assert "RX Power7         :  0.0000 dBm" in result
        assert "TX Bias7          :  0.0000 mA" in result
        assert "Host SNR Lane7    :  0.0000 dB" in result
        assert "Media SNR Lane7   :  0.0000 dB" in result

    def test_get_optical_info_does_not_infer_lane_count_from_interface_code(self):
        data = (
            PortInfo(port_id=0, chip_id=0),
            OpticalModuleInfo(
                port_id=0,
                chip_id=0,
                optical_type_name="SMF Optical",
                interface_code=0x0E,
                lane_count=0,
                tx_power=[1.0] * 16,
                rx_power=[2.0] * 16,
                tx_bias=[3.0] * 16,
                host_snr=[4.0] * 16,
                media_snr=[5.0] * 16,
            ),
        )

        result = format_optical_info_from_data(0, 0, data)

        assert result is not None
        assert "Lane Count        : 0" in result
        assert "TX Power0" not in result

    def test_get_optical_info_outputs_na_for_failed_numeric_fields(self):
        data = (
            PortInfo(port_id=0, chip_id=0),
            OpticalModuleInfo(
                port_id=0,
                chip_id=0,
                optical_type_name="SMF Optical",
                lane_count=1,
                temp=None,
                vcc=None,
                tx_power=[None] + [0.0] * 15,
                rx_power=[-2.0] + [0.0] * 15,
                tx_bias=[None] + [0.0] * 15,
                host_snr=[25.0] + [0.0] * 15,
                media_snr=[None] + [0.0] * 15,
                tx_los_flag=None,
                rx_los_flag=0,
                tx_lol_flag=None,
                rx_lol_flag=0,
            ),
        )

        result = format_optical_info_from_data(0, 0, data)

        assert result is not None
        assert "temperature       :      N/A" in result
        assert "Vcc               :      N/A" in result
        assert "TX Power0         :        N/A dBm" in result
        assert "TX Los Flag       :        N/A" in result

    def test_get_ip_address_formats(self):
        result = get_ip_address(0, 0, inet6=True)

        assert result is not None
        assert "2001:0db8" in result

    def test_get_ip_address_does_not_collect_southbound_data(self):
        with patch.object(northbound_module.southbound, 'get_port_data') as mock_get_port_data:
            result = get_ip_address(0, 0, inet6=True)

        assert result is not None
        mock_get_port_data.assert_not_called()

    def test_get_link_status_normal_return(self):
        with patch.object(northbound_module.southbound, 'get_port_data', return_value=self._collected_data("LINK STATUS OK")):
            result = get_link_status(0, 0)

        assert result == "LINK STATUS OK"

    def test_get_link_status_empty_string_returns_none(self):
        result = process_command(0, 0, 0, command='link_stat', data=self._collected_data(""))

        assert result is None

    def test_get_link_status_collect_miss_returns_none(self):
        with patch.object(northbound_module.southbound, 'get_port_data', return_value=None):
            result = get_link_status(0, 0)

        assert result is None

    @pytest.mark.parametrize("command,expected_in_result", [
        ('port_snr', "port SNR info"),
        ('stat', "error codeword statistics info"),
        ('optical', "optical info"),
        ('ip', "ip info"),
        ('link_stat', "port 0 link UP"),
    ])
    def test_process_command_routing_with_collected_data(self, command, expected_in_result):
        with patch.object(northbound_module.southbound, 'get_port_data') as mock_get_port_data:
            result = process_command(0, 0, 0, command=command, inet6=True, data=self._collected_data())

        assert result is not None
        assert expected_in_result in result
        mock_get_port_data.assert_not_called()

    def test_process_command_collects_when_data_not_provided(self):
        with patch.object(northbound_module.southbound, 'get_port_data', return_value=self._collected_data()) as mock_get_port_data:
            result = process_command(0, 0, 1, command='stat')

        assert result is not None
        mock_get_port_data.assert_called_once_with(0, 0, 1, use_cache=False)

    def test_process_command_unknown_command(self):
        result = process_command(0, 0, 0, command='unknown_command')
        assert result is None
