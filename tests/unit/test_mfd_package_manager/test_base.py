# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Tests for `mfd_package_manager` package."""

import re
from textwrap import dedent

import pytest
from mfd_common_libs import log_levels
from mfd_common_libs.exceptions import UnexpectedOSException
from mfd_connect import RPyCConnection
from mfd_connect.base import ConnectionCompletedProcess
from mfd_connect.exceptions import ConnectionCalledProcessError
from mfd_devcon import Devcon
from mfd_typing import OSName, OSBitness, DeviceID

from mfd_package_manager.base import PackageManager
from mfd_package_manager.bsd import BSDPackageManager
from mfd_package_manager.esxi import ESXiPackageManager
from mfd_package_manager.exceptions import (
    PackageManagerConnectedOSNotSupported,
    PackageManagerNotFoundException,
    PackageManagerModuleException,
)
from mfd_package_manager.linux import LinuxPackageManager
from mfd_package_manager.windows import WindowsPackageManager


class TestMfdPackageManager:
    def test_linux_owner_created(self, mocker):
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.LINUX
        mocker.patch("mfd_ethtool.Ethtool", return_value=mocker.Mock())
        assert isinstance(PackageManager(connection=conn), LinuxPackageManager)

    def test_windows_owner_created(self, mocker):
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.WINDOWS
        mocker.patch(
            "mfd_package_manager.WindowsPackageManager._prepare_devcon", return_value=mocker.create_autospec(Devcon)
        )
        assert isinstance(PackageManager(connection=conn), WindowsPackageManager)

    def test_freebsd_owner_created(self, mocker):
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.FREEBSD
        conn.get_os_bitness.return_value = OSBitness.OS_64BIT

        assert isinstance(PackageManager(connection=conn), BSDPackageManager)

    def test_esxi_owner_created(self, mocker):
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.ESXI

        assert isinstance(PackageManager(connection=conn), ESXiPackageManager)

    def test_unsupported_os(self, mocker):
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.EFISHELL

        with pytest.raises(PackageManagerConnectedOSNotSupported):
            PackageManager(connection=conn)

    def test_ordinary_constructor_os_supported_ok(self, mocker):
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.LINUX
        mocker.patch("mfd_ethtool.Ethtool", return_value=mocker.Mock())

        assert isinstance(LinuxPackageManager(connection=conn), LinuxPackageManager)

    def test_ordinary_constructor_os_supported_fail(self, mocker):
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.WINDOWS
        with pytest.raises(UnexpectedOSException):
            LinuxPackageManager(connection=conn)

    @pytest.fixture()
    def manager(self, mocker):
        conn = mocker.create_autospec(RPyCConnection)
        conn2 = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.LINUX
        conn2.get_os_name.return_value = OSName.LINUX
        mocker.patch("mfd_ethtool.Ethtool", return_value=mocker.Mock())
        yield LinuxPackageManager(connection=conn, controller_connection=conn2)

    def test__get_interface_driver(self, manager):
        assert manager._get_interface_driver(DeviceID(0x1572)) == "i40e"
        with pytest.raises(PackageManagerNotFoundException, match="Not found corresponding driver for 1111 device ID"):
            manager._get_interface_driver(DeviceID(0x1111))

    def test__get_driver_directory(self, manager):
        assert manager._get_driver_directory("i40e") == "PRO40GB"
        with pytest.raises(PackageManagerNotFoundException, match="Not found driver directory for inone driver"):
            manager._get_driver_directory("inone")

    def test__glob_glob_method_windows(self, manager):
        manager._controller_connection.get_os_name.return_value = OSName.WINDOWS
        manager._controller_connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout="C:\\driver\\i40ea.inf\nC:\\driver\\i40eb.inf"
        )
        assert manager._glob_glob_method("", "c:\\driver\\i40*.inf") == [
            "C:\\driver\\i40ea.inf",
            "C:\\driver\\i40eb.inf",
        ]
        manager._controller_connection.execute_command.assert_called_once_with(
            'DIR /B /S "c:\\driver\\i40*.inf"', shell=True
        )

    def test__glob_glob_method_linux(self, manager):
        manager._controller_connection.get_os_name.return_value = OSName.LINUX
        manager._controller_connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout="/home/driver/i40ea.inf\n/home/driver/i40eb.inf"
        )
        assert manager._glob_glob_method("/home/driver/", "/home/driver/i40*.inf") == [
            "/home/driver/i40ea.inf",
            "/home/driver/i40eb.inf",
        ]
        manager._controller_connection.execute_command.assert_called_once_with(
            "find /home/driver/ -ipath '/home/driver/i40*.inf'"
        )

    @pytest.mark.parametrize("conn_name", [OSName.WINDOWS, OSName.LINUX])
    @pytest.mark.parametrize("contr_conn_name", [OSName.WINDOWS, OSName.LINUX])
    def test_controller_connection(self, mocker, conn_name, contr_conn_name):
        mocker.patch(
            "mfd_package_manager.WindowsPackageManager._prepare_devcon", return_value=mocker.create_autospec(Devcon)
        )
        mocker.patch("mfd_ethtool.Ethtool", return_value=mocker.Mock())
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = conn_name
        conn2 = mocker.create_autospec(RPyCConnection)
        conn2.get_os_name.return_value = contr_conn_name
        PackageManager(connection=conn, controller_connection=conn2)

    def test_controller_connection_not_supported(self, mocker):
        mocker.patch("mfd_ethtool.Ethtool", return_value=mocker.Mock())
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.LINUX
        conn2 = mocker.create_autospec(RPyCConnection)
        conn2.get_os_name.return_value = OSName.ESXI
        with pytest.raises(
            PackageManagerConnectedOSNotSupported, match="Not supported OS for controller PackageManager: [OSName.ESXI|VMKernel]"
        ):
            PackageManager(connection=conn, controller_connection=conn2)

    def test_pip_install_package(self, manager, caplog):
        caplog.set_level(level=log_levels.MODULE_DEBUG)
        output = dedent(
            """\
        Installing collected packages: pyserial, future, textfsm, paramiko, ntc-templates, netmiko
          Attempting uninstall: paramiko
            Found existing installation: paramiko 2.9.2
            Uninstalling paramiko-2.9.2:
              Successfully uninstalled paramiko-2.9.2
        Successfully installed future-0.18.3 netmiko-4.2.0 ntc-templates-3.5.0 paramiko-3.3.1 pyserial-3.5"""
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(args="", stdout=output)
        python_executable = "python3.10"
        manager.pip_install_package("paramiko==3.1", python_executable)
        cmd = "unset no_proxy; python3.10 -m pip install --index-url https://pypi.org/simple paramiko==3.1 --retries 3"
        assert "'paramiko' package installation success" in caplog.text
        manager._connection.execute_command.assert_called_once_with(cmd, shell=True, stderr_to_stdout=True)
        manager.pip_install_package("paramiko", python_executable, force_install=True)
        cmd = (
            "unset no_proxy; python3.10 -m pip install --force-reinstall "
            "--index-url https://pypi.org/simple paramiko --retries 3"
        )
        manager._connection.execute_command.assert_called_with(cmd, shell=True, stderr_to_stdout=True)
        manager.pip_install_package("paramiko", python_executable, use_trusted_host=True)
        cmd = (
            "unset no_proxy; python3.10 -m pip install --trusted-host files.pythonhosted.org "
            "--trusted-host pypi.org --trusted-host pypi.python.org "
            "--index-url https://pypi.org/simple paramiko --retries 3"
        )
        manager._connection.execute_command.assert_called_with(cmd, shell=True, stderr_to_stdout=True)

    def test_pip_install_package_with_whitespace(self, manager):
        output = dedent(
            """\
        Installing collected packages: pyserial, future, textfsm, paramiko, ntc-templates, netmiko
          Attempting uninstall: paramiko
            Found existing installation: paramiko 2.9.2
            Uninstalling paramiko-2.9.2:
              Successfully uninstalled paramiko-2.9.2
        Successfully installed future-0.18.3 netmiko-4.2.0 ntc-templates-3.5.0 paramiko-3.3.1 pyserial-3.5"""
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(args="", stdout=output)
        manager.pip_install_package("paramiko == 3.1", "python3")
        cmd = "unset no_proxy; python3 -m pip install --index-url https://pypi.org/simple paramiko==3.1 --retries 3"
        manager._connection.execute_command.assert_called_once_with(cmd, shell=True, stderr_to_stdout=True)

    def test_pip_install_package_package_already_installed(self, manager, caplog):
        output = r"Requirement already satisfied: pytest in c:\venvs\mfd-package-manager310\lib\site-packages (6.2.5)"
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(args="", stdout=output)
        caplog.set_level(log_levels.MODULE_DEBUG)

        package_name = "pytest"
        package_version = "6.2.5"
        package = f"{package_name}=={package_version}"

        manager.pip_install_package(package, use_connection_interpreter=True)

        assert "package is already installed" in caplog.text
        assert package_name in caplog.text

    def test_pip_install_package_package_installation_failure(self, manager, caplog):
        package_name = "example-package"
        package_version = "1.0.0"
        package = f"{package_name}=={package_version}"
        manager._connection.execute_command.side_effect = ConnectionCalledProcessError(returncode=1, cmd="")
        with pytest.raises(PackageManagerModuleException) as exc_info:
            manager.pip_install_package(package, use_connection_interpreter=True)

        assert "Packages installation failed with error:" in str(exc_info.value)

    def test_pip_install_package_failed_package_installation(self, manager, caplog):
        package_name = "example-package"
        package_version = "1.0.0"
        package = f"{package_name}=={package_version}"
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(args="", stdout="")
        with pytest.raises(
            PackageManagerModuleException, match=re.escape("'example-package' package installation failed")
        ):
            manager.pip_install_package(package, use_connection_interpreter=True)

    def test_pip_install_package_no_proxy(self, manager, caplog):
        caplog.set_level(log_levels.MODULE_DEBUG)
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout="Successfully installed example-package"
        )
        manager._connection.modules().sys.executable = "/path/to/python"
        package_name = "example-package"
        package_version = "1.0.0"
        package = f"{package_name}=={package_version}"

        no_proxy_value = "localhost,127.0.0.1"

        manager.pip_install_package(
            package, python_executable="/path/to/python", no_proxy=no_proxy_value, use_connection_interpreter=True
        )
        manager._connection.execute_command.assert_called_with(
            f"export no_proxy={no_proxy_value}; /path/to/python -m pip install "
            "--index-url https://pypi.org/simple example-package==1.0.0 --retries 3",
            shell=True,
            stderr_to_stdout=True,
        )

    def test_valid_package_installation_without_connection_interpreter(self, manager, caplog):
        caplog.set_level(log_levels.MODULE_DEBUG)
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout="Successfully installed example-package"
        )
        package_name = "example-package"
        package_version = "1.0.0"
        package = f"{package_name}=={package_version}"

        manager.pip_install_package(package, python_executable="/path/to/python", use_connection_interpreter=False)

        assert "package installation success" in caplog.text
        assert package_name in caplog.text

    def test_valid_parameters(self, manager):
        manager._verify_pip_parameters(True, "/usr/bin/python", True)

    def test_missing_executable(self, manager):
        with pytest.raises(ValueError):
            manager._verify_pip_parameters(False, None, True)

    def test_use_connection_interpreter_without_python_connection(self, manager, caplog):
        caplog.set_level(log_levels.MODULE_DEBUG)
        manager._verify_pip_parameters(False, "/usr/bin/python", True)
        assert (
            "Connection interpreter is not available for other connection than Python (RPyC and Local)" in caplog.text
        )

    def test_use_connection_interpreter_with_python_connection(self, manager):
        manager._verify_pip_parameters(True, "/usr/bin/python", True)

    def test_pip_install_packages(self, manager, mocker):
        manager.pip_install_package = mocker.create_autospec(manager.pip_install_package)
        manager.pip_install_packages(package_list=["example-package", "paramiko"])
        calls = [
            mocker.call(
                force_install=False,
                index_url="https://pypi.org/simple",
                no_proxy=None,
                package="example-package",
                python_executable=None,
                use_trusted_host=False,
                use_connection_interpreter=False,
            ),
            mocker.call(
                force_install=False,
                index_url="https://pypi.org/simple",
                no_proxy=None,
                package="paramiko",
                python_executable=None,
                use_trusted_host=False,
                use_connection_interpreter=False,
            ),
        ]

        manager.pip_install_package.assert_has_calls(calls)
