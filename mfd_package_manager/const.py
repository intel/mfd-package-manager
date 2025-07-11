# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Module for const."""

import uuid

unique_id = uuid.uuid4()

PROSET_DCB_FLAGS = "BD=1 DMIX=1 iSCSI=1"
PROSETDX_INSTALL_LOG_PATH = f"C:\\prosetdx_install_log_{unique_id}.txt"
uninstall_key = r"HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall"
