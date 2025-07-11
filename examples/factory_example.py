# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
import logging

from mfd_package_manager import PackageManager
from mfd_connect import RPyCConnection

logging.basicConfig(level=logging.DEBUG)  # for scripting purpose, do not use in amber

logger = logging.getLogger(__name__)

conn = RPyCConnection("10.10.10.10")
package_manager = PackageManager(connection=conn)
logger.info(type(package_manager))
