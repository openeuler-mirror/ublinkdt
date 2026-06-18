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
from unittest.mock import patch, MagicMock
from src.otpd.system_interface import (
    RealSystemInterface, get_system_interface,
)


class TestSystemInterfaceFactory:
    def test_get_system_interface_default(self):
        """Test get_system_interface default returns RealSystemInterface."""
        interface = get_system_interface()
        assert isinstance(interface, RealSystemInterface)

    def test_get_system_interface_unknown_source(self):
        """Test get_system_interface unknown source raises."""
        with pytest.raises(ValueError, match="Unknown source"):
            get_system_interface("unknown")


class TestRealSystemInterfacePlatform:
    """Test RealSystemInterface platform dispatch and parsing."""

    def test_get_system_interface_real(self):
        interface = get_system_interface("real")
        assert isinstance(interface, RealSystemInterface)

    @patch('src.otpd.system_interface.platform.system', return_value="Linux")
    @patch('src.otpd.system_interface.subprocess.run')
    def test_linux_ipv6_dispatch(self, mock_run, mock_platform):
        """Test that Linux platform dispatches to _get_ip_linux."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = (
            "1: lo: <LOOPBACK> state UNKNOWN\n"
            "    inet6 ::1/128 scope host\n"
            "2: eth0: <BROADCAST> state UP\n"
            "    inet6 fe80::1/64 scope link noprefixroute\n"
        )
        mock_run.return_value = mock_proc

        interface = RealSystemInterface()
        result = interface.get_ip_address(41000, 0, inet6=True)

        assert result == "fe80::1"
        mock_run.assert_called_once_with(
            ['ip', '-6', 'addr', 'show'],
            capture_output=True,
            text=True,
            timeout=5,
        )

    @patch('src.otpd.system_interface.platform.system', return_value="Linux")
    @patch('src.otpd.system_interface.subprocess.run')
    def test_linux_ipv6_returns_first_address(self, mock_run, mock_platform):
        """Test multiple IPv6 addresses return the earliest parsed address."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = (
            "2: eth0: <BROADCAST> state UP\n"
            "    inet6 fe80::1/64 scope link noprefixroute\n"
            "    inet6 fe80::2/64 scope link noprefixroute\n"
        )
        mock_run.return_value = mock_proc

        interface = RealSystemInterface()
        result = interface.get_ip_address(41000, 0, inet6=True)

        assert result == "fe80::1"

    @patch('src.otpd.system_interface.platform.system', return_value="Windows")
    @patch('src.otpd.system_interface.subprocess.run')
    def test_windows_ipv6_dispatch(self, mock_run, mock_platform):
        """Test that Windows platform dispatches to _get_ip_windows."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = (
            "Windows IP Configuration\n\n"
            "Ethernet adapter Ethernet:\n\n"
            "   IPv6 Address. . . . . . . : 2400:1000::1\n"
            "   Link-local IPv6 Address . . . : fe80::1%12\n"
        )
        mock_run.return_value = mock_proc

        interface = RealSystemInterface()
        result = interface.get_ip_address(41000, 0, inet6=True)

        assert result == "2400:1000::1"

    @patch('src.otpd.system_interface.platform.system', return_value="Windows")
    @patch('src.otpd.system_interface.subprocess.run')
    def test_windows_ipv6_returns_first_address(self, mock_run, mock_platform):
        """Test Windows multiple IPv6 addresses return the earliest parsed address."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = (
            "Windows IP Configuration\n\n"
            "Ethernet adapter Ethernet:\n\n"
            "   IPv6 Address. . . . . . . : 2400:1000::1\n"
            "   IPv6 Address. . . . . . . : 2400:1000::2\n"
        )
        mock_run.return_value = mock_proc

        interface = RealSystemInterface()
        result = interface.get_ip_address(41000, 0, inet6=True)

        assert result == "2400:1000::1"

    @patch('src.otpd.system_interface.platform.system', return_value="FreeBSD")
    def test_unsupported_platform(self, mock_platform):
        """Test unsupported platform returns None."""
        interface = RealSystemInterface()
        result = interface.get_ip_address(41000, 0, inet6=True)
        assert result is None


class TestRealSystemInterfaceLinuxParsing:
    """Test Linux ip command output parsing."""

    def test_parse_linux_ip_output_returns_ipv6_in_output_order(self):
        """Test IPv6 addresses are returned in output order without filtering."""
        output = (
            "1: eth0: <BROADCAST> state UP\n"
            "    inet6 fe80::1/64 scope link noprefixroute\n"
            "    inet6 2400:1000::1/64 scope global\n"
        )
        interface = RealSystemInterface()
        result = interface._parse_linux_ip_output(output, inet6=True)
        assert result == ["fe80::1", "2400:1000::1"]

    def test_parse_centos_ipv6_ip_addr_show_output(self):
        """Test CentOS-style ip -6 addr show output parsing."""
        output = (
            "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 state UNKNOWN qlen 1000\n"
            "    inet6 ::1/128 scope host\n"
            "       valid_lft forever preferred_lft forever\n"
            "2: ens192: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP qlen 1000\n"
            "    inet6 fe80::250:56ff:feaa:bbcc/64 scope link noprefixroute\n"
            "       valid_lft forever preferred_lft forever\n"
            "    inet6 2400:1000:85a3::8a2e:370:7334/64 scope global noprefixroute\n"
            "       valid_lft forever preferred_lft forever\n"
        )
        interface = RealSystemInterface()
        result = interface._parse_linux_ip_output(output, inet6=True)
        assert result == [
            "fe80::250:56ff:feaa:bbcc",
            "2400:1000:85a3::8a2e:370:7334",
        ]

    def test_parse_linux_ip_output_filters_loopback(self):
        """Test that ::1 loopback is filtered."""
        output = (
            "1: lo: <LOOPBACK> state UNKNOWN\n"
            "    inet6 ::1/128 scope host\n"
        )
        interface = RealSystemInterface()
        result = interface._parse_linux_ip_output(output, inet6=True)
        assert result == []

    def test_parse_linux_ip_output_keeps_docker_ipv6(self):
        """Test that docker interface IPv6 addresses are returned."""
        output = (
            "1: docker0: <BROADCAST> state UP\n"
            "    inet6 fe80::99/64 scope link noprefixroute\n"
            "2: eth0: <BROADCAST> state UP\n"
            "    inet6 fe80::1/64 scope link noprefixroute\n"
        )
        interface = RealSystemInterface()
        result = interface._parse_linux_ip_output(output, inet6=True)
        assert result == ["fe80::99", "fe80::1"]

    def test_parse_linux_ip_output_ipv4(self):
        """Test IPv4 parsing."""
        output = (
            "1: eth0: <BROADCAST> state UP\n"
            "    inet 192.168.1.100/24 brd 192.168.1.255 scope global eth0\n"
        )
        interface = RealSystemInterface()
        result = interface._parse_linux_ip_output(output, inet6=False)
        assert "192.168.1.100" in result

    def test_parse_linux_ip_output_keeps_fe80(self):
        """Test link-local IPv6 addresses can be returned for internal networks."""
        output = (
            "1: eth0: <BROADCAST> state UP\n"
            "    inet6 fe80::1234:5678:abcd/64 scope link noprefixroute\n"
            "    inet6 2400:1000::1/64 scope global\n"
        )
        interface = RealSystemInterface()
        result = interface._parse_linux_ip_output(output, inet6=True)
        assert result == ["fe80::1234:5678:abcd", "2400:1000::1"]

    def test_parse_linux_ip_output_filters_unusable_ipv6(self):
        """Test clearly unusable IPv6 addresses are filtered."""
        output = (
            "1: eth0: <BROADCAST> state UP\n"
            "    inet6 ::/128 scope global\n"
            "    inet6 ff02::1/128 scope global\n"
            "    inet6 2001:db8::1/64 scope global\n"
            "    inet6 fec0::1/64 scope global\n"
            "    inet6 2400:1000::1/64 scope global deprecated\n"
            "    inet6 2400:1000::2/64 scope global tentative\n"
            "    inet6 2400:1000::3/64 scope global\n"
        )
        interface = RealSystemInterface()
        result = interface._parse_linux_ip_output(output, inet6=True)
        assert result == ["2400:1000::3"]


class TestRealSystemInterfaceWindowsParsing:
    """Test Windows ipconfig output parsing."""

    def test_parse_windows_ipconfig_ipv6_normal(self, sample_ipconfig_output):
        """Test normal IPv6 parsing from ipconfig output."""
        result = RealSystemInterface._parse_windows_ipconfig_ipv6(sample_ipconfig_output)
        assert "2400:1000::1" in result
        assert "2400:1000:0:0:0:ff:fe00:1234" in result

    def test_parse_windows_ipconfig_keeps_link_local(self, sample_ipconfig_output):
        """Test that fe80:: link-local addresses are returned."""
        result = RealSystemInterface._parse_windows_ipconfig_ipv6(sample_ipconfig_output)
        assert "fe80::1234" in result

    def test_parse_windows_ipconfig_filters_loopback(self):
        """Test that ::1 loopback is filtered."""
        output = (
            "Loopback Pseudo-Interface 1:\n"
            "   IPv6 Address. . . . . . : ::1\n"
        )
        result = RealSystemInterface._parse_windows_ipconfig_ipv6(output)
        assert result == []

    def test_parse_windows_ipconfig_keeps_tunnel(self):
        """Test that tunnel/virtual adapter IPv6 addresses are returned."""
        output = (
            "Tunnel adapter isatap.example.com:\n\n"
            "   IPv6 Address. . . . . . : 2400:1000::bad\n\n"
            "Ethernet adapter Ethernet:\n\n"
            "   IPv6 Address. . . . . . : 2400:1000::beef\n"
        )
        result = RealSystemInterface._parse_windows_ipconfig_ipv6(output)
        assert result == ["2400:1000::bad", "2400:1000::beef"]

    def test_parse_windows_ipconfig_strips_zone_id(self):
        """Test that zone IDs (%N) are stripped from addresses."""
        output = (
            "Ethernet adapter Ethernet:\n\n"
            "   IPv6 Address. . . . . . : 2400:1000::1%12\n"
        )
        result = RealSystemInterface._parse_windows_ipconfig_ipv6(output)
        assert "2400:1000::1" in result
        assert "%" not in result[0]

    def test_parse_powershell_ipv6_normal(self, sample_powershell_ipv6_output):
        """Test normal IPv6 parsing from PowerShell output."""
        result = RealSystemInterface._parse_powershell_ipv6(sample_powershell_ipv6_output)
        assert "2400:1000::1" in result
        assert "2400:1000:0:0:0:ff:fe00:1234" in result

    def test_parse_powershell_ipv6_filters_unusable_addresses(self):
        """Test that clearly unusable IPv6 addresses are filtered."""
        output = "fe80::1\n::1\n2001:db8::1\nff02::1\n2400:1000::1\n"
        result = RealSystemInterface._parse_powershell_ipv6(output)
        assert result == ["fe80::1", "2400:1000::1"]

    def test_parse_windows_ipconfig_ipv4(self):
        """Test IPv4 parsing from ipconfig output."""
        output = (
            "Ethernet adapter Ethernet:\n\n"
            "   IPv4 Address. . . . . . : 192.168.1.100\n"
            "   Subnet Mask . . . . . . : 255.255.255.0\n"
        )
        result = RealSystemInterface._parse_windows_ipconfig_ipv4(output)
        assert "192.168.1.100" in result
