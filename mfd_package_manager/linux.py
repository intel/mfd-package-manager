# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Module for Linux."""

import logging
import re
import typing
from dataclasses import dataclass
from typing import Optional, Union, List, Tuple, Dict

from mfd_common_libs import os_supported, log_levels
from mfd_connect import LocalConnection
from mfd_connect.util.rpc_copy_utils import copy
from mfd_typing import OSName, PCIAddress, DeviceID, MACAddress
from mfd_typing.driver_info import DriverInfo
from mfd_typing.cpu_values import CPUArchitecture

from mfd_package_manager.data_structures import DriverDetails
from mfd_package_manager.exceptions import PackageManagerNotFoundException, PackageManagerModuleException
from mfd_package_manager.unix import UnixPackageManager
from pathlib import Path, PurePosixPath

if typing.TYPE_CHECKING:
    from mfd_connect.base import ConnectionCompletedProcess
    from mfd_connect import Connection
    from netaddr import IPAddress
    from mfd_ethtool import Ethtool

logger = logging.getLogger(__name__)


@dataclass
class LsModOutput:
    """Structure representing a lsmod entries."""

    module: str
    size: int
    used_by: str

    def __post_init__(self):
        self.size = int(self.size)


class LinuxPackageManager(UnixPackageManager):
    """Package manager for Linux."""

    DRIVER_REGEX = r"(?P<name>\w+)-(?P<version>\d+(\.\d+)+\.?(?:(?!_simics)(?:\w|\.))+)\.tar\.gz"
    DEVICE_ID_REGEX = r"^Device\s*:.*\[(?P<device_id>\w+)\]$"

    @os_supported(OSName.LINUX)
    def __init__(self, *, connection: "Connection", controller_connection: "Connection" = LocalConnection()):
        """
        Initialize utility.

        :param connection: Object of mfd-connect
        """
        super().__init__(connection=connection, controller_connection=controller_connection)
        self.__ethtool = None

    @property
    def _ethtool(self) -> "Ethtool":
        """
        Get ethtool object.

        :return: Ethtool object
        """
        if self.__ethtool is None:
            from mfd_ethtool import Ethtool

            self.__ethtool = Ethtool(connection=self._connection)
        return self.__ethtool

    def is_module_loaded(self, module_name: str) -> bool:  # noqa D102
        result = self._connection.execute_command(
            f'lsmod | grep "\\<{module_name}\\>"', shell=True, expected_return_codes=None
        )
        return result.return_code == 0 and result.stdout != ""

    def bind_driver(self, pci_address: PCIAddress, driver_name: str) -> "ConnectionCompletedProcess":
        """
        Bind driver.

        :param pci_address: PCI address of interface
        :param driver_name: Name of driver
        :return: Result of binding
        """
        return self._connection.execute_command(
            f"echo {pci_address.lspci} > /sys/bus/pci/drivers/{driver_name}/bind",
            expected_return_codes={0},
            shell=True,
        )

    def unbind_driver(self, pci_address: PCIAddress, driver_name: str) -> "ConnectionCompletedProcess":
        """
        Unbind driver.

        :param pci_address: PCI address of interface
        :param driver_name: Name of driver
        :return: Result of unbinding
        """
        return self._connection.execute_command(
            f"echo {pci_address.lspci} > /sys/bus/pci/drivers/{driver_name}/unbind",
            expected_return_codes={0},
            shell=True,
        )

    def add_module_to_blacklist(self, module_name: str) -> "ConnectionCompletedProcess":
        """
        Add module to modprobe blacklist.

        :param module_name: Module name to blacklist
        :return: Result of adding module to blacklist
        """
        return self._connection.execute_command(
            f"echo 'blacklist {module_name}' >> /etc/modprobe.d/blacklist.conf", expected_return_codes={0}, shell=True
        )

    def remove_module_from_blacklist(self, module_name: str) -> "ConnectionCompletedProcess":
        """
        Remove module from modprobe blacklist.

        :param module_name: Module name to blacklist
        :return: Result of removing module from blacklist
        """
        return self._connection.execute_command(
            f"sed -i.bak '/blacklist {module_name}/d' /etc/modprobe.d/blacklist.conf",
            expected_return_codes={0},
            shell=True,
        )

    def is_module_on_blacklist(self, module_name: str) -> bool:
        """
        Check if module is on blacklist.

        :param module_name: Module name to check if is on blacklist
        :return: Status of existence module on blacklist
        """
        result = self._connection.execute_command(
            f"cat /etc/modprobe.d/blacklist.conf | grep 'blacklist {module_name}'",
            expected_return_codes={0, 1},
            shell=True,
        )
        return result.stdout != ""

    def get_driver_info(self, driver_name: str) -> "DriverInfo":
        """
        Get driver information (driver name, version).

        :param driver_name: Driver to check
        :return: Structure with driver info
        """
        result = self._connection.execute_command(
            f"modinfo {driver_name}", expected_return_codes={0, 1}, shell=True, stderr_to_stdout=True
        )
        if result.return_code == 1:
            raise ModuleNotFoundError(result.stdout)
        version_regex = r"^\s*version:\s+(?P<version>.*)"
        name_regex = r"^\s*name:\s+(?P<name>.*)"
        version_match = re.search(version_regex, result.stdout, flags=re.MULTILINE)
        name_match = re.search(name_regex, result.stdout, flags=re.MULTILINE)
        name = name_match.group("name") if name_match is not None else "N/A"
        version = version_match.group("version") if version_match is not None else "N/A"
        return DriverInfo(driver_version=version, driver_name=name)

    def insert_module(self, module_path: Union[str, "Path"], params: str = "") -> "ConnectionCompletedProcess":
        """
        Add kernel module with configuration parameters.

        :param module_path: Path to module
        :param params: Parameter(s) passed to module before inserting
        :return: Result of inserting module
        """
        return self._connection.execute_command(f"insmod {module_path} {params}", expected_return_codes={0}, shell=True)

    def load_module(self, module_name: str, params: str = "") -> "ConnectionCompletedProcess":
        """
        Load kernel module with configuration parameters. Module must be available in the /lib/modules directory.

        :param module_name: Name of module
        :param params: Parameter(s) passed to module before loading
        :return: Result of loading module
        """
        return self._connection.execute_command(
            f"modprobe {module_name} {params}", expected_return_codes={0}, shell=True
        )

    def list_modules(self, module_name: Optional[str] = None) -> List[LsModOutput]:
        """
        List modules in loaded in system.

        :param module_name: Optional module name to grep
        :return: List of lsmod output structures
        """
        command = "lsmod"
        expected_return_codes = {0}
        if module_name is not None:
            command += f" | grep '^{module_name}'"
            expected_return_codes.add(1)
        output = self._connection.execute_command(
            command, expected_return_codes=expected_return_codes, shell=True
        ).stdout.splitlines()
        if output == "":
            return []
        if module_name is None:
            output = output[1:]  # skip header of lsmod
        output.sort()
        return [LsModOutput(*module.split(maxsplit=2)) for module in output]

    def unload_module(
        self, module_name: str, options: Optional[str] = None, *, with_dependencies: bool = False
    ) -> "ConnectionCompletedProcess":
        """
        Unload module from system.

        :param module_name: Module to unload
        :param options: Optional options to unload
        :param with_dependencies: If true modprobe -r will be used, otherwise rmmod
        :return: Result of unloading
        """
        if with_dependencies:
            command_list = ["modprobe -r"]
        else:
            command_list = ["rmmod"]
        if options is not None:
            command_list.append(options)
        command_list.append(module_name)
        command = " ".join(command_list)
        return self._connection.execute_command(command, expected_return_codes={0}, shell=True, stderr_to_stdout=True)

    def install_package_via_rpm(
        self, package: str, cwd: Optional[Union["Path", str]] = None
    ) -> "ConnectionCompletedProcess":
        """
        Install package using rpm tool.

        :param package: Package to install, name, full path or package with wildcard
        :param cwd: Directory where rpm will be called
        :return: Result of installation
        """
        return self._connection.execute_command(
            f"rpm -i --force {package}", expected_return_codes={0}, shell=True, stderr_to_stdout=True, cwd=cwd
        )

    def install_package_via_yum(
        self, package: str, cwd: Optional[Union["Path", str]] = None
    ) -> "ConnectionCompletedProcess":
        """
        Install package using yum tool.

        :param package: Package to install, name, full path or package with wildcard
        :param cwd: Directory where yum will be called
        :return: Result of installation
        """
        return self._connection.execute_command(
            f"yum -y install --allowerasing {package}",
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
            cwd=cwd,
        )

    def remove_package_via_yum(
        self, package: str, cwd: Optional[Union["Path", str]] = None
    ) -> "ConnectionCompletedProcess":
        """
        Remove package using yum tool.

        :param package: Package to install, name, full path or package with wildcard
        :param cwd: Directory where yum will be called
        :return: Result of installation
        """
        return self._connection.execute_command(
            f"yum -y remove {package}",
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
            cwd=cwd,
        )

    def remove_package_via_dnf(
        self, package: str, cwd: Optional[Union["Path", str]] = None
    ) -> "ConnectionCompletedProcess":
        """
        Remove package using dnf tool.

        :param package: Package to remove, name, full path or package with wildcard
        :param cwd: Directory where dnf will be called
        :return: Result of removal
        """
        result = self._connection.execute_command(
            f"dnf -y remove {package}",
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
            cwd=cwd,
        )
        if "removed" not in result.stdout.casefold() and "no match for argument" not in result.stdout.casefold():
            raise PackageManagerModuleException(f"Removal of package {package} failed: {result.stdout}")
        return result

    def update_initramfs_via_update(self) -> "ConnectionCompletedProcess":
        """
        Update initramfs using update-initramfs.

        :return: Result of update
        """
        return self._connection.execute_command(
            "update-initramfs -u", expected_return_codes={0}, shell=True, stderr_to_stdout=True
        )

    def update_initramfs_via_dracut(self) -> "ConnectionCompletedProcess":
        """
        Update initramfs using dracut.

        :return:Result of update
        """
        return self._connection.execute_command(
            "dracut --force", expected_return_codes={0}, shell=True, stderr_to_stdout=True
        )

    def uninstall_module(self, module_name: str, kernel_version: Optional[str] = None) -> "ConnectionCompletedProcess":
        """
        Remove intel driver from kernel.

        :param module_name: Driver to remove
        :param kernel_version: Optional version of kernel, if not passed running kernel will be used
        :return: Result of removing
        """
        if kernel_version is None:
            kernel_version = self._connection.get_system_info().kernel_version
        common_prefix = f"/lib/modules/{kernel_version}"
        command_list = [
            "rm -rf",
            f"{common_prefix}/updates/drivers/net/ethernet/intel/{module_name}/{module_name}.ko*",
            f"{common_prefix}/kernel/drivers/net/ethernet/intel/{module_name}/{module_name}.ko*",
        ]

        command = " ".join(command_list)
        remove_result = self._connection.execute_command(
            command, expected_return_codes={0}, shell=True, stderr_to_stdout=True
        )
        self.update_driver_dependencies()
        return remove_result

    def update_driver_dependencies(self) -> None:
        """Update driver dependencies using depmod."""
        self._connection.execute_command("depmod -a", expected_return_codes={0}, shell=True, stderr_to_stdout=True)

    def uninstall_package_via_rpm(self, package_name: str) -> "ConnectionCompletedProcess":
        """
        Uninstall package using rpm tool.

        :param package_name: Package to uninstall
        :return: Result of uninstallation
        """
        return self._connection.execute_command(
            f"rpm -e $(rpm -qa '{package_name}')", expected_return_codes={0}, shell=True, stderr_to_stdout=True
        )

    def build_rpm(self, module_path: Union["Path", str], module_filename: str) -> None:
        """
        Build RPM using RPM Package Manager.

        :param module_path: Path to module sources
        :param module_filename: Name of module
        """
        logger.log(level=log_levels.MODULE_DEBUG, msg="Installing module using RPM Package Manager")
        arch_path = "x86_64"
        if self._connection.get_cpu_architecture() is CPUArchitecture.ARM64:
            arch_path = "aarch64"
        rpmbuild_path = f"/rpmbuildpath/RPMS/{arch_path}"

        logger.log(level=log_levels.MODULE_DEBUG, msg="Creating local rpmbuild tree in /rpmbuildpath/")
        command = "mkdir -p /rpmbuildpath/{BUILD,RPMS,SOURCES,SPECS,SRPMS}"
        self._connection.execute_command(command)

        logger.log(level=log_levels.MODULE_DEBUG, msg="Delete already build rpms")
        command = f"rm -rf {rpmbuild_path}/*"
        self._connection.execute_command(command, cwd=module_path, expected_return_codes={0})

        logger.log(level=log_levels.MODULE_DEBUG, msg="Building rpm in the local rpmbuild tree")
        command = f"rpmbuild --define '_topdir /rpmbuildpath' -tb {module_filename}"
        self._connection.execute_command(command, cwd=module_path, expected_return_codes={0})
        self.install_package_via_rpm("*.rpm", cwd=rpmbuild_path)

    def _unload_if_required(self, module_name: str) -> None:
        """
        Unload module if it's loaded.

        :param module_name: Name of module
        """
        if self.is_module_loaded(module_name):
            self.unload_module(module_name)

    def get_device_ids_to_install(self) -> List[DeviceID]:
        """
        Get list of interfaces to install build.

        :return: List of Device IDs to install.
        """
        device_ids = []
        command = "lspci -D -nnvvvmm"
        lspci_output = self._connection.execute_command(command, shell=True).stdout.strip()
        for match in re.finditer(self.DEVICE_ID_REGEX, lspci_output, flags=re.M):
            possible_device_id = DeviceID(match.group("device_id"))
            try:
                self._get_interface_driver(possible_device_id)  # check if device_id is supported (is in DB)
                logger.log(level=log_levels.MODULE_DEBUG, msg=f"Found device_id: {possible_device_id}")
            except PackageManagerNotFoundException:
                continue
            device_ids.append(possible_device_id)
        device_ids = list(set(device_ids))
        return device_ids

    def find_management_device_id(self) -> Optional[DeviceID]:
        """
        Get device_id of management interface using connection IP address.

        :return: Device ID of management interface if found
        """
        management_ip_address = self._connection.ip
        mac_address = self._get_mac_address_for_ip(management_ip_address)
        if not mac_address:
            return
        # find interface_names with the same mac address as management ip interface
        interface_names = self._get_interface_names_for_mac(mac_address)
        if not interface_names:
            return
        # find device_id of correct management interface
        for interface_name in interface_names:
            pci_address = "N/A"
            ethtool_output = self._ethtool.get_driver_information(interface_name)
            if hasattr(ethtool_output, "bus_info"):
                pci_address = ethtool_output.bus_info[0]
            if pci_address == "N/A":
                continue
            pci_address = PCIAddress(data=pci_address)
            return self._get_device_id_for_pci_address(pci_address)

    def _get_mac_address_for_ip(self, management_ip_address: "IPAddress") -> Optional[MACAddress]:
        """
        Get mac address of the management interface based on the IP address.

        :param management_ip_address: Management IP address
        :return: MAC address if found
        """
        ip_addr_output = self._connection.execute_command(
            f"ip addr show | grep -B2 'inet {management_ip_address}'", shell=True
        ).stdout.strip()
        mac_address_pattern = r"ether\s(?P<mac_address>([a-f\d]{2}:){5}[a-f\d]{2})"
        match = re.search(mac_address_pattern, ip_addr_output, re.I)  # get mac address related with management ip
        if not match:
            return None
        return MACAddress(match.group("mac_address"))

    def _get_interface_names_for_mac(self, mac_address: MACAddress) -> List[str]:
        """
        Get Interface names of the interfaces associated with the given mac address.

        :param mac_address: MAC address
        :return: List of interface names
        """
        macs = self._connection.execute_command(f"ip link show | grep {mac_address} -B1", shell=True).stdout.strip()
        lspci_blocks = re.split(r"\n--|^\s*$", macs, flags=re.MULTILINE)
        interface_names = []
        for block in lspci_blocks:
            rege = r"\d+\s*:\s*(?P<interface_name>\w+)\s*:"
            match = re.search(rege, block)
            if match:
                interface_names.append(match.group("interface_name"))
        return interface_names

    def _get_device_id_for_pci_address(self, pci_address: PCIAddress) -> DeviceID:
        """
        Get Device ID associated with pci address.

        :param pci_address: PCI Address
        :return: Device ID of interface
        """
        lspci_output = self._connection.execute_command(
            f"lspci -D -nnvvvmm | grep -A3 {pci_address}", shell=True
        ).stdout.strip()
        matches = re.findall(self.DEVICE_ID_REGEX, lspci_output, flags=re.M)
        if len(matches) > 1:
            raise Exception(f"Found more than one device_id for pci address {pci_address}")
        device_id = matches[0]
        logger.log(level=log_levels.MODULE_DEBUG, msg=f"Found management device id: {device_id}.")
        return DeviceID(device_id)

    def install_build_for_device_id(  # noqa D102
        self,
        build_path: Union[str, "Path"],
        device_id: "DeviceID",
        reboot_timeout: int = 120,
        cflags: Optional[Union[Dict, str]] = None,
        installation_method: str = None,
        proset_flags: bool = False,
    ) -> None:
        """
        Install driver for interface.

        :param build_path: Path to build
        :param device_id: Device ID of adapter
        :param reboot_timeout: Timeout for reboot of machine in case when reboot is required
        :param installation_method: installation_method to set
        :param proset_flags: proset_flags to set
        """
        logger.log(level=log_levels.MODULE_DEBUG, msg=f"Looking for drivers in {build_path} for {device_id} device id.")
        drivers = self.find_drivers(build_path, device_id)
        drivers_to_install = self.get_drivers_details(drivers)
        if not drivers:
            raise PackageManagerNotFoundException("Not found drivers in build")

        driver_destination = self._connection.path(self.DRIVERS_REMOTE_LOCATION)
        if driver_destination.exists():
            self._rmtree(driver_destination)

        for driver_to_install in drivers_to_install:
            target = driver_destination / driver_to_install.driver_path.name
            logger.log(
                level=log_levels.MODULE_DEBUG,
                msg=f"Copying {driver_to_install.driver_path.name} driver to "
                f"{self._connection}:{self._connection._ip}.",
            )
            copy(
                src_conn=self._controller_connection,
                dst_conn=self._connection,
                source=driver_to_install.driver_path,
                target=target,
            )
            logger.log(
                level=log_levels.MODULE_DEBUG,
                msg=f"Unpacking {target.name} archive to {target.parent}",
            )
            self._connection.execute_command(f"tar xf {target} -C {target.parent} --no-same-owner")  # todo mfd-connect

            module_name = driver_to_install.driver_name
            logger.log(
                level=log_levels.MODULE_DEBUG,
                msg=f"Looking for installed drivers in system for {device_id} device id.",
            )
            if self.is_module_loaded(module_name):
                if module_name == "i40e":
                    self._unload_if_required("i40iw")
                if module_name == "ice":
                    self._unload_if_required("irdma")
                logger.log(level=log_levels.MODULE_DEBUG, msg=f"Unloading {module_name} driver from system.")
                self.unload_module(module_name)

            src_directory = target.parent / target.name.replace(".tar.gz", "") / "src"
            logger.log(level=log_levels.MODULE_DEBUG, msg=f"Compiling {src_directory.parent.name} driver.")
            self.make_clean(cwd=src_directory, cflags=cflags)
            self.make_install(cwd=src_directory, cflags=cflags)

            logger.log(
                level=log_levels.MODULE_DEBUG,
                msg=f"Removing {module_name} driver from initramfs and reloading it again.",
            )
            self.remove_driver_from_initramfs(module_name)
            self.load_module(module_name)

            if self.get_driver_info(module_name).driver_version != driver_to_install.driver_version:
                raise PackageManagerModuleException(
                    f"Driver {target} is in different version than expected {driver_to_install.driver_version}"
                )
            logger.log(
                level=log_levels.MODULE_DEBUG,
                msg=f"Installed {module_name} driver in {driver_to_install.driver_version} version",
            )

    def remove_driver_from_initramfs(self, module_name: str) -> None:
        """
        Remove driver from initramfs.

        Unload module and update initramfs.

        :param module_name: Name of module
        """
        self._unload_if_required(module_name)
        os_name = self._connection.get_system_info().os_name
        if "proton" in os_name.casefold():
            return
        if "ubuntu" in os_name.casefold():
            self.update_initramfs_via_update()
        else:
            self.update_initramfs_via_dracut()

    def read_driver_details(self, driver_tar_filename: str) -> Tuple[str, str]:
        """
        Get name and version of driver based on the name of tar.

        :param driver_tar_filename: Name of packed driver
        :return: Name and version strings as tuple
        :raises PackageManagerNotFoundException: if not found details in filename
        """
        match = re.match(self.DRIVER_REGEX, driver_tar_filename)
        if match:
            return match.group("name"), match.group("version")
        raise PackageManagerNotFoundException(f"Not found version in {driver_tar_filename}")

    def get_drivers_details(self, list_of_drivers: List[Path]) -> List[DriverDetails]:
        """
        Get list of drivers details (path, version, name).

        :param list_of_drivers: List of drivers paths
        :return: List of driver details (path, version)
        """
        matching_drivers = []
        for driver in list_of_drivers:
            name, version = self.read_driver_details(driver.name)
            matching_drivers.append(DriverDetails(driver, version, name))
        logger.log(level=log_levels.MODULE_DEBUG, msg=f"Found {matching_drivers} drivers in build")
        return matching_drivers

    def find_drivers(self, build_path: Union[str, Path], device_id: "DeviceID") -> List[Path]:
        """
        Find drivers in build path for given driver_details.

        :param build_path: Path to build
        :param device_id: Device ID of interface to find drivers
        :return: List of found drivers paths
        :raises PackageManagerNotFoundException: when not found something in flow
        (driver_name, driver_directory or windows_version_folder)
        """
        if isinstance(build_path, str):
            build_path = self._controller_connection.path(build_path)
        if not build_path.exists():
            raise PackageManagerNotFoundException(f"Build path {build_path} does not exist.")
        driver_name = self._get_interface_driver(device_id)
        driver_directory = self._get_driver_directory(driver_name)
        search_string = str(build_path / driver_directory / "linux" / f"{driver_name}*.tar.gz")
        logger.log(level=log_levels.MODULE_DEBUG, msg=f"Looking in {search_string} for drivers.")
        found_drivers = [
            self._controller_connection.path(driver)
            for driver in self._glob_glob_method(str(build_path), search_string)
            if re.search(self.DRIVER_REGEX, driver)
        ]
        logger.log(
            level=log_levels.MODULE_DEBUG,
            msg=f"Found {found_drivers} drivers in build potentially for device_id: {device_id}",
        )
        return found_drivers

    def is_loaded_driver_inbox(self, driver_name: str) -> bool:
        """
        Check if loaded driver is inbox.

        :param driver_name: Driver name
        :return: Inbox statement
        :raises ModuleNotFoundError: when found issue like driver is not found.
        """
        inbox_string = "kernel/drivers"
        result = self._connection.execute_command(
            f"modinfo {driver_name} | grep -w filename",
            expected_return_codes={0, 1},
            shell=True,
            stderr_to_stdout=True,
        )
        if result.return_code == 1:
            raise ModuleNotFoundError(result.stdout)

        return inbox_string in result.stdout.casefold()

    def recompile_and_load_driver(
        self,
        driver_name: str,
        build_path: Union[str, "Path"],
        jobs: Optional[Union[str, int]] = None,
        cflags: Optional[Union[Dict, str]] = None,
    ) -> "ConnectionCompletedProcess":
        """
        Recompile and reload the driver.

        :param driver_name: Name of the driver such as i40e
        :param build_path: Directory where make will be executed.
        :param jobs: Amount of 'threads' to use, or system evaluation like '$(nproc)'
        :param cflags: Flags for compilation
        :return: Result of inserting module
        """
        self.make_clean(jobs=jobs, cflags=cflags, cwd=build_path)
        self.make_install(jobs=jobs, cflags=cflags, cwd=build_path)
        self.unload_module(driver_name)
        self.remove_driver_from_initramfs(driver_name)
        driver_ko_path = str(PurePosixPath(build_path, f"{driver_name}.ko"))
        return self.insert_module(driver_ko_path)

    def is_package_installed_via_rpm(self, package: str, cwd: "Path | str | None" = None) -> bool:
        """
        Check if specified package is already installed using rpm tool.

        :param package: Package to check for
        :param cwd: Directory where rpm will be called
        :return: True if package is installed, False if package not installed or error occurs while checking
        """
        is_package_present = self._connection.execute_command(
            command=f"rpm -q {package}", shell=True, cwd=cwd, expected_return_codes={}
        )
        return is_package_present.return_code == 0

    def is_package_installed_via_dpkg(self, package: str, cwd: "Path | str | None" = None) -> bool:
        """
        Check if specified package is already installed using dpkg tool.

        :param package: Package to check for
        :param cwd: Directory where dpkg will be called
        :return: True if package is installed, False if package not installed or error occurs while checking
        """
        is_package_present = self._connection.execute_command(
            command=f"dpkg -l {package}", shell=True, cwd=cwd, expected_return_codes={}
        )
        return is_package_present.return_code == 0

    def install_package_via_dnf(self, package: str, cwd: "Path | str | None" = None) -> "ConnectionCompletedProcess":
        """
        Install package using dnf tool.

        :param package: Package to install, name, full path or package with wildcard
        :param cwd: Directory where dnf will be called
        :return: Result of installation
        """
        return self._connection.execute_command(
            f"dnf install {package} -y",
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
            cwd=cwd,
        )

    def install_package_via_zypper(self, package: str, cwd: "Path | str | None" = None) -> "ConnectionCompletedProcess":
        """
        Install package using zypper tool.

        :param package: Package to install, name, full path or package with wildcard
        :param cwd: Directory where zypper will be called
        :return: Result of installation
        """
        return self._connection.execute_command(
            f"zypper install -y {package}",
            expected_return_codes={0},
            shell=True,
            stderr_to_stdout=True,
            cwd=cwd,
        )
