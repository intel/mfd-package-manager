# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
import dataclasses
import re
from pathlib import PurePath, Path
from textwrap import dedent

import pytest
from mfd_common_libs import log_levels
from mfd_connect import RPyCConnection, SSHConnection, LocalConnection
from mfd_connect.base import ConnectionCompletedProcess
from mfd_devcon import Devcon, DevconDriverNodes, DevconHwids
from mfd_typing.os_values import SystemInfo

from mfd_package_manager.data_structures import WindowsStoreDriver, DriverDetails, InstallationMethod
from mfd_package_manager.exceptions import (
    PackageManagerModuleException,
    PackageManagerConnectedOSNotSupported,
    PackageManagerNotFoundException,
)
from mfd_typing import OSName, DeviceID

from mfd_package_manager import WindowsPackageManager
from mfd_win_registry import WindowsRegistry


class TestWindowsPackageManager:
    @pytest.fixture()
    def manager(self, mocker):
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.WINDOWS
        devcon_mock = mocker.create_autospec(Devcon)
        devcon_mock._tool_exec = "devcon.exe"
        devcon_mock._connection = conn
        conn.ip = "10.10.10.10"
        mocker.patch("mfd_package_manager.WindowsPackageManager._prepare_devcon", return_value=devcon_mock)
        yield WindowsPackageManager(connection=conn)

    def test_delete_driver_via_pnputil(self, manager, mocker):
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout="deleted successfully", return_code=0
        )
        manager.delete_driver_via_pnputil("oem3.inf")
        manager._connection.execute_command.assert_called_with(
            "pnputil /delete-driver oem3.inf /force /uninstall",
            timeout=90,
            expected_return_codes=None,
            stderr_to_stdout=True,
        )
        manager._connection.execute_command.side_effect = [
            ConnectionCompletedProcess(args="", stdout="", return_code=1),
            ConnectionCompletedProcess(args="", stdout="deleted successfully", return_code=0),
        ]
        manager.delete_driver_via_pnputil("oem3.inf")
        manager._connection.execute_command.assert_has_calls(
            [
                mocker.call(
                    "pnputil /delete-driver oem3.inf /force /uninstall",
                    timeout=90,
                    expected_return_codes=None,
                    stderr_to_stdout=True,
                ),
                mocker.call(
                    "pnputil /delete-driver oem3.inf /force",
                    timeout=90,
                    expected_return_codes=None,
                    stderr_to_stdout=True,
                ),
            ]
        )
        manager._connection.execute_command.side_effect = [
            ConnectionCompletedProcess(args="", stdout="", return_code=1),
            ConnectionCompletedProcess(args="", stdout="", return_code=1),
        ]
        with pytest.raises(PackageManagerModuleException):
            manager.delete_driver_via_pnputil("oem3.inf")
            manager._connection.execute_command.assert_has_calls(
                [
                    mocker.call(
                        "pnputil /delete-driver /force /uninstall oem3.inf",
                        timeout=90,
                        expected_return_codes=None,
                        stderr_to_stdout=True,
                    ),
                    mocker.call(
                        "pnputil /delete-driver /force oem3.inf",
                        timeout=90,
                        expected_return_codes=None,
                        stderr_to_stdout=True,
                    ),
                ]
            )

    def test_get_driver_filename_from_registry(self, manager):
        output = dedent(
            r"""\
        ImagePath    : \SystemRoot\System32\drivers\i40ea68.sys
        PSPath       : Microsoft.PowerShell.Core\Registry::HKEY_LOCAL_MACHINE\system\CurrentControlSet\services\i40ea
        PSParentPath : Microsoft.PowerShell.Core\Registry::HKEY_LOCAL_MACHINE\system\CurrentControlSet\services
        PSChildName  : i40ea
        PSDrive      : HKLM
        PSProvider   : Microsoft.PowerShell.Core\Registry
        """
        )
        manager._connection.execute_powershell.return_value = ConnectionCompletedProcess(
            args="", stdout=output, return_code=0
        )
        assert manager.get_driver_filename_from_registry("i40ea") == "i40ea68.sys"
        manager._connection.execute_powershell.assert_called_with(
            r"Get-ItemProperty -path 'HKLM:\system\CurrentControlSet\services\i40ea' -name 'ImagePath'",
            stderr_to_stdout=True,
        )
        manager._connection.execute_powershell.return_value = ConnectionCompletedProcess(
            args="", stdout="output", return_code=0
        )
        with pytest.raises(PackageManagerModuleException):
            manager.get_driver_filename_from_registry("i40ea") == "i40ea68.sys"

    def test_install_inf_driver_for_matching_devices(self, manager):
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout="package installed", return_code=0
        )
        manager.install_inf_driver_for_matching_devices("c:\\driver\\i40ea.inf")
        manager._connection.execute_command.assert_called_with(
            'pnputil /add-driver "c:\\driver\\i40ea.inf" /install',
            shell=True,
            stderr_to_stdout=True,
            expected_return_codes={0, 259, 3010, 1641},
        )

    def test_get_driver_version_by_inf_name(self, manager):
        manager._connection.execute_powershell.return_value = ConnectionCompletedProcess(
            args="", stdout="10.0.17763.1\n", return_code=0
        )
        assert manager.get_driver_version_by_inf_name("i40ea.inf") == "10.0.17763.1"
        manager._connection.execute_powershell.assert_called_with(
            'Get-WindowsDriver -Online -All | ? {$_.OriginalFileName -like "*i40ea.inf"} '
            "| select -ExpandProperty Version",
            stderr_to_stdout=True,
        )

    def test_install_certificates_from_driver(self, manager, mocker):
        expected_command = (
            "$exportType = [System.Security.Cryptography.X509Certificates.X509ContentType]::Cert;"
            '$cert = (Get-AuthenticodeSignature "C:\\driver\\i40ea.sys").SignerCertificate;'
            '[System.IO.File]::WriteAllBytes("C:\\exported_output.cer", $cert.Export($exportType));'
            'Import-Certificate -FilePath "C:\\exported_output.cer" -CertStoreLocation '
            "Cert:\\LocalMachine\\TrustedPublisher; Import-Certificate "
            '-FilePath "C:\\exported_output.cer" -CertStoreLocation Cert:\\LocalMachine\\Root'
        )
        expected_command2 = (
            "$exportType = [System.Security.Cryptography.X509Certificates.X509ContentType]::Cert;"
            '$cert = (Get-AuthenticodeSignature "C:\\driver\\i40ea.cat").SignerCertificate;'
            '[System.IO.File]::WriteAllBytes("C:\\exported_output.cer", $cert.Export($exportType));'
            'Import-Certificate -FilePath "C:\\exported_output.cer" '
            "-CertStoreLocation Cert:\\LocalMachine\\TrustedPublisher; "
            'Import-Certificate -FilePath "C:\\exported_output.cer" '
            "-CertStoreLocation Cert:\\LocalMachine\\Root"
        )
        path_to_cert_mock = mocker.create_autospec(PurePath("C:\\exported_output.cer"))
        path_to_cert_mock.__str__.return_value = "C:\\exported_output.cer"
        inf_path_mock = mocker.create_autospec(Path("C:\\driver\\i40ea.inf"))
        inf_path_mock.exists.return_value = True
        inf_path_mock.__str__.return_value = "C:\\driver\\i40ea.inf"
        path_to_sys_mock = mocker.create_autospec(Path("C:\\driver\\i40ea.sys"))
        path_to_sys_mock.exists.return_value = True
        path_to_sys_mock.__str__.return_value = "C:\\driver\\i40ea.sys"
        path_to_sys_mock2 = mocker.create_autospec(Path("C:\\driver\\i40ea.cat"))
        path_to_sys_mock2.exists.return_value = True
        path_to_sys_mock2.__str__.return_value = "C:\\driver\\i40ea.cat"
        inf_path_mock.with_suffix.side_effect = [path_to_sys_mock, path_to_sys_mock2]
        manager._connection.path.side_effect = [path_to_cert_mock, inf_path_mock]
        manager.install_certificates_from_driver("C:\\driver\\i40ea.inf")
        manager._connection.execute_powershell.assert_has_calls(
            [
                mocker.call(command=expected_command, expected_return_codes={0}),
                mocker.call(command=expected_command2, expected_return_codes={0}),
            ]
        )

    def test_unload_driver(self, manager):
        manager.unload_driver("PCI\\VEN_8086&DEV_1563&SUBSYS_35D48086&REV_01\\0000C9FFFF00000000")
        manager.devcon.remove_devices.assert_called_with(
            device_id="PCI\\VEN_8086&DEV_1563&SUBSYS_35D48086&REV_01\\0000C9FFFF00000000",
        )

    def test_get_driver_path_in_system_for_interface(self, manager):
        manager._connection.execute_powershell.return_value = ConnectionCompletedProcess(
            args="", stdout="\\SystemRoot\\System32\\drivers\\i40ea68.sys\n", return_code=0
        )
        assert (
            manager.get_driver_path_in_system_for_interface("Ethernet 5") == r"C:\Windows\System32\drivers\i40ea68.inf"
        )

    def test_get_driver_files(self, manager):
        expected_output = [
            WindowsStoreDriver(
                published_name="oem15.inf",
                original_name="i40ea68.inf",
                provider_name="Intel",
                class_name="Network adapters",
                class_guid="{4d36e972-e325-11ce-bfc1-08002be10318}",
                driver_version="12/22/2022 1.16.202.10",
                signer_name="Microsoft Windows Hardware Compatibility Publisher",
            ),
            WindowsStoreDriver(
                published_name="oem1.inf",
                original_name="netkvm.inf",
                provider_name="Red Hat, Inc.",
                class_name="Network adapters",
                class_guid="{4d36e972-e325-11ce-bfc1-08002be10318}",
                driver_version="02/23/2022 100.90.104.21700",
                signer_name="Microsoft Windows Hardware Compatibility Publisher",
            ),
        ]
        stdout = dedent(
            """\
        Microsoft PnP Utility

        Published Name:     oem15.inf
        Original Name:      i40ea68.inf
        Provider Name:      Intel
        Class Name:         Network adapters
        Class GUID:         {4d36e972-e325-11ce-bfc1-08002be10318}
        Driver Version:     12/22/2022 1.16.202.10
        Signer Name:        Microsoft Windows Hardware Compatibility Publisher

        Published Name:     oem1.inf
        Original Name:      netkvm.inf
        Provider Name:      Red Hat, Inc.
        Class Name:         Network adapters
        Class GUID:         {4d36e972-e325-11ce-bfc1-08002be10318}
        Driver Version:     02/23/2022 100.90.104.21700
        Signer Name:        Microsoft Windows Hardware Compatibility Publisher
        """
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=stdout, return_code=0
        )
        assert manager.get_driver_files() == expected_output

    def test_check_device_status(self, manager):
        stdout = dedent(
            r"""
        PCI\VEN_8086&DEV_1572&SUBSYS_00078086&REV_01\388BCFFFFFFEFD3C00
        Name: Intel(R) Ethernet Converged Network Adapter X710-2
        Driver is running.
        PCI\VEN_8086&DEV_1572&SUBSYS_00008086&REV_01\388BCFFFFFFEFD3C01
            Name: Intel(R) Ethernet Converged Network Adapter X710
            Driver is running.
        2 matching device(s) found."""
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=stdout, return_code=0
        )
        assert manager.check_device_status(DeviceID("1572")) is False
        stdout = dedent(
            r"""
        PCI\VEN_8086&DEV_1572&SUBSYS_00078086&REV_01\388BCFFFFFFEFD3C00
            Name: Intel(R) Ethernet Converged Network Adapter X710-2
            The device has the following problem: Cannot start device
        PCI\VEN_8086&DEV_1572&SUBSYS_00008086&REV_01\388BCFFFFFFEFD3C01
            Name: Intel(R) Ethernet Converged Network Adapter X710
            Driver is running.
        2 matching device(s) found."""
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=stdout, return_code=0
        )
        assert manager.check_device_status(DeviceID("1572")) is True

    def test_get_installed_drivers_for_device(self, manager, caplog):
        caplog.set_level(log_levels.MODULE_DEBUG)
        manager.devcon.get_drivernodes.return_value = [
            DevconDriverNodes(
                device_pnp="ACPI\\FIXEDBUTTON\\2&DABA3FF&0",
                name="ACPI Fixed Feature Button",
                driver_nodes={
                    "0": {
                        "inf_file": "C:\\windows\\INF\\machine.inf",
                        "inf_section": "NO_DRV",
                        "driver_desc": "ACPI Fixed Feature Button",
                        "manufacturer_name": "(Standard system devices)",
                        "provider_name": "Microsoft",
                        "driver_date": "6/21/2006",
                        "driver_version": "10.0.22000.1",
                        "driver_node_rank": "16711680",
                        "driver_node_flags": "00142044",
                    }
                },
            ),
            DevconDriverNodes(
                device_pnp="USB4\\VIRTUAL_POWER_PDO\\4&26DBF7B8&0&0",
                name="USB4 Virtual power coordination device",
                driver_nodes={},
            ),
            DevconDriverNodes(
                device_pnp="PCI\\VEN_8086&DEV_51EF&SUBSYS_897F103C&REV_01\\3&11583659&0&A2",
                name="Intel(R) Shared SRAM - 51EF",
                driver_nodes={
                    "0": {
                        "inf_file": "C:\\windows\\INF\\machine.inf",
                        "inf_section": "NO_DRV",
                        "driver_desc": "PCI standard RAM Controller",
                        "manufacturer_name": "(Standard system devices)",
                        "provider_name": "Microsoft",
                        "driver_date": "6/21/2006",
                        "driver_version": "10.0.22000.1",
                        "driver_node_rank": "16719878",
                        "driver_node_flags": "00102044",
                    },
                    "1": {
                        "inf_file": "C:\\windows\\INF\\oem104.inf",
                        "inf_section": "Needs_NO_DRV",
                        "driver_desc": "Intel(R) Shared SRAM - 51EF",
                        "manufacturer_name": "INTEL",
                        "provider_name": "INTEL",
                        "driver_date": "7/18/1968",
                        "driver_version": "10.1.36.7",
                        "driver_node_rank": "16719873",
                        "driver_node_flags": "00042044",
                    },
                },
            ),
        ]
        assert manager.get_installed_drivers_for_device(DeviceID("51EF")) == ["oem104.inf"]
        assert "Found ['oem104.inf'] in system for device_id: 51EF" in caplog.text
        manager.devcon.get_drivernodes.return_value = [
            DevconDriverNodes(
                device_pnp="ACPI\\FIXEDBUTTON\\2&DABA3FF&0",
                name="ACPI Fixed Feature Button",
                driver_nodes={
                    "0": {
                        "inf_file": "C:\\windows\\INF\\machine.inf",
                        "inf_section": "NO_DRV",
                        "driver_desc": "ACPI Fixed Feature Button",
                        "manufacturer_name": "(Standard system devices)",
                        "provider_name": "Microsoft",
                        "driver_date": "6/21/2006",
                        "driver_version": "10.0.22000.1",
                        "driver_node_rank": "16711680",
                        "driver_node_flags": "00142044",
                    }
                },
            )
        ]
        assert manager.get_installed_drivers_for_device(DeviceID("51EF")) == []

    def test_read_version_of_inf_driver(self, manager):
        content = dedent(
            """\
        (...)
        [Version]
        Signature   = "$Windows NT$"
        Class       = Net
        ClassGUID   = {4d36e972-e325-11ce-bfc1-08002be10318}
        Provider    = %Intel%
        CatalogFile = i40ea68.cat
        DriverVer   = 12/22/2022,1.16.202.10

        [Manufacturer]
        %Intel% = Intel, NTamd64.10.0, NTamd64.10.0.1
        (...)"""
        )
        assert manager.read_version_of_inf_driver(content) == "1.16.202.10"
        assert manager.read_version_of_inf_driver("content") == "N/A"

    def test_get_matching_drivers(self, manager, mocker):
        path1, path2 = mocker.create_autospec(Path), mocker.create_autospec(Path)
        path1.with_suffix.return_value.name = "i40ea68"
        path1.read_text.return_value = dedent(
            r"""\
        (...)
        [Version]
        Signature   = "$Windows NT$"
        Class       = Net
        ClassGUID   = {4d36e972-e325-11ce-bfc1-08002be10318}
        Provider    = %Intel%
        CatalogFile = i40ea68.cat
        DriverVer   = 12/22/2022,1.16.202.10

        [Manufacturer]
        %Intel% = Intel, NTamd64.10.0, NTamd64.10.0.1

        [Intel]

        [Intel.NTamd64.10.0]
        ; DisplayName                               Section                DeviceID
        ; -----------                               -------                --------
        %F10A6.Generic.Description%               = NO_DRV,                PCI\VEN_8086&DEV_10A6
        %F1572.Generic.Description%               = F1572,                 PCI\VEN_8086&DEV_1572
        %F1580.Generic.Description%               = F1580,                 PCI\VEN_8086&DEV_1580
        (...)"""
        )
        path2.read_text.return_value = ""
        list_of_drivers = [path1, path2]
        manager._is_matching_device = mocker.create_autospec(manager._is_matching_device, side_effect=[True, False])
        assert manager.get_matching_drivers(list_of_drivers, DeviceID("1572")) == [
            DriverDetails(path1, "1.16.202.10", "i40ea68")
        ]

    def test__rmtree(self, manager, mocker):
        manager._connection = mocker.create_autospec(SSHConnection)
        manager._rmtree("path")
        manager._connection.path.return_value.rmdir.assert_called_once()
        manager._connection = mocker.create_autospec(RPyCConnection)
        manager._rmtree("path")
        manager._connection.modules.return_value.shutil.rmtree.assert_called_once_with("path")

    def test___is_matching_device(self, manager):
        inf_content = dedent(
            r"""\
        (...)
        [Version]
        Signature   = "$Windows NT$"
        Class       = Net
        ClassGUID   = {4d36e972-e325-11ce-bfc1-08002be10318}
        Provider    = %Intel%
        CatalogFile = i40ea68.cat
        DriverVer   = 12/22/2022,1.16.202.10

        [Manufacturer]
        %Intel% = Intel, NTamd64.10.0, NTamd64.10.0.1

        [Intel]

        [Intel.NTamd64.10.0]
        ; DisplayName                               Section                DeviceID
        ; -----------                               -------                --------
        %F10A6.Generic.Description%               = NO_DRV,                PCI\VEN_8086&DEV_10A6
        %F1572.Generic.Description%               = F1572,                 PCI\VEN_8086&DEV_1572
        %F1580.Generic.Description%               = F1580,                 PCI\VEN_8086&DEV_1580
        (...)"""
        )
        assert manager._is_matching_device(inf_content, DeviceID("1572")) is True
        assert manager._is_matching_device(inf_content, DeviceID("1573")) is False

    def test__get_folder_for_os_version(self, manager):
        assert manager._get_folder_for_os_version(17790) == "NDIS68"
        with pytest.raises(
            PackageManagerConnectedOSNotSupported, match="Windows in version 9700 is not supported by module."
        ):
            manager._get_folder_for_os_version(9700)

    def test__prepare_devcon(self, mocker):
        local_path_mock = mocker.patch("mfd_package_manager.windows.Path")
        local_path_mock.return_value = Path("/tmp/windows.py")
        mocker.patch("mfd_package_manager.windows.Devcon")
        conn = mocker.create_autospec(RPyCConnection)
        conn.path.return_value = mocker.Mock()
        conn._ip = "127.0.0.1"
        conn.get_os_name.return_value = OSName.WINDOWS
        devcon_mock = mocker.create_autospec(Devcon)
        devcon_mock._tool_exec = "devcon.exe"
        devcon_mock._connection = conn
        WindowsPackageManager(connection=conn)

    @pytest.fixture()
    def prepared_install_build(self, manager, mocker):
        manager.find_drivers = mocker.create_autospec(
            manager.find_drivers, return_value=[Path("/home/user/build/i40e.inf")]
        )
        manager.get_matching_drivers = mocker.create_autospec(
            manager.get_matching_drivers,
            return_value=[DriverDetails(Path("/home/user/build/i40e.inf"), "1.1.1.1", "i40ea68")],
        )
        manager.get_installed_drivers_for_device = mocker.create_autospec(
            manager.get_installed_drivers_for_device, return_value=[]
        )
        manager.install_certificates_from_driver = mocker.create_autospec(manager.install_certificates_from_driver)
        manager.get_driver_version_by_inf_name = mocker.create_autospec(
            manager.get_driver_version_by_inf_name, return_value="1.1.1.1"
        )
        manager.check_device_status = mocker.create_autospec(manager.check_device_status, return_value=False)
        manager._controller_connection = mocker.create_autospec(LocalConnection)

        yield manager

    def test_install_build(self, prepared_install_build, mocker):
        copy_mock = mocker.patch("mfd_package_manager.windows.copy")
        prepared_install_build.install_inf_driver_for_matching_devices = mocker.create_autospec(
            prepared_install_build.install_inf_driver_for_matching_devices,
            return_value=ConnectionCompletedProcess(return_code=0, args=""),
        )
        target_path_mock = mocker.create_autospec(Path)
        prepared_install_build._connection.path.return_value = target_path_mock
        prepared_install_build._connection._ip = "127.0.0.1"
        prepared_install_build.install_build("/home/user/build", DeviceID(0x1572))
        prepared_install_build.devcon.remove_devices.assert_called_once_with(device_id="PCI\\VEN_8086&DEV_1572*")
        assert prepared_install_build.devcon.rescan_devices.call_count == 2

        copy_mock.assert_called_once_with(
            src_conn=prepared_install_build._controller_connection,
            dst_conn=prepared_install_build._connection,
            source=Path("/home/user/build/*"),
            target=target_path_mock / "build",
        )

    def test_install_build_prosetdx_exe(self, prepared_install_build, mocker):
        mocker.patch(
            "mfd_package_manager.WindowsPackageManager._prosetdx_install",
            mocker.create_autospec(WindowsPackageManager._prosetdx_install, return_value=True),
        )
        prepared_install_build.install_build(
            build_path="C:\\home\\user\\build\\", device_id=(0x1572), installation_method=InstallationMethod.EXE
        )

    def test__prosetdx_install(self, prepared_install_build, manager, mocker):
        copy_mock = mocker.patch("mfd_package_manager.windows.copy")
        build_path = "C:\\home\\user\\build\\"
        target_path_mock = manager._controller_connection.path(build_path, r"APPS\PROSETDX\winx64\DxSetup.exe")
        target_path_mock.exists.return_value = True
        prepared_install_build._connection.path.return_value = target_path_mock
        prepared_install_build._connection.execute_with_timeout = mocker.Mock(
            return_value=ConnectionCompletedProcess(return_code=0, args="", stdout="", stderr="")
        )
        mocker.patch(
            "mfd_package_manager.WindowsPackageManager._parse_log",
            mocker.create_autospec(WindowsPackageManager._parse_log, return_value=True),
        )
        mocker.patch(
            "mfd_package_manager.WindowsPackageManager._is_installed_win",
            mocker.create_autospec(WindowsPackageManager._is_installed_win, return_value=True),
        )
        assert (
            prepared_install_build._prosetdx_install(proset_flags=False, build_path="C:\\home\\user\\build\\") is True
        )
        copy_mock.assert_called_once_with(
            src_conn=prepared_install_build._controller_connection,
            dst_conn=prepared_install_build._connection,
            source="C:\\home\\user\\build\\APPS\\PROSETDX\\winx64",
            target=target_path_mock,
        )

    def test__parse_log(self, prepared_install_build, manager, mocker):
        path = mocker.create_autospec(Path)
        output = dedent(
            r"""\
            '=== Logging started: 4/23/2024  8:47:49 ===\nAction start 8:47:49: INSTALL.
        \nAction start 8:47:49: FindRelatedProducts. Logging stopped: 4/23/2024  8:47:59 ===\nMSI (s) (F8:58)
        [08:47:59:279]: Product: Intel(R) Network Connections -- Configuration completed successfully.\n\nMSI (s)
        (F8:58) [08:47:59:279]: Windows Installer reconfigured the product. Product Name: Intel(R) Network
        Connections. Product Version: 29.1.0.0. Product Language: 1033. Manufacturer: Intel.
        Reconfiguration success or error status: 0.\n\n'"""
        )
        mocker.patch(
            "mfd_package_manager.WindowsPackageManager._get_sfile",
            mocker.create_autospec(WindowsPackageManager._get_sfile, return_value=output),
        )
        assert manager._parse_log(path, "completed successfully") is True

    def test__parse_log_debug_info(self, prepared_install_build, manager, mocker):
        path = mocker.create_autospec(Path)
        output = dedent(
            r"""\
            '=== Logging started: 4/23/2024  8:47:49 ===\nAction start 8:47:49: INSTALL.
            \nAction start 8:47:49: FindRelatedProducts. Logging stopped: 4/23/2024  8:47:59 ===
            \nMSI (s) (F8:58) [08:47:59:279]: Product:
Intel(R) Network Connections -- Error in configuration.
            Windows Installer reconfigured the product. Product Name: Intel(R) Network Connections.
            Product Version: 29.1.0.0. Product Language: 1033. Manufacturer: Intel.
            Reconfiguration success or error status: 0.\n\n'"""
        )
        mocker.patch(
            "mfd_package_manager.WindowsPackageManager._get_sfile",
            mocker.create_autospec(WindowsPackageManager._get_sfile, return_value=output),
        )
        assert manager._parse_log_debug_info(path) == "Intel(R) Network Connections -- Error in configuration."

    def test__installed_win(self, manager, prepared_install_build, mocker):
        get_registry_path_expected_output = {
            "\\PROSetDX": {
                "(default)": "",
                "InstallVer": "1389169096",
                "AuthorizedCDFPrefix": "",
                "Comments": "",
                "Contact": "Intel",
                "DisplayVersion": "29.1.0.2",
                "HelpLink": "DOCS\\Adapter_User_Guide.pdf",
                "HelpTelephone": "",
                "InstallDate": "20240411",
                "InstallLocation": "C:\\Program",
                "InstallSource": "C:\\user\\var\\builds\\Release_29.1_Reference\\292_59181\\APPS\\PROSETDX\\winx64\\",
                "ModifyPath": "MsiExec.exe",
                "NoModify": "1",
                "NoRepair": "1",
                "Publisher": "Intel",
                "Readme": "",
                "Size": "",
                "EstimatedSize": "20009",
                "UninstallString": "MsiExec.exe",
                "URLInfoAbout": "http://www.intel.com/support",
                "URLUpdateInfo": "",
                "VersionMajor": "29",
                "VersionMinor": "1",
                "WindowsInstaller": "0",
                "Version": "486604802",
                "Language": "0",
                "DisplayName": "Intel(R)",
                "PSChildName": "PROSetDX",
                "PSDrive": "HKLM",
                "PSProvider": "Microsoft.PowerShell.Core\\Registry",
            },
        }
        mocker.patch(
            "mfd_win_registry.WindowsRegistry.get_registry_path",
            mocker.create_autospec(WindowsRegistry.get_registry_path, return_value=get_registry_path_expected_output),
        )
        assert manager._is_installed_win() is True

    def test_install_build_inf_devcon(self, prepared_install_build, mocker):
        output = dedent(
            r"""\ Updating drivers for PCI\VEN_8086&DEV_1572&SUBSYS_1F5B1028&REV_00\0000B82A72DA80E200 from
             C:\windows\inf\test.inf. Drivers updated successfully. """
        )
        copy_mock = mocker.patch("mfd_package_manager.windows.copy")
        target_path_mock = mocker.create_autospec(Path)
        prepared_install_build.devcon.update_drivers.return_value = output
        prepared_install_build._connection.path.return_value = target_path_mock
        prepared_install_build._connection._ip = "127.0.0.1"
        prepared_install_build.install_build(
            "/home/user/build", DeviceID(0x1572), installation_method=InstallationMethod.INF_DEVCON
        )
        prepared_install_build.devcon.remove_devices.assert_called_once_with(device_id="PCI\\VEN_8086&DEV_1572*")
        assert prepared_install_build.devcon.rescan_devices.call_count == 2

        copy_mock.assert_called_once_with(
            src_conn=prepared_install_build._controller_connection,
            dst_conn=prepared_install_build._connection,
            source=Path("/home/user/build/*"),
            target=target_path_mock / "build",
        )

    def test_install_build_with_reboot(self, prepared_install_build, mocker):
        copy_mock = mocker.patch("mfd_package_manager.windows.copy")
        prepared_install_build.install_inf_driver_for_matching_devices = mocker.create_autospec(
            prepared_install_build.install_inf_driver_for_matching_devices,
            return_value=ConnectionCompletedProcess(return_code=3010, args=""),
        )
        target_path_mock = mocker.create_autospec(Path)
        prepared_install_build._connection.path.return_value = target_path_mock
        prepared_install_build._connection._ip = "127.0.0.1"
        prepared_install_build.install_build("/home/user/build", DeviceID(0x1572))
        prepared_install_build.devcon.remove_devices.assert_called_once_with(device_id="PCI\\VEN_8086&DEV_1572*")
        assert prepared_install_build.devcon.rescan_devices.call_count == 2

        copy_mock.assert_called_once_with(
            src_conn=prepared_install_build._controller_connection,
            dst_conn=prepared_install_build._connection,
            source=Path("/home/user/build/*"),
            target=target_path_mock / "build",
        )
        prepared_install_build._connection.restart_platform.assert_called_once()
        prepared_install_build._connection.wait_for_host.assert_called_once_with(timeout=120)

    def test_install_build_with_uninstall(self, prepared_install_build, mocker):
        mocker.patch("mfd_package_manager.windows.copy")
        target_path_mock = mocker.create_autospec(Path)
        prepared_install_build._connection.path.return_value = target_path_mock
        prepared_install_build._connection._ip = "127.0.0.1"
        prepared_install_build.get_installed_drivers_for_device = mocker.Mock(return_value=["oem1.inf"])
        prepared_install_build.delete_driver_via_pnputil = mocker.create_autospec(
            prepared_install_build.delete_driver_via_pnputil
        )
        prepared_install_build.install_build("/home/user/build", DeviceID(0x1572))
        prepared_install_build.delete_driver_via_pnputil.assert_called_once_with("oem1.inf")

    def test_install_build_without_drivers(self, mocker, manager):
        manager.find_drivers = mocker.create_autospec(
            manager.find_drivers, return_value=[Path("/home/user/build/i40e.inf")]
        )
        manager.get_matching_drivers = mocker.create_autospec(manager.get_matching_drivers, return_value=[])
        with pytest.raises(PackageManagerNotFoundException, match="Not found drivers in build"):
            manager.install_build("/home/user/build", DeviceID(0x1572))

    def test_install_build_mismatch(self, prepared_install_build, mocker):
        mocker.patch("mfd_package_manager.windows.copy")
        prepared_install_build.install_inf_driver_for_matching_devices = mocker.Mock(
            return_value=ConnectionCompletedProcess(return_code=0, args="")
        )
        target_path_mock = mocker.create_autospec(Path)
        prepared_install_build._connection.path.return_value = target_path_mock
        prepared_install_build._connection._ip = "127.0.0.1"
        mocker.patch("mfd_package_manager.windows.LocalConnection")
        prepared_install_build.get_driver_version_by_inf_name = mocker.Mock(return_value="1.2.1.1")
        with pytest.raises(PackageManagerModuleException):
            prepared_install_build.install_build("/home/user/build", DeviceID(0x1572))

    def test_install_build_problem_with_device(self, prepared_install_build, mocker):
        mocker.patch("mfd_package_manager.windows.copy")
        prepared_install_build.install_inf_driver_for_matching_devices = mocker.Mock(
            return_value=ConnectionCompletedProcess(return_code=0, args="")
        )
        target_path_mock = mocker.create_autospec(Path)
        prepared_install_build._connection.path.return_value = target_path_mock
        prepared_install_build._connection._ip = "127.0.0.1"
        mocker.patch("mfd_package_manager.windows.LocalConnection")
        prepared_install_build.check_device_status = mocker.Mock(return_value=True)
        with pytest.raises(PackageManagerModuleException):
            prepared_install_build.install_build("/home/user/build", DeviceID(0x1572))

    def test_find_drivers(self, manager, mocker):
        manager._glob_glob_method = mocker.create_autospec(manager._glob_glob_method)
        manager._glob_glob_method.return_value = iter(["/home/user/build/i40e.inf"])
        mocker.patch("mfd_package_manager.windows.Path.exists", return_value=True)
        manager._get_interface_driver = mocker.create_autospec(manager._get_interface_driver, return_value="i40e")
        manager._get_driver_directory = mocker.create_autospec(manager._get_driver_directory, return_value="PRO40GB")
        manager._get_folder_for_os_version = mocker.create_autospec(
            manager._get_folder_for_os_version, return_value="NDIS68"
        )
        args = {field.name: None for field in dataclasses.fields(SystemInfo)}
        args["kernel_version"] = "17719"
        manager._connection.get_system_info.return_value = SystemInfo(**args)
        assert manager.find_drivers("/home/user/build", DeviceID(0x1572)) == [Path("/home/user/build/i40e.inf")]
        manager._glob_glob_method.assert_called_once_with(
            str(Path("/home/user/build")), str(Path("/home/user/build/PRO40GB/Winx64/NDIS68/i40e*.inf"))
        )

    def test_find_drivers_not_found(self, manager, mocker):
        manager._glob_glob_method = mocker.create_autospec(manager._glob_glob_method)
        manager._glob_glob_method.return_value = iter(["/home/user/build/i40e.inf"])
        mocker.patch("mfd_package_manager.windows.Path.exists", return_value=False)
        with pytest.raises(
            PackageManagerNotFoundException, match=re.escape(f"Build path {Path('/home/user/build')} does not exist.")
        ):
            manager.find_drivers("/home/user/build", DeviceID(0x1572))

    def test_get_device_ids_to_install(self, manager):
        manager.devcon.get_hwids.return_value = [
            DevconHwids(
                device_pnp="ROOT\\BASICRENDER\\0000",
                name="Microsoft Basic Render Driver",
                hardware_ids=["ROOT\\BasicRender"],
                compatible_ids=[],
            ),
            DevconHwids(
                device_pnp="PCI\\VEN_8086&DEV_2FE1&SUBSYS_2FE18086&REV_02\\3&103A9D54&0&61",
                name="Base System Device",
                hardware_ids=[
                    "PCI\\VEN_8086&DEV_2FE1&SUBSYS_2FE18086&REV_02",
                    "PCI\\VEN_8086&DEV_2FE1&SUBSYS_2FE18086",
                    "PCI\\VEN_8086&DEV_2FE1&CC_088000",
                    "PCI\\VEN_8086&DEV_2FE1&CC_0880",
                ],
                compatible_ids=[
                    "PCI\\VEN_8086&DEV_2FE1&REV_02",
                    "PCI\\VEN_8086&DEV_2FE1",
                    "PCI\\VEN_8086&CC_088000",
                    "PCI\\VEN_8086&CC_0880",
                    "PCI\\VEN_8086",
                    "PCI\\CC_088000",
                    "PCI\\CC_0880",
                ],
            ),
            DevconHwids(
                device_pnp="PCI\\VEN_8086&DEV_1572&SUBSYS_2FE18086&REV_02\\3&103A9D54&0&61",
                name="Ethernet 1572",
                hardware_ids=[
                    "PCI\\VEN_8086&DEV_15721&SUBSYS_2FE18086&REV_02",
                    "PCI\\VEN_8086&DEV_15721&SUBSYS_2FE18086",
                    "PCI\\VEN_8086&DEV_15721&CC_088000",
                    "PCI\\VEN_8086&DEV_15721&CC_0880",
                ],
                compatible_ids=[
                    "PCI\\VEN_8086&DEV_1572&REV_02",
                    "PCI\\VEN_8086&DEV_1572",
                    "PCI\\VEN_8086&CC_088000",
                    "PCI\\VEN_8086&CC_0880",
                    "PCI\\VEN_8086",
                    "PCI\\CC_088000",
                    "PCI\\CC_0880",
                ],
            ),
            DevconHwids(
                device_pnp="PCI\\VEN_8086&DEV_1563&SUBSYS_2FE18086&REV_02\\3&103A9D54&0&61",
                name="Ethernet 1563",
                hardware_ids=[
                    "PCI\\VEN_8086&DEV_1563&SUBSYS_2FE18086&REV_02",
                    "PCI\\VEN_8086&DEV_1563&SUBSYS_2FE18086",
                    "PCI\\VEN_8086&DEV_1563&CC_088000",
                    "PCI\\VEN_8086&DEV_1563&CC_0880",
                ],
                compatible_ids=[
                    "PCI\\VEN_8086&DEV_1563&REV_02",
                    "PCI\\VEN_8086&DEV_1563",
                    "PCI\\VEN_8086&CC_088000",
                    "PCI\\VEN_8086&CC_0880",
                    "PCI\\VEN_8086",
                    "PCI\\CC_088000",
                    "PCI\\CC_0880",
                ],
            ),
        ]
        assert manager.get_device_ids_to_install() == [DeviceID("1572"), DeviceID("1563")]

    def test_find_management_device_id(self, manager, mocker):
        first_call_stdout = "1014\n"
        second_call_stdout = "PCI\\VEN_8086&DEV_1563&SUBSYS_35D48086&REV_01\\0000C9FFFF00000000\n"
        manager._connection.execute_powershell.side_effect = [
            ConnectionCompletedProcess(args="", stdout=first_call_stdout, return_code=0),
            ConnectionCompletedProcess(args="", stdout=second_call_stdout, return_code=0),
        ]
        assert manager.find_management_device_id() == DeviceID("1563")
        first_call = mocker.call(
            'Get-WmiObject Win32_NetworkAdapterConfiguration | Where-Object IPAddress -like "*10.10.10.10*" '
            '| Select -expand "Index"'
        )
        second_call = mocker.call(
            'gwmi win32_networkadapter | Where-Object Index -eq 1014 | Select -expand "PNPDeviceID"'
        )
        manager._connection.execute_powershell.assert_has_calls([first_call, second_call])

    def test__read_inf_file_and_create_base_dictionary_with_read_text(self, manager, mocker):
        inf_file_content = r"""[Version]
        Signature   = "$Windows NT$"
        Class       = Net
        ClassGUID   = {4d36e972-e325-11ce-bfc1-08002be10318}
        Provider    = %Intel%
        CatalogFile = i40ea68.cat
        DriverVer   = 12/22/2022,1.16.202.10

        [Manufacturer]
        %Intel% = Intel, NTamd64.10.0, NTamd64.10.0.1

        [Intel]

        [Intel.NTamd64.10.0]
        ; DisplayName                               Section               DeviceID
        ; -----------                               -------               --------
        %F10A6.Generic.Description%               = NO_DRV,               PCI\VEN_8086&DEV_10A6
        %F1572.Generic.Description%               = F1572,                PCI\VEN_8086&DEV_1572
        %F1580.Generic.Description%               = F1580,                PCI\VEN_8086&DEV_1580"""

        inf_path = mocker.create_autospec(Path)
        inf_path.read_text.return_value = inf_file_content

        expected_section_dict = {"version": [], "manufacturer": [], "intel": [], "intel.ntamd64.10.0": []}
        expected_all_lines = [
            "version",
            'Signature   = "$Windows NT$"',
            "Class       = Net",
            "ClassGUID   = {4d36e972-e325-11ce-bfc1-08002be10318}",
            "Provider    = %Intel%",
            "CatalogFile = i40ea68.cat",
            "DriverVer   = 12/22/2022,1.16.202.10",
            "",
            "manufacturer",
            "%Intel% = Intel, NTamd64.10.0, NTamd64.10.0.1",
            "",
            "intel",
            "",
            "intel.ntamd64.10.0",
            "; DisplayName                               Section               DeviceID",
            "; -----------                               -------               --------",
            "%F10A6.Generic.Description%               = NO_DRV,               PCI\\VEN_8086&DEV_10A6",
            "%F1572.Generic.Description%               = F1572,                PCI\\VEN_8086&DEV_1572",
            "%F1580.Generic.Description%               = F1580,                PCI\\VEN_8086&DEV_1580",
        ]

        section_dict, all_lines = manager._read_inf_file_and_create_base_dictionary(inf_path)
        assert section_dict == expected_section_dict and all_lines == expected_all_lines

    def test__read_inf_file_and_create_base_dictionary_with_read_bytes(self, manager, mocker):
        inf_file_content = rb"""[Version]
        Signature   = "$Windows NT$"
        Class       = Net
        ClassGUID   = {4d36e972-e325-11ce-bfc1-08002be10318}
        Provider    = %Intel%
        CatalogFile = i40ea68.cat
        DriverVer   = 12/22/2022,1.16.202.10

        [Manufacturer]
        %Intel% = Intel, NTamd64.10.0, NTamd64.10.0.1

        [Intel]

        [Intel.NTamd64.10.0]
        ; DisplayName                               Section               DeviceID
        ; -----------                               -------               --------
        %F10A6.Generic.Description%               = NO_DRV,               PCI\VEN_8086&DEV_10A6
        %F1572.Generic.Description%               = F1572,                PCI\VEN_8086&DEV_1572
        %F1580.Generic.Description%               = F1580,                PCI\VEN_8086&DEV_1580"""

        inf_path = mocker.create_autospec(Path)
        inf_path.read_text.side_effect = UnicodeDecodeError("mocked", b"", 1, 2, "mocked")
        inf_path.read_bytes.return_value = inf_file_content

        expected_section_dict = {"version": [], "manufacturer": [], "intel": [], "intel.ntamd64.10.0": []}
        expected_all_lines = [
            "version",
            'Signature   = "$Windows NT$"',
            "Class       = Net",
            "ClassGUID   = {4d36e972-e325-11ce-bfc1-08002be10318}",
            "Provider    = %Intel%",
            "CatalogFile = i40ea68.cat",
            "DriverVer   = 12/22/2022,1.16.202.10",
            "",
            "manufacturer",
            "%Intel% = Intel, NTamd64.10.0, NTamd64.10.0.1",
            "",
            "intel",
            "",
            "intel.ntamd64.10.0",
            "; DisplayName                               Section               DeviceID",
            "; -----------                               -------               --------",
            "%F10A6.Generic.Description%               = NO_DRV,               PCI\\VEN_8086&DEV_10A6",
            "%F1572.Generic.Description%               = F1572,                PCI\\VEN_8086&DEV_1572",
            "%F1580.Generic.Description%               = F1580,                PCI\\VEN_8086&DEV_1580",
        ]

        # with pytest.raises(UnicodeDecodeError):
        section_dict, all_lines = manager._read_inf_file_and_create_base_dictionary(inf_path)
        assert section_dict == expected_section_dict and all_lines == expected_all_lines

    def test__update_section_dictionary(self, manager):
        section_dict = {"version": [], "manufacturer": [], "intel": [], "intel.ntamd64.10.0": []}
        file_content = [
            "version",
            'Signature   = "$Windows NT$"',
            "Class       = Net",
            "ClassGUID   = {4d36e972-e325-11ce-bfc1-08002be10318}",
            "Provider    = %Intel%",
            "CatalogFile = i40ea68.cat",
            "DriverVer   = 12/22/2022,1.16.202.10",
            "",
            "manufacturer",
            "%Intel% = Intel, NTamd64.10.0, NTamd64.10.0.1",
            "",
            "intel",
            "",
            "intel.ntamd64.10.0",
            "; DisplayName                               Section               DeviceID",
            "; -----------                               -------               --------",
            "%F10A6.Generic.Description%               = NO_DRV,               PCI\\VEN_8086&DEV_10A6",
            "%F1572.Generic.Description%               = F1572,                PCI\\VEN_8086&DEV_1572",
            "%F1580.Generic.Description%               = F1580,                PCI\\VEN_8086&DEV_1580",
        ]

        expected_section_dict = {
            "version": [
                'Signature   = "$Windows NT$"',
                "Class       = Net",
                "ClassGUID   = {4d36e972-e325-11ce-bfc1-08002be10318}",
                "Provider    = %Intel%",
                "CatalogFile = i40ea68.cat",
                "DriverVer   = 12/22/2022,1.16.202.10",
            ],
            "manufacturer": ["%Intel% = Intel, NTamd64.10.0, NTamd64.10.0.1"],
            "intel": [],
            "intel.ntamd64.10.0": [
                "; DisplayName                               Section               DeviceID",
                "; -----------                               -------               --------",
                "%F10A6.Generic.Description%               = NO_DRV,               PCI\\VEN_8086&DEV_10A6",
                "%F1572.Generic.Description%               = F1572,                PCI\\VEN_8086&DEV_1572",
                "%F1580.Generic.Description%               = F1580,                PCI\\VEN_8086&DEV_1580",
            ],
        }

        assert (
            manager._update_section_dictionary(section_dictionary=section_dict, file_content=file_content)
            == expected_section_dict
        )

    def test__get_inf_device_section_name_server_os(self, manager, mocker):
        build_name = "NDIS68"
        component_id = "PCI\\VEN_8086&DEV_1572A"
        section_dict = {
            "version": [
                'Signature   = "$Windows NT$"',
                "Class       = Net",
                "ClassGUID   = {4d36e972-e325-11ce-bfc1-08002be10318}",
                "Provider    = %Intel%",
                "CatalogFile = i40ea68.cat",
                "DriverVer   = 12/22/2022,1.16.202.10",
            ],
            "manufacturer": ["%Intel% = Intel, NTamd64.10.0, NTamd64.10.0.1"],
            "intel": [],
            "intel.ntamd64.10.0": [
                "; DisplayName                               Section               DeviceID",
                "; -----------                               -------               --------",
                "%F10A6.Generic.Description%               = NO_DRV,               PCI\\VEN_8086&DEV_10A6",
                "%F1572.Generic.Description%               = F1572A,                PCI\\VEN_8086&DEV_1572A",
                "%F1580.Generic.Description%               = F1580,                PCI\\VEN_8086&DEV_1580",
            ],
            "intel.ntamd64.10.0.1": [
                "; DisplayName                               Section               DeviceID",
                "; -----------                               -------               --------",
                "%F10A6.Generic.Description%               = NO_DRV,               PCI\\VEN_8086&DEV_10A6",
                "%F1572.Generic.Description%               = F1572B,                PCI\\VEN_8086&DEV_1572B",
                "%F1580.Generic.Description%               = F1580,                PCI\\VEN_8086&DEV_1580",
            ],
        }

        manager._find_server_or_client_section_name = mocker.create_autospec(
            manager._find_server_or_client_section_name,
            return_value=[
                "; DisplayName                               Section               DeviceID",
                "; -----------                               -------               --------",
                "%F10A6.Generic.Description%               = NO_DRV,               PCI\\VEN_8086&DEV_10A6",
                "%F1572.Generic.Description%               = F1572A,                PCI\\VEN_8086&DEV_1572A",
                "%F1580.Generic.Description%               = F1580,                PCI\\VEN_8086&DEV_1580",
            ],
        )

        assert (
            manager._get_inf_device_section_name(
                build=build_name, section_dictionary=section_dict, component_id=component_id, client_os=False
            )
            == "f1572a"
        )

    def test__get_inf_device_section_name_client_os(self, manager, mocker):
        build_name = "NDIS68"
        component_id = "PCI\\VEN_8086&DEV_1572B"
        section_dict = {
            "version": [
                'Signature   = "$Windows NT$"',
                "Class       = Net",
                "ClassGUID   = {4d36e972-e325-11ce-bfc1-08002be10318}",
                "Provider    = %Intel%",
                "CatalogFile = i40ea68.cat",
                "DriverVer   = 12/22/2022,1.16.202.10",
            ],
            "manufacturer": ["%Intel% = Intel, NTamd64.10.0, NTamd64.10.0.1"],
            "intel": [],
            "intel.ntamd64.10.0": [
                "; DisplayName                               Section               DeviceID",
                "; -----------                               -------               --------",
                "%F10A6.Generic.Description%               = NO_DRV,               PCI\\VEN_8086&DEV_10A6",
                "%F1572.Generic.Description%               = F1572A,                PCI\\VEN_8086&DEV_1572A",
                "%F1580.Generic.Description%               = F1580,                PCI\\VEN_8086&DEV_1580",
            ],
            "intel.ntamd64.10.0.1": [
                "; DisplayName                               Section               DeviceID",
                "; -----------                               -------               --------",
                "%F10A6.Generic.Description%               = NO_DRV,               PCI\\VEN_8086&DEV_10A6",
                "%F1572.Generic.Description%               = F1572B,                PCI\\VEN_8086&DEV_1572B",
                "%F1580.Generic.Description%               = F1580,                PCI\\VEN_8086&DEV_1580",
            ],
        }

        manager._find_server_or_client_section_name = mocker.create_autospec(
            manager._find_server_or_client_section_name,
            return_value=[
                "; DisplayName                               Section               DeviceID",
                "; -----------                               -------               --------",
                "%F10A6.Generic.Description%               = NO_DRV,               PCI\\VEN_8086&DEV_10A6",
                "%F1572.Generic.Description%               = F1572B,                PCI\\VEN_8086&DEV_1572B",
                "%F1580.Generic.Description%               = F1580,                PCI\\VEN_8086&DEV_1580",
            ],
        )

        assert (
            manager._get_inf_device_section_name(
                build=build_name, section_dictionary=section_dict, component_id=component_id, client_os=True
            )
            == "f1572b"
        )

    def test__get_default_vals_from_inf(self, manager):
        device_section_name = "f1572"
        section_dict_with_default_values = {
            "f1572": [
                "Characteristics     = 0x84 ; NCF_HAS_UI | NCF_PHYSICAL",
                "BusType             = 5 ; PCI",
                "Port1FunctionNumber = 0",
                "AddReg              = RSS.reg",
            ],
            "rss.reg": [
                "; NumRssQueues",
                "HKR, Ndi\\Params\\*NumRssQueues,                   ParamDesc,              0, %NumRssQueues2%",
                'HKR, Ndi\\Params\\*NumRssQueues,                   default,                0, "8"',
                'HKR, Ndi\\params\\*NumRssQueues,                   min,                    0, "1"',
                'HKR, Ndi\\params\\*NumRssQueues,                   max,                    0, "32"',
                'HKR, Ndi\\params\\*NumRssQueues,                   step,                   0, "1"',
                'HKR, Ndi\\params\\*NumRssQueues,                   base,                   0, "10"',
                'HKR, Ndi\\Params\\*NumRssQueues,                   type,                   0, "dword"',
                "; *RSS",
                "HKR, Ndi\\Params\\*RSS,                           ParamDesc,              0, %RSS%",
                'HKR, Ndi\\Params\\*RSS,                           default,                0, "1"',
                'HKR, Ndi\\Params\\*RSS\\Enum,                      "0",                    0, %Disabled%',
                'HKR, Ndi\\Params\\*RSS\\Enum,                      "1",                    0, %Enabled%',
                'HKR, Ndi\\Params\\*RSS,                           type,                   0, "enum"',
                "; *RssBaseProcNumber",
                "HKR, Ndi\\params\\*RssBaseProcNumber,             ParamDesc,              0, %RssBaseProcNumber%",
                'HKR, Ndi\\params\\*RssBaseProcNumber,             default,                0, "0"',
                'HKR, Ndi\\params\\*RssBaseProcNumber,             min,                    0, "0"',
                'HKR, Ndi\\params\\*RssBaseProcNumber,             max,                    0, "63"',
                'HKR, Ndi\\params\\*RssBaseProcNumber,             step,                   0, "1"',
                'HKR, Ndi\\params\\*RssBaseProcNumber,             Optional,               0, "0"',
                'HKR, Ndi\\params\\*RssBaseProcNumber,             type,                   0, "int"',
            ],
        }

        expected_out = [("*NumRssQueues", "8"), ("*RSS", "1"), ("*RssBaseProcNumber", "0")]

        assert (
            manager._get_default_vals_from_inf(
                device_section_name=device_section_name, section_dictionary=section_dict_with_default_values
            )
            == expected_out
        )

    def test_FOLDER_OS_VERSION_MATCH(self, manager):
        assert 25000 in manager.FOLDER_OS_VERSION_MATCH["WS2022"]
        assert 23598 in manager.FOLDER_OS_VERSION_MATCH["WS2022"]
        assert 20348 in manager.FOLDER_OS_VERSION_MATCH["WS2022"]
        assert 9200 in manager.FOLDER_OS_VERSION_MATCH["NDIS64"]
