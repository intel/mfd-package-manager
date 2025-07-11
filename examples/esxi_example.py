# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
import logging

from mfd_connect import RPyCConnection

from mfd_package_manager import ESXiPackageManager

logging.basicConfig(level=logging.DEBUG)  # for scripting purpose, do not use in amber

logger = logging.getLogger(__name__)

conn = RPyCConnection("10.10.10.10")
package_manager = ESXiPackageManager(connection=conn)

logger.info(package_manager.get_driver_info("interface_name"))

logger.info(package_manager.get_installed_vibs())
logger.info(package_manager.install_vib("vib_path"))
logger.info(package_manager.uninstall_vib("vib_name"))

logger.info(package_manager.get_module_params("module_name"))
logger.info(package_manager.load_module("module_name"))
logger.info(package_manager.load_module("module_name", "max_vfs=8 rx_queues=16"))
logger.info(package_manager.unload_module("module_name"))
