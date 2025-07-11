# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Linux Package Manager example."""
import logging

from mfd_connect import RPyCConnection
from mfd_typing import PCIAddress, DeviceID

from mfd_package_manager import LinuxPackageManager

logging.basicConfig(level=logging.DEBUG)  # for scripting purpose, do not use in amber

logger = logging.getLogger(__name__)

conn = RPyCConnection("10.10.10.10")
controller_conn = RPyCConnection("10.10.10.11")
package_manager = LinuxPackageManager(connection=conn)
# in case when drivers are stored on different machine
package_manager = LinuxPackageManager(connection=conn, controller_connection=controller_conn)
package_manager.bind_driver(PCIAddress(data="0000:12:03.1"), "i40e")
package_manager.unbind_driver(PCIAddress(data="0000:12:03.1"), "ice")
package_manager.add_module_to_blacklist("ice")
package_manager.remove_module_from_blacklist("ice")
package_manager.is_module_on_blacklist("ice")
package_manager.get_driver_info("ice")
package_manager.insert_module("/home/ice/ice.ko")
package_manager.load_module("/home/ice/ice.ko", params="-a")
logger.info(package_manager.list_modules())
package_manager.unload_module("ice")
package_manager.install_package_via_rpm("ice.rpm")
package_manager.install_package_via_yum("ice.rpm")
package_manager.update_initramfs_via_update()
package_manager.update_initramfs_via_dracut()
package_manager.uninstall_module("i40e")
package_manager.update_driver_dependencies()
package_manager.uninstall_package_via_rpm("qvdriver")
package_manager.build_rpm("/home/i40e/src", "i40e")
device_id = DeviceID(0x1572)

package_manager.install_build(r"C:\Users\admin\Downloads\drivers", device_id)
package_manager.install_build(r"C:\Users\admin\Downloads\drivers")  # will install on all devices

# with specific version
package_manager.pip_install_package(package="paramiko == 1.2.3", python_executable="/usr/bin/python310")
# just package name
package_manager.pip_install_package(package="paramiko", python_executable="/usr/bin/python310")
# with specific version
package_manager.pip_install_packages(
    package_list=["paramiko", "netmiko==1.23"], python_executable="/usr/bin/python310"
)
package_manager.is_package_installed_via_rpm(package="make", cwd="/home/user")
package_manager.is_package_installed_via_dpkg(package="docker")
package_manager.install_package_via_dnf("1.2.3", cwd="/home")
