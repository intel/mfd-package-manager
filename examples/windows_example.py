# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
import logging

from mfd_connect import RPyCConnection
from mfd_typing import DeviceID

from mfd_package_manager import WindowsPackageManager

logging.basicConfig(level=logging.DEBUG)  # for scripting purpose, do not use in amber

logger = logging.getLogger(__name__)

conn = RPyCConnection("10.10.10.10")
controller_connection = RPyCConnection("10.10.10.11")
package_manager = WindowsPackageManager(connection=conn)
# in case where driver are stored on different machine
package_manager = WindowsPackageManager(connection=conn, controller_connection=controller_connection)
package_manager.delete_driver_via_pnputil("oem3.inf")
package_manager.get_driver_filename_from_registry("i40ea68")
package_manager.install_inf_driver_for_matching_devices("c:\\driver\\i40ea.inf")
package_manager.unload_driver(
    "PCI\\VEN_8086&DEV_1563&SUBSYS_35D48086&REV_01\\0000C9FFFF00000000"
)  # network_interface.interface_info.pnp_device_id
package_manager.get_driver_version_by_inf_name("i40ea.inf")
package_manager.get_driver_path_in_system_for_interface("Ethernet 5")
package_manager.install_certificates_from_driver("C:\\driver\\i40ea.inf")
package_manager.get_driver_files()

device_id = DeviceID(0x1572)

package_manager.install_build(r"C:\Users\admin\Downloads\drivers", device_id)
package_manager.install_build(r"C:\Users\admin\Downloads\drivers")  # will install on all devices
