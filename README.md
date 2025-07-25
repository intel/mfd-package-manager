> [!IMPORTANT] 
> This project is under development. All source code and features on the main branch are for the purpose of testing or evaluation and not production ready.

# MFD Package Manager

Module for managing packages, drivers, and modules across Linux, Windows, ESXi, and FreeBSD systems.

## Usage

`PackageManager` contains internal factory which will automatically create object bases OSName of connection.

```python
from mfd_package_manager import PackageManager
(...)

package_manager = PackageManager(connection=<mfd_connection_object>, controller_connection=<mfd_connection_object>)
# optional controller_connection if required
package_manager.is_module_loaded("i40e")

connection = <mfd_connection_object>
package_manager.make(targets="clean", cwd="/home/user/builds/Test_Build/96_31275/PROXGB/FREEBSD/ixv-1.5.33/src")
package_manager.make_clean(cwd=connection.path("/home/user/builds/Test_Build/96_31275/PROXGB/FREEBSD/ixv-1.5.33/src"))
```

### Class inheritance

```mermaid
graph TD;
    PackageManager --> ESXiPackageManager;
    PackageManager --> WindowsPackageManager;
    PackageManager --> UnixPackageManager;
    UnixPackageManager --> BSDPackageManager;
    UnixPackageManager --> LinuxPackageManager;
```
### Exceptions

`PackageManagerModuleException` - handle module exceptions.

`PackageManagerConnectedOSNotSupported` - handle unsupported OS.

`PackageManagerNotFoundException` - handle not found exceptions.

### Supported API

#### PackageManger:

Constructor:
* `PackageManger(connection: "Connection", controller_connection: "Connection" = LocalConnection()):` - initialize the package manager. controller_connection is optional, default local connection

* `install_build(self, build_path: Union[str, "Path"], device_id: Optional["DeviceID"] = None, reboot_timeout: int = 120, cflags: Optional[Union[Dict, str]] = None) -> None` - install build from path for all devices or for passed device
* `install_build_for_device_id(self, build_path: Union[str, "Path"], device_id: "DeviceID", reboot_timeout: int = 120, cflags: Optional[Union[Dict, str]] = None) -> None` - install build from path for passed device id
* `get_device_ids_to_install() -> List[DeviceID]` - get all devices in system suggested to install build
* `find_management_device_id() -> DeviceID` - get device id of management interface bases on IP address of connection
* `pip_install_packages(package_list: List[str],
        python_executable: Optional[str] = None,
        index_url: str = "https://pypi.org/simple",
        use_trusted_host: bool = False,
        force_install: bool = False,
        no_proxy: Optional[str] = None,
        use_connection_interpreter: bool = False,)` - install listed packages using pip, e.g. `[paramiko==2.5.2, netmiko]`
* `pip_install_package(package: str,
        python_executable: Optional[str] = None,
        index_url: str = "https://pypi.org/simple",
        use_trusted_host: bool = False,
        force_install: bool = False,
        no_proxy: Optional[str] = None,
        use_connection_interpreter: bool = False,)` - install package using pip, specific version is supported

#### UnixPackageManager:
* `is_module_loaded(module_name: str) -> bool` - checks if module is loaded in kernel.
* `make(targets: Optional[Union[List, str]] = None, jobs: Optional[Union[str, int]] = None, cflags: Optional[Union[Dict, str]] = None, cwd: Optional[Union[str, "Path"]] = None,)` - calls `make` command
* `make_install(jobs: Optional[Union[str, int]] = None, cflags: Optional[Union[Dict, str]] = None, cwd: Optional[Union[str, "Path"]] = None,)` - calls `make install` command
* `make_uninstall(jobs: Optional[Union[str, int]] = None, cflags: Optional[Union[Dict, str]] = None, cwd: Optional[Union[str, "Path"]] = None,)` - calls `make uninstall` command
* `make_clean(jobs: Optional[Union[str, int]] = None, cflags: Optional[Union[Dict, str]] = None, cwd: Optional[Union[str, "Path"]] = None,)` - calls `make clean` command
* `make_modules_uninstall(jobs: Optional[Union[str, int]] = None, cflags: Optional[Union[Dict, str]] = None, cwd: Optional[Union[str, "Path"]] = None,)` - calls `make module_uninstall` command

#### LinuxPackageManager:
* API from Unix Package Manager
* `install_build(self, build_path: Union[str, "Path"], device_id: "DeviceID", reboot_timeout: int = 120, cflags: Optional[Union[Dict, str]] = None) -> None` - install build from path for passed device id
* `bind_driver(self, pci_address: PCIAddress, driver_name: str) -> "ConnectionCompletedProcess"` - bind driver
* `unbind_driver(self, pci_address: PCIAddress, driver_name: str) -> "ConnectionCompletedProcess"` - unbind driver
* `add_module_to_blacklist(self, module_name: str) -> "ConnectionCompletedProcess"` - add module to modprobe blacklist.
* `remove_module_from_blacklist(self, module_name: str) -> "ConnectionCompletedProcess"` - remove module from modprobe blacklist.
* `is_module_on_blacklist(self, module_name: str) -> bool` - check if module is on blacklist.
* `get_driver_info(self, driver_name: str) -> "DriverInfo"` - get driver information (name, version)
* `insert_module(self, module_path: Union[str, "Path"], params: str) -> "ConnectionCompletedProcess"` - add kernel module.
* `load_module(self, module_name: str, params: str) -> "ConnectionCompletedProcess"` - load kernel module.
* `list_modules(self, module_name: Optional[str] = None) -> List[LsModOutput]` - get loaded modules.
* `unload_module(self, module_name: str, options: Optional[str] = None, *, with_dependencies: bool = False) -> "ConnectionCompletedProcess"` - unload module from system using rmmod or modprobe -r
* `install_package_via_rpm(self, package: str, cwd: Optional[Union["Path", str]] = None) -> "ConnectionCompletedProcess":` - install package using rpm
* `install_package_via_yum(self, package: str, cwd: Optional[Union["Path", str]] = None) -> "ConnectionCompletedProcess":` - install package using yum
* `remove_package_via_yum(self, package: str, cwd: Optional[Union["Path", str]] = None) -> "ConnectionCompletedProcess":` - remove package using yum
* `remove_package_via_dnf(self, package: str, cwd: Optional[Union["Path", str]] = None) -> "ConnectionCompletedProcess":` - remove package using dnf
* `update_initramfs_via_update(self) -> "ConnectionCompletedProcess":` update initramfs using update-initramfs
* `update_initramfs_via_dracut(self) -> "ConnectionCompletedProcess":` update initramfs using dracut
* `uninstall_module(self, module_name: str, kernel_version: Optional[str] = None) -> "ConnectionCompletedProcess"` - remove intel driver from kernel
* `update_driver_dependencies(self) -> None:` - update driver dependencies using depmod
* `uninstall_package_via_rpm(self, package_name: str) -> "ConnectionCompletedProcess":` - uninstall package using rpm tool.
* `build_rpm(self, module_path: Union["Path", str], module_filename: str) -> None:` - build RPM using RPM Package Manager.
* `find_drivers(self, build_path: Union[str, Path], device_id) -> List[Path]:` -> get paths for compatible drivers for device_id from build on controller.
* `remove_driver_from_initramfs(self, module_name: str) -> List[Path]:` -> unload module and refresh initramfs
* `read_driver_details(self, driver_tar_filename: str) -> Tuple[str, str]:` - get name and version of driver based on the name of tar.
* `get_drivers_details(self, list_of_drivers: List[Path]) -> List[DriverDetails]:` - get list of drivers details (path, version, name).
* `is_loaded_driver_inbox(self, driver_name: str) -> bool` - check if loaded driver is inbox.
* `recompile_and_load_driver(
        driver_name: str,
        build_path: Union[str, "Path"],
        jobs: Optional[Union[str, int]] = None,
        cflags: Optional[Union[Dict, str]] = None,
    ) -> "ConnectionCompletedProcess":` - recompile and reload the driver.
* `is_package_installed_via_rpm(self, package: str, cwd: "Path | str | None" = None) -> bool` - verify if package installed using rpm
* `is_package_installed_via_dpkg(self, package: str, cwd: "Path | str | None" = None) -> bool`- verify if package installed using dpkg
* `install_package_via_dnf(self, package: str, cwd: "Path | str | None" = None) -> "ConnectionCompletedProcess":` - install package using dnf

#### ESXiPackageManager:
* `get_driver_info(self, interface_name: str) -> DriverInfo` - Get driver info (name, version).
* `get_installed_vibs(self) -> List[VIBData]` - Get installed VIBs.
* `get_module_params(self, module_name: str) -> str` - Get module params.
* `get_module_params_as_dict(self, module_name: str) -> Dict[str, str]:` - Get module params as dictionary, e.g.: {"vmdq": "1,1,0,0"}.
* `install_vib(self, vib_path: Union["Path", str], params: Optional[str] = None) -> "ConnectionCompletedProcess"` - Install VIB.
* `uninstall_vib(self, vib_name: str) -> "ConnectionCompletedProcess"` - Uninstall VIB.
* `load_module(self, module_name: str, params: str = "") -> "ConnectionCompletedProcess"` - Load module with configuration parameters.
* `unload_module(self, module_name: str) -> "ConnectionCompletedProcess"` - Unload module from system.

#### WindowsPackageManager:
* `delete_driver_via_pnputil(self, inf_filename: str) -> "ConnectionCompletedProcess"` - delete driver using pnputil.
* `get_driver_filename_from_registry(self, driver_name: str) -> str:` - get driver filename from registry
* `install_inf_driver_for_matching_devices(self, inf_path: Union[str, "Path"]) -> "ConnectionCompletedProcess":` - add and install driver using pnputil install for compatible devices.
* `unload_driver(self, pnp_device_id: str) -> "ConnectionCompletedProcess":` - remove device specified by device instance ID.
* `get_driver_version_by_inf_name(self, inf_name: str) -> str:` - get version of inf driver from system.
* `get_driver_path_in_system_for_interface(self, interface_name: str) -> str:` - read system driver path for interface.
* `install_certificates_from_driver(self, inf_path: Union["Path", str]) -> None:` - install certificates from driver.
* `get_driver_files(self) -> List[WindowsStoreDriver]:` - read driver from DriverStore.
* `find_drivers(self, build_path: Union[str, Path], device_id) -> List[Path]:` -> get paths for compatible drivers for device_id from build on controller.
* `get_matching_drivers(self, list_of_drivers: List[Path], device_id: "DeviceID") -> List[DriverDetails]:` - get list of drivers compatible with device.
* `read_version_of_inf_driver(self, driver_file_content: str)` -> read version of driver bases on inf file.
* `get_installed_drivers_for_device(self, device_id: "DeviceID") -> List[str]:` - get list of drivers installed in system used by device.
* `check_device_status(self, device_id: "DeviceID") -> bool` - check if there is problem with device
* `create_default_values_dict_from_inf_file(self, build_path: Union[str, "Path"], os_build: str, driver_name: str, device_id: "DeviceID", component_id: str, is_client_os: bool) -> Dict[str, str]` get the default feature values from the inf file for a given device and store them in a dictionary
* `_get_inf_file_content(self, file: "Path") -> Tuple[Union[str, bytes], bool]` get the contents of the specified inf file
* `_read_inf_file_and_create_base_dictionary(self, file: "Path") -> Tuple[Dict[str, List], List[str]]` read the inf file and create the base dictionary for storing the section names and inf file lines for each section
* `_update_section_dictionary(self, section_dictionary: Dict[str, List[str], file_content: List[str]) -> Dict[str, List[str]]` fill in the section dictionary values with the lines from the inf file that fall under each section header key
* `_get_inf_device_section_name(self, build: str, section_dictionary: Dict[str, List[str]], component_id: str, client_os: bool) -> str` get the section name from the parsed section dictionary corresponding to the specified component id
* `_get_server_or_client_section(self, section_dictionary: Dict[str, List[str]], client_os: bool) -> List[str]` get all the component ids from the parsed section dictionary for either the server or client OS section
* `_get_default_vals_from_inf(self, device_section_name: str, section_dictionary: Dict[str, List[str]]) -> List[Tuple[str, str]]` get all advanced feature names and the default value for each feature   

#### BSDPackageManager:
* API from Unix Package Manager
* `load_module(self, module_path: Union[str, "Path"], params: Optional[dict[str, str]]) -> "ConnectionCompletedProcess"` - Load given kernel module.
* `unload_module(self, module: str) -> "ConnectionCompletedProcess"` - Unload module from system.
* `get_module_filename(self, module_name: str) -> Union[str, None]` - Get filename of the module loaded in the kernel.
* `get_driver_version(self, module_name: str) -> Union[str, int]` - Get module version.

### Data Structures

```python
@dataclass
class VIBData:
    """VIB data class."""

    name: Optional[str] = None
    version: Optional[str] = None
    vendor: Optional[str] = None
    acceptance_level: Optional[str] = None
    install_date: Optional[str] = None
```

```python
@dataclass
class LsModOutput:
    """Structure representing a lsmod entries."""

    module: str
    size: int
    used_by: str
```

```python
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
```

```python
@dataclass
class DriverDetails:
    """Details of driver in build."""

    driver_path: "Path"  # /home/user/build/PRO40GB/Winx64/NDIS68/i40ea48.inf
    driver_version: str  # 1.1.2.12
    driver_name: str  # i40ea48
```

## Windows build installation flow
```mermaid
graph TD;
    id1(find drivers in build) --> id2(check which are compatible with device) --> id3(delete installed drivers related with device if required) --> id4(remove device from system) --> id(for each driver) -->id5(copy driver directory to machine) --> id6(install certificates and rescan devices) --> id7(install driver);
    id8(reboot machine after installations if required) --> id9(compare required and installed driver versions) --> id10(check if device has reported problem);
    id7 --> id;
    id --> id8;
```

## Linux build installation flow
```mermaid
graph TD;
    id1(find drivers in build) --> id2(get driver details) --> id(for each driver) -->id5(copy driver directory to machine) --> id6(unpack) --> id7(unload old driver + extra drivers 'i40iw, irdma') --> id8(compile driver) --> id10(remove driver from initramfs and reload) --> id9(compare required and installed driver versions);
    id9 --> id;
```

## OS supported:
* LNX
* WINDOWS
* ESXi
* FreeBSD

## Controller supported OS:
* LNX
* WINDOWS
* FreeBSD

## Issue reporting

If you encounter any bugs or have suggestions for improvements, you're welcome to contribute directly or open an issue [here](https://github.com/intel/mfd-package-manager/issues).

