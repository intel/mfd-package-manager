# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Module for ESXi."""

import re
from typing import List, Tuple, Dict, Union, TYPE_CHECKING, Optional

from mfd_common_libs import os_supported
from mfd_typing import OSName
from mfd_typing.driver_info import DriverInfo

from mfd_package_manager.base import PackageManager
from mfd_package_manager.data_structures import VIBData, _cmd_to_vibdata_field

if TYPE_CHECKING:
    from mfd_connect.base import ConnectionCompletedProcess
    from pathlib import Path
    from mfd_typing import DeviceID


class ESXiPackageManager(PackageManager):
    """Package manager for ESXi."""

    DRIVERS_REMOTE_LOCATION = "/scratch/drivers_under_test/"

    __init__ = os_supported(OSName.ESXI)(PackageManager.__init__)

    def get_driver_info(self, interface_name: str) -> DriverInfo:
        """
        Get driver info (name, version).

        :param interface_name: Name of the interface to check
        :return: DriverInfo object from mfd-typing
        """
        name_pattern = r"^\s*Driver:\s+(?P<name>.*)$"
        version_pattern = r"^\s*Version:\s+(?P<version>.*)$"

        output = self._connection.execute_command(f"esxcli network nic get -n {interface_name}").stdout
        name_match = re.search(name_pattern, output, re.M)
        version_match = re.search(version_pattern, output, re.M)

        name = name_match.group("name") if name_match is not None else "N/A"
        version = version_match.group("version") if version_match is not None else "N/A"
        return DriverInfo(name, version)

    def get_installed_vibs(self) -> List[VIBData]:
        """
        Get installed VIBs.

        :return: List of VIBData objects
        """
        output = self._connection.execute_command("esxcli software vib list").stdout.strip()
        return self._parse_list_output(output)

    def get_module_params(self, module_name: str) -> str:
        """
        Get module params.

        :param module_name: Name of module
        :return: Command output with details
        """
        return self._connection.execute_command(f"esxcfg-module -g {module_name}").stdout.strip()

    def get_module_params_as_dict(self, module_name: str) -> Dict[str, str]:
        """
        Get module params as dictionary, e.g.: {"vmdq": "1,1,0,0"}.

        :param module_name: Name of module
        :return: Dictionary with driver param settings
        """
        current_params = self.get_module_params(module_name).split("'")[1]
        pattern = r"(?P<param>\S+)=(?P<values>(?:\d|,)+)"
        return {match.group("param"): match.group("values") for match in re.finditer(pattern, current_params)}

    def install_vib(self, vib_path: Union["Path", str], params: Optional[str] = None) -> "ConnectionCompletedProcess":
        """
        Install VIB.

        :param vib_path: VIB path
        :param params: Additional params passed to the command
        :return: Result of installation
        """
        command_list = ["esxcli software vib install"]
        if params is not None:
            command_list.append(params)
        command_list.append(self._define_vib_prefix(vib_path))
        command_list.append(vib_path)
        command = " ".join(command_list)
        return self._connection.execute_command(command)

    def _define_vib_prefix(self, vib_path: "Path | str") -> str:
        """
        Define VIB prefix.

        When path contains .vib, it should be -v, otherwise -d.

        :param vib_path: VIB path
        :return: Prefix for VIB
        """
        return "-v" if str(vib_path).endswith(".vib") else "-d"

    def uninstall_vib(self, vib_name: str) -> "ConnectionCompletedProcess":
        """
        Uninstall VIB.

        :param vib_name: VIB name
        :return: Result of uninstallation
        """
        return self._connection.execute_command(f"esxcli software vib remove -n {vib_name}")

    def load_module(self, module_name: str, params: str = "") -> "ConnectionCompletedProcess":
        """
        Load module with configuration parameters.

        :param module_name: Module's name
        :param params: Parameters to be set
        :return: Result of loading module
        """
        params = f' -s "{params}"' if params else " -s ''"
        result = self._connection.execute_command(f"esxcfg-module {module_name}{params}")
        self._connection.execute_command("pkill -HUP vmkdevmgr", shell=True)
        return result

    def unload_module(self, module_name: str) -> "ConnectionCompletedProcess":
        """
        Unload module from system.

        :param module_name: Module to unload
        :return: Result of unloading
        """
        return self._connection.execute_command(f"vmkload_mod -u {module_name}")

    @staticmethod
    def _parse_list_output(output: str) -> List[VIBData]:
        """
        Parse output.

        :param output: Output in list form
        :return: VIBData object
        """
        lines = output.splitlines()
        dash_line = lines[1]  # 2nd line is the one with dashes
        columns_width = [dashes.count("-") for dashes in dash_line.strip().split()]

        start = 0
        name_range: Dict[str, Tuple[int, int]] = {}
        for width in columns_width:
            end = start + width + 2  # 2 spaces after each column
            vibdata_field = _cmd_to_vibdata_field.get(lines[0][start:end].strip())
            if vibdata_field is None:
                start = end
                continue

            name_range[vibdata_field] = (start, end)
            start = end

        vibdata_list: List[VIBData] = []
        for line in lines[2:]:
            vibdata = VIBData()
            for field, (range_start, range_end) in name_range.items():
                setattr(vibdata, field, line[range_start:range_end].strip())
            vibdata_list.append(vibdata)

        return vibdata_list

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
