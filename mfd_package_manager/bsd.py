# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Module for FreeBSD."""

import logging
import re
import typing
import copy as cpy
from typing import Union, Dict, Set, Optional, List

from mfd_const.network import DRIVER_DEVICE_ID_MAP
from mfd_sysctl import Sysctl
from mfd_common_libs import os_supported
from mfd_typing import OSName
from mfd_package_manager.unix import UnixPackageManager
from mfd_connect import LocalConnection

if typing.TYPE_CHECKING:
    from mfd_connect.base import ConnectionCompletedProcess
    from pathlib import Path
    from mfd_connect import Connection
    from mfd_typing import DeviceID

logger = logging.getLogger(__name__)


class BSDPackageManager(UnixPackageManager):
    """Package manager for FreeBSD."""

    def _prepare_map(self) -> Dict[str, Set]:
        """Update mapping for BSD driver names."""
        driver_map = cpy.copy(DRIVER_DEVICE_ID_MAP)
        driver_map["ixl"] = driver_map["i40e"]
        driver_map["ix"] = driver_map["ixgbe"]
        driver_map["em"] = driver_map["e1000e"]
        driver_map["ixv"] = driver_map["ixgbevf"]
        del driver_map["i40e"]
        del driver_map["ixgbe"]
        del driver_map["e1000e"]
        del driver_map["ixv"]
        return driver_map

    @os_supported(OSName.FREEBSD)
    def __init__(self, *, connection: "Connection", controller_connection: "Connection" = LocalConnection()) -> None:
        """
        Initialize BSDPackageManager class.

        :param connection: Object of mfd-connect
        :param controller_connection: Object of mfd-connect to controller, default local connection
        """
        self.sysctl = Sysctl(connection=connection)
        super().__init__(connection=connection)
        self.DRIVER_DEVICE_ID_MAP = self._prepare_map()

    def is_module_loaded(self, module_name: str) -> bool:
        """
        Check if given kernel module is loaded.

        :param module_name: Module's name
        :return: True if module is loaded, False otherwise.
        """
        result = self._connection.execute_command(
            f"kldstat | grep {module_name}.ko", shell=True, expected_return_codes=None
        )
        return result.return_code == 0 and result.stdout != ""

    def load_module(
        self, module_path: Union[str, "Path"], params: Optional[dict[str, str]] = None
    ) -> "ConnectionCompletedProcess":
        """
        Load given kernel module (with the optional kernel environment variables).

        :param module_path: Path to module
        :param params: Kernel environment variables to set before loading the driver module (kenv).
                       They will be unset after loading the driver module.
        :return: Result of loading module
        """
        if params:
            for param, value in params.items():
                self.set_kenv(param, value)
        ret = self._connection.execute_command(f"kldload -v {module_path}", expected_return_codes={0}, shell=True)
        if params:
            for param in params.keys():
                self.unset_kenv(param)
        return ret

    def unload_module(self, module: str) -> "ConnectionCompletedProcess":
        """
        Unload module from system.

        :param module: Module's name
        :return: Result of unloading module
        """
        return self._connection.execute_command(f"kldunload -v {module}", expected_return_codes={0}, shell=True)

    def get_module_filename(self, module_name: str) -> Union[str, None]:
        """
        Get filename of the module loaded in the kernel.

        :param module_name: Module's name
        :return: Module filename or None if none found
        """
        result = self._connection.execute_command("kldstat -v", expected_return_codes={0}, shell=True)
        pattern = rf"\((?P<path>\S*?)\)(?:\n.*){{3}}pci/{module_name}$"
        match = re.search(pattern, result.stdout, flags=re.MULTILINE)
        return match.group("path") if match else None

    def get_driver_version(self, module_name: str) -> Union[str, int]:
        """
        Get module version.

        :param module_name: Module's name
        :return: Current driver version
        """
        oid_name = f"dev.{module_name}.0.iflib.driver_version"
        driver_version = self.sysctl.get_sysctl_value(oid_name)
        return driver_version

    def install_build(  # noqa D102
        self, build_path: Union[str, "Path"], device_id: Optional["DeviceID"] = None, reboot_timeout: int = 120
    ) -> None:
        raise NotImplementedError()

    def install_build_for_device_id(  # noqa D102
        self, build_path: Union[str, "Path"], device_id: "DeviceID", reboot_timeout: int = 120
    ) -> None:
        raise NotImplementedError()

    def get_device_ids_to_install(self) -> List["DeviceID"]:  # noqa D102
        raise NotImplementedError()

    def find_management_device_id(self) -> Optional["DeviceID"]:  # noqa D102
        raise NotImplementedError()

    def set_kenv(self, variable: str, value: str) -> None:
        """
        Set a kernel environment variable.

        :param variable: variable name
        :param value: value to set the variable to
        """
        command = f"kenv {variable}={value}"
        self._connection.execute_command(command, expected_return_codes={0})

    def unset_kenv(self, variable: str) -> None:
        """
        Unset a kernel environment variable.

        :param variable: variable name
        """
        command = f"kenv -u {variable}"
        self._connection.execute_command(command, expected_return_codes={0, 1})
