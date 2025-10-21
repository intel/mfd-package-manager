# E835 Controller Device IDs

This document describes the E835 controller device IDs that have been added to the ice driver mapping in the mfd-const package.

## Overview

The E835 controllers come in three variants (CC, C, and L) and support three different connection types (Backplane, QSFP, and SFP), resulting in 9 unique device IDs.

## Device ID Mappings

All E835 device IDs are mapped to the **ice driver** in `DRIVER_DEVICE_ID_MAP`.

### Backplane Controllers

| Device ID | Variant | Description              |
|-----------|---------|--------------------------|
| 0x1248    | E835-CC | E835-CC for backplane    |
| 0x1261    | E835-C  | E835-C for backplane     |
| 0x1265    | E835-L  | E835-L for backplane     |

### QSFP Controllers

| Device ID | Variant | Description              |
|-----------|---------|--------------------------|
| 0x1249    | E835-CC | E835-CC for QSFP         |
| 0x1262    | E835-C  | E835-C for QSFP          |
| 0x1266    | E835-L  | E835-L for QSFP          |

### SFP Controllers

| Device ID | Variant | Description              |
|-----------|---------|--------------------------|
| 0x124A    | E835-CC | E835-CC for SFP          |
| 0x1263    | E835-C  | E835-C for SFP           |
| 0x1267    | E835-L  | E835-L for SFP           |

## Variants

- **E835-CC**: ColumbiaVille Cloud Controller
- **E835-C**: ColumbiaVille Controller  
- **E835-L**: ColumbiaVille Lite Controller

## Connection Types

- **Backplane**: Direct backplane connection
- **QSFP**: Quad Small Form-factor Pluggable transceiver
- **SFP**: Small Form-factor Pluggable transceiver

## Dependencies

These device IDs require **mfd-const >= 0.23.0** to be present in the `DRIVER_DEVICE_ID_MAP` for the ice driver.

## Testing

Comprehensive tests for these device IDs are available in:
```
tests/unit/test_mfd_package_manager/test_e835_device_ids.py
```

Run tests with:
```bash
pytest tests/unit/test_mfd_package_manager/test_e835_device_ids.py -v
```

## Usage Example

```python
from mfd_typing import DeviceID
from mfd_package_manager import PackageManager

# Create a device ID for E835-CC Backplane controller
device_id = DeviceID(0x1248)

# The PackageManager will automatically detect this as an ice driver device
package_manager = PackageManager(connection=your_connection)
driver = package_manager._get_interface_driver(device_id)
# driver will be "ice"
```

## Related Documentation

- [ice driver documentation](https://www.intel.com/content/www/us/en/download/19630/intel-network-adapter-driver-for-e810-series-devices-under-linux.html)
- [mfd-const package](https://github.com/intel/mfd-const)
