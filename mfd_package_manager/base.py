# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Module for package manager abstraction and factory."""

import logging
import re
import typing
from abc import ABC, abstractmethod

from mfd_common_libs import log_levels
from mfd_typing import OSName, DeviceID
from typing import Union, Optional, Dict, List
from mfd_connect import PythonConnection, LocalConnection
from mfd_package_manager.exceptions import (
    PackageManagerConnectedOSNotSupported,
    PackageManagerNotFoundException,
    PackageManagerModuleException,
)
from mfd_const.network import DRIVER_DIRECTORY_MAP, DRIVER_DEVICE_ID_MAP
from mfd_package_manager.data_structures import InstallationMethod

if typing.TYPE_CHECKING:
    from mfd_connect import Connection
    from pathlib import Path

logger = logging.getLogger(__name__)


class PackageManager(ABC):
    """Class for package manager abstraction and factory."""

    DRIVER_DIRECTORIES = set(DRIVER_DIRECTORY_MAP.values())
    TRUSTED_HOSTS = ["files.pythonhosted.org", "pypi.org", "pypi.python.org"]

    @property
    @abstractmethod
    def DRIVERS_REMOTE_LOCATION(self) -> str:
        """Path on remote machine for drivers."""

    def __new__(cls, connection: "Connection", controller_connection: "Connection" = LocalConnection()):
        """
        Choose PackageManager subclass based on provided connection object.

        :param connection: connection
        :return: instance of NetworkAdapterOwner subclass
        """
        if cls != PackageManager:
            return super().__new__(cls)
        supported_controllers = [OSName.WINDOWS, OSName.LINUX, OSName.FREEBSD]
        from .linux import LinuxPackageManager
        from .windows import WindowsPackageManager
        from .esxi import ESXiPackageManager
        from .bsd import BSDPackageManager

        os_name = connection.get_os_name()
        os_name_to_class = {
            OSName.WINDOWS: WindowsPackageManager,
            OSName.LINUX: LinuxPackageManager,
            OSName.ESXI: ESXiPackageManager,
            OSName.FREEBSD: BSDPackageManager,
        }

        if os_name not in os_name_to_class.keys():
            raise PackageManagerConnectedOSNotSupported(f"Not supported OS for PackageManager: {os_name}")

        controller_os_name = controller_connection.get_os_name()
        if controller_os_name not in supported_controllers:
            raise PackageManagerConnectedOSNotSupported(
                f"Not supported OS for controller PackageManager: {controller_os_name}"
            )

        owner_class = os_name_to_class.get(os_name)
        return super().__new__(owner_class)

    def __init__(self, *, connection: "Connection", controller_connection: "Connection" = LocalConnection()):
        """
        Initialize utility.

        :param connection: Object of mfd-connect
        :param controller_connection: Object of mfd-connect to controller, default local connection
        """
        self._connection = connection
        self._controller_connection = controller_connection
        self.DRIVER_DEVICE_ID_MAP = DRIVER_DEVICE_ID_MAP

    def _get_driver_directory(self, driver_name: str) -> str:
        """
        Return corresponding directory for driver name.

        :param driver_name: Name of driver.
        :return: Corresponding directory in build for driver.
        :raises PackageManagerNotFoundException: When not found driver directory.
        """
        driver_directory = DRIVER_DIRECTORY_MAP.get(driver_name)
        if driver_directory is None:
            raise PackageManagerNotFoundException(f"Not found driver directory for {driver_name} driver.")
        return driver_directory

    def _get_interface_driver(self, device_id: DeviceID) -> str:
        """
        Return corresponding driver name for passed device.

        :param device_id: Device ID of adapter.
        :return: Driver name.
        :raises PackageManagerNotFoundException: When not found driver for device ID.
        """
        for driver, dev_ids in self.DRIVER_DEVICE_ID_MAP.items():
            if device_id in dev_ids:
                return driver
        raise PackageManagerNotFoundException(f"Not found corresponding driver for {device_id} device ID.")

    def _rmtree(self, directory: Union[str, "Path"]) -> None:
        logger.log(level=log_levels.MODULE_DEBUG, msg=f"Removing {directory} directory from system")
        if isinstance(self._connection, PythonConnection):
            self._connection.modules().shutil.rmtree(directory)
        else:
            self._connection.path(directory).rmdir()

    def _glob_glob_method(self, path_to_search: str, search_string: str) -> List[str]:
        """
        Find path using search string.

        :param path_to_search: For linux/bsd root directory of search. Not used in windows.
        :param search_string: String with or without wildcards to find entries.
        :return: List of strings with paths.
        # todo https://github.com/intel/mfd-network-adapter/issues/1
        """
        if self._controller_connection.get_os_name() == OSName.WINDOWS:
            return self._controller_connection.execute_command(
                f'DIR /B /S "{search_string}"', shell=True
            ).stdout.splitlines()
        elif self._controller_connection.get_os_name() in [OSName.LINUX, OSName.FREEBSD]:
            return self._controller_connection.execute_command(
                f"find {path_to_search} -ipath '{search_string}'"
            ).stdout.splitlines()

    def install_build(
        self,
        build_path: Union[str, "Path"],
        device_id: Optional["DeviceID"] = None,
        reboot_timeout: int = 120,
        cflags: Optional[Union[Dict, str]] = None,
        management_device_id: Optional["DeviceID"] = None,
        installation_method: InstallationMethod = InstallationMethod.PNP_UTIL,
        proset_flags: bool = False,
    ) -> None:
        """
        Install driver for interface.

        :param build_path: Path to build
        :param device_id: Device ID of adapter, optional, if none build will be installed on supported devices
        :param reboot_timeout: Timeout for reboot of machine in case when reboot is required
        :param cflags: Flags for compilation, supported on Unix systems only
        :param management_device_id: Device ID of management interface if known, otherwise will be detected
        :param installation_method: Installation method to set
        :param proset_flags: flags to set
        """
        if not device_id:
            device_ids = self.get_device_ids_to_install()
            if not management_device_id:
                management_device_id = self.find_management_device_id()
            if management_device_id in device_ids:
                logger.log(
                    level=log_levels.MODULE_DEBUG,
                    msg="Removing management interface from the list of devices to install build.",
                )
                device_ids.remove(management_device_id)
        else:  # to have common call for passed or not device_id
            device_ids = [device_id]
        logger.log(level=log_levels.MODULE_DEBUG, msg=f"Installing build for devices: {device_ids}")
        for device_id in device_ids:
            self.install_build_for_device_id(
                build_path, device_id, reboot_timeout, cflags, installation_method, proset_flags
            )

    @abstractmethod
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
        :param cflags: Flags for compilation, supported on Unix systems only
        :param installation_method: Installation method to set
        :param proset_flags: flags to set
        """

    @abstractmethod
    def get_device_ids_to_install(self) -> List[DeviceID]:
        """
        Get list of interfaces to install build.

        :return: List of Device IDs to install.
        """

    @abstractmethod
    def find_management_device_id(self) -> Optional[DeviceID]:
        """
        Get device_id of management interface using connection IP address.

        :return: Device ID of management interface if found
        """

    def pip_install_packages(
        self,
        package_list: List[str],
        python_executable: Optional[str] = None,
        index_url: str = "https://pypi.org/simple",
        use_trusted_host: bool = False,
        force_install: bool = False,
        no_proxy: Optional[str] = None,
        use_connection_interpreter: bool = False,
    ) -> None:
        """
        Install python packages using pip.

        Package can be versioned with commandline format (without whitespaces between ==),
        e.g. ["paramiko==1.2.3", "netmiko"]

        :param python_executable: Path to python executable or name of python interpreter
                                    e.g. /tmp/python/bin/python310
                                         python310
        :param package_list: List of packages to install
        :param index_url: Index URL from which to install packages
        :param use_trusted_host: Enable use of host or host:port pair as trusted to install package from
        :param force_install: To enable force install packages even if installed
        :param no_proxy: List of proxies to bypass when installing packages
        :param use_connection_interpreter: Flag to use interpreter used for connection (RPyC, Local)
        :raises PackageManagerModuleException: on failure
        """
        for package in package_list:
            self.pip_install_package(
                force_install=force_install,
                index_url=index_url,
                no_proxy=no_proxy,
                package=package,
                python_executable=python_executable,
                use_trusted_host=use_trusted_host,
                use_connection_interpreter=use_connection_interpreter,
            )

    def pip_install_package(
        self,
        package: str,
        python_executable: Optional[str] = None,
        index_url: str = "https://pypi.org/simple",
        use_trusted_host: bool = False,
        force_install: bool = False,
        no_proxy: Optional[str] = None,
        use_connection_interpreter: bool = False,
    ) -> None:
        """
        Install python package using pip.

        Package can be versioned, e.g. "paramiko==1.2.3"

        :param python_executable: Path to python executable or name of python interpreter
                                    e.g. /tmp/python/bin/python310
                                         python310
        :param package: Package to install
        :param index_url: Index URL from which to install packages
        :param use_trusted_host: Enable use of host or host:port pair as trusted to install package from
        :param force_install: To enable force install packages even if installed
        :param no_proxy: List of proxies to bypass when installing packages
        :param use_connection_interpreter: Flag to use interpreter used for connection (RPyC, Local)
        :raises PackageManagerModuleException: on failure
        """
        is_python_connection = isinstance(self._connection, PythonConnection)
        self._verify_pip_parameters(is_python_connection, python_executable, use_connection_interpreter)
        cleared_package = package.replace(" ", "")
        # removed whitespace which pip commandline doesn't support

        package_name = cleared_package.split("==")[0]

        if use_connection_interpreter and is_python_connection:
            python_executable = self._connection.modules().sys.executable

        no_proxy_cmd = f"export no_proxy={no_proxy}" if no_proxy else "unset no_proxy"
        trusted_hosts_string = " --trusted-host ".join(self.TRUSTED_HOSTS)

        command_parts = list(
            filter(
                None,
                [
                    f"{no_proxy_cmd};",
                    f"{python_executable}",
                    "-m pip install",
                    f"--trusted-host {trusted_hosts_string}" if use_trusted_host else "",
                    "--force-reinstall" if force_install else "",
                    f"--index-url {index_url}",
                    cleared_package,
                    "--retries 3",
                ],
            )
        )

        cmd = " ".join(command_parts)

        try:
            result = self._connection.execute_command(cmd, shell=True, stderr_to_stdout=True)
        except Exception as ex:
            raise PackageManagerModuleException(f"Packages installation failed with error: {ex}")

        if f"requirement already satisfied: {package_name}" in result.stdout.casefold():
            logger.log(level=log_levels.MODULE_DEBUG, msg=f"'{package_name}' package is already installed")
        elif re.search(rf"Successfully installed.*\s({package_name})", result.stdout, re.IGNORECASE):
            logger.log(level=log_levels.MODULE_DEBUG, msg=f"'{package_name}' package installation success")
        else:
            raise PackageManagerModuleException(f"'{package_name}' package installation failed")

    def _verify_pip_parameters(
        self, is_python_connection: bool, python_executable: Optional[str], use_connection_interpreter: bool
    ) -> None:
        if python_executable is None and not is_python_connection:
            raise ValueError("Not passed required python executable")
        if use_connection_interpreter and not is_python_connection:
            logger.log(
                level=log_levels.MODULE_DEBUG,
                msg="Connection interpreter is not available for other connection than Python (RPyC and Local)",
            )
