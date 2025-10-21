# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Tests for E835 controller device IDs in ice driver mapping."""

import pytest
from mfd_typing import DeviceID
from mfd_const.network import DRIVER_DEVICE_ID_MAP


class TestE835DeviceIDs:
    """Test class for E835 controller device IDs."""

    # E835 device IDs that should be mapped to the ice driver
    E835_DEVICE_IDS = {
        # Backplane Controllers
        0x1248: "E835-CC for backplane",
        0x1261: "E835-C for backplane",
        0x1265: "E835-L for backplane",
        # QSFP Controllers
        0x1249: "E835-CC for QSFP",
        0x1262: "E835-C for QSFP",
        0x1266: "E835-L for QSFP",
        # SFP Controllers
        0x124A: "E835-CC for SFP",
        0x1263: "E835-C for SFP",
        0x1267: "E835-L for SFP",
    }

    @pytest.mark.parametrize("device_id_hex,description", E835_DEVICE_IDS.items())
    def test_e835_device_id_in_ice_driver(self, device_id_hex, description):
        """
        Test that E835 device IDs are present in ice driver mapping.

        :param device_id_hex: Device ID in hexadecimal format
        :param description: Description of the device
        """
        device_id = DeviceID(device_id_hex)
        ice_device_ids = DRIVER_DEVICE_ID_MAP.get("ice", set())
        
        assert device_id in ice_device_ids, (
            f"Device ID {hex(device_id_hex)} ({description}) "
            f"should be in ice driver mapping"
        )

    def test_all_e835_devices_present(self):
        """Test that all E835 device IDs are present in ice driver mapping."""
        ice_device_ids = DRIVER_DEVICE_ID_MAP.get("ice", set())
        
        for device_id_hex, description in self.E835_DEVICE_IDS.items():
            device_id = DeviceID(device_id_hex)
            assert device_id in ice_device_ids, (
                f"Device ID {hex(device_id_hex)} ({description}) is missing"
            )

    def test_ice_driver_exists_in_mapping(self):
        """Test that ice driver exists in DRIVER_DEVICE_ID_MAP."""
        assert "ice" in DRIVER_DEVICE_ID_MAP, "ice driver should be in DRIVER_DEVICE_ID_MAP"

    def test_e835_backplane_controllers(self):
        """Test E835 Backplane Controller device IDs."""
        ice_device_ids = DRIVER_DEVICE_ID_MAP.get("ice", set())
        
        backplane_ids = [
            DeviceID(0x1248),  # E835-CC for backplane
            DeviceID(0x1261),  # E835-C for backplane
            DeviceID(0x1265),  # E835-L for backplane
        ]
        
        for device_id in backplane_ids:
            assert device_id in ice_device_ids, (
                f"Backplane controller {hex(int(device_id))} should be in ice driver"
            )

    def test_e835_qsfp_controllers(self):
        """Test E835 QSFP Controller device IDs."""
        ice_device_ids = DRIVER_DEVICE_ID_MAP.get("ice", set())
        
        qsfp_ids = [
            DeviceID(0x1249),  # E835-CC for QSFP
            DeviceID(0x1262),  # E835-C for QSFP
            DeviceID(0x1266),  # E835-L for QSFP
        ]
        
        for device_id in qsfp_ids:
            assert device_id in ice_device_ids, (
                f"QSFP controller {hex(int(device_id))} should be in ice driver"
            )

    def test_e835_sfp_controllers(self):
        """Test E835 SFP Controller device IDs."""
        ice_device_ids = DRIVER_DEVICE_ID_MAP.get("ice", set())
        
        sfp_ids = [
            DeviceID(0x124A),  # E835-CC for SFP
            DeviceID(0x1263),  # E835-C for SFP
            DeviceID(0x1267),  # E835-L for SFP
        ]
        
        for device_id in sfp_ids:
            assert device_id in ice_device_ids, (
                f"SFP controller {hex(int(device_id))} should be in ice driver"
            )
