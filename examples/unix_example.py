# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
import logging

from mfd_connect import RPyCConnection

from mfd_package_manager import BSDPackageManager

logging.basicConfig(level=logging.DEBUG)  # for scripting purpose, do not use in amber

logger = logging.getLogger(__name__)

conn = RPyCConnection("10.10.10.10")
package_manager = BSDPackageManager(connection=conn)
logger.info(package_manager.is_module_loaded("ixv"))
logger.info(
    package_manager.make(
        targets="clean",
        cwd=conn.path("/home/user/builds/96_31275/PROXGB/FREEBSD/ixv-1.5.33/src"),
    )
)
