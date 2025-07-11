# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
from textwrap import dedent

import pytest
from mfd_connect import RPyCConnection
from mfd_connect.base import ConnectionCompletedProcess
from mfd_typing import OSName, OSBitness

from mfd_package_manager import BSDPackageManager


class TestBSDPackageManager:
    @pytest.fixture()
    def manager(self, mocker):
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.FREEBSD
        conn.get_os_bitness.return_value = OSBitness.OS_64BIT
        yield BSDPackageManager(connection=conn)

    def test_is_module_loaded(self, manager):
        manager._connection.execute_command.side_effect = [
            ConnectionCompletedProcess(args="", stdout=" 4    1 0xffffffff821fa000    77758 if_igb.ko", return_code=0),
            ConnectionCompletedProcess(args="", stdout="", return_code=1),
        ]
        assert manager.is_module_loaded("i40e") is True
        assert manager.is_module_loaded("igb") is False

    def test_load_module(self, manager):
        manager.load_module("ixl")
        manager._connection.execute_command.assert_called_with("kldload -v ixl", expected_return_codes={0}, shell=True)

    def test_unload_module(self, manager):
        manager.unload_module("ixl")
        manager._connection.execute_command.assert_called_with(
            "kldunload -v ixl", expected_return_codes={0}, shell=True
        )

    def test_get_module_filename(self, manager):
        output = dedent(
            """
                         2    1 0xffffffff82111000    57560 if_ixl.ko (/boot/kernel/if_ixl.ko)
                Contains modules:
                     Id Name
                      1 pci/ixl
             3    1 0xffffffff82169000    52748 if_ix.ko (/boot/kernel/if_ix.ko)
                Contains modules:
                     Id Name
                      2 pci/ix
             4    1 0xffffffff821bc000    79c58 if_igb.ko (/boot/kernel/if_igb.ko)
                Contains modules:
                     Id Name
                      4 pci/igb
                      3 pci/em
            """
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=output, return_code=0
        )
        assert manager.get_module_filename("ixl") == "/boot/kernel/if_ixl.ko"
