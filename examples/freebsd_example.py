# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
import logging

from mfd_connect import RPyCConnection

from mfd_package_manager import BSDPackageManager

logging.basicConfig(level=logging.DEBUG)  # for scripting purpose, do not use in amber

logger = logging.getLogger(__name__)

conn = RPyCConnection("10.10.10.10")
package_manager = BSDPackageManager(connection=conn)
package_manager.load_module("/boot/kernel/if_ixl.ko")
package_manager.unload_module("ixl")
package_manager.get_module_filename("ixl")
package_manager.get_driver_version("ixl")
