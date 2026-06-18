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
import platform
import subprocess
import re
import ipaddress
from abc import ABC, abstractmethod
from typing import Optional, List

logger = logging.getLogger(__name__)

UNUSABLE_IPV6_NETWORKS = (
    ipaddress.IPv6Network('2001:db8::/32'),
    ipaddress.IPv6Network('fec0::/10'),
)
UNUSABLE_IPV6_STATES = ('tentative', 'dadfailed', 'deprecated', 'duplicate')


class SystemInterface(ABC):
    """System interface base class."""

    @abstractmethod
    def get_ip_address(self, port_id: int, chip_id: int, inet6: bool = False) -> Optional[str]:
        """Get IP address.

        Args:
            port_id: Port ID
            chip_id: Chip ID (0 or 1)
            inet6: Whether to get IPv6 address

        Returns:
            IP address string or None
        """
        pass


class RealSystemInterface(SystemInterface):
    """Real system interface (for production).

    Supports both Linux and Windows platforms for IP address queries.
    """

    def get_ip_address(self, port_id: int, chip_id: int, inet6: bool = False) -> Optional[str]:
        """Get real IP address (cross-platform).

        Detects the current platform and dispatches to the appropriate
        command and parser.

        Args:
            port_id: Port ID
            chip_id: Chip ID (0 or 1)
            inet6: Whether to get IPv6 address

        Returns:
            IP address string or None
        """
        try:
            current_platform = platform.system()

            if current_platform == "Linux":
                return self._get_ip_linux(inet6)
            elif current_platform == "Windows":
                return self._get_ip_windows(inet6)
            else:
                logger.warning(f"Unsupported platform: {current_platform}")
                return None

        except subprocess.TimeoutExpired:
            logger.error("IP address query timed out")
            return None
        except Exception as e:
            logger.error(f"Error getting IP address: {e}")
            return None

    # ── Linux ──────────────────────────────────────────────────────

    def _get_ip_linux(self, inet6: bool) -> Optional[str]:
        """Get IP address on Linux using the ``ip`` command."""
        if inet6:
            cmd = ['ip', '-6', 'addr', 'show']
        else:
            cmd = ['ip', '-4', 'addr', 'show']

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            logger.error(f"Failed to execute command: {result.stderr}")
            return None

        ip_addresses = self._parse_linux_ip_output(result.stdout, inet6)
        if not ip_addresses:
            return None
        return ip_addresses[0]

    def _parse_linux_ip_output(self, output: str, inet6: bool) -> List[str]:
        """Parse Linux ``ip`` command output to extract IP addresses."""
        ip_addresses = []
        skip_prefixes = ['lo', 'docker', 'br-', 'veth', 'flannel', 'cni']

        current_interface = None
        interface_state = 'UNKNOWN'

        for line in output.split('\n'):
            line = line.strip()

            if not line:
                continue

            if line[0].isdigit():
                match = re.match(r'^\d+:\s+(\S+):', line)
                if match:
                    current_interface = match.group(1)
                    interface_state = 'UP' if 'state UP' in line or 'state UNKNOWN' in line else 'DOWN'

            elif line.startswith('inet6 '):
                if current_interface:
                    parts = line.split()
                    if len(parts) >= 2:
                        ip = parts[1].split('/')[0]
                        if self._is_usable_ipv6_address(ip, line):
                            ip_addresses.append(ip)

            elif line.startswith('inet '):
                if current_interface:
                    skip_interface = any(current_interface.startswith(prefix) for prefix in skip_prefixes)
                    if skip_interface or interface_state == 'DOWN':
                        continue

                    parts = line.split()
                    if len(parts) >= 2:
                        ip = parts[1].split('/')[0]
                        if ip and ip != '127.0.0.1':
                            ip_addresses.append(ip)

        return ip_addresses

    # ── Windows ────────────────────────────────────────────────────

    def _get_ip_windows(self, inet6: bool) -> Optional[str]:
        """Get IP address on Windows."""
        if inet6:
            ip_addresses = self._get_ipv6_windows_ipconfig()
            if not ip_addresses:
                ip_addresses = self._get_ipv6_windows_powershell()
        else:
            ip_addresses = self._get_ipv4_windows()
        if not ip_addresses:
            return None
        return ip_addresses[0]

    def _get_ipv6_windows_ipconfig(self) -> List[str]:
        """Get IPv6 addresses using ``ipconfig``."""
        try:
            result = subprocess.run(
                ['ipconfig'],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return []
            return self._parse_windows_ipconfig_ipv6(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    def _get_ipv6_windows_powershell(self) -> List[str]:
        """Get IPv6 addresses using PowerShell ``Get-NetIPAddress``."""
        try:
            cmd = [
                'powershell', '-NoProfile', '-Command',
                'Get-NetIPAddress -AddressFamily IPv6 | '
                'Where-Object { $_.AddressState -eq "Preferred" } | '
                'Select-Object -ExpandProperty IPAddress',
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                return []
            return self._parse_powershell_ipv6(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    def _get_ipv4_windows(self) -> List[str]:
        """Get IPv4 addresses using ``ipconfig``."""
        try:
            result = subprocess.run(
                ['ipconfig'],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return []
            return self._parse_windows_ipconfig_ipv4(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    @staticmethod
    def _is_usable_ipv6_address(ip: str, context: str = "") -> bool:
        """Return False for IPv6 addresses that are clearly not useful."""
        if any(state in context.lower() for state in UNUSABLE_IPV6_STATES):
            return False

        address_text = ip.split('%', 1)[0].strip()
        try:
            address = ipaddress.IPv6Address(address_text)
        except ValueError:
            return False

        if address.is_unspecified or address.is_loopback or address.is_multicast:
            return False

        return not any(address in network for network in UNUSABLE_IPV6_NETWORKS)

    @staticmethod
    def _parse_windows_ipconfig_ipv6(output: str) -> List[str]:
        """Parse IPv6 addresses from ``ipconfig`` text output.

        Returns usable IPv6 addresses in output order.
        """
        ip_addresses = []

        for line in output.split('\n'):
            stripped = line.strip()

            if stripped.endswith(':') and not stripped.startswith(' '):
                continue

            lower = stripped.lower()
            if 'ipv6' in lower and 'address' in lower:
                # Split on the FIRST colon (label:value separator)
                # IPv6 address colons come after the first colon.
                if ':' in stripped:
                    value = stripped.split(':', 1)[1].strip()
                    ip = value.split('%')[0]
                    if RealSystemInterface._is_usable_ipv6_address(ip, stripped):
                        ip_addresses.append(ip)

        return ip_addresses

    @staticmethod
    def _parse_windows_ipconfig_ipv4(output: str) -> List[str]:
        """Parse IPv4 addresses from ``ipconfig`` text output."""
        ip_addresses = []
        skip_adapter_keywords = [
            'tunnel', 'loopback', 'isatap', 'teredo',
            'bluetooth', 'vmware', 'virtual',
        ]
        current_adapter = None
        skip_current = False

        for line in output.split('\n'):
            stripped = line.strip()

            if stripped.endswith(':') and not stripped.startswith(' '):
                current_adapter = stripped.rstrip(':').lower()
                skip_current = any(
                    kw in current_adapter for kw in skip_adapter_keywords
                )
                continue

            if skip_current:
                continue

            lower = stripped.lower()
            if 'ipv4' in lower and 'address' in lower:
                if ':' in stripped:
                    value = stripped.split(':', 1)[1].strip()
                    if value and value != '127.0.0.1':
                        ip_addresses.append(value)

        return ip_addresses

    @staticmethod
    def _parse_powershell_ipv6(output: str) -> List[str]:
        """Parse IPv6 addresses from PowerShell ``Get-NetIPAddress`` output."""
        ip_addresses = []
        for line in output.strip().split('\n'):
            ip = line.strip()
            if ip and ':' in ip and RealSystemInterface._is_usable_ipv6_address(ip, line):
                ip_addresses.append(ip)
        return ip_addresses


def get_system_interface(source: str = "real") -> SystemInterface:
    """Get system interface instance.

    Args:
        source: Interface type ("real")

    Returns:
        SystemInterface instance
    """
    if source == "real":
        return RealSystemInterface()
    raise ValueError(f"Unknown source '{source}'")


system_interface = get_system_interface()
