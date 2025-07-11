# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Module for Package Manager."""

from .base import PackageManager
from .linux import LinuxPackageManager
from .windows import WindowsPackageManager
from .esxi import ESXiPackageManager
from .bsd import BSDPackageManager
