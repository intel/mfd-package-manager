# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Module for unix."""

from abc import ABC, abstractmethod
from typing import Union, Dict, List, Optional
import typing

if typing.TYPE_CHECKING:
    from mfd_connect.base import ConnectionCompletedProcess
    from pathlib import Path

from mfd_package_manager.base import PackageManager


class UnixPackageManager(PackageManager, ABC):
    """Package manager for Unix."""

    DRIVERS_REMOTE_LOCATION = "/tmp/drivers_under_test/"

    @abstractmethod
    def is_module_loaded(self, module_name: str) -> bool:
        """
        Check if module is loaded.

        :param module_name: The name of the module to check.
        :return: Status of module.
        """

    def make(
        self,
        targets: Optional[Union[List, str]] = None,
        jobs: Optional[Union[str, int]] = None,
        cflags: Optional[Union[Dict, str]] = None,
        cwd: Optional[Union[str, "Path"]] = None,
    ) -> "ConnectionCompletedProcess":
        """
        Call make command.

        :param jobs: Amount of 'threads' to use, or system evaluation like '$(nproc)'
        :param cflags: Flags for compilation
        :param targets: Keywords for make, like 'all', 'install', 'clean'. Defined in MAKEFILE.
        :param cwd: Directory where make will be executed, otherwise RPC default.
        :return: Completed process
        """
        command = ["make"]
        if jobs is not None:
            command.append(f"-j{jobs}")
        if cflags is not None:
            if isinstance(cflags, dict):
                compilation_flags_list = []
                for k, v in cflags.items():
                    compilation_flags_list.append(f"{k}={v}")
                compilation_flags = " ".join(compilation_flags_list)
            else:
                compilation_flags = cflags
            command.append(compilation_flags)

        if targets is not None:
            command.append(" ".join(targets) if isinstance(targets, list) else targets)
        command = " ".join(command)
        return self._connection.execute_command(command, cwd=cwd)

    def make_install(
        self,
        jobs: Optional[Union[str, int]] = None,
        cflags: Optional[Union[Dict, str]] = None,
        cwd: Optional[Union[str, "Path"]] = None,
    ) -> "ConnectionCompletedProcess":
        """
        Call make install command.

        :param jobs: Amount of 'threads' to use, or system evaluation like '$(nproc)'
        :param cflags: Flags for compilation
        :param cwd: Directory where make will be executed, otherwise RPC default.
        :return: Completed process
        """
        return self.make(jobs=jobs, cflags=cflags, targets="install", cwd=cwd)

    def make_uninstall(
        self,
        jobs: Optional[Union[str, int]] = None,
        cflags: Optional[Union[Dict, str]] = None,
        cwd: Optional[Union[str, "Path"]] = None,
    ) -> "ConnectionCompletedProcess":
        """
        Call make uninstall command.

        :param jobs: Amount of 'threads' to use, or system evaluation like '$(nproc)'
        :param cflags: Flags for compilation
        :param cwd: Directory where make will be executed, otherwise RPC default.
        :return: Completed process
        """
        return self.make(jobs=jobs, cflags=cflags, targets="uninstall", cwd=cwd)

    def make_modules_uninstall(
        self,
        jobs: Optional[Union[str, int]] = None,
        cflags: Optional[Union[Dict, str]] = None,
        cwd: Optional[Union[str, "Path"]] = None,
    ) -> "ConnectionCompletedProcess":
        """
        Call make modules_uninstall command.

        :param jobs: Amount of 'threads' to use, or system evaluation like '$(nproc)'
        :param cflags: Flags for compilation
        :param cwd: Directory where make will be executed, otherwise RPC default.
        :return: Completed process
        """
        return self.make(jobs=jobs, cflags=cflags, targets="modules_uninstall", cwd=cwd)

    def make_clean(
        self,
        jobs: Optional[Union[str, int]] = None,
        cflags: Optional[Union[Dict, str]] = None,
        cwd: Optional[Union[str, "Path"]] = None,
    ) -> "ConnectionCompletedProcess":
        """
        Call make clean command.

        :param jobs: Amount of 'threads' to use, or system evaluation like '$(nproc)'
        :param cflags: Flags for compilation
        :param cwd: Directory where make will be executed, otherwise RPC default.
        :return: Completed process
        """
        return self.make(jobs=jobs, cflags=cflags, targets="clean", cwd=cwd)
