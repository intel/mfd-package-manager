# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Module for exceptions."""


class PackageManagerModuleException(Exception):
    """Handle module exceptions."""


class PackageManagerConnectedOSNotSupported(PackageManagerModuleException):
    """Handle unsupported OS."""


class PackageManagerNotFoundException(PackageManagerModuleException):
    """Handle not found exceptions."""
