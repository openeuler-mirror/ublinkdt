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

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

@pytest.fixture
def sample_port_info_dict():
    """Sample port info dictionary."""
    return {
        'port_id': 0,
        'chip_id': 0,
        'port_snrlane': [25.0, 26.3, 27.1, 25.8],
        'cw_fec_cnt': 1234567890,
        'cw_uncorrect_cnt': 1234,
        'cw_total_cnt': 1234567890 + 1234 * 1000
    }


@pytest.fixture
def sample_optical_info_dict():
    """Sample optical module info dictionary."""
    return {
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
        'tx_power': [-3.0 + i * 0.1 for i in range(8)] + [0.0] * 8,
        'rx_power': [-8.0 + i * 0.1 for i in range(8)] + [0.0] * 8,
        'vcc': 3300,
        'temp': 35,
        'tx_bias': [45.0 + i * 1.0 for i in range(8)] + [0.0] * 8,
        'host_snr': [2.5 + i * 0.1 for i in range(8)] + [0.0] * 8,
        'media_snr': [2.8 + i * 0.1 for i in range(8)] + [0.0] * 8
    }


@pytest.fixture
def sample_ipconfig_output():
    """Provide sample Windows ipconfig output text."""
    return (
        "Windows IP Configuration\n\n"
        "Ethernet adapter Ethernet:\n\n"
        "   Connection-specific DNS Suffix  . :\n"
        "   IPv6 Address. . . . . . . . . . : 2400:1000::1\n"
        "   Link-local IPv6 Address . . . . : fe80::1234%12\n"
        "   IPv4 Address. . . . . . . . . . : 192.168.1.100\n"
        "   Subnet Mask . . . . . . . . . . : 255.255.255.0\n\n"
        "Tunnel adapter isatap.example.com:\n\n"
        "   IPv6 Address. . . . . . . . . . : 2001:db8::bad\n\n"
        "Ethernet adapter Ethernet 2:\n\n"
        "   IPv6 Address. . . . . . . . . . : 2400:1000:0:0:0:ff:fe00:1234\n"
    )


@pytest.fixture
def sample_powershell_ipv6_output():
    """Provide sample PowerShell Get-NetIPAddress output text."""
    return (
        "fe80::1234%12\n"
        "2400:1000::1\n"
        "::1\n"
        "2400:1000:0:0:0:ff:fe00:1234\n"
    )
