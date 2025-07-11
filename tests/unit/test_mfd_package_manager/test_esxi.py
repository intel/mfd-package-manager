# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
from textwrap import dedent
from unittest.mock import call

import pytest
from mfd_connect import RPyCConnection
from mfd_connect.base import ConnectionCompletedProcess
from mfd_typing import OSName
from mfd_typing.driver_info import DriverInfo

from mfd_package_manager import ESXiPackageManager
from mfd_package_manager.data_structures import VIBData


class TestESXiPackageManager:
    @pytest.fixture
    def manager(self, mocker):
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.ESXI
        return ESXiPackageManager(connection=conn)

    def test_unload_module(self, manager):
        manager.unload_module("module_name")
        manager._connection.execute_command.assert_called_with("vmkload_mod -u module_name")

    def test_load_module(self, manager):
        manager.load_module("module_name", "p=a r=a m=s")
        manager._connection.execute_command.assert_has_calls(
            [
                call('esxcfg-module module_name -s "p=a r=a m=s"'),
                call("pkill -HUP vmkdevmgr", shell=True),
            ]
        )

    def test_uninstall_vib(self, manager):
        manager.uninstall_vib("vib_name")
        manager._connection.execute_command.assert_called_with("esxcli software vib remove -n vib_name")

    def test_install_vib(self, manager):
        manager.install_vib("vib_path", "p=a r=a m=s")
        manager._connection.execute_command.assert_called_with("esxcli software vib install p=a r=a m=s -d vib_path")

    def test_install_vib_vib(self, manager):
        manager.install_vib("vib_path.vib", "p=a r=a m=s")
        manager._connection.execute_command.assert_called_with(
            "esxcli software vib install p=a r=a m=s -v vib_path.vib"
        )

    def test_get_module_params(self, manager):
        output = "vmkernel enabled = 1 options = ''"
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=output, return_code=0
        )
        assert manager.get_module_params("vmkernel") == output

    def test_get_module_params_as_dict(self, manager):
        output = "icen enabled = 1 options = 'vmdq=1,2,3,4 sriov=0,0,1,1'"
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=output, return_code=0
        )
        assert manager.get_module_params_as_dict("icen") == {"vmdq": "1,2,3,4", "sriov": "0,0,1,1"}

    def test_get_module_params_as_dict_empty_options(self, manager):
        output = "icen enabled = 1 options = ''"
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=output, return_code=0
        )
        assert manager.get_module_params_as_dict("icen") == {}

    def test_get_installed_vibs(self, manager):
        output = dedent(
            """\
            Name                           Version                                Vendor  Acceptance Level  Install Date
            -----------------------------  -------------------------------------  ------  ----------------  ------------
            ixgben                         1.12.3.0-1OEM.700.1.0.15843807         INT     VMwareCertified   2023-05-05
            itp_tools                      2.0.8                                  Intel   VMwareCertified   2023-05-05
            atlantic                       1.0.3.0-8vmw.703.0.20.19193900         VMW     VMwareCertified   2023-05-05
            """
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=output, return_code=0
        )
        vib_list = [
            VIBData("ixgben", "1.12.3.0-1OEM.700.1.0.15843807", "INT", "VMwareCertified", "2023-05-05"),
            VIBData("itp_tools", "2.0.8", "Intel", "VMwareCertified", "2023-05-05"),
            VIBData("atlantic", "1.0.3.0-8vmw.703.0.20.19193900", "VMW", "VMwareCertified", "2023-05-05"),
        ]
        assert manager.get_installed_vibs() == vib_list

    def test_get_driver_info(self, manager):
        output = dedent(
            """\
            Advertised Auto Negotiation: true
            Advertised Link Modes: Auto, 100BaseT/Full, 1000BaseT/Full, 2500BaseT/Full, 5000BaseT/Full, 10000BaseT/Full
            Auto Negotiation: true
            Cable Type: Twisted Pair
            Current Message Level: 0
            Driver Info:
                Bus Info: 0000:18:00:0
                Driver: ixgben
                Firmware Version: 1.55 0x80000a42, 1.1767.0
                Version: 1.12.3.0
            Link Detected: true
            Link Status: Up
            Name: vmnic0
            PHYAddress: 0
            Pause Autonegotiate: false
            Pause RX: true
            Pause TX: true
            Supported Ports: TP
            Supports Auto Negotiation: true
            Supports Pause: true
            Supports Wakeon: false
            Transceiver:
            Virtual Address: 00:50:56:55:95:95
            Wakeon: None
            """
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=output, return_code=0
        )
        assert manager.get_driver_info("interface_name") == DriverInfo("ixgben", "1.12.3.0")
