# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
import dataclasses
import re
from pathlib import Path
from textwrap import dedent
from unittest.mock import call

import pytest
from mfd_connect import RPyCConnection, LocalConnection
from mfd_connect.base import ConnectionCompletedProcess

from mfd_typing import OSName, PCIAddress, DeviceID, MACAddress
from mfd_typing.driver_info import DriverInfo
from mfd_typing.os_values import SystemInfo
from netaddr import IPAddress

from mfd_package_manager import LinuxPackageManager
from mfd_package_manager.data_structures import DriverDetails
from mfd_package_manager.exceptions import PackageManagerNotFoundException, PackageManagerModuleException
from mfd_package_manager.linux import LsModOutput


class TestLinuxPackageManager:
    @pytest.fixture()
    def manager(self, mocker):
        conn = mocker.create_autospec(RPyCConnection)
        conn.get_os_name.return_value = OSName.LINUX
        conn.ip = "127.0.0.1"
        man = LinuxPackageManager(connection=conn)
        yield man

    def test_is_module_loaded(self, manager):
        manager._connection.execute_command.side_effect = [
            ConnectionCompletedProcess(args="", stdout="i40e                  495616  0", return_code=0),
            ConnectionCompletedProcess(args="", stdout="ice                  1499136  0", return_code=0),
            ConnectionCompletedProcess(args="", stdout="", return_code=1),
        ]
        assert manager.is_module_loaded("i40e") is True
        assert manager.is_module_loaded("ice") is True
        assert manager.is_module_loaded("igb") is False

    def test_bind_driver(self, manager):
        manager.bind_driver(PCIAddress(data="0000:11:11.1"), "i40e")
        manager._connection.execute_command.assert_called_with(
            "echo 0000:11:11.1 > /sys/bus/pci/drivers/i40e/bind", expected_return_codes={0}, shell=True
        )

    def test_unbind_driver(self, manager):
        manager.unbind_driver(PCIAddress(data="0000:11:11.1"), "i40e")
        manager._connection.execute_command.assert_called_with(
            "echo 0000:11:11.1 > /sys/bus/pci/drivers/i40e/unbind", expected_return_codes={0}, shell=True
        )

    def test_remove_module_from_blacklist(self, manager):
        manager.remove_module_from_blacklist("i40e")
        manager._connection.execute_command.assert_called_with(
            "sed -i.bak '/blacklist i40e/d' /etc/modprobe.d/blacklist.conf", expected_return_codes={0}, shell=True
        )

    def test_add_module_to_blacklist(self, manager):
        manager.add_module_to_blacklist("i40e")
        manager._connection.execute_command.assert_called_with(
            "echo 'blacklist i40e' >> /etc/modprobe.d/blacklist.conf", expected_return_codes={0}, shell=True
        )

    def test_is_module_on_blacklist(self, manager):
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout="blacklist i40e", return_code=0
        )
        assert manager.is_module_on_blacklist("i40e") is True
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(args="", stdout="", return_code=1)
        assert manager.is_module_on_blacklist("i40e") is False
        manager._connection.execute_command.assert_called_with(
            "cat /etc/modprobe.d/blacklist.conf | grep 'blacklist i40e'", expected_return_codes={0, 1}, shell=True
        )

    def test_get_driver_info(self, manager):
        output = dedent(
            """\
        filename:       /lib/modules/4.18.0-372.32.1.el8_6.x86_64/kernel/drivers/net/ethernet/intel/i40e/i40e.ko.xz
        version:        4.18.0-372.32.1.el8_6.x86_64
        license:        GPL v2
        description:    Intel(R) Ethernet Connection XL710 Network Driver
        author:         Intel Corporation, <e1000-devel@lists.sourceforge.net>
        rhelversion:    8.6
        srcversion:     DD34DCEBF74D8B4948A6525
        alias:          pci:v00008086d0000158Bsv*sd*bc*sc*i*
        alias:          pci:v00008086d0000158Asv*sd*bc*sc*i*
        alias:          pci:v00008086d00000D58sv*sd*bc*sc*i*
        alias:          pci:v00008086d00000CF8sv*sd*bc*sc*i*
        alias:          pci:v00008086d00001588sv*sd*bc*sc*i*
        alias:          pci:v00008086d00001587sv*sd*bc*sc*i*
        alias:          pci:v00008086d000037D3sv*sd*bc*sc*i*
        alias:          pci:v00008086d000037D2sv*sd*bc*sc*i*
        alias:          pci:v00008086d000037D1sv*sd*bc*sc*i*
        alias:          pci:v00008086d000037D0sv*sd*bc*sc*i*
        alias:          pci:v00008086d000037CFsv*sd*bc*sc*i*
        alias:          pci:v00008086d000037CEsv*sd*bc*sc*i*
        alias:          pci:v00008086d0000104Fsv*sd*bc*sc*i*
        alias:          pci:v00008086d0000104Esv*sd*bc*sc*i*
        alias:          pci:v00008086d000015FFsv*sd*bc*sc*i*
        alias:          pci:v00008086d00001589sv*sd*bc*sc*i*
        alias:          pci:v00008086d00001586sv*sd*bc*sc*i*
        alias:          pci:v00008086d00001585sv*sd*bc*sc*i*
        alias:          pci:v00008086d00001584sv*sd*bc*sc*i*
        alias:          pci:v00008086d00001583sv*sd*bc*sc*i*
        alias:          pci:v00008086d00001581sv*sd*bc*sc*i*
        alias:          pci:v00008086d00001580sv*sd*bc*sc*i*
        alias:          pci:v00008086d00001574sv*sd*bc*sc*i*
        alias:          pci:v00008086d00001572sv*sd*bc*sc*i*
        depends:
        intree:         Y
        name:           i40e
        vermagic:       4.18.0-372.32.1.el8_6.x86_64 SMP mod_unload modversions
        sig_id:         PKCS#7
        signer:         Red Hat Enterprise Linux kernel signing key
        sig_key:        03:65:13:4B:D4:B7:D3:5F:C9:A1:B1:07:34:92:73:04:F1:E9:08:FD
        sig_hashalgo:   sha256
        signature:      A1:DC:15:F6:77:74:A4:20:8B:E3:ED:D9:92:DA:72:FD:A1:E3:54:85:
                        01:DB:6F:08:07:69:9D:17:73:AA:0F:1B:88:F6:7B:65:A5:01:03:A2:
                        AD:06:A4:35:1D:8D:A4:7D:12:56:F2:BE:50:27:AD:A6:1D:BC:D1:10:
                        BD:5C:6B:44:F4:B9:55:3E:27:2C:60:F3:10:A6:C6:FD:7B:04:6F:1C:
                        9B:4D:E4:F6:6B:AF:74:6D:A2:45:05:6B:98:7E:BA:13:09:04:93:0E:
                        C7:59:72:15:72:6E:96:1E:E2:12:31:8D:D4:D5:54:88:12:12:1A:84:
                        17:4C:91:63:AC:75:FB:2F:A8:D7:4D:A1:A6:69:80:60:81:C6:05:AA:
                        7E:A9:84:DF:9E:74:93:99:1D:DF:69:5C:6A:03:79:E5:4F:79:1E:10:
                        E8:19:12:9A:43:13:17:DA:2A:4B:F6:62:59:23:B1:4D:63:63:4A:24:
                        1C:D5:C8:7B:01:4A:8E:EE:2E:24:5F:6D:A2:DE:70:4F:67:62:24:40:
                        C3:BE:B8:77:53:36:CD:93:79:30:7D:A4:2B:60:A6:CA:C4:B0:F1:DE:
                        9A:05:B5:F1:61:3C:D7:72:55:3F:09:12:7A:75:E9:27:7B:77:2E:DF:
                        44:2A:94:C3:ED:21:F0:D7:69:FD:CF:7B:81:A3:79:A2:1A:23:34:E5:
                        5F:0D:4A:4A:B6:BC:79:B1:87:5A:90:0E:D2:FE:51:E7:78:29:5E:D0:
                        16:F2:AC:A6:73:E3:30:AD:CB:D8:71:54:09:3A:27:72:1B:BB:86:53:
                        82:57:BA:4E:FE:C2:8B:C5:42:08:32:53:83:63:40:2E:55:10:03:52:
                        6B:34:51:63:6F:BA:F0:9A:E2:A0:7A:55:E5:E9:FD:2A:E9:BF:09:CD:
                        84:4C:EA:25:40:BE:35:11:4A:FA:FD:EE:47:A6:F0:EF:29:6C:74:EA:
                        6D:69:A0:87:94:A4:4C:A4:23:7C:FA:20:94:AD:DB:44:55:8E:DF:8C:
                        25:15:2E:E7
        parm:           debug:Debug level (0=none,...,16=all), Debug mask (0x8XXXXXXX) (uint)
        """
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=output, return_code=0
        )
        assert manager.get_driver_info("i40e") == DriverInfo(
            driver_name="i40e", driver_version="4.18.0-372.32.1.el8_6.x86_64"
        )

    def test_get_driver_info_no_module(self, manager):
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout="modinfo: ERROR: Module as not found.", return_code=1
        )
        with pytest.raises(ModuleNotFoundError):
            manager.get_driver_info("as")

    def test_get_driver_info_no_info(self, manager):
        output = dedent(
            """\
        filename:       /lib/modules/4.18.0-372.32.1.el8_6.x86_64/kernel/drivers/net/ethernet/intel/i40e/i40e.ko.xz
        """
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=output, return_code=0
        )
        assert manager.get_driver_info("i40e") == DriverInfo(driver_name="N/A", driver_version="N/A")

    def test_insert_module(self, manager):
        manager.insert_module("i40e", "-a")
        manager._connection.execute_command.assert_called_with("insmod i40e -a", expected_return_codes={0}, shell=True)

    def test_load_module(self, manager):
        manager.load_module("i40e", "-a")
        manager._connection.execute_command.assert_called_with(
            "modprobe i40e -a", expected_return_codes={0}, shell=True
        )

    def test_list_modules(self, manager):
        first_output = dedent(
            """\
        Module                  Size  Used by
        ipmi_msghandler       114688  4 ipmi_devintf,ipmi_si,acpi_ipmi,ipmi_ssif
        fuse                  155648  3
        """
        )
        second_output = "fuse                  155648  3"
        expected_output = [
            LsModOutput("fuse", 155648, "3"),
            LsModOutput("ipmi_msghandler", 114688, "4 ipmi_devintf,ipmi_si,acpi_ipmi,ipmi_ssif"),
        ]
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=first_output, return_code=0
        )
        assert manager.list_modules() == expected_output
        manager._connection.execute_command.assert_called_with("lsmod", expected_return_codes={0}, shell=True)
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=second_output, return_code=0
        )

        assert manager.list_modules("fuse") == [expected_output[0]]
        manager._connection.execute_command.assert_called_with(
            "lsmod | grep '^fuse'", expected_return_codes={0, 1}, shell=True
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(args="", stdout="", return_code=1)
        assert manager.list_modules("fuse") == []

    def test_unload_module(self, manager):
        manager.unload_module("i40e")
        manager._connection.execute_command.assert_called_with(
            "rmmod i40e", expected_return_codes={0}, shell=True, stderr_to_stdout=True
        )
        manager.unload_module("i40e", "--force")
        manager._connection.execute_command.assert_called_with(
            "rmmod --force i40e", expected_return_codes={0}, shell=True, stderr_to_stdout=True
        )
        manager.unload_module("i40e", "--verbose", with_dependencies=True)
        manager._connection.execute_command.assert_called_with(
            "modprobe -r --verbose i40e", expected_return_codes={0}, shell=True, stderr_to_stdout=True
        )

    def test_install_package_via_rpm(self, manager):
        manager.install_package_via_rpm("i40e", cwd="/home")
        manager._connection.execute_command.assert_called_with(
            "rpm -i --force i40e", expected_return_codes={0}, shell=True, stderr_to_stdout=True, cwd="/home"
        )

    def test_install_package_via_yum(self, manager):
        manager.install_package_via_yum("i40e", cwd="/home")
        manager._connection.execute_command.assert_called_with(
            "yum -y install --allowerasing i40e",
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
            cwd="/home",
        )

    def test_update_initramfs_via_update(self, manager):
        manager.update_initramfs_via_update()
        manager._connection.execute_command.assert_called_with(
            "update-initramfs -u",
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
        )

    def test_update_initramfs_via_dracut(self, manager):
        manager.update_initramfs_via_dracut()
        manager._connection.execute_command.assert_called_with(
            "dracut --force",
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
        )

    def test_uninstall_module(self, manager, mocker):
        manager._connection.get_system_info.return_value.kernel_version = "4.18.0-372.32.1.el8_6.x86_64"
        manager.update_driver_dependencies = mocker.create_autospec(manager.update_driver_dependencies)
        expected_command = (
            "rm -rf"
            " /lib/modules/4.18.0-372.32.1.el8_6.x86_64/updates/drivers/net/ethernet/intel/i40e/i40e.ko*"
            " /lib/modules/4.18.0-372.32.1.el8_6.x86_64/kernel/drivers/net/ethernet/intel/i40e/i40e.ko*"
        )

        manager.uninstall_module("i40e")
        manager._connection.execute_command.assert_called_with(
            expected_command,
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
        )
        expected_command = (
            "rm -rf"
            " /lib/modules/3.15/updates/drivers/net/ethernet/intel/i40e/i40e.ko*"
            " /lib/modules/3.15/kernel/drivers/net/ethernet/intel/i40e/i40e.ko*"
        )

        manager.uninstall_module("i40e", "3.15")
        manager._connection.execute_command.assert_called_with(
            expected_command,
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
        )

    def test_update_driver_dependencies(self, manager):
        manager.update_driver_dependencies()
        manager._connection.execute_command.assert_called_with(
            "depmod -a",
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
        )

    def test_uninstall_package_via_rpm(self, manager):
        manager.uninstall_package_via_rpm("i40e")
        manager._connection.execute_command.assert_called_with(
            "rpm -e $(rpm -qa 'i40e')",
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
        )

    def test_build_rpm(self, manager, mocker):
        manager.install_package_via_rpm = mocker.create_autospec(manager.install_package_via_rpm)
        calls = [
            mocker.call("mkdir -p /rpmbuildpath/{BUILD,RPMS,SOURCES,SPECS,SRPMS}"),
            mocker.call("rm -rf /rpmbuildpath/RPMS/x86_64/*", cwd="/home/i40e/", expected_return_codes={0}),
            mocker.call(
                "rpmbuild --define '_topdir /rpmbuildpath' -tb i40e", cwd="/home/i40e/", expected_return_codes={0}
            ),
        ]
        manager.build_rpm("/home/i40e/", "i40e")
        manager._connection.execute_command.assert_has_calls(calls)
        manager.install_package_via_rpm.assert_called_with("*.rpm", cwd="/rpmbuildpath/RPMS/x86_64")

    def test__unload_if_required(self, manager, mocker):
        manager.is_module_loaded = mocker.create_autospec(manager.is_module_loaded, return_value=True)
        manager.unload_module = mocker.create_autospec(manager.unload_module)
        manager._unload_if_required("i40e")
        manager.unload_module.assert_called_with("i40e")
        manager.unload_module.reset_mock()
        manager.is_module_loaded.return_value = False
        manager._unload_if_required("i40e")
        manager.unload_module.assert_not_called()

    @pytest.mark.parametrize(
        "os_name, dracut_count, update_count", [("Ubuntu", 0, 1), ("Red Hat Enterprise Linux", 1, 0), ("Proton", 0, 0)]
    )
    def test_remove_driver_from_initramfs(self, manager, mocker, os_name, dracut_count, update_count):
        manager._unload_if_required = mocker.create_autospec(manager._unload_if_required)
        manager.update_initramfs_via_dracut = mocker.create_autospec(manager.update_initramfs_via_dracut)
        manager.update_initramfs_via_update = mocker.create_autospec(manager.update_initramfs_via_update)
        args = {field.name: None for field in dataclasses.fields(SystemInfo)}
        args["os_name"] = os_name
        manager._connection.get_system_info.return_value = SystemInfo(**args)
        manager.remove_driver_from_initramfs("i40e")
        assert manager.update_initramfs_via_dracut.call_count == dracut_count
        assert manager.update_initramfs_via_update.call_count == update_count

    def test_read_driver_details(self, manager):
        assert manager.read_driver_details("i40e-2.22.18.tar.gz") == ("i40e", "2.22.18")
        with pytest.raises(PackageManagerNotFoundException, match="Not found version in i40e.tar.gz"):
            manager.read_driver_details("i40e.tar.gz")

    def test_get_drivers_details(self, manager, mocker):
        manager.read_driver_details = mocker.create_autospec(
            manager.read_driver_details, return_value=("i40e", "2.22.18")
        )
        assert manager.get_drivers_details([Path("/dir/i40e-2.22.18.tar.gz")]) == [
            DriverDetails(Path("/dir/i40e-2.22.18.tar.gz"), "2.22.18", "i40e")
        ]

    def test_find_drivers(self, manager, mocker):
        manager._glob_glob_method = mocker.create_autospec(manager._glob_glob_method)
        manager._glob_glob_method.return_value = iter(["/home/user/build/i40e-2.22.18.tar.gz"])
        mocker.patch("mfd_package_manager.linux.Path.exists", return_value=True)
        manager._get_interface_driver = mocker.create_autospec(manager._get_interface_driver, return_value="i40e")
        manager._get_driver_directory = mocker.create_autospec(manager._get_driver_directory, return_value="PRO40GB")
        assert manager.find_drivers("/home/user/build", DeviceID(0x1572)) == [
            Path("/home/user/build/i40e-2.22.18.tar.gz")
        ]
        manager._glob_glob_method.assert_called_once_with(
            str(Path("/home/user/build/")), str(Path("/home/user/build/PRO40GB/linux/i40e*.tar.gz"))
        )

    def test_find_drivers_not_found(self, manager, mocker):
        manager._glob_glob_method = mocker.create_autospec(manager._glob_glob_method)
        manager._glob_glob_method.return_value = iter(["/home/user/build/i40e-2.22.18.tar.gz"])
        mocker.patch("mfd_package_manager.linux.Path.exists", return_value=False)
        with pytest.raises(
            PackageManagerNotFoundException, match=re.escape(f"Build path {Path('/home/user/build')} does not exist.")
        ):
            manager.find_drivers("/home/user/build", DeviceID(0x1572))

    @pytest.fixture()
    def prepared_install_build(self, manager, mocker):
        manager.find_drivers = mocker.create_autospec(
            manager.find_drivers, return_value=[Path("/home/user/build/i40e-2.22.18.tar.gz")]
        )
        manager.get_drivers_details = mocker.create_autospec(
            manager.get_drivers_details,
            return_value=[DriverDetails(Path("/home/user/build/i40e-2.22.18.tar.gz"), "2.22.18", "i40e")],
        )
        manager.is_module_loaded = mocker.create_autospec(manager.is_module_loaded, return_value=True)
        manager._unload_if_required = mocker.create_autospec(manager._unload_if_required)
        manager.unload_module = mocker.create_autospec(manager.unload_module)
        manager.make_clean = mocker.create_autospec(manager.make_clean)
        manager.make_install = mocker.create_autospec(manager.make_install)
        manager.remove_driver_from_initramfs = mocker.create_autospec(manager.remove_driver_from_initramfs)
        manager.load_module = mocker.create_autospec(manager.load_module)
        manager.get_driver_info = mocker.create_autospec(
            manager.get_driver_info, return_value=DriverInfo("i40e", "2.22.18")
        )
        manager._controller_connection = mocker.create_autospec(LocalConnection)

        yield manager

    def test_install_build(self, prepared_install_build, mocker):
        copy_mock = mocker.patch("mfd_package_manager.linux.copy")
        target_path_mock = mocker.create_autospec(Path)
        prepared_install_build._connection.path.return_value = target_path_mock
        prepared_install_build._connection._ip = "127.0.0.1"
        prepared_install_build.install_build("/home/user/build", DeviceID(0x1572), cflags="FLAG")

        copy_mock.assert_called_once_with(
            src_conn=prepared_install_build._controller_connection,
            dst_conn=prepared_install_build._connection,
            source=Path("/home/user/build/i40e-2.22.18.tar.gz"),
            target=target_path_mock / "i40e-2.22.18.tar.gz",
        )
        prepared_install_build._connection.execute_command.assert_called_with(
            f"tar xf {target_path_mock / 'i40e-2.22.18.tar.gz'} -C "
            f"{(target_path_mock / 'i40e-2.22.18.tar.gz').parent} --no-same-owner"
        )
        prepared_install_build.load_module.assert_called_once_with("i40e")
        prepared_install_build.make_clean.assert_called_once_with(cwd=mocker.ANY, cflags="FLAG")
        prepared_install_build.make_install.assert_called_once_with(cwd=mocker.ANY, cflags="FLAG")
        prepared_install_build.remove_driver_from_initramfs.assert_called_once()
        prepared_install_build.get_driver_info.assert_called_once_with("i40e")
        prepared_install_build._unload_if_required.assert_called_once_with("i40iw")

    def test_install_build_not_found(self, prepared_install_build):
        prepared_install_build.find_drivers.return_value = []
        with pytest.raises(PackageManagerNotFoundException):
            prepared_install_build.install_build("/home/user/build", DeviceID(0x1572))

    def test_install_build_missmatch(self, prepared_install_build, mocker):
        mocker.patch("mfd_package_manager.linux.copy")
        target_path_mock = mocker.create_autospec(Path)
        prepared_install_build._connection.path.return_value = target_path_mock
        prepared_install_build._connection._ip = "127.0.0.1"
        prepared_install_build.get_driver_info = mocker.Mock(return_value=DriverInfo("i40e", "2.10.18"))

        with pytest.raises(PackageManagerModuleException):
            prepared_install_build.install_build("/home/user/build", DeviceID(0x1572))

    def test_get_device_ids_to_install(self, manager):
        stdout = dedent(
            """\
        Slot:   0000:3b:00.0
        Class:  Ethernet controller [0200]
        Vendor: Intel Corporation [8086]
        Device: Ethernet Controller X710 for 10GbE SFP+ [1572]
        SVendor:        Intel Corporation [8086]
        SDevice:        Ethernet Converged Network Adapter X710-2 [0007]
        Rev:    01
        NUMANode:       0
        IOMMUGroup:     68

        Slot:   0000:3b:00.1
        Class:  Ethernet controller [0200]
        Vendor: Intel Corporation [8086]
        Device: Ethernet Controller X710 for 10GbE SFP+ [1572]
        SVendor:        Intel Corporation [8086]
        SDevice:        Ethernet Converged Network Adapter X710 [0000]
        Rev:    01
        NUMANode:       0
        IOMMUGroup:     69

        Slot:   0000:17:1e.6
        Class:  System peripheral [0880]
        Vendor: Intel Corporation [8086]
        Device: Sky Lake-E PCU Registers [2086]
        SVendor:        Intel Corporation [8086]
        SDevice:        Device [35d4]
        Rev:    07
        NUMANode:       0
        IOMMUGroup:     35

        Slot:   0000:18:00.0
        Class:  Ethernet controller [0200]
        Vendor: Intel Corporation [8086]
        Device: Ethernet Controller 10G X550T [1563]
        SVendor:        Intel Corporation [8086]
        SDevice:        Device [35d4]
        Rev:    01
        NUMANode:       0
        IOMMUGroup:     36

        Slot:   0000:18:00.1
        Class:  Ethernet controller [0200]
        Vendor: Intel Corporation [8086]
        Device: Ethernet Controller 10G X550T [1563]
        SVendor:        Intel Corporation [8086]
        SDevice:        Device [35d4]
        Rev:    01
        NUMANode:       0
        IOMMUGroup:     37

        Slot:   0000:3a:00.0
        Class:  PCI bridge [0604]
        Vendor: Intel Corporation [8086]
        Device: Sky Lake-E PCI Express Root Port A [2030]
        PhySlot:        785
        Rev:    07
        NUMANode:       0
        IOMMUGroup:     38

        Slot:   0000:3a:05.0
        Class:  System peripheral [0880]
        Vendor: Intel Corporation [8086]
        Device: Sky Lake-E VT-d [2034]
        SVendor:        Intel Corporation [8086]
        SDevice:        Device [35d4]
        Rev:    07
        NUMANode:       0
        IOMMUGroup:     39

        Slot:   0000:3a:05.2
        Class:  System peripheral [0880]
        Vendor: Intel Corporation [8086]
        Device: Sky Lake-E RAS Configuration Registers [2035]
        SVendor:        Intel Corporation [8086]
        SDevice:        Device [35d4]
        Rev:    07
        NUMANode:       0
        IOMMUGroup:     40"""
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=stdout, return_code=0
        )
        assert manager.get_device_ids_to_install() == [DeviceID("1572"), DeviceID("1563")]

    def test_find_management_device_id(self, manager, mocker):
        mocker.patch("mfd_ethtool.Ethtool", return_value=mocker.Mock())
        manager._get_mac_address_for_ip = mocker.create_autospec(
            manager._get_mac_address_for_ip, return_value=MACAddress("a4:bf:01:64:63:39")
        )
        manager._get_interface_names_for_mac = mocker.create_autospec(
            manager._get_interface_names_for_mac, return_value=["bootnet"]
        )
        manager._ethtool.get_driver_information.return_value.bus_info = ["0000:18:00.0"]
        manager._get_device_id_for_pci_address = mocker.create_autospec(
            manager._get_device_id_for_pci_address, return_value=DeviceID("1563")
        )
        assert manager.find_management_device_id() == DeviceID("1563")
        manager._get_mac_address_for_ip.assert_called_once_with(manager._connection.ip)
        manager._get_interface_names_for_mac.assert_called_once_with(MACAddress("a4:bf:01:64:63:39"))
        manager._ethtool.get_driver_information.assert_called_once_with("bootnet")
        manager._get_device_id_for_pci_address.assert_called_once_with(PCIAddress(data="0000:18:00.0"))

    def test__get_mac_address_for_ip(self, manager):
        stdout = dedent(
            """\
        8: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default qlen 1000
            link/ether a4:bf:01:64:63:39 brd ff:ff:ff:ff:ff:ff
            inet 10.91.243.164/24 brd 10.91.243.255 scope global dynamic noprefixroute br0"""
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=stdout, return_code=0
        )
        assert manager._get_mac_address_for_ip(IPAddress("10.91.243.164")) == MACAddress("a4:bf:01:64:63:39")
        manager._connection.execute_command.assert_called_once_with(
            "ip addr show | grep -B2 'inet 10.91.243.164'", shell=True
        )

    def test__get_interface_names_for_mac(self, manager):
        stdout = dedent(
            """\
        6: bootnet: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq master br0 state UP mode DEFAULT qlen 1000
            link/ether a4:bf:01:64:63:39 brd ff:ff:ff:ff:ff:ff
        --
        8: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT group default qlen 1000
            link/ether a4:bf:01:64:63:39 brd ff:ff:ff:ff:ff:ff"""
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=stdout, return_code=0
        )
        assert manager._get_interface_names_for_mac(MACAddress("a4:bf:01:64:63:39")) == ["bootnet", "br0"]
        manager._connection.execute_command.assert_called_once_with(
            "ip link show | grep a4:bf:01:64:63:39 -B1", shell=True
        )

    def test__get_device_id_for_pci_address(self, manager):
        stdout = dedent(
            """\
        Slot:   0000:18:00.0
        Class:  Ethernet controller [0200]
        Vendor: Intel Corporation [8086]
        Device: Ethernet Controller 10G X550T [1563]"""
        )
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=stdout, return_code=0
        )
        assert manager._get_device_id_for_pci_address(PCIAddress(data="0000:18:00.0")) == DeviceID("1563")
        manager._connection.execute_command.assert_called_once_with(
            "lspci -D -nnvvvmm | grep -A3 0000:18:00.0", shell=True
        )

    @pytest.mark.parametrize("message", ["No match for argument: module", "Removed module"])
    def test_remove_package_via_dnf(self, manager, message):
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout=message, return_code=0
        )
        manager.remove_package_via_dnf("module")
        manager._connection.execute_command.assert_called_once_with(
            "dnf -y remove module", expected_return_codes={0}, shell=True, stderr_to_stdout=True, cwd=None
        )

    def test_remove_package_via_yum(self, manager):
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="", stdout="stdout", return_code=0
        )
        manager.remove_package_via_yum("module")
        manager._connection.execute_command.assert_called_once_with(
            "yum -y remove module", expected_return_codes={0}, shell=True, stderr_to_stdout=True, cwd=None
        )

    def test_is_loaded_driver_inbox_driver(self, manager):
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="",
            stdout="/lib/modules/5.4.0-74-generic/kernel/drivers/net/ethernet/intel/i40e/i40e.ko",
            return_code=0,
        )
        assert manager.is_loaded_driver_inbox("i40e") is True
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="",
            stdout="/lib/modules/4.18.0-372.32.1.el8_6.x86_64/updates/drivers/net/ethernet/intel/i40e/i40e.ko",
            return_code=0,
        )
        assert manager.is_loaded_driver_inbox("i40e") is False

    def test_is_loaded_driver_inbox_failure(self, manager):
        manager._connection.execute_command.return_value = ConnectionCompletedProcess(
            args="",
            stdout="some error",
            return_code=1,
        )
        with pytest.raises(ModuleNotFoundError):
            manager.is_loaded_driver_inbox("i40e")

    def test_recompile_and_load_driver(self, manager, mocker):
        manager.make_clean = mocker.create_autospec(manager.make_clean)
        manager.make_install = mocker.create_autospec(manager.make_install)
        manager.unload_module = mocker.create_autospec(manager.unload_module)
        manager.remove_driver_from_initramfs = mocker.create_autospec(manager.remove_driver_from_initramfs)
        manager.insert_module = mocker.create_autospec(
            manager.insert_module,
            return_value=ConnectionCompletedProcess(args="", stdout="some output", return_code=0),
        )
        manager.recompile_and_load_driver("i40e", "/home/user/i40e/src/")
        manager.insert_module.assert_called_with("/home/user/i40e/src/i40e.ko")
        manager.make_clean.assert_called_once_with(jobs=None, cflags=None, cwd="/home/user/i40e/src/")
        manager.make_install.assert_called_once_with(jobs=None, cflags=None, cwd="/home/user/i40e/src/")
        manager.unload_module.assert_called_once_with("i40e")
        manager.remove_driver_from_initramfs.assert_called_once_with("i40e")

    def test_is_package_installed_via_rpm(self, manager):
        manager._connection.execute_command.side_effect = [
            ConnectionCompletedProcess(args="", stdout="package lib is not installed", return_code=1),
            ConnectionCompletedProcess(args="", stdout="make-4.3-11.fc37.x86_64", return_code=0),
        ]
        assert manager.is_package_installed_via_rpm(package="lib", cwd="/home/user") is False
        assert manager.is_package_installed_via_rpm(package="make") is True
        manager._connection.execute_command.assert_has_calls(
            [
                call(command="rpm -q lib", shell=True, cwd="/home/user", expected_return_codes={}),
                call(command="rpm -q make", shell=True, cwd=None, expected_return_codes={}),
            ]
        )

    def test_is_package_installed_via_dpkg(self, manager):
        output = dedent(
            """
        Desired=Unknown/Install/Remove/Purge/Hold
        | Status=Not/Inst/Conf-files/Unpacked/halF-conf/Half-inst/trig-aWait/Trig-pend
        |/ Err?=(none)/Reinst-required (Status,Err: uppercase=bad)
        ||/ Name           Version      Architecture Description
        +++-==============-============-============-=================================
        un  docker         <none>       <none>       (no description available)
            """
        )
        manager._connection.execute_command.side_effect = [
            ConnectionCompletedProcess(args="", stdout="dpkg-query: no packages found matching rqm", return_code=1),
            ConnectionCompletedProcess(args="", stdout=output, return_code=0),
        ]
        assert manager.is_package_installed_via_dpkg(package="rqm", cwd="/home/user") is False
        assert manager.is_package_installed_via_dpkg(package="docker") is True
        manager._connection.execute_command.assert_has_calls(
            [
                call(command="dpkg -l rqm", shell=True, cwd="/home/user", expected_return_codes={}),
                call(command="dpkg -l docker", shell=True, cwd=None, expected_return_codes={}),
            ]
        )

    def test_install_package_via_dnf(self, manager):
        manager.install_package_via_dnf("1.2.3", cwd="/home")
        manager._connection.execute_command.assert_called_with(
            "dnf install 1.2.3 -y",
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
            cwd="/home",
        )

    def test_install_package_via_zypper(self, manager):
        manager.install_package_via_zypper("podman-docker", cwd="/home")
        manager._connection.execute_command.assert_called_with(
            "zypper install -y podman-docker",
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
            cwd="/home",
        )

    def test_ethtool(self, manager, mocker):
        mocker.patch("mfd_ethtool.Ethtool", return_value=mocker.Mock(name="ethtool"))
        assert manager._LinuxPackageManager__ethtool is None
        manager._ethtool
        assert manager._LinuxPackageManager__ethtool is not None
