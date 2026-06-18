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

from dataclasses import dataclass, field
from typing import List, Optional

from .schema import OPTICAL_LANE_COUNT, OPTICAL_TYPE_MAP, PORT_SNR_LANE_COUNT


def get_optical_type_name(optical_type: int) -> str:
    """Get optical type name from type code."""
    return OPTICAL_TYPE_MAP.get(optical_type, "Reserved")


@dataclass
class PortInfo:
    """Port information data model."""
    port_id: int
    chip_id: int
    port_snrlane: List[float] = field(default_factory=lambda: [0.0] * PORT_SNR_LANE_COUNT)
    cw_fec_cnt: int = 0
    cw_uncorrect_cnt: int = 0
    cw_total_cnt: int = 0
    link_status: str = ""

    def __post_init__(self):
        if len(self.port_snrlane) != PORT_SNR_LANE_COUNT:
            self.port_snrlane = [0.0] * PORT_SNR_LANE_COUNT

    def validate(self) -> bool:
        """Validate port info data."""
        if self.port_id < 0:
            return False
        if self.chip_id not in (0, 1):
            return False
        if len(self.port_snrlane) != PORT_SNR_LANE_COUNT:
            return False
        if self.cw_fec_cnt < 0 or self.cw_uncorrect_cnt < 0:
            return False
        return True

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'port_id': self.port_id,
            'chip_id': self.chip_id,
            'port_snrlane': self.port_snrlane,
            'cw_fec_cnt': self.cw_fec_cnt,
            'cw_uncorrect_cnt': self.cw_uncorrect_cnt,
            'cw_total_cnt': self.cw_total_cnt,
            'link_status': self.link_status
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'PortInfo':
        """Create from dictionary."""
        return cls(
            port_id=data.get('port_id', 0),
            chip_id=data.get('chip_id', 0),
            port_snrlane=data.get('port_snrlane', [0.0] * PORT_SNR_LANE_COUNT),
            cw_fec_cnt=data.get('cw_fec_cnt', 0),
            cw_uncorrect_cnt=data.get('cw_uncorrect_cnt', 0),
            cw_total_cnt=data.get('cw_total_cnt', 0),
            link_status=data.get('link_status', '')
        )


@dataclass
class OpticalModuleInfo:
    """Optical module information data model."""
    port_id: int
    chip_id: int
    optical_sn: str = ''
    optical_vendor: str = ''
    optical_state: int = 0
    optical_type: int = 0
    optical_type_name: str = ''
    interface_code: int = 0
    lane_count: int = 0
    tx_los_flag: Optional[int] = 0
    rx_los_flag: Optional[int] = 0
    tx_lol_flag: Optional[int] = 0
    rx_lol_flag: Optional[int] = 0
    tx_power: List[Optional[float]] = field(default_factory=lambda: [0.0] * OPTICAL_LANE_COUNT)
    rx_power: List[Optional[float]] = field(default_factory=lambda: [0.0] * OPTICAL_LANE_COUNT)
    vcc: Optional[int] = 0
    temp: Optional[int] = 0
    tx_bias: List[Optional[float]] = field(default_factory=lambda: [0.0] * OPTICAL_LANE_COUNT)
    host_snr: List[Optional[float]] = field(default_factory=lambda: [0.0] * OPTICAL_LANE_COUNT)
    media_snr: List[Optional[float]] = field(default_factory=lambda: [0.0] * OPTICAL_LANE_COUNT)

    def __post_init__(self):
        if len(self.tx_power) != OPTICAL_LANE_COUNT:
            self.tx_power = [0.0] * OPTICAL_LANE_COUNT
        if len(self.rx_power) != OPTICAL_LANE_COUNT:
            self.rx_power = [0.0] * OPTICAL_LANE_COUNT
        if len(self.tx_bias) != OPTICAL_LANE_COUNT:
            self.tx_bias = [0.0] * OPTICAL_LANE_COUNT
        if len(self.host_snr) != OPTICAL_LANE_COUNT:
            self.host_snr = [0.0] * OPTICAL_LANE_COUNT
        if len(self.media_snr) != OPTICAL_LANE_COUNT:
            self.media_snr = [0.0] * OPTICAL_LANE_COUNT

    def validate(self) -> bool:
        """Validate optical module info data."""
        if self.port_id < 0:
            return False
        if self.chip_id not in (0, 1):
            return False
        if len(self.tx_power) != OPTICAL_LANE_COUNT or len(self.rx_power) != OPTICAL_LANE_COUNT:
            return False
        if len(self.tx_bias) != OPTICAL_LANE_COUNT or len(self.host_snr) != OPTICAL_LANE_COUNT or len(self.media_snr) != OPTICAL_LANE_COUNT:
            return False
        return True

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'port_id': self.port_id,
            'chip_id': self.chip_id,
            'optical_sn': self.optical_sn,
            'optical_vendor': self.optical_vendor,
            'optical_state': self.optical_state,
            'optical_type': self.optical_type,
            'optical_type_name': self.optical_type_name,
            'interface_code': self.interface_code,
            'lane_count': self.lane_count,
            'tx_los_flag': self.tx_los_flag,
            'rx_los_flag': self.rx_los_flag,
            'tx_lol_flag': self.tx_lol_flag,
            'rx_lol_flag': self.rx_lol_flag,
            'tx_power': self.tx_power,
            'rx_power': self.rx_power,
            'vcc': self.vcc,
            'temp': self.temp,
            'tx_bias': self.tx_bias,
            'host_snr': self.host_snr,
            'media_snr': self.media_snr
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'OpticalModuleInfo':
        """Create from dictionary."""
        return cls(
            port_id=data.get('port_id', 0),
            chip_id=data.get('chip_id', 0),
            optical_sn=data.get('optical_sn', ''),
            optical_vendor=data.get('optical_vendor', ''),
            optical_state=data.get('optical_state', 0),
            optical_type=data.get('optical_type', 0),
            optical_type_name=data.get('optical_type_name', ''),
            interface_code=data.get('interface_code', 0),
            lane_count=data.get('lane_count', 0),
            tx_los_flag=data.get('tx_los_flag', 0),
            rx_los_flag=data.get('rx_los_flag', 0),
            tx_lol_flag=data.get('tx_lol_flag', 0),
            rx_lol_flag=data.get('rx_lol_flag', 0),
            tx_power=data.get('tx_power', [0.0] * OPTICAL_LANE_COUNT),
            rx_power=data.get('rx_power', [0.0] * OPTICAL_LANE_COUNT),
            vcc=data.get('vcc', 0),
            temp=data.get('temp', 0),
            tx_bias=data.get('tx_bias', [0.0] * OPTICAL_LANE_COUNT),
            host_snr=data.get('host_snr', [0.0] * OPTICAL_LANE_COUNT),
            media_snr=data.get('media_snr', [0.0] * OPTICAL_LANE_COUNT)
        )
