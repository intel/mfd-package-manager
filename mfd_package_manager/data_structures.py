# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Module for data structures."""

import typing
from dataclasses import dataclass
from typing import Optional
from enum import Enum

if typing.TYPE_CHECKING:
    from pathlib import Path


@dataclass
class VIBData:
    """VIB data class."""

    name: Optional[str] = None
    version: Optional[str] = None
    vendor: Optional[str] = None
    acceptance_level: Optional[str] = None
    install_date: Optional[str] = None


_cmd_to_vibdata_field = {
    "Name": "name",
    "Version": "version",
    "Vendor": "vendor",
    "Acceptance Level": "acceptance_level",
    "Install Date": "install_date",
}


@dataclass
class WindowsStoreDriver:
    """Driver info from Windows DriverStore."""

    published_name: str  # Published Name:     oem15.inf
    original_name: str  # Original Name:      i40ea68.inf
    provider_name: str  # Provider Name:      Intel
    class_name: str  # Class Name:         Network adapters
    class_guid: str  # Class GUID:         {4d36e972-e325-11ce-bfc1-08002be10318}
    driver_version: str  # Driver Version:     12/22/2022 1.16.202.10
    signer_name: str  # Signer Name:        Microsoft Windows Hardware Compatibility Publisher


@dataclass
class DriverDetails:
    """Details of driver in build."""

    driver_path: "Path"
    driver_version: str
    driver_name: str


class InstallationMethod(Enum):
    """Enum class for installation method."""

    EXE = "exe"
    INF_DEVCON = "inf_devcon"
    PNP_UTIL = "pnp_util"
