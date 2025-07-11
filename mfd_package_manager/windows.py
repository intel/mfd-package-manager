# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Module for windows."""

import logging
import re
import typing
from itertools import chain
from typing import List, Union, Dict, Set, Optional, Tuple
import copy as cpy
from pathlib import Path
import ntpath

from mfd_common_libs import os_supported, log_levels
from mfd_connect.util.rpc_copy_utils import copy
from mfd_devcon import Devcon
from mfd_connect import LocalConnection
from mfd_connect.exceptions import ConnectionCalledProcessError
from mfd_typing import OSName, DeviceID
from mfd_const.network import WINDOWS_DRIVER_DEVICE_ID_MAP, DRIVER_DEVICE_ID_MAP

from mfd_package_manager.base import PackageManager
from mfd_package_manager.data_structures import (
    WindowsStoreDriver,
    DriverDetails,
    InstallationMethod,
)
from mfd_package_manager.const import PROSET_DCB_FLAGS, PROSETDX_INSTALL_LOG_PATH, uninstall_key
from mfd_package_manager.exceptions import (
    PackageManagerModuleException,
    PackageManagerConnectedOSNotSupported,
    PackageManagerNotFoundException,
)
from mfd_win_registry import WindowsRegistry

if typing.TYPE_CHECKING:
    from mfd_connect.base import ConnectionCompletedProcess
    from mfd_connect import Connection

logger = logging.getLogger(__name__)


class WindowsPackageManager(PackageManager):
    """Package manager for Windows."""

    DRIVERS_REMOTE_LOCATION = "c:\\drivers_under_test\\"
    PCI_DEVICE_PATTERN = re.compile(r"PCI\\VEN_(\w+)&DEV_(?P<device_id>\w+).*&REV")

    FOLDER_OS_VERSION_MATCH = {
        "NDIS64": range(9200, 9600 + 1),
        "NDIS65": range(14393, 14393 + 1),
        "NDIS68": range(17600, 19042 + 1),
        "WS2022": list(chain(range(20348, 22000), [23598], range(25000, 25999))),
        "W11": range(22000, 22999),
        "WS2025": range(26000, 26999),
    }

    def _prepare_map(self) -> Dict[str, Set]:
        """Update mapping for Windows driver names."""
        driver_map = cpy.copy(DRIVER_DEVICE_ID_MAP)
        driver_map["v1q"] = driver_map["igbvf"]
        driver_map["ix"] = driver_map["ixgbe"]
        driver_map["vx"] = driver_map["ixgbevf"]
        driver_map["e2f"] = driver_map["igc"]
        driver_map["scea"] = WINDOWS_DRIVER_DEVICE_ID_MAP["scea"]
        driver_map["ice"] = driver_map["ice"] - driver_map["scea"]
        del driver_map["igbvf"]
        del driver_map["ixgbe"]
        del driver_map["ixgbevf"]
        del driver_map["igc"]

        return driver_map

    @os_supported(OSName.WINDOWS)
    def __init__(self, *, connection: "Connection", controller_connection: "Connection" = LocalConnection()):
        """
        Initialize package manager.

        Copy devcon exe and establish devcon object.

        :param connection: connection object
        :param controller_connection: Object of mfd-connect to controller, default local connection
        """
        super(WindowsPackageManager, self).__init__(connection=connection, controller_connection=controller_connection)
        self.DRIVER_DEVICE_ID_MAP = self._prepare_map()
        self.devcon = self._prepare_devcon()
        self._win_registry = WindowsRegistry(connection=connection)

    def delete_driver_via_pnputil(self, inf_filename: str) -> "ConnectionCompletedProcess":
        """
        Delete driver using pnputil.

        :param inf_filename: Name of windows driver file
        :return: Result of uninstallation
        :raises PackageManagerModuleException: when cannot uninstall driver
        """
        possible_command = (
            f"pnputil /delete-driver {inf_filename} /force /uninstall",
            f"pnputil /delete-driver {inf_filename} /force",
        )
        for command in possible_command:
            logger.log(
                level=log_levels.MODULE_DEBUG, msg=f"Trying to uninstall and delete driver by command: {command}..."
            )
            result = self._connection.execute_command(
                command, timeout=90, expected_return_codes=None, stderr_to_stdout=True
            )
            logger.log(level=log_levels.MODULE_DEBUG, msg=f"Finished executing '{command}', output:\n{result.stdout}")
            if result.return_code != 0:
                continue
            return result
        raise PackageManagerModuleException(f"Cannot uninstall '{inf_filename}'")

    def get_driver_filename_from_registry(self, driver_name: str) -> str:  # todo mfd-windows-registry
        """
        Get driver filename from registry.

        :param driver_name: Name of driver
        :return: Driver filename
        :raises PackageManagerModuleException: if not found driver
        """
        command = rf"Get-ItemProperty -path 'HKLM:\system\CurrentControlSet\services\{driver_name}' -name 'ImagePath'"
        result = self._connection.execute_powershell(command, stderr_to_stdout=True)
        match = re.search(r"ImagePath.*\\(?P<filename>.*sys)", result.stdout)
        if not match:
            logger.log(level=log_levels.MODULE_DEBUG, msg=f"Wrong format of output: {result.stdout}")
            raise PackageManagerModuleException("Not found filename in output")

        return match.group("filename")

    def install_inf_driver_for_matching_devices(self, inf_path: Union[str, "Path"]) -> "ConnectionCompletedProcess":
        """
        Add and install driver using pnputil install for compatible devices.

        :param inf_path: Path to driver inf file to install.
        :return: Result of installation
        """
        command = f'pnputil /add-driver "{inf_path}" /install'
        result = self._connection.execute_command(
            command, shell=True, stderr_to_stdout=True, expected_return_codes={0, 259, 3010, 1641}
        )
        # expected_return_codes:
        # ERROR_SUCCESS (0): The requested operation completed successfully.
        # ERROR_NO_MORE_ITEMS (259): No devices match the supplied driver or the target device is already using a better
        # or newer driver than the driver specified for installation.
        # ERROR_SUCCESS_REBOOT_REQUIRED (3010): The requested operation completed successfully and a system reboot
        # is required. For example, if the /install /add-driver options were specified, one or more devices were
        # successfully installed and a system reboot is required to finalize installation.
        # ERROR_SUCCESS_REBOOT_INITIATED (1641): The operation was successful and a system reboot is underway because
        # the /reboot option was specified.
        if result.return_code == 259:
            if "Driver package is up-to-date on all applicable targets".casefold() not in result.stdout.casefold():
                raise ConnectionCalledProcessError(returncode=result.return_code, cmd=command, output=result.stdout)
        return result

    def unload_driver(self, pnp_device_id: str) -> str:
        """
        Remove device specified by device instance ID.

        :param pnp_device_id: PNP ID of device
        :return: Result of unloading
        """
        return self.devcon.remove_devices(device_id=f"{pnp_device_id}")

    def get_driver_version_by_inf_name(self, inf_name: str) -> str:
        """
        Get version of inf driver from system.

        :param inf_name: Name of inf file.
        :return: Version of loaded inf file.
        """
        command = (
            rf'Get-WindowsDriver -Online -All | ? {{$_.OriginalFileName -like "*{inf_name}"}} '
            "| select -ExpandProperty Version"
        )
        return self._connection.execute_powershell(command, stderr_to_stdout=True).stdout.strip()

    def get_driver_path_in_system_for_interface(self, interface_name: str) -> str:
        """
        Read system driver path for interface.

        :param interface_name: Name of interface.
        :return: Path to inf driver
        """
        command = f'Get-NetAdapter -name "{interface_name}" | select -ExpandProperty DriverName'
        driver_sys_path = self._connection.execute_powershell(command, stderr_to_stdout=True).stdout
        return driver_sys_path.replace(".sys", ".inf").replace(r"\SystemRoot", r"C:\Windows").rstrip()

    def install_certificates_from_driver(self, inf_path: Union["Path", str]) -> None:
        """
        Install certificates from driver.

        :param inf_path: Path to inf file of driver
        """
        path_to_cer = self._connection.path("C:\\exported_output.cer")
        inf_path: Path = self._connection.path(inf_path)
        if not inf_path.exists():
            raise PackageManagerModuleException(f"Cannot find .inf file: {inf_path} on remote machine")

        for ext in [".sys", ".cat"]:
            path_to_sys = inf_path.with_suffix(ext)
            if not path_to_sys.exists():
                raise PackageManagerModuleException(f"Cannot find {ext} file: {path_to_sys} on remote machine")

            command = (
                "$exportType = [System.Security.Cryptography.X509Certificates.X509ContentType]::Cert;"
                '$cert = (Get-AuthenticodeSignature "{path_to_sys}").SignerCertificate;'
                '[System.IO.File]::WriteAllBytes("{path_to_cer}", $cert.Export($exportType));'
                'Import-Certificate -FilePath "{path_to_cer}" '
                "-CertStoreLocation Cert:\\LocalMachine\\TrustedPublisher; "
                'Import-Certificate -FilePath "{path_to_cer}" '
                "-CertStoreLocation Cert:\\LocalMachine\\Root".format(path_to_sys=path_to_sys, path_to_cer=path_to_cer)
            )
            self._connection.execute_powershell(command=command, expected_return_codes={0})

    def get_driver_files(self) -> List[WindowsStoreDriver]:
        """
        Read driver from DriverStore.

        :return: List of StoreDriver structures
        """
        store_drivers_output = self._connection.execute_command("pnputil /enum-drivers", stderr_to_stdout=True).stdout
        regex = (
            r"Published Name:\s+(?P<published_name>.*)\n"
            r"Original Name:\s+(?P<original_name>.*)\n"
            r"Provider Name:\s+(?P<provider_name>.*)\n"
            r"Class Name:\s+(?P<class_name>.*)\n"
            r"Class GUID:\s+(?P<class_guid>.*)\n"
            r"Driver Version:\s+(?P<driver_version>.*)\n"
            r"Signer Name:\s+(?P<signer_name>.*)"
        )

        return [WindowsStoreDriver(**m.groupdict()) for m in re.finditer(regex, store_drivers_output)]

    def get_device_ids_to_install(self) -> List[DeviceID]:
        """
        Get list of interfaces to install build.

        :return: List of Device IDs to install.
        """
        device_ids = []
        hw_ids = self.devcon.get_hwids(pattern="*")
        for hw_id in hw_ids:
            match = self.PCI_DEVICE_PATTERN.search(hw_id.device_pnp)
            if not match:
                continue
            possible_device_id = DeviceID(match.group("device_id"))
            try:
                self._get_interface_driver(possible_device_id)  # check if device_id is supported (is in DB)
                logger.log(level=log_levels.MODULE_DEBUG, msg=f"Found device_id: {possible_device_id}")
            except PackageManagerNotFoundException:
                continue
            device_ids.append(possible_device_id)
        device_ids = list(set(device_ids))
        return device_ids

    def find_management_device_id(self) -> DeviceID:
        """
        Get device_id of management interface using connection IP address.

        :return: Device ID of management interface if found
        """
        management_ip_address = self._connection.ip
        interface_id = self._connection.execute_powershell(
            f"Get-WmiObject Win32_NetworkAdapterConfiguration | "
            f'Where-Object IPAddress -like "*{management_ip_address}*" | Select -expand "Index"'
        ).stdout.rstrip()  # get interface id of management interface
        pnpdevice_id = self._connection.execute_powershell(
            f'gwmi win32_networkadapter | Where-Object Index -eq {interface_id} | Select -expand "PNPDeviceID"'
        ).stdout.rstrip()  # get pnpdevice_id using interface id
        match = self.PCI_DEVICE_PATTERN.search(pnpdevice_id)
        if match:
            device_id = match.group("device_id")
            logger.log(level=log_levels.MODULE_DEBUG, msg=f"Found management device id: {device_id}.")
            return DeviceID(device_id)

    def install_build_for_device_id(
        self,
        build_path: Union[str, "Path"],
        device_id: "DeviceID",
        reboot_timeout: int = 120,
        cflags: Optional[Union[Dict, str]] = None,
        installation_method: InstallationMethod = InstallationMethod.PNP_UTIL,
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
        if installation_method is InstallationMethod.EXE:
            self._prosetdx_install(proset_flags=proset_flags, build_path=build_path)
        else:
            logger.log(
                level=log_levels.MODULE_DEBUG, msg=f"Looking for drivers in {build_path} for {device_id} device id."
            )
            drivers = self.find_drivers(build_path, device_id)
            drivers_to_install = self.get_matching_drivers(drivers, device_id)
            if not drivers_to_install:
                raise PackageManagerNotFoundException("Not found drivers in build")

            logger.log(
                level=log_levels.MODULE_DEBUG,
                msg=f"Looking for installed drivers in system for {device_id} device id.",
            )
            for driver in self.get_installed_drivers_for_device(device_id):
                logger.log(level=log_levels.MODULE_DEBUG, msg=f"Removing {driver} driver from system.")
                self.delete_driver_via_pnputil(driver)

            self.devcon.remove_devices(device_id=f"PCI\\VEN_8086&DEV_{device_id}*")

            driver_destination = self._connection.path(self.DRIVERS_REMOTE_LOCATION)
            if driver_destination.exists():
                self._rmtree(driver_destination)

            reboot_required = False
            for driver_to_install in drivers_to_install:
                target = driver_destination / driver_to_install.driver_path.parent.name
                target_driver_inf_path = str(target / driver_to_install.driver_path.name)
                target_driver_inf_path_name = (target / driver_to_install.driver_path.name).name
                copy(
                    src_conn=self._controller_connection,
                    dst_conn=self._connection,
                    source=driver_to_install.driver_path.parent / "*",
                    target=target,
                )
                logger.log(
                    level=log_levels.MODULE_DEBUG, msg=f"Installing certificates from driver {target_driver_inf_path}"
                )
                self.install_certificates_from_driver(target_driver_inf_path)

                self.devcon.rescan_devices()
                reboot_required = self._install_driver_and_check_reboot(
                    installation_method, target_driver_inf_path, device_id
                )

            self.devcon.rescan_devices()
            if reboot_required:
                logger.log(
                    level=log_levels.MODULE_DEBUG,
                    msg="Reboot after driver installation is required. Performing reboot.",
                )
                self._connection.restart_platform()
                self._connection.wait_for_host(timeout=reboot_timeout)

            for driver_to_install in drivers_to_install:
                installed_version = self.get_driver_version_by_inf_name(target_driver_inf_path_name)
                if installed_version != driver_to_install.driver_version:
                    raise PackageManagerModuleException(
                        f"Driver {target_driver_inf_path} is in different versions "
                        f"than expected {driver_to_install.driver_version}"
                    )
                logger.log(
                    level=log_levels.MODULE_DEBUG,
                    msg=f"Installed {target_driver_inf_path} driver in version {driver_to_install.driver_version}",
                )

            if self.check_device_status(device_id):
                raise PackageManagerModuleException(f"Device {device_id} has problem after driver installation")

    def _install_driver_and_check_reboot(
        self,
        installation_method: str,
        target_driver_inf_path: str,
        device_id: "DeviceID",
    ) -> bool:
        """
        Installs the driver based on the specified installation method and checks if a reboot is required.

        :param installation_method: The method to use for driver installation.
        :param target_driver_inf_path: The path to the driver INF file.
        :param device_id: The device ID for which the driver is being installed.
        :return: True if a system reboot is required, False otherwise.
        """
        reboot_required = False
        if installation_method == InstallationMethod.PNP_UTIL:
            return_code = self.install_inf_driver_for_matching_devices(target_driver_inf_path).return_code

            if return_code == 3010:
                reboot_required = True
        elif installation_method == InstallationMethod.INF_DEVCON:
            self.devcon.update_drivers(device_id=f"PCI\\VEN_8086&DEV_{device_id}", inf_file=target_driver_inf_path)

        return reboot_required

    def _prosetdx_install(self, proset_flags: bool, build_path: str, timeout: int = 60) -> bool:
        """
        Install PROSetDX for Windows.

        :param proset_flags: bool with PROSet flag
        :param build_path: path for driver
        :param timeout: timeout in seconds
        :return: Information about status of installation (dict)
        """
        logger.log(level=log_levels.MODULE_DEBUG, msg="Starting PROSETDX installation...")
        proset_path = self._controller_connection.path(build_path, r"APPS\PROSETDX\winx64\DxSetup.exe")
        if not proset_path.exists():
            raise PackageManagerNotFoundException(f"Cannot find {proset_path}")

        driver_destination = self._connection.path(self.DRIVERS_REMOTE_LOCATION)
        if driver_destination.exists():
            self._rmtree(driver_destination)

        driver_path = ntpath.join(build_path, r"APPS\PROSETDX\winx64")
        copy(
            src_conn=self._controller_connection,
            dst_conn=self._connection,
            source=driver_path,
            target=driver_destination,
        )

        install_path = self._connection.path(driver_destination, r"winx64\DxSetup.exe")
        if not install_path.exists():
            raise PackageManagerNotFoundException(f"Cannot find {install_path}")

        logger.log(level=log_levels.MODULE_DEBUG, msg=f"ProSetDX is {proset_path}")
        logger.log(
            level=log_levels.MODULE_DEBUG, msg=f"Starting DxSetup - {timeout} secs ( {timeout / 60} mins) timeout"
        )
        proset_flags = PROSET_DCB_FLAGS if proset_flags else ""
        setup_params = f"/qn /l*! {PROSETDX_INSTALL_LOG_PATH} {proset_flags}"
        installer_cmd = f"{install_path} {setup_params}"

        logger.log(level=log_levels.MODULE_DEBUG, msg=f"Installation command: {installer_cmd}")
        rc = self._connection.execute_with_timeout(
            command=installer_cmd,
            timeout=timeout,
        ).return_code
        if not rc:
            logger.log(level=log_levels.MODULE_DEBUG, msg="DxSetup exited with return code 0")
            if self._is_installed_win():
                logger.log(
                    level=log_levels.MODULE_DEBUG,
                    msg=f"DxSetup installed with return code {rc}.",
                )
        else:
            logger.log(level=log_levels.MODULE_DEBUG, msg=f"{installer_cmd} FAILED, rc {rc}")
            # Add debug information
            first_error = self._parse_log_debug_info(PROSETDX_INSTALL_LOG_PATH)
            logger.log(level=log_levels.MODULE_DEBUG, msg=first_error)
            return False

        # Process installation log
        verify_log = self._parse_log(PROSETDX_INSTALL_LOG_PATH, " completed successfully.")
        if not verify_log:
            logger.log(level=log_levels.MODULE_DEBUG, msg="Cannot find installation log file")
            return False
        else:
            logger.log(level=log_levels.MODULE_DEBUG, msg="No problems detected in installation log")
        return True

    def _is_installed_win(self) -> bool:
        """Check in the registry if build is available for uninstallation."""
        key_dict = self._win_registry.get_registry_path(uninstall_key, 2)
        for dict_val in list(key_dict.values()):
            if isinstance(dict_val, dict):
                try:
                    if "Intel(R)" in dict_val["DisplayName"]:
                        return True
                except KeyError:
                    continue
        return False

    def _get_sfile(self, file_path: str) -> str:
        """Get content of file from file_path. From client or sut. (BINARY).

        :param file_path: path to file
        :return contents from the file
        """
        if not self._connection.path(file_path).exists():
            raise PackageManagerModuleException(f"Path {file_path} does not exist.")

        stream = self._connection.path(file_path).read_text("utf-16", "ignore")
        return stream

    def _parse_log(self, filepath: str, message: str) -> bool:
        """Return true if no problems were detected in installation log.

        :param filepath: path to file
        """
        log_content = self._get_sfile(filepath)
        if not log_content:
            raise PackageManagerNotFoundException(f"Failed to open DxSetup log file: {filepath}")

        logger.log(level=log_levels.MODULE_DEBUG, msg=f"Verify installation log: {filepath}")

        if log_content.find(message) == -1:
            logger.log(level=log_levels.MODULE_DEBUG, msg=f"Statement: {message} not found in installation log")
            return False

        logger.log(level=log_levels.MODULE_DEBUG, msg=f"OK - statement: {message} found")
        return True

    def _parse_log_debug_info(self, filepath: str) -> str:
        """Add debug information with errors found in log file and return first encounter error.

        :param filepath: path to file
        :return error message
        """
        error_found = False
        first_error = ""

        log_content = self._get_sfile(filepath)
        if not log_content:
            raise PackageManagerNotFoundException("No installation log present.")

        for line in log_content.splitlines():
            if line.find("Error") >= 0:
                if not error_found:
                    first_error = line
                error_found = True

        if error_found:
            logger.log(level=log_levels.MODULE_DEBUG, msg="Some log error(s) found in installation log file.")
        else:
            logger.log(level=log_levels.MODULE_DEBUG, msg="No errors found in installation log file.")
        return first_error

    def _prepare_devcon(self) -> Devcon:
        """
        Copy and establish devcon object.

        :return: Devcon object
        """
        destination = self._connection.path("c:\\mfd_tools\\devcon\\")
        return Devcon(connection=self._connection, absolute_path_to_binary_dir=destination)

    def _get_folder_for_os_version(self, os_version: int) -> str:
        """
        Return correct Windows OS directory required for driver searching.

        :param os_version: Version of Windows kernel.
        :return: Directory correct for version.
        :raises PackageManagerConnectedOSNotSupported: When version is not supported.
        """
        for folder, version in self.FOLDER_OS_VERSION_MATCH.items():
            if os_version in version:
                return folder
        raise PackageManagerConnectedOSNotSupported(f"Windows in version {os_version} is not supported by module.")

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
        logger.log(level=log_levels.MODULE_DEBUG, msg=f"Going to use {driver_name} driver name.")

        driver_directory = self._get_driver_directory(driver_name)
        logger.log(level=log_levels.MODULE_DEBUG, msg=f"Going to use {driver_directory} driver directory.")

        kernel_version = int(self._connection.get_system_info().kernel_version)
        windows_version_folder = self._get_folder_for_os_version(kernel_version)
        logger.log(
            level=log_levels.MODULE_DEBUG, msg=f"Going to use {windows_version_folder} windows version directory."
        )

        search_string = str(build_path / driver_directory / "Winx64" / windows_version_folder / f"{driver_name}*.inf")

        logger.log(level=log_levels.MODULE_DEBUG, msg=f"Looking in {search_string} for drivers.")

        found_drivers = [
            self._controller_connection.path(driver)
            for driver in self._glob_glob_method(str(build_path), search_string=search_string)
        ]
        logger.log(
            level=log_levels.MODULE_DEBUG,
            msg=f"Found {found_drivers} drivers in build potentially for device_id: {device_id}",
        )
        return found_drivers

    def _is_matching_device(self, inf_content: str, device_id: "DeviceID") -> bool:
        """
        Check if driver is compatible with device_id.

        :param inf_content: Content of driver inf file.
        :param device_id: Device ID of interface.
        :return: Status of compatibility with driver.
        """
        return rf"PCI\VEN_8086&DEV_{device_id}" in inf_content

    def get_matching_drivers(self, list_of_drivers: List[Path], device_id: "DeviceID") -> List[DriverDetails]:
        """
        Get list of drivers compatible with device.

        :param list_of_drivers: List of drivers paths
        :param device_id: Device ID
        :return: List of driver details (path, version)
        """
        matching_drivers = []
        for driver in list_of_drivers:
            driver_file_content = driver.read_text(errors="ignore")
            version = self.read_version_of_inf_driver(driver_file_content)
            if self._is_matching_device(driver_file_content, device_id):
                matching_drivers.append(DriverDetails(driver, version, driver.with_suffix("").name))
        logger.log(
            level=log_levels.MODULE_DEBUG, msg=f"Found {matching_drivers} drivers in build for device_id: {device_id}"
        )
        return matching_drivers

    def read_version_of_inf_driver(self, driver_file_content: str) -> str:
        """
        Get version of driver.

        :param: driver_file_content: Driver file content
        :return: Driver version
        """
        match = re.search(r"DriverVer\s*=\s*.*,(?P<driver_version>.+)", driver_file_content)  # 06/06/2023,1.18.363.0
        version = "N/A"
        if match:
            version = match.group("driver_version").strip()
        return version

    def get_installed_drivers_for_device(self, device_id: "DeviceID") -> List[str]:
        """
        Get compatible drivers in system for device.

        :param device_id: Device ID
        :return: List of paths for drivers
        """
        matches = []
        for driver_node in self.devcon.get_drivernodes(pattern=f"PCI\\VEN_8086&DEV_{device_id}*"):
            for value in driver_node.driver_nodes.values():
                inf_file = value.get("inf_file")
                if inf_file:
                    match = re.search(r"(?P<driverfile>oem\d+.inf)", inf_file)
                    if match:
                        matches.append(match.group("driverfile"))
        found_drivers = list(set(matches)) if matches else []
        logger.log(level=log_levels.MODULE_DEBUG, msg=f"Found {found_drivers} in system for device_id: {device_id}")
        return found_drivers

    def check_device_status(self, device_id: "DeviceID") -> bool:  # todo mfd-devcon
        """
        Check if device has problem.

        :param device_id: Device id
        :return: True if found problem with device
        """
        command = f'{self.devcon._tool_exec} status "PCI\\VEN_8086&DEV_{device_id}*"'
        result = self.devcon._connection.execute_command(command, stderr_to_stdout=True, shell=True)
        return "The device has the following problem:".casefold() in result.stdout.casefold()

    def create_default_values_dict_from_inf_file(
        self,
        build_path: Union[str, "Path"],
        os_build: str,
        driver_name: str,
        device_id: "DeviceID",
        component_id: str,
        is_client_os: bool,
    ) -> Dict[str, str]:
        r"""
        Read in default values from the associated inf file to get the most accurate default values for all features.

        :param build_path: path to the inf file used for the installed driver
        :param os_build: name of the OS build to use (i.e. NDIS65, NDIS68, WS2022, W11 for example)
        :param driver_name: name of the driver (example: e1r, i40ea, i40eb)
        :param device_id: device ID to look for in the inf file
        :param component_id: component id for the device (in the form of PCI\VEN_XXXX&DEV_XXXX.....)
        :param is_client_os: whether the installed OS is a client or server OS
        :return: dictionary containing advanced features as the key with the default value as the value
        :raises PackageManagerModuleException: if unable to find a matching inf file name for the specified driver name
        """
        default_val_dict = {}
        filename = ""

        # get all possible inf files for the given device
        inf_files = self.find_drivers(build_path=build_path, device_id=DeviceID(device_id))
        file_names = [file.__str__() for file in inf_files]
        # get the correct inf file associated with the installed driver (example i40ea.inf for i40ea driver)
        for file in file_names:
            if driver_name in file:
                filename = file
                break
        # if filename is an empty string it means we didn't find a valid inf file, so raise exception
        if filename == "":
            raise PackageManagerModuleException(
                "Unable to find a valid inf file for driver {driver_name} in the list of inf files"
            )

        logger.log(level=log_levels.MODULE_DEBUG, msg=f"Found matching inf file {filename}")
        logger.log(level=log_levels.MFD_INFO, msg="Reading inf file")
        section_dictionary, inf_file_content = self._read_inf_file_and_create_base_dictionary(
            file=self._connection.path(filename)
        )
        logger.log(level=log_levels.MFD_INFO, msg="Updating section dictionary with content from inf file")
        section_dictionary = self._update_section_dictionary(
            section_dictionary=section_dictionary, file_content=inf_file_content
        )
        logger.log(level=log_levels.MFD_INFO, msg="Getting device section name to reference")
        device_section_name = self._get_inf_device_section_name(
            build=os_build, section_dictionary=section_dictionary, component_id=component_id, client_os=is_client_os
        )
        logger.log(level=log_levels.MFD_INFO, msg="Getting features and their associated default values")
        feature_val_tuple = self._get_default_vals_from_inf(
            device_section_name=device_section_name, section_dictionary=section_dictionary
        )
        logger.log(
            level=log_levels.MODULE_DEBUG, msg=f"List of features and their default values:\n{feature_val_tuple}"
        )

        # build the default feature value dictionary, using the feature names as the keys
        for tup in feature_val_tuple:
            default_val_dict[tup[0]] = tup[1]

        return default_val_dict

    def _get_inf_file_content(self, file: "Path") -> Tuple[Union[str, bytes], bool]:
        """
        Get the contents of the provided inf file.

        :param file: path of the inf file to parse
        :return: file content (in string or bytes), whether file was read as bytes
        """
        file_content = ""
        bytes_read = False
        try:
            try:
                # as not all connections support read_bytes, we will first try using read_text
                file_content = file.read_text()
            except UnicodeDecodeError:
                # in case read_text doesn't work we will use read_bytes
                file_content = file.read_bytes()
                bytes_read = True
        except FileNotFoundError:
            logger.log(level=logging.WARNING, msg=f"Could not find the specified file {file}")
        return file_content, bytes_read

    def _read_inf_file_and_create_base_dictionary(self, file: "Path") -> Tuple[Dict[str, List], List[str]]:
        """
        Read in the inf file and create the basic dictionary that will be filled in.

        :param file: path of the inf file to parse
        :return: dictionary containing a list of the inf section headers (all values are an empty list),
                 all lines in the inf file
        """
        all_lines = []
        section_dict = {}

        inf_file_output, bytes_read = self._get_inf_file_content(file)
        for line in inf_file_output.splitlines():
            # if we used read_bytes, we will need to decode the line to ascii
            if bytes_read:
                try:
                    line = line.decode("ascii")
                except UnicodeDecodeError:
                    # this is an expected error as some of the lines do not contain decodeable text
                    # all lines that do not have decodable text can be ignored so we can just move onto the next line
                    continue
            if "[" in line:
                # any line beginning with a [ character is a section header
                for char in ["[", "]"]:
                    # strip the [] characters around the string to get the section name
                    line = " ".join(line.split(char)).strip().lower()
                # create an entry in the dictionary for the section header with the value set to empty list
                section_dict[line] = []
            # add the line to a list of all the lines in the file (used to fill out the section_dict later)
            all_lines.append(line.strip())
        return section_dict, all_lines

    def _update_section_dictionary(
        self, section_dictionary: Dict[str, List[str]], file_content: List[str]
    ) -> Dict[str, List[str]]:
        """
        Fill in the section_dictionary with the lines from the inf file that fall under each section header.

        :param section_dictionary: dictionary with the section headers as keys
        :param file_content: all lines from the inf file
        :return: dictionary with the section headers as keys and all lines from the inf file under the section header
                 as the value for that key
        """
        for key in section_dictionary.keys():
            idx = 0
            lines_read = []
            for line in file_content:
                if key == line or line == "":
                    # since this is the section header or blank line, we can ignore it
                    idx += 1
                    continue
                elif any(section == line for section in section_dictionary.keys()):
                    # this is a different section header than the one we want so we can add all of the read lines to
                    # the current section
                    idx += 1
                    # update starting scope of the list so we don't start reading from the beginning again
                    file_content = file_content[idx:]
                    break
                # add the line to the list of lines read so it will be added to the dictionary for the current section
                lines_read.append(line)
                idx += 1
            # add all lines read to the given section name
            section_dictionary[key] = lines_read
        return section_dictionary

    def _get_inf_device_section_name(
        self, build: str, section_dictionary: Dict[str, List[str]], component_id: str, client_os: bool = False
    ) -> str:
        r"""
        Get the device section name as it appears in the inf section headers.

        :param build: name of the OS build to use (i.e. NDIS65, NDIS68, WS2022, W11 for example)
        :param section_dictionary: dictionary of section headers with all lines of the inf file for each section
        :param component_id: component id for the device (in the form of PCI\VEN_XXXX&DEV_XXXX.....)
        :param client_os: if the system OS is client or server version
        :return: name of the device section header
        """
        devices_to_search = ""
        special_build_set = False
        for key in section_dictionary.keys():
            # for certain builds (such as 18362) there is a special section header, so this will take higher precedence
            # over any other sections
            if build in key:
                devices_to_search = section_dictionary[key]
                special_build_set = True
                break
        if not special_build_set:
            devices_to_search = self._find_server_or_client_section_name(
                section_dictionary=section_dictionary, client_os=client_os
            )
        for dev_info in devices_to_search:
            if "=" not in dev_info:
                # all lines that we care about follow a standard format that contains an = character, so we can ignore
                # any other lines
                continue
            dev_info = dev_info.split(",")
            if component_id in dev_info[1].strip():
                return dev_info[0].split("=")[1].strip().lower()
        return ""

    def _find_server_or_client_section_name(
        self, section_dictionary: Dict[str, List[str]], client_os: bool
    ) -> List[str]:
        """
        Return all of the component ids from either the server or client OS section.

        :param section_dictionary: dictionary of section headers with all lines of the inf file for each section
        :param client_os: if the system OS is client or server version
        :return: server or client section name
        """
        device_section_name = []
        try:
            # there were no section headers found containing the build, so we can just use the usual Server/Client
            # sections
            device_section_name = (
                section_dictionary["intel.ntamd64.10.0.1"] if client_os else section_dictionary["intel.ntamd64.10.0"]
            )
        except KeyError:
            logger.log(
                level=logging.WARNING, msg="Unable to find matching header section, will default to Server header"
            )
            try:
                device_section_name = section_dictionary["intel.ntamd64.10.0"]
            except KeyError:
                logger.log(level=logging.WARNING, msg="Unable to find header section")
        return device_section_name

    def _get_default_vals_from_inf(
        self, device_section_name: str, section_dictionary: Dict[str, List[str]]
    ) -> List[Tuple[str, str]]:
        """
        Get all advanced feature names and the default value for each feature.

        :param device_section_name: name of the device section name to look under
        :param section_dictionary: dictionary containing the section names and all lines under each section
        :return: list of tuples containing the feature name and default value pairing
        """
        feature_val_tuple_list = []
        reg_sections = []
        try:
            for line in section_dictionary[device_section_name]:
                # get all of the .reg section names that we will need to parse through
                if "addreg" in line.lower():
                    section_names = line.split("=")[1]
                    reg_sections += section_names.split(",")

            for section in reg_sections:
                for line in section_dictionary[section.strip().lower()]:
                    # get the default feature value
                    if "default," in line.lower():
                        split_line = line.split(",")
                        # get the feature name
                        feature = split_line[1].strip().split("\\")[2]
                        # get the default value
                        default_val = split_line[4].strip().replace('"', "")
                        # append this pairing to the list
                        feature_val_tuple_list.append((str(feature), str(default_val)))
            return feature_val_tuple_list
        except KeyError:
            logger.log(level=logging.WARNING, msg="Unable to find the default feature values")
            return []
