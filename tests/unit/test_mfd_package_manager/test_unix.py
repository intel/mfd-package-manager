# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
import pytest
from mfd_connect import RPyCConnection
from mfd_typing import OSName

from mfd_package_manager.unix import UnixPackageManager


class TestUnixPackageManager:
    @pytest.fixture()
    def manager(self, mocker):
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.LINUX
        mocker.patch("mfd_package_manager.unix.UnixPackageManager.__abstractmethods__", [])
        yield UnixPackageManager(connection=conn)

    def test_simple_make(self, manager):
        manager.make()
        manager._connection.execute_command.assert_called_with("make", cwd=None)

    def test_make(self, manager):
        cwd_path = "/home/driver/src"
        manager.make(targets=["install", "clean"], jobs=2, cwd=cwd_path)
        manager._connection.execute_command.assert_called_with("make -j2 install clean", cwd=cwd_path)
        manager.make(targets="install clean", jobs=4, cwd=cwd_path)
        manager._connection.execute_command.assert_called_with("make -j4 install clean", cwd=cwd_path)
        manager.make(targets="install clean", cflags="c=1 a=5")
        manager._connection.execute_command.assert_called_with("make c=1 a=5 install clean", cwd=None)
        manager.make(targets="install clean", cflags={"c": 1, "a": 5})
        manager._connection.execute_command.assert_called_with("make c=1 a=5 install clean", cwd=None)

    def test_simple_make_install(self, manager):
        manager.make_install()
        manager._connection.execute_command.assert_called_with("make install", cwd=None)

    def test_simple_make_uninstall(self, manager):
        manager.make_uninstall()
        manager._connection.execute_command.assert_called_with("make uninstall", cwd=None)

    def test_simple_make_clean(self, manager):
        manager.make_clean()
        manager._connection.execute_command.assert_called_with("make clean", cwd=None)

    def test_simple_make_modules_uninstall(self, manager):
        manager.make_modules_uninstall()
        manager._connection.execute_command.assert_called_with("make modules_uninstall", cwd=None)
