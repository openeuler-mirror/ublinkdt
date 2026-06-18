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

import importlib
import os
import pytest
from unittest.mock import patch, MagicMock
from src.otpd.southbound import (
    SouthboundInterface, ZeroBaselineSouthbound,
    CommandEntry, CommandBasedSouthbound, CompositeSouthbound,
    get_southbound_interface, is_debug_mode, is_stub_mode,
    reset_query_context, set_query_context,
)
from src.otpd.models import PortInfo, OpticalModuleInfo
from src.otpd.command_parsers import (
    parse_bit_err_stats,
    parse_hikptool_serdes_info,
    parse_hex_or_unset,
    parse_lane_count,
    parse_link_status,
    parse_optical_dom,
    parse_port_info_stats,
    parse_rate_to_bps,
)
from src.otpd.field_calculators import calculate_derived_fields, make_derived_fields_calculator
from src.otpd.southbound_commands import build_command_southbound

runtime_module = importlib.import_module("src.otpd.runtime")


@pytest.fixture
def stub_mode_off(monkeypatch):
    """Ensure debug-gated stub mode is off for the test."""
    monkeypatch.setattr(runtime_module, "DEBUG_BUILD", False)
    monkeypatch.delenv("OTPD_STUB_MODE", raising=False)
    yield


@pytest.fixture
def stub_mode_on(monkeypatch):
    """Enable debug-gated stub mode for the test."""
    monkeypatch.setattr(runtime_module, "DEBUG_BUILD", True)
    monkeypatch.setenv("OTPD_STUB_MODE", "1")
    yield


@pytest.fixture
def debug_mode_on(monkeypatch):
    """Enable debug mode while letting tests choose the stub flag value."""
    monkeypatch.setattr(runtime_module, "DEBUG_BUILD", True)
    yield


class TestZeroBaselineSouthbound:
    """Test ZeroBaselineSouthbound returns all-zero data."""

    def setup_method(self):
        ZeroBaselineSouthbound._data_cache.clear()

    def test_returns_all_zero_port_info(self):
        sb = ZeroBaselineSouthbound()
        result = sb.get_port_data(0, 0)
        assert result is not None
        port_info, optical_info = result
        assert port_info.port_id == 0
        assert port_info.chip_id == 0
        assert all(s == 0.0 for s in port_info.port_snrlane)
        assert port_info.cw_fec_cnt == 0

    def test_returns_all_zero_optical_info(self):
        sb = ZeroBaselineSouthbound()
        result = sb.get_port_data(0, 0)
        assert result is not None
        _, optical_info = result
        assert optical_info.optical_sn == ""
        assert optical_info.temp == 0
        assert all(p == 0.0 for p in optical_info.tx_power)


class TestCommandEntry:
    """Test CommandEntry dataclass."""

    def test_default_values(self):
        entry = CommandEntry(
            name="test",
            command=["echo", "hello"],
            parser=lambda x: {},
        )
        assert entry.timeout == 10.0
        assert entry.enabled is True
        assert entry.output_mode == "text"

    def test_custom_values(self):
        entry = CommandEntry(
            name="test",
            command=["tool"],
            parser=lambda x: {},
            timeout=5.0,
            enabled=False,
        )
        assert entry.timeout == 5.0
        assert entry.enabled is False

    def test_output_mode_binary(self):
        entry = CommandEntry(
            name="test",
            command=["tool"],
            parser=lambda x: {},
            output_mode="binary",
        )
        assert entry.output_mode == "binary"


class TestCommandBasedSouthbound:
    """Test CommandBasedSouthbound."""

    def setup_method(self):
        """Clear class-level cache before each test."""
        CommandBasedSouthbound._data_cache.clear()

    @staticmethod
    def _make_port_parser():
        """Return a parser that simulates port data from text output."""
        def parser(stdout: str):
            result = {}
            for line in stdout.strip().split('\n'):
                if '=' not in line:
                    continue
                key, value = line.split('=', 1)
                if key == 'FecCnt':
                    result['cw_fec_cnt'] = int(value)
                elif key == 'UncorrectCnt':
                    result['cw_uncorrect_cnt'] = int(value)
            return result
        return parser

    @staticmethod
    def _make_optical_parser():
        """Return a parser that simulates optical data from text output."""
        def parser(stdout: str):
            result = {}
            for line in stdout.strip().split('\n'):
                if '=' not in line:
                    continue
                key, value = line.split('=', 1)
                if key == 'SN':
                    result['optical_sn'] = value
                elif key == 'InterfaceCode':
                    result['interface_code'] = int(value)
                elif key == 'Temp':
                    result['temp'] = int(value)
            return result
        return parser

    def test_register_and_unregister(self):
        sb = CommandBasedSouthbound()
        entry = CommandEntry(
            name="test_cmd", command=["echo"], parser=lambda x: {},
        )
        sb.register_command(entry)
        assert "test_cmd" in sb._command_registry
        sb.unregister_command("test_cmd")
        assert "test_cmd" not in sb._command_registry

    @patch('src.otpd.southbound.subprocess.run')
    def test_get_port_data_text_format_with_parser(self, mock_run):
        """Test command execution with text output parsed via parser."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "FecCnt=1234567890\nUncorrectCnt=1234\n"
        mock_run.return_value = mock_proc

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="port_tool",
            command=["get-data", "--port", "{port_id}"],
            parser=self._make_port_parser(),
        ))

        result = sb.get_port_data(0, 0)
        assert result is not None
        port_info, optical_info = result
        assert port_info.cw_fec_cnt == 1234567890
        assert port_info.cw_uncorrect_cnt == 1234

    @patch('src.otpd.southbound.subprocess.run')
    def test_get_port_data_multi_command_merge(self, mock_run):
        """Test multiple commands contributing different fields."""
        def side_effect_first(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = "FecCnt=100\nUncorrectCnt=5\n"
            return proc

        def side_effect_second(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = "SN=ABC123\nInterfaceCode=14\nTemp=35\n"
            return proc

        mock_run.side_effect = [side_effect_first(), side_effect_second()]

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="errors",
            command=["get-errors"],
            parser=self._make_port_parser(),
        ))
        sb.register_command(CommandEntry(
            name="optical",
            command=["get-optical"],
            parser=self._make_optical_parser(),
        ))

        result = sb.get_port_data(0, 0)
        assert result is not None
        port_info, optical_info = result
        assert port_info.cw_fec_cnt == 100
        assert optical_info.optical_sn == "ABC123"
        assert optical_info.interface_code == 14

    @patch('src.otpd.southbound.subprocess.run')
    def test_get_port_data_command_failure(self, mock_run):
        """Test command with non-zero returncode returns empty dict."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "error"
        mock_run.return_value = mock_proc

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="fail_cmd",
            command=["failing-tool"],
            parser=lambda x: {"cw_fec_cnt": 1},
        ))

        result = sb.get_port_data(0, 0)
        # Command failed, merged dict is empty, returns None
        assert result is None

    @patch('src.otpd.southbound.subprocess.run')
    def test_get_port_data_command_failure_stub_mode_is_not_error(self, mock_run, caplog, stub_mode_on):
        """Test non-zero returncode is stubbed without error logs in stub mode."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "error"
        mock_run.return_value = mock_proc

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="fail_cmd",
            command=["failing-tool"],
            parser=lambda x: {"cw_fec_cnt": 1},
            fields=["cw_fec_cnt"],
        ))

        with caplog.at_level("WARNING", logger="src.otpd.southbound"):
            result = sb.get_port_data(0, 0)

        assert result is None
        assert not [record for record in caplog.records if record.name == "src.otpd.southbound"]

    @patch('src.otpd.southbound.subprocess.run')
    def test_get_port_data_command_timeout(self, mock_run):
        """Test command timeout returns empty dict."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="slow_cmd",
            command=["slow-tool"],
            parser=lambda x: {},
        ))

        result = sb.get_port_data(0, 0)
        assert result is None

    @patch('src.otpd.southbound.subprocess.run')
    def test_get_port_data_command_not_found_production_mode(self, mock_run, stub_mode_off):
        """Test FileNotFoundError is re-raised in production mode."""
        mock_run.side_effect = FileNotFoundError("not found")

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="missing_cmd",
            command=["nonexistent-tool"],
            parser=lambda x: {},
            fields=["cw_fec_cnt"],
        ))

        with pytest.raises(FileNotFoundError):
            sb.get_port_data(0, 0)

    @patch('src.otpd.southbound.subprocess.run')
    def test_get_port_data_command_not_found_stub_mode(self, mock_run, stub_mode_on):
        """Test FileNotFoundError returns empty in stub mode."""
        mock_run.side_effect = FileNotFoundError("not found")

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="missing_cmd",
            command=["nonexistent-tool"],
            parser=lambda x: {},
            fields=["cw_fec_cnt"],
        ))

        result = sb.get_port_data(0, 0)
        assert result is None

    @patch('src.otpd.southbound.subprocess.run')
    def test_cache_used_on_second_call(self, mock_run):
        """Test second call uses cache without re-executing command."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "FecCnt=999\n"
        mock_run.return_value = mock_proc

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="cached",
            command=["tool"],
            parser=self._make_port_parser(),
        ))

        result1 = sb.get_port_data(0, 0)
        result2 = sb.get_port_data(0, 0)

        assert result1 is not None
        assert result2 is not None
        # subprocess.run called only once
        assert mock_run.call_count == 1

    @patch('src.otpd.southbound.subprocess.run')
    def test_cache_bypassed_with_use_cache_false(self, mock_run):
        """Test use_cache=False forces re-execution."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "FecCnt=100\n"
        mock_run.return_value = mock_proc

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="fresh",
            command=["tool"],
            parser=self._make_port_parser(),
        ))

        sb.get_port_data(0, 0)
        sb.get_port_data(0, 0, use_cache=False)

        assert mock_run.call_count == 2

    @patch('src.otpd.southbound.subprocess.run')
    def test_get_port_data_filters_by_required_fields(self, mock_run):
        """Test get_port_data only executes commands relevant to required fields."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "FecCnt=100\n"
        mock_run.return_value = mock_proc

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="fec",
            command=["fec-tool"],
            parser=self._make_port_parser(),
            fields=["cw_fec_cnt"],
        ))
        sb.register_command(CommandEntry(
            name="optical",
            command=["optical-tool"],
            parser=self._make_optical_parser(),
            fields=["optical_sn"],
        ))

        result = sb.get_port_data(0, 0, required_fields={"cw_fec_cnt"})

        assert result is not None
        port_info, _ = result
        assert port_info.cw_fec_cnt == 100
        mock_run.assert_called_once()
        assert mock_run.call_args.args[0] == ["fec-tool"]

    def test_disabled_command_skipped(self):
        """Test that disabled commands are skipped."""
        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="disabled",
            command=["echo"],
            parser=lambda x: {"cw_fec_cnt": 1},
            enabled=False,
        ))

        with patch('src.otpd.southbound.subprocess.run') as mock_run:
            result = sb.get_port_data(0, 0)
            assert result is None
            mock_run.assert_not_called()

    def test_format_command_substitutes_params(self):
        cmd = CommandBasedSouthbound._format_command(
            ["tool", "--port", "{port_id}", "--chip", "{chip_id}", "--die", "{die_id}"],
            0, 1, 0,
        )
        assert cmd == ["tool", "--port", "0", "--chip", "1", "--die", "0"]

    def test_format_command_supports_integer_offsets(self):
        cmd = CommandBasedSouthbound._format_command(
            ["hikptool", "serdes_info", "-i", "{chip_id}", "-s", "m{port_id+10}d0"],
            1, 0, 0,
        )
        assert cmd == ["hikptool", "serdes_info", "-i", "0", "-s", "m11d0"]

    def test_format_command_no_params(self):
        cmd = CommandBasedSouthbound._format_command(["echo", "hello"], 0, 0, 0)
        assert cmd == ["echo", "hello"]

    def test_assemble_port_info(self):
        merged = {
            "port_snrlane": [25.0] * 4,
            "cw_fec_cnt": 100,
            "cw_uncorrect_cnt": 5,
            "cw_total_cnt": 105,
        }
        port_info = CommandBasedSouthbound._assemble_port_info(0, 0, merged)
        assert port_info.port_id == 0
        assert port_info.cw_fec_cnt == 100
        assert port_info.cw_total_cnt == 105

    def test_assemble_port_info_does_not_use_temporary_cw_total_formula(self):
        merged = {"cw_fec_cnt": 100, "cw_uncorrect_cnt": 5}
        port_info = CommandBasedSouthbound._assemble_port_info(0, 0, merged)
        assert port_info.cw_fec_cnt == 100
        assert port_info.cw_total_cnt == 0

    def test_assemble_optical_info(self):
        merged = {
            "optical_sn": "TEST-SN",
            "interface_code": 14,
            "temp": 35,
        }
        optical_info = CommandBasedSouthbound._assemble_optical_info(0, 0, merged)
        assert optical_info.optical_sn == "TEST-SN"
        assert optical_info.interface_code == 14
        assert optical_info.temp == 35

    @patch('src.otpd.southbound.subprocess.run')
    def test_binary_mode_passes_bytes_to_parser(self, mock_run):
        """Test binary mode subprocess stdout is passed as bytes to parser."""
        binary_stdout = b'\x00' * 56
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = binary_stdout
        mock_run.return_value = mock_proc

        received_bytes = []

        def binary_parser(stdout):
            received_bytes.append(stdout)
            return {"cw_fec_cnt": 42}

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="binary_cmd",
            command=["read-bin"],
            parser=binary_parser,
            output_mode="binary",
        ))

        sb.get_port_data(0, 0)
        assert len(received_bytes) == 1
        assert received_bytes[0] == binary_stdout
        assert isinstance(received_bytes[0], bytes)

    @patch('src.otpd.southbound.subprocess.run')
    def test_mixed_text_and_binary_merge(self, mock_run):
        """Test merging text and binary command results."""
        def side_effect_first(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = "FecCnt=500\nUncorrectCnt=2\n"
            return proc

        def side_effect_second(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = "SN=MIXED-TEST\nTemp=40\nInterfaceCode=14\n"
            return proc

        mock_run.side_effect = [side_effect_first(), side_effect_second()]

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="text_cmd",
            command=["text-tool"],
            parser=self._make_port_parser(),
            output_mode="text",
        ))
        sb.register_command(CommandEntry(
            name="text_optical",
            command=["optical-tool"],
            parser=self._make_optical_parser(),
            output_mode="text",
        ))

        result = sb.get_port_data(0, 0)
        assert result is not None
        port_info, optical_info = result
        assert port_info.cw_fec_cnt == 500
        assert optical_info.optical_sn == "MIXED-TEST"
        assert optical_info.interface_code == 14
        assert optical_info.temp == 40

    @patch('src.otpd.southbound.subprocess.run')
    def test_binary_mode_timeout_returns_empty(self, mock_run):
        """Test binary command timeout returns empty dict."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="slow-bin", timeout=5)

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="slow_binary",
            command=["slow-bin-tool"],
            parser=lambda x: {"cw_fec_cnt": 1},
            output_mode="binary",
        ))

        result = sb.get_port_data(0, 0)
        assert result is None

    @patch('src.otpd.southbound.subprocess.run')
    def test_binary_mode_command_failure_returns_empty(self, mock_run):
        """Test binary command with non-zero returncode returns empty dict."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = b'\x00' * 56
        mock_run.return_value = mock_proc

        sb = CommandBasedSouthbound()
        sb.register_command(CommandEntry(
            name="fail_binary",
            command=["fail-bin-tool"],
            parser=lambda x: {"cw_fec_cnt": 1},
            output_mode="binary",
        ))

        result = sb.get_port_data(0, 0)
        assert result is None


class TestStatCommandParsers:
    """Test parsers for ubctl -stat source commands."""

    def test_parse_rate_to_bps(self):
        assert parse_rate_to_bps("112G") == 112 * 1024 * 1024 * 1024
        assert parse_rate_to_bps("25.5G") == int(25.5 * 1024 * 1024 * 1024)
        assert parse_rate_to_bps("UNSET") == 0

    def test_parse_lane_count(self):
        assert parse_lane_count("X4") == 4
        assert parse_lane_count("x8") == 8
        assert parse_lane_count("UNSET") == 0

    def test_parse_hex_or_unset(self):
        assert parse_hex_or_unset("0x10") == 16
        assert parse_hex_or_unset("UNSET") == 0

    def test_parse_port_info_stats(self):
        stdout = """
        unrelated: value
        sds_rate: 112G
        cur_tx_lane_num: X4
        """
        result = parse_port_info_stats(stdout)
        assert result == {
            "sds_rate_bps": 112 * 1024 * 1024 * 1024,
            "tx_lane_num": 4,
        }

    def test_parse_port_info_stats_unset_as_zero(self):
        stdout = """
        sds_rate: UNSET
        cur_tx_lane_num: UNSET
        """
        result = parse_port_info_stats(stdout)
        assert result == {
            "sds_rate_bps": 0,
            "tx_lane_num": 0,
        }

    def test_parse_bit_err_stats(self):
        stdout = """
        st_fec_decoding_fail_num: 0x10
        st_fec_err_bit_num: 0x2a
        """
        result = parse_bit_err_stats(stdout)
        assert result == {
            "cw_fec_cnt": 16,
            "cw_uncorrect_cnt": 42,
        }

    def test_parse_bit_err_stats_unset_as_zero(self):
        stdout = """
        st_fec_decoding_fail_num: UNSET
        st_fec_err_bit_num: UNSET
        """
        result = parse_bit_err_stats(stdout)
        assert result == {
            "cw_fec_cnt": 0,
            "cw_uncorrect_cnt": 0,
        }

    def test_parse_hikptool_serdes_info_port_snr(self):
        stdout = """
        header line
        chip1 (M11,ds0) [ 0, -8, 53, 2, 0][0,0, 7, 0, 2, 1, 0, 2, 5, 9, 0,15, 3, 5, 0, 3, 3, 0, 1, 0][ 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,][ 0, 0, 0, 0][501216, 0, 0,681, 92]
        chip1 (M11,ds1) [ 0, -8, 53, 2, 0][0,0, 7, 0, 2, 1, 0, 2, 5, 9, 0,15, 3, 5, 0, 3, 3, 0, 1, 0][ 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,][ 0, 0, 0, 0][488800, 0, 0,650, 94]
        chip1 (M11,ds2) [ 0, -8, 53, 2, 0][0,0, 7, 0, 2, 1, 0, 2, 5, 9, 0,15, 3, 5, 0, 3, 3, 0, 1, 0][ 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,][ 0, 0, 0, 0][523032, 0, 0,703, 93]
        chip1 (M11,ds3) [ 0, -8, 53, 2, 0][0,0, 7, 0, 2, 1, 0, 2, 5, 9, 0,15, 3, 5, 0, 3, 3, 0, 1, 0][ 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,][ 0, 0, 0, 0][472440, 0, 0,635, 93]
        """
        result = parse_hikptool_serdes_info(stdout)

        assert result == {
            "port_snrlane": [
                501216.0, 488800.0, 523032.0, 472440.0,
            ],
        }

    def test_parse_hikptool_serdes_info_no_data(self):
        assert parse_hikptool_serdes_info("header only\n") == {}

    def test_default_stat_commands_registered(self):
        sb = build_command_southbound()
        assert "ubctl_port_info_stats" in sb._command_registry
        assert "ubctl_bit_err_stats" in sb._command_registry
        assert "hikptool_serdes_info_port_snr" in sb._command_registry
        assert "ubctl_port_link" in sb._command_registry
        assert "hikptool_optical_dom" in sb._command_registry
        assert sb._command_registry["ubctl_port_info_stats"].command == [
            "ubctl", "-c", "{chip_id}", "-p", "{port_id}",
            "-d", "{die_id}", "-m", "port_info",
        ]
        assert sb._command_registry["ubctl_bit_err_stats"].command == [
            "ubctl", "-c", "{chip_id}", "-p", "{port_id}",
            "-d", "{die_id}", "-m", "dl", "-f", "bit_err",
        ]
        assert sb._command_registry["hikptool_serdes_info_port_snr"].command == [
            "hikptool", "serdes_info",
            "-i", "{chip_id}", "-s", "m{port_id+10}d0", "-n", "4", "-k",
        ]
        assert sb._command_registry["ubctl_port_link"].command == [
            "ubctl", "-c", "{chip_id}", "-d", "{die_id}",
            "-p", "{port_id}", "-m", "port_link",
        ]
        assert sb._command_registry["hikptool_optical_dom"].command == [
            "hikptool", "optical_dom",
            "-c", "{chip_id}", "-d", "{die_id}", "-p", "{port_id}",
        ]

    def test_parse_link_status_passthrough(self):
        stdout = "port 0 chip 0 die 0 link UP\nport 0 chip 0 die 1 link DOWN"
        result = parse_link_status(stdout)
        assert result == {"link_status": stdout}

    def test_parse_link_status_empty(self):
        result = parse_link_status("")
        assert result == {"link_status": ""}


class TestOpticalDomParser:
    """Test parser for hikptool optical_dom output."""

    def test_parse_optical_dom_normal_output(self):
        stdout = """
        Media Type      : SMF Optical
        Host Lane Count : x8
        Vendor Name     : TestVendor
        Vendor SN       : SN123
        Temperature     : +30.60 c
        Voltage         : 3.300 V
        --------------------------- Channel Diagnostics ----------------------------
        Lane : TX Power(dBm)  RX Power(dBm)  TX Bias(mA)  Host SNR(dB)  Media SNR(dB)
        0    :         0.00          -2.00        15.00          25.0           23.0
        1    :        -1.00          -4.00        12.00          22.0           20.0
        7    :       -20.00         -23.98         1.10           4.0            2.0
        RX LOS: 0x00            TX LOS:0x05         RX LOL: 0x14        TX LOL: 0x00
        """
        result = parse_optical_dom(stdout)

        assert result["optical_type_name"] == "SMF Optical"
        assert result["lane_count"] == 8
        assert result["optical_vendor"] == "TestVendor"
        assert result["optical_sn"] == "SN123"
        assert result["temp"] == 31
        assert result["vcc"] == 3300
        assert len(result["tx_power"]) == 16
        assert result["tx_power"][0] == 0.0
        assert result["rx_power"][1] == -4.0
        assert result["tx_bias"][7] == 1.1
        assert result["host_snr"][0] == 25.0
        assert result["media_snr"][7] == 2.0
        assert result["tx_los_flag"] == 5
        assert result["rx_los_flag"] == 0
        assert result["tx_lol_flag"] == 0
        assert result["rx_lol_flag"] == 20

    def test_parse_optical_dom_absent_output(self):
        result = parse_optical_dom("no optical module present on port 0\n")

        assert result["optical_state"] == 0
        assert result["optical_sn"] == ""
        assert result["optical_vendor"] == ""
        assert result["optical_type_name"] == ""
        assert result["lane_count"] == 0
        assert result["temp"] == 0
        assert result["vcc"] == 0
        assert result["tx_power"] == [0.0] * 16

    def test_parse_optical_dom_all_invalid_is_absent(self):
        stdout = """
        Temperature     : bad
        Voltage         : bad
        RX LOS: bad            TX LOS:bad         RX LOL: bad        TX LOL: bad
        """
        result = parse_optical_dom(stdout)

        assert result["optical_state"] == 0
        assert result["temp"] == 0
        assert result["vcc"] == 0

    def test_parse_optical_dom_partial_failures_become_none(self):
        stdout = """
        Media Type      : SMF Optical
        Host Lane Count : x2
        Temperature     : bad
        Voltage         : bad
        Lane : TX Power(dBm)  RX Power(dBm)  TX Bias(mA)  Host SNR(dB)  Media SNR(dB)
        0    :         bad          -2.00        bad          25.0           bad
        RX LOS: bad            TX LOS:0x05         RX LOL: bad        TX LOL: 0x00
        """
        result = parse_optical_dom(stdout)

        assert result["optical_state"] == 1
        assert result["temp"] is None
        assert result["vcc"] is None
        assert result["tx_power"][0] is None
        assert result["rx_power"][0] == -2.0
        assert result["tx_bias"][0] is None
        assert result["host_snr"][0] == 25.0
        assert result["media_snr"][0] is None
        assert result["rx_los_flag"] is None
        assert result["tx_los_flag"] == 5
        assert result["rx_lol_flag"] is None
        assert result["tx_lol_flag"] == 0


class TestCompositeSouthbound:
    """Test baseline + command overlay southbound."""

    def setup_method(self):
        CompositeSouthbound._data_cache.clear()

    class _BaselineSouthbound(SouthboundInterface):
        def get_port_data(self, port_id: int, chip_id: int, die_id: int = 0, use_cache: bool = True):
            return (
                PortInfo(
                    port_id=port_id,
                    chip_id=chip_id,
                    port_snrlane=[1.0] * 4,
                    cw_fec_cnt=10,
                    cw_uncorrect_cnt=1,
                    cw_total_cnt=1010,
                ),
                OpticalModuleInfo(
                    port_id=port_id,
                    chip_id=chip_id,
                    optical_sn="BASELINE-SN",
                    optical_vendor="BASELINE-VENDOR",
                    temp=30,
                    interface_code=3,
                ),
            )

    def test_command_fields_override_baseline_fields(self):
        """Command overlay fields override baseline, other fields keep baseline."""
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="dummy",
            command=["echo"],
            parser=lambda x: {},
            fields=["cw_fec_cnt", "temp"],
        ))
        overlay.get_field_data_with_failures = lambda port_id, chip_id, die_id=0, required_fields=None: (
            {"cw_fec_cnt": 20, "temp": 40}, []
        )

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
            calculators=[calculate_derived_fields],
        )

        result = sb.get_port_data(0, 0)
        assert result is not None
        port_info, optical_info = result
        assert port_info.cw_fec_cnt == 20
        assert port_info.port_snrlane == [1.0] * 4  # baseline preserved
        assert optical_info.temp == 40
        assert optical_info.optical_sn == "BASELINE-SN"  # baseline preserved

    def test_optical_absent_does_not_leak_baseline_fields(self):
        """Optical command absent output must zero command-covered baseline fields."""
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="optical",
            command=["echo"],
            parser=parse_optical_dom,
            fields=[
                "optical_sn", "optical_vendor", "optical_state",
                "optical_type_name", "lane_count", "temp", "vcc",
                "tx_power", "rx_power", "tx_bias", "host_snr", "media_snr",
                "tx_los_flag", "rx_los_flag", "tx_lol_flag", "rx_lol_flag",
            ],
        ))
        overlay.get_field_data_with_failures = lambda port_id, chip_id, die_id=0, required_fields=None: (
            parse_optical_dom("no optical module present on port 0"), []
        )

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
        )

        result = sb.get_port_data(0, 0)
        assert result is not None
        _, optical_info = result
        assert optical_info.optical_sn == ""
        assert optical_info.optical_vendor == ""
        assert optical_info.optical_type_name == ""
        assert optical_info.lane_count == 0
        assert optical_info.temp == 0
        assert optical_info.tx_power == [0.0] * 16

    def test_all_commands_fail_returns_none_production_mode(self, caplog, stub_mode_off):
        """When bound overlay commands fail in production mode, return None."""
        overlay = CommandBasedSouthbound()
        failed_entry = CommandEntry(
            name="dummy",
            command=["echo"],
            parser=lambda x: {},
            fields=["cw_fec_cnt", "cw_uncorrect_cnt"],
        )
        overlay.register_command(failed_entry)
        overlay.get_field_data_with_failures = lambda port_id, chip_id, die_id=0, required_fields=None: (
            {}, [failed_entry]
        )

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
            calculators=[calculate_derived_fields],
        )

        token = set_query_context("ublinkdt -m otpd -p 0 -c 0 -d 0 --stat")
        try:
            with caplog.at_level("WARNING", logger="src.otpd.southbound"):
                result = sb.get_port_data(0, 0)
        finally:
            reset_query_context(token)
        assert result is None
        assert "Southbound fields missing" in caplog.text
        assert "ublinkdt_command='ublinkdt -m otpd -p 0 -c 0 -d 0 --stat'" in caplog.text
        assert "target=port:0,chip:0,die:0" in caplog.text
        assert "southbound_command='dummy'" in caplog.text
        assert "command='echo'" in caplog.text
        assert "missing_fields=['cw_fec_cnt', 'cw_uncorrect_cnt']" in caplog.text

    def test_all_commands_fail_falls_back_to_zeros_stub_mode(self, caplog, stub_mode_on):
        """When bound overlay commands fail in stub mode, fall back to zero baseline."""
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="dummy",
            command=["echo"],
            parser=lambda x: {},
            fields=["cw_fec_cnt", "cw_uncorrect_cnt"],
        ))
        overlay.get_field_data_with_failures = lambda port_id, chip_id, die_id=0, required_fields=None: ({}, [])

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
            calculators=[calculate_derived_fields],
        )

        with caplog.at_level("WARNING", logger="src.otpd.southbound"):
            result = sb.get_port_data(0, 0)
        assert result is not None
        port_info, _ = result
        assert port_info.cw_fec_cnt == 0
        assert port_info.cw_uncorrect_cnt == 0
        assert not [record for record in caplog.records if record.name == "src.otpd.southbound"]

    def test_string_field_all_commands_fail_returns_none_production_mode(self, caplog, stub_mode_off):
        """When bound overlay commands fail in production mode, return None even for string fields."""
        overlay = CommandBasedSouthbound()
        failed_entry = CommandEntry(
            name="port_link",
            command=["echo"],
            parser=lambda x: {},
            fields=["link_status"],
        )
        overlay.register_command(failed_entry)
        overlay.get_field_data_with_failures = lambda pid, cid, did=0, required_fields=None: (
            {}, [failed_entry]
        )

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
        )
        with caplog.at_level("WARNING", logger="src.otpd.southbound"):
            result = sb.get_port_data(0, 0)
        assert result is None
        assert "Southbound fields missing" in caplog.text
        assert "southbound_command='port_link'" in caplog.text
        assert "missing_fields=['link_status']" in caplog.text

    def test_link_status_all_commands_fail_uses_mock_stub_mode(self, caplog, stub_mode_on):
        """When link status fails in stub mode, return mock status instead of zero/empty."""
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="port_link",
            command=["echo"],
            parser=lambda x: {},
            fields=["link_status"],
        ))
        overlay.get_field_data_with_failures = lambda pid, cid, did=0, required_fields=None: ({}, [])

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
        )
        with caplog.at_level("WARNING", logger="src.otpd.southbound"):
            result = sb.get_port_data(0, 0)
        assert result is not None
        port_info, _ = result
        assert "link status info:" in port_info.link_status
        assert "current_time" in port_info.link_status
        assert "link_up_count      : 2" in port_info.link_status
        assert "link_down_count    : 1" in port_info.link_status
        assert "Mon Oct 23 10:30:15 2023  LINK UP" in port_info.link_status
        assert "Mon Oct 23 10:25:10 2023  LINK DOWN" in port_info.link_status
        assert not [record for record in caplog.records if record.name == "src.otpd.southbound"]

    def test_link_status_mock_stub_mode_uses_static_counts(self, stub_mode_on):
        """Link status stub keeps stable counts independent of the chip."""
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="port_link",
            command=["echo"],
            parser=lambda x: {},
            fields=["link_status"],
        ))
        overlay.get_field_data_with_failures = lambda pid, cid, did=0, required_fields=None: ({}, [])

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
        )

        port_info, _ = sb.get_port_data(0, 1, required_fields={"link_status"})

        assert "link_up_count      : 2" in port_info.link_status
        assert "link_down_count    : 1" in port_info.link_status

    def test_optical_all_commands_fail_uses_realistic_stub_mode(self, stub_mode_on):
        """Optical stub output should keep 8 lanes and visible placeholder identity."""
        optical_fields = [
            "optical_sn", "optical_vendor", "optical_state",
            "optical_type", "optical_type_name", "interface_code",
            "lane_count", "tx_los_flag", "rx_los_flag",
            "tx_lol_flag", "rx_lol_flag", "tx_power", "rx_power",
            "vcc", "temp", "tx_bias", "host_snr", "media_snr",
        ]
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="optical",
            command=["hikptool", "optical_dom"],
            parser=lambda x: {},
            fields=optical_fields,
        ))
        overlay.get_field_data_with_failures = lambda pid, cid, did=0, required_fields=None: ({}, [])

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
        )

        _, optical_info = sb.get_port_data(
            0, 0, required_fields=set(optical_fields)
        )

        assert optical_info.optical_sn == "XXXXX"
        assert optical_info.optical_vendor == "XXXXX"
        assert optical_info.optical_type_name == "XXXXX"
        assert optical_info.lane_count == 8
        assert optical_info.temp == 0
        assert optical_info.vcc == 0
        assert optical_info.tx_power == [0.0] * 16
        assert optical_info.rx_power == [0.0] * 16
        assert optical_info.tx_bias == [0.0] * 16
        assert optical_info.host_snr == [0.0] * 16
        assert optical_info.media_snr == [0.0] * 16

    def test_unbound_required_fields_use_baseline_without_warning(self, caplog):
        """When no enabled command is bound for requested fields, use baseline only."""
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="stat_cmd",
            command=["echo"],
            parser=lambda x: {},
            fields=["cw_fec_cnt"],
        ))
        overlay.get_field_data_with_failures = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("irrelevant command should not run")
        )

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
        )

        with caplog.at_level("WARNING", logger="src.otpd.southbound"):
            result = sb.get_port_data(0, 0, required_fields={"port_snrlane"})

        assert result is not None
        port_info, optical_info = result
        assert port_info.port_snrlane == [1.0] * 4
        assert optical_info.optical_sn == "BASELINE-SN"
        assert "Bound overlay commands returned no data" not in caplog.text

    def test_no_commands_uses_baseline(self):
        """When overlay has no registered commands, baseline is used."""
        overlay = CommandBasedSouthbound()

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
            calculators=[calculate_derived_fields],
        )

        result = sb.get_port_data(0, 0)
        assert result is not None
        port_info, optical_info = result
        assert port_info.port_snrlane == [1.0] * 4
        assert port_info.cw_fec_cnt == 10
        assert optical_info.optical_sn == "BASELINE-SN"

    def test_missing_cw_total_inputs_warns_and_sets_zero(self, caplog):
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="dummy",
            command=["echo"],
            parser=lambda x: {},
            fields=["cw_fec_cnt", "cw_uncorrect_cnt"],
        ))
        overlay.get_field_data_with_failures = lambda port_id, chip_id, die_id=0, required_fields=None: (
            {"cw_fec_cnt": 20, "cw_uncorrect_cnt": 2}, []
        )

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
            calculators=[calculate_derived_fields],
        )

        with caplog.at_level("WARNING", logger="src.otpd.field_calculators"):
            port_info, _ = sb.get_port_data(0, 0, use_cache=False)

        assert port_info.cw_fec_cnt == 20
        assert port_info.cw_uncorrect_cnt == 2
        assert port_info.cw_total_cnt == 0
        assert "Cannot calculate cw_total_cnt" in caplog.text

    def test_port_snr_query_does_not_calculate_cw_total_cnt(self, caplog):
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="dummy",
            command=["echo"],
            parser=lambda x: {},
            fields=["port_snrlane"],
        ))
        overlay.get_field_data_with_failures = lambda port_id, chip_id, die_id=0, required_fields=None: (
            {"port_snrlane": [446400.0, 502272.0, 497072.0, 490304.0]}, []
        )

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
            calculators=[calculate_derived_fields],
        )

        with caplog.at_level("WARNING", logger="src.otpd.field_calculators"):
            port_info, _ = sb.get_port_data(
                0, 0, use_cache=False, required_fields={"port_snrlane"}
            )

        assert port_info.port_snrlane == [446400.0, 502272.0, 497072.0, 490304.0]
        assert "Cannot calculate cw_total_cnt" not in caplog.text

    def test_cache_key_includes_required_fields(self):
        """Field-filtered cached queries must not reuse each other's data."""
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="snr_cmd",
            command=["echo"],
            parser=lambda x: {},
            fields=["port_snrlane"],
        ))
        overlay.register_command(CommandEntry(
            name="link_cmd",
            command=["echo"],
            parser=lambda x: {},
            fields=["link_status"],
        ))

        def get_field_data_with_failures(port_id, chip_id, die_id=0, required_fields=None):
            if required_fields == {"port_snrlane"}:
                return {"port_snrlane": [9.0] * 4}, []
            if required_fields == {"link_status"}:
                return {"link_status": "LINK UP"}, []
            return {}, []

        overlay.get_field_data_with_failures = get_field_data_with_failures

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
        )

        snr_port_info, _ = sb.get_port_data(0, 0, required_fields={"port_snrlane"})
        link_port_info, _ = sb.get_port_data(0, 0, required_fields={"link_status"})

        assert snr_port_info.port_snrlane == [9.0] * 4
        assert snr_port_info.link_status == ""
        assert link_port_info.port_snrlane == [1.0] * 4
        assert link_port_info.link_status == "LINK UP"

    def test_use_cache_false_recalculates_cw_total_from_current_port_info_echo(self):
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="dummy",
            command=["echo"],
            parser=lambda x: {},
            fields=["sds_rate_bps", "tx_lane_num", "cw_fec_cnt", "cw_uncorrect_cnt"],
        ))
        overlay_values = [
            (
                {
                    "sds_rate_bps": 1000,
                    "tx_lane_num": 4,
                    "cw_fec_cnt": 20,
                    "cw_uncorrect_cnt": 2,
                },
                [],
            ),
            (
                {
                    "sds_rate_bps": 2000,
                    "tx_lane_num": 8,
                    "cw_fec_cnt": 30,
                    "cw_uncorrect_cnt": 3,
                },
                [],
            ),
        ]

        def get_field_data_with_failures(port_id, chip_id, die_id=0, required_fields=None):
            return overlay_values.pop(0)

        overlay.get_field_data_with_failures = get_field_data_with_failures

        sb = CompositeSouthbound(
            baseline=self._BaselineSouthbound(),
            overlay=overlay,
            calculators=[make_derived_fields_calculator(collection_window=2.0)],
        )

        first_port_info, _ = sb.get_port_data(0, 0, use_cache=False)
        second_port_info, _ = sb.get_port_data(0, 0, use_cache=False)

        assert first_port_info.cw_fec_cnt == 20
        assert first_port_info.cw_uncorrect_cnt == 2
        assert first_port_info.cw_total_cnt == 8000
        assert second_port_info.cw_fec_cnt == 30
        assert second_port_info.cw_uncorrect_cnt == 3
        assert second_port_info.cw_total_cnt == 32000


class TestNoBaselineLeakage:
    """Comprehensive tests: command-covered fields must never show baseline values."""

    def setup_method(self):
        CompositeSouthbound._data_cache.clear()

    # Baseline returns distinctive non-zero values so leaks are detectable.
    class _NonZeroBaseline(SouthboundInterface):
        def get_port_data(self, port_id, chip_id, die_id=0, use_cache=True):
            return (
                PortInfo(
                    port_id=port_id,
                    chip_id=chip_id,
                    port_snrlane=[25.0] * 4,
                    cw_fec_cnt=999,
                    cw_uncorrect_cnt=888,
                    cw_total_cnt=1999,
                ),
                OpticalModuleInfo(
                    port_id=port_id,
                    chip_id=chip_id,
                    optical_sn="BASELINE-SN",
                    optical_vendor="BASELINE-VENDOR",
                    temp=99,
                    vcc=9999,
                    tx_power=[1.1] * 16,
                    rx_power=[2.2] * 16,
                    tx_bias=[3.3] * 16,
                    host_snr=[4.4] * 16,
                    media_snr=[5.5] * 16,
                    interface_code=3,
                ),
            )

    def test_command_succeeds_real_data_overrides_baseline(self):
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="stat_cmd",
            command=["echo"],
            parser=lambda x: {},
            fields=["cw_fec_cnt", "cw_uncorrect_cnt"],
        ))
        overlay.get_field_data_with_failures = lambda pid, cid, did=0, required_fields=None: (
            {"cw_fec_cnt": 42, "cw_uncorrect_cnt": 7}, []
        )

        sb = CompositeSouthbound(
            baseline=self._NonZeroBaseline(),
            overlay=overlay,
        )
        port_info, _ = sb.get_port_data(0, 0)

        assert port_info.cw_fec_cnt == 42       # real, not 999
        assert port_info.cw_uncorrect_cnt == 7   # real, not 888
        assert port_info.port_snrlane == [25.0] * 4  # baseline OK

    def test_command_empty_result_returns_none_production_mode(self, stub_mode_off):
        overlay = CommandBasedSouthbound()
        failed_entry = CommandEntry(
            name="stat_cmd",
            command=["echo"],
            parser=lambda x: {},
            fields=["cw_fec_cnt", "cw_uncorrect_cnt"],
        )
        overlay.register_command(failed_entry)
        overlay.get_field_data_with_failures = lambda pid, cid, did=0, required_fields=None: (
            {}, [failed_entry]
        )

        sb = CompositeSouthbound(
            baseline=self._NonZeroBaseline(),
            overlay=overlay,
        )
        result = sb.get_port_data(0, 0)
        assert result is None

    def test_command_not_found_raises_production_mode(self, stub_mode_off):
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="stat_cmd",
            command=["echo"],
            parser=lambda x: {},
            fields=["cw_fec_cnt", "cw_uncorrect_cnt"],
        ))
        overlay.get_field_data_with_failures = lambda pid, cid, did=0, required_fields=None: (_ for _ in ()).throw(
            FileNotFoundError("ubctl not found")
        )

        sb = CompositeSouthbound(
            baseline=self._NonZeroBaseline(),
            overlay=overlay,
        )

        with pytest.raises(FileNotFoundError):
            sb.get_port_data(0, 0)

    def test_no_commands_all_baseline(self):
        overlay = CommandBasedSouthbound()

        sb = CompositeSouthbound(
            baseline=self._NonZeroBaseline(),
            overlay=overlay,
        )
        port_info, optical_info = sb.get_port_data(0, 0)

        assert port_info.cw_fec_cnt == 999
        assert port_info.cw_uncorrect_cnt == 888
        assert optical_info.optical_sn == "BASELINE-SN"

    def test_optical_command_all_fail_returns_none_production_mode(self, stub_mode_off):
        overlay = CommandBasedSouthbound()
        failed_entry = CommandEntry(
            name="optical_cmd",
            command=["echo"],
            parser=lambda x: {},
            fields=["temp", "vcc"],
        )
        overlay.register_command(failed_entry)
        overlay.get_field_data_with_failures = lambda pid, cid, did=0, required_fields=None: (
            {}, [failed_entry]
        )

        sb = CompositeSouthbound(
            baseline=self._NonZeroBaseline(),
            overlay=overlay,
        )
        result = sb.get_port_data(0, 0)
        assert result is None

    def test_mixed_command_success_and_failure(self, caplog, stub_mode_off):
        optical_entry = CommandEntry(
            name="optical_cmd",
            command=["echo"],
            parser=lambda x: {},
            fields=["temp", "vcc"],
        )
        overlay = CommandBasedSouthbound()
        overlay.register_command(CommandEntry(
            name="fec_cmd",
            command=["echo"],
            parser=lambda x: {},
            fields=["cw_fec_cnt", "cw_uncorrect_cnt"],
        ))
        overlay.register_command(optical_entry)
        overlay.get_field_data_with_failures = lambda pid, cid, did=0, required_fields=None: (
            {"cw_fec_cnt": 50, "cw_uncorrect_cnt": 3}, [optical_entry]
        )

        sb = CompositeSouthbound(
            baseline=self._NonZeroBaseline(),
            overlay=overlay,
        )
        with caplog.at_level("WARNING", logger="src.otpd.southbound"):
            port_info, optical_info = sb.get_port_data(0, 0)

        assert port_info.cw_fec_cnt == 50       # real from fec_cmd
        assert port_info.cw_uncorrect_cnt == 3   # real from fec_cmd
        assert port_info.port_snrlane == [25.0] * 4  # baseline
        assert optical_info.temp == 0            # zero, NOT 99
        assert optical_info.vcc == 0             # zero, NOT 9999
        assert "Southbound fields missing" in caplog.text
        assert "southbound_command='optical_cmd'" in caplog.text
        assert "missing_fields=['temp', 'vcc']" in caplog.text

    def test_baseline_values_never_leak_into_command_fields(self, stub_mode_off):
        baseline_cw_fec = 999
        baseline_cw_uncorrect = 888

        stat_entry = CommandEntry(
            name="stat_cmd",
            command=["echo"],
            parser=lambda x: {},
            fields=["cw_fec_cnt", "cw_uncorrect_cnt"],
        )
        overlay = CommandBasedSouthbound()
        overlay.register_command(stat_entry)

        # Production mode: all commands failed -> returns None
        overlay.get_field_data_with_failures = lambda pid, cid, did=0, required_fields=None: (
            {}, [stat_entry]
        )
        sb = CompositeSouthbound(
            baseline=self._NonZeroBaseline(),
            overlay=overlay,
        )
        result = sb.get_port_data(0, 0, use_cache=False)
        assert result is None

        # Test with partial result (some fields present, some zeroed)
        CompositeSouthbound._data_cache.clear()
        overlay.get_field_data_with_failures = lambda pid, cid, did=0, required_fields=None: (
            {"cw_fec_cnt": 0}, [stat_entry]
        )
        port_info, _ = sb.get_port_data(0, 0, use_cache=False)
        assert port_info.cw_fec_cnt != baseline_cw_fec
        assert port_info.cw_uncorrect_cnt != baseline_cw_uncorrect
        assert port_info.cw_fec_cnt == 0
        assert port_info.cw_uncorrect_cnt == 0


class TestFactory:
    """Test get_southbound_interface factory function."""

    def test_command_source(self):
        sb = get_southbound_interface("command", default_timeout=5.0)
        assert isinstance(sb, CommandBasedSouthbound)

    def test_hybrid_source(self):
        sb = get_southbound_interface("hybrid")
        assert isinstance(sb, CompositeSouthbound)

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="Unknown source"):
            get_southbound_interface("nonexistent")


class TestStubMode:
    """Test debug-gated stub mode environment variables."""

    def test_default_is_production_mode(self, stub_mode_off):
        assert is_debug_mode() is False
        assert is_stub_mode() is False

    def test_delivery_mode_ignores_stub_environment(self, stub_mode_off):
        os.environ["OTPD_STUB_MODE"] = "1"

        assert is_debug_mode() is False
        assert is_stub_mode() is False

    def test_stub_mode_enabled_with_1(self, stub_mode_on):
        assert is_debug_mode() is True
        assert is_stub_mode() is True

    def test_stub_mode_enabled_with_true(self, debug_mode_on):
        old = os.environ.get("OTPD_STUB_MODE")
        os.environ["OTPD_STUB_MODE"] = "true"
        try:
            assert is_stub_mode() is True
        finally:
            if old is not None:
                os.environ["OTPD_STUB_MODE"] = old
            else:
                os.environ.pop("OTPD_STUB_MODE", None)

    def test_stub_mode_enabled_with_yes(self, debug_mode_on):
        old = os.environ.get("OTPD_STUB_MODE")
        os.environ["OTPD_STUB_MODE"] = "yes"
        try:
            assert is_stub_mode() is True
        finally:
            if old is not None:
                os.environ["OTPD_STUB_MODE"] = old
            else:
                os.environ.pop("OTPD_STUB_MODE", None)

    def test_stub_mode_disabled_with_0(self, debug_mode_on):
        old = os.environ.get("OTPD_STUB_MODE")
        os.environ["OTPD_STUB_MODE"] = "0"
        try:
            assert is_stub_mode() is False
        finally:
            if old is not None:
                os.environ["OTPD_STUB_MODE"] = old
            else:
                os.environ.pop("OTPD_STUB_MODE", None)

    def test_stub_mode_case_insensitive(self, debug_mode_on):
        old = os.environ.get("OTPD_STUB_MODE")
        os.environ["OTPD_STUB_MODE"] = "TRUE"
        try:
            assert is_stub_mode() is True
        finally:
            if old is not None:
                os.environ["OTPD_STUB_MODE"] = old
            else:
                os.environ.pop("OTPD_STUB_MODE", None)
