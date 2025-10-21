# MFD-Const Package Changes Required

## Overview

This document describes the changes required to the external `mfd-const` package to support E835 controller device IDs in the `mfd-package-manager`.

## Package Information

- **Package**: `mfd-const`
- **Minimum Version**: 0.23.0
- **Module**: `mfd_const.network`
- **File**: `network.py`

## Changes Required

The following device IDs need to be added to the `DRIVER_DEVICE_ID_MAP["ice"]` set in `mfd_const/network.py`:

### Device IDs to Add

```python
# E835 Backplane Controllers
DeviceID(0x1248),  # E835-CC for backplane
DeviceID(0x1261),  # E835-C for backplane
DeviceID(0x1265),  # E835-L for backplane

# E835 QSFP Controllers
DeviceID(0x1249),  # E835-CC for QSFP
DeviceID(0x1262),  # E835-C for QSFP
DeviceID(0x1266),  # E835-L for QSFP

# E835 SFP Controllers
DeviceID(0x124A),  # E835-CC for SFP
DeviceID(0x1263),  # E835-C for SFP
DeviceID(0x1267),  # E835-L for SFP
```

## Location in File

These IDs should be added to the `ice` driver section of `DRIVER_DEVICE_ID_MAP`, which starts around line 880 in `network.py`. They should be inserted in numerical order after the existing `0x124x` entries.

### Before (lines 880-885):
```python
"ice": {
    DeviceID(0x124C),
    DeviceID(0x124D),
    DeviceID(0x124E),
    DeviceID(0x124F),
    DeviceID(0x12D0),
    ...
```

### After (lines 880-894):
```python
"ice": {
    DeviceID(0x1248),
    DeviceID(0x1249),
    DeviceID(0x124A),
    DeviceID(0x124C),
    DeviceID(0x124D),
    DeviceID(0x124E),
    DeviceID(0x124F),
    DeviceID(0x1261),
    DeviceID(0x1262),
    DeviceID(0x1263),
    DeviceID(0x1265),
    DeviceID(0x1266),
    DeviceID(0x1267),
    DeviceID(0x12D0),
    ...
```

## Testing

After making these changes to `mfd-const`, verify with:

```bash
python3 -c "from mfd_const.network import DRIVER_DEVICE_ID_MAP; from mfd_typing import DeviceID; \
ice_ids = DRIVER_DEVICE_ID_MAP['ice']; \
new_ids = [DeviceID(0x1248), DeviceID(0x1249), DeviceID(0x124A), \
           DeviceID(0x1261), DeviceID(0x1262), DeviceID(0x1263), \
           DeviceID(0x1265), DeviceID(0x1266), DeviceID(0x1267)]; \
print('All new IDs present:', all(id in ice_ids for id in new_ids))"
```

## Integration with mfd-package-manager

Once these changes are merged into `mfd-const` and released, update the dependency in `requirements.txt`:

```
mfd-const>=0.24.0  # or whichever version includes the E835 device IDs
```

## Validation Tests

The `mfd-package-manager` repository includes comprehensive tests for these device IDs:
- `tests/unit/test_mfd_package_manager/test_e835_device_ids.py`

These tests will validate that the device IDs are properly available and mapped to the ice driver.

## Related Issues

- E835 controller device ID support
- Ice driver device mapping extension
- Backplane, QSFP, and SFP controller support

## Upstream Repository

- Repository: https://github.com/intel/mfd-const (if public)
- Issue/PR: [To be created]

## Notes

For development and testing purposes, the changes can be applied directly to the installed package in:
```
/path/to/site-packages/mfd_const/network.py
```

However, for production use, these changes must be integrated into the official `mfd-const` package release.
