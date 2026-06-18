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

import argparse
import importlib
from unittest.mock import patch

import pytest

import src.otpd.cli as cli_module
from src.otpd.cli import (
    create_parser, execute_commands, format_ublinkdt_command, main, validate_args,
)
from src.otpd.southbound import CommandBasedSouthbound, CompositeSouthbound, SouthboundInterface

runtime_module = importlib.import_module("src.otpd.runtime")


def make_args(**overrides):
    defaults = dict(
        module='otpd',
        port_id=0,
        die_id=0,
        chip_id=0,
        port_snr=False,
        stat=False,
        optical=False,
        ip=False,
        inet6=False,
        link_stat=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestCLIParser:
    """Test CLI argument parser."""

    def test_create_parser_returns_valid_parser(self):
        parser = create_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    @pytest.mark.parametrize("args_list,expected_attrs", [
        (['-m', 'otpd', '-p', '0', '-c', '0', '--port-snr'], {'port_id': 0, 'die_id': None, 'chip_id': 0, 'port_snr': True, 'stat': False}),
        (['-m', 'otpd', '-p', '0', '-d', '1', '-c', '1', '--stat'], {'port_id': 0, 'die_id': 1, 'chip_id': 1, 'port_snr': False, 'stat': True}),
        (['-m', 'otpd', '-p', '0', '-d', '0', '-c', '0', '--port-snr', '--stat', '--optical', '--ip', '--inet6', '--link-stat'],
         {'port_id': 0, 'die_id': 0, 'chip_id': 0, 'port_snr': True, 'stat': True, 'optical': True, 'ip': True, 'inet6': True, 'link_stat': True}),
    ])
    def test_parse_args_combinations(self, args_list, expected_attrs):
        parser = create_parser()
        args = parser.parse_args(args_list)
        for attr, expected_val in expected_attrs.items():
            assert getattr(args, attr) == expected_val

    @pytest.mark.parametrize("management_command", ["start", "stop", "status"])
    def test_management_commands_are_not_supported(self, management_command):
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(['-m', 'otpd', management_command])

    @pytest.mark.parametrize("legacy_option", [
        "-portSNR", "-port_snr", "-stat", "-optical", "-ip", "-inet6", "-link_stat",
    ])
    def test_legacy_multi_character_single_dash_options_are_rejected(self, legacy_option):
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(['-m', 'otpd', '-p', '0', '-c', '0', legacy_option])

    def test_parser_has_no_daemon_options(self):
        parser = create_parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        assert "--interval" not in option_strings
        assert "--runtime-dir" not in option_strings

    def test_missing_required_params_fails_validation(self, capsys):
        parser = create_parser()
        args = parser.parse_args(['-m', 'otpd', '--port-snr'])
        assert validate_args(args) is False
        captured = capsys.readouterr()
        assert "Port ID is required" in captured.err

    def test_missing_chip_id_fails_validation(self, capsys):
        parser = create_parser()
        args = parser.parse_args(['-m', 'otpd', '-p', '0', '--port-snr'])
        assert validate_args(args) is False
        captured = capsys.readouterr()
        assert "Chip ID is required" in captured.err

    def test_port_snr_does_not_require_die_id(self):
        parser = create_parser()
        args = parser.parse_args(['-m', 'otpd', '-p', '0', '-c', '0', '--port-snr'])
        assert validate_args(args) is True

    def test_port_snr_ignores_die_id(self):
        parser = create_parser()
        args = parser.parse_args(['-m', 'otpd', '-p', '0', '-c', '0', '-d', '3', '--port-snr'])
        assert validate_args(args) is True

    def test_die_query_missing_die_id_fails_validation(self, capsys):
        parser = create_parser()
        args = parser.parse_args(['-m', 'otpd', '-p', '0', '-c', '0', '--stat'])
        assert validate_args(args) is False
        captured = capsys.readouterr()
        assert "Die ID is required" in captured.err

    def test_format_ublinkdt_command_for_diagnostic_context(self):
        args = make_args(stat=True, port_id=3, chip_id=1, die_id=0)

        result = format_ublinkdt_command(args, "--stat")

        assert result == "ublinkdt -m otpd -p 3 -c 1 -d 0 --stat"

    def test_format_ublinkdt_command_for_ip_context(self):
        args = make_args(ip=True, inet6=True, port_id=3, chip_id=1)

        result = format_ublinkdt_command(args, "--ip")

        assert result == "ublinkdt -m otpd -p 3 -c 1 --ip --inet6"

    def test_format_ublinkdt_command_for_port_snr_context(self):
        args = make_args(port_snr=True, port_id=3, chip_id=1, die_id=None)

        result = format_ublinkdt_command(args, "--port-snr")

        assert result == "ublinkdt -m otpd -p 3 -c 1 --port-snr"

    def test_format_ublinkdt_command_for_optical_context_uses_die_three(self):
        args = make_args(optical=True, port_id=3, chip_id=1, die_id=0)

        result = format_ublinkdt_command(args, "--optical")

        assert result == "ublinkdt -m otpd -p 3 -c 1 -d 3 --optical"


class TestCLIValidation:
    """Test CLI argument validation."""

    @pytest.mark.parametrize("port_id,chip_id,die_id,expected_result", [
        (-1, 0, 0, False),
        (0, 2, 0, False),
        (0, -1, 0, False),
        (0, 0, 2, False),
        (0, 0, -1, False),
        (0, 0, 0, True),
        (0, 1, 1, True),
    ])
    def test_validate_args_port_id_chip_id_and_die_id(self, port_id, chip_id, die_id, expected_result):
        args = make_args(port_id=port_id, chip_id=chip_id, die_id=die_id)
        assert validate_args(args) == expected_result

    def test_validate_args_rejects_ip_without_inet6(self, capsys):
        args = make_args(ip=True, inet6=False)
        assert validate_args(args) is False
        captured = capsys.readouterr()
        assert "--ip requires --inet6" in captured.err

    def test_validate_args_accepts_port_snr_without_die_id(self):
        args = make_args(port_snr=True, die_id=None)
        assert validate_args(args) is True

    def test_validate_args_rejects_die_query_without_die_id(self, capsys):
        args = make_args(stat=True, die_id=None)
        assert validate_args(args) is False
        captured = capsys.readouterr()
        assert "Die ID is required" in captured.err

    def test_validate_args_accepts_optical_with_die_id_three(self):
        args = make_args(optical=True, die_id=3)
        assert validate_args(args) is True

    def test_validate_args_accepts_optical_without_die_id(self):
        args = make_args(optical=True, die_id=None)
        assert validate_args(args) is True

    def test_validate_args_accepts_optical_with_any_die_id(self):
        args = make_args(optical=True, die_id=0)
        assert validate_args(args) is True

    def test_validate_args_rejects_stat_with_die_id_three(self, capsys):
        args = make_args(stat=True, die_id=3)
        assert validate_args(args) is False
        captured = capsys.readouterr()
        assert "Die ID must be 0 or 1" in captured.err


class TestCLIExecution:
    """Test CLI command execution."""

    def setup_method(self):
        SouthboundInterface._data_cache.clear()
        CommandBasedSouthbound._data_cache.clear()
        CompositeSouthbound._data_cache.clear()

    @pytest.mark.parametrize("command_attr,northbound_func,expected_in_output", [
        ('port_snr', 'get_port_snr', "port SNR info"),
        ('stat', 'get_statistics', "error codeword statistics info"),
        ('optical', 'get_optical_info', "optical info"),
    ])
    def test_execute_commands_single_southbound_query(self, command_attr, northbound_func, expected_in_output, capsys):
        die_id = 3 if command_attr == 'optical' else 0
        args = make_args(die_id=die_id, **{command_attr: True})

        with patch(f'src.otpd.northbound.{northbound_func}', return_value=expected_in_output) as mock_func:
            result = execute_commands(args)

        assert result == 0
        mock_func.assert_called_once_with(0, 0, die_id)
        assert expected_in_output in capsys.readouterr().out

    def test_execute_commands_multiple_southbound_queries(self, capsys):
        args = make_args(port_snr=True, stat=True, link_stat=True)

        with patch('src.otpd.northbound.get_port_snr', return_value="port SNR info") as mock_snr:
            with patch('src.otpd.northbound.get_statistics', return_value="error codeword statistics info") as mock_stat:
                with patch('src.otpd.northbound.get_link_status', return_value="link status info") as mock_link:
                    result = execute_commands(args)

        assert result == 0
        mock_snr.assert_called_once_with(0, 0, 0)
        mock_stat.assert_called_once_with(0, 0, 0)
        mock_link.assert_called_once_with(0, 0, 0)
        output = capsys.readouterr().out
        assert "port SNR info" in output
        assert "error codeword statistics info" in output
        assert "link status info" in output

    def test_execute_commands_ip_does_not_collect_southbound_data(self):
        args = make_args(ip=True, inet6=True)
        with patch('src.otpd.northbound.get_ip_address', return_value="ip info:\nipv6_address        : fe80::1") as mock_ip:
            result = execute_commands(args)

        assert result == 0
        mock_ip.assert_called_once_with(0, 0, True)

    def test_execute_commands_no_longer_checks_daemon(self):
        assert not hasattr(cli_module, 'is_daemon_running')

    def test_execute_port_snr_without_die_id_uses_default_die_zero(self, capsys):
        args = make_args(port_snr=True, die_id=None)
        with patch('src.otpd.northbound.get_port_snr', return_value="port SNR info") as mock_snr:
            result = execute_commands(args)

        assert result == 0
        mock_snr.assert_called_once_with(0, 0, 0)
        assert "port SNR info" in capsys.readouterr().out

    def test_execute_port_snr_ignores_die_id(self, capsys):
        args = make_args(port_snr=True, die_id=3)
        with patch('src.otpd.northbound.get_port_snr', return_value="port SNR info") as mock_snr:
            result = execute_commands(args)

        assert result == 0
        mock_snr.assert_called_once_with(0, 0, 0)
        assert "port SNR info" in capsys.readouterr().out

    def test_execute_optical_uses_die_three(self, capsys):
        args = make_args(optical=True, die_id=0)
        with patch('src.otpd.northbound.get_optical_info', return_value="optical info") as mock_optical:
            result = execute_commands(args)

        assert result == 0
        mock_optical.assert_called_once_with(0, 0, 3)
        assert "optical info" in capsys.readouterr().out

    def test_execute_port_snr_uses_stub_mode_when_command_is_missing(self, monkeypatch, capsys):
        monkeypatch.setattr(runtime_module, "DEBUG_BUILD", True)
        monkeypatch.setenv("OTPD_STUB_MODE", "1")
        args = make_args(port_snr=True, die_id=3)

        with patch('src.otpd.southbound.subprocess.run', side_effect=FileNotFoundError("hikptool")):
            result = execute_commands(args)

        captured = capsys.readouterr()
        assert result == 0
        assert "port SNR info:" in captured.out
        assert "port SNR Lane0" in captured.out
        assert captured.err == ""

    def test_execute_optical_uses_stub_mode_when_command_is_missing(self, monkeypatch, capsys):
        monkeypatch.setattr(runtime_module, "DEBUG_BUILD", True)
        monkeypatch.setenv("OTPD_STUB_MODE", "1")
        args = make_args(optical=True, die_id=0)

        with patch('src.otpd.southbound.subprocess.run', side_effect=FileNotFoundError("hikptool")):
            result = execute_commands(args)

        captured = capsys.readouterr()
        assert result == 0
        assert "optical info:" in captured.out
        assert "SN                : XXXXX" in captured.out
        assert "Lane Count        : 8" in captured.out
        assert captured.err == ""

    def test_execute_commands_no_commands(self, capsys):
        result = execute_commands(make_args())
        assert result == 1
        captured = capsys.readouterr()
        assert "Error: No command specified" in captured.err

    def test_execute_commands_command_failure(self, capsys):
        args = make_args(port_snr=True)
        with patch('src.otpd.northbound.get_port_snr', return_value=None):
            result = execute_commands(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Error: Failed to get port SNR" in captured.err

    def test_execute_commands_missing_required_southbound_command(self, capsys):
        args = make_args(stat=True)
        with patch('src.otpd.northbound.get_statistics', side_effect=FileNotFoundError("ubctl")):
            result = execute_commands(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Required command not found" in captured.err
        assert "ubctl" in captured.err

    def test_main_success(self):
        test_args = ['ublinkdt', '-m', 'otpd', '-p', '0', '-c', '0', '--port-snr']
        with patch.object(__import__('sys'), 'argv', test_args):
            with patch('src.otpd.cli.execute_commands', return_value=0):
                assert main() == 0
