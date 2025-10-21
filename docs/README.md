# Documentation

This directory contains documentation for the mfd-package-manager project.

## E835 Controller Device IDs

Documentation related to the E835 controller device ID extension for the ice driver:

### [E835_DEVICE_IDS.md](E835_DEVICE_IDS.md)
Complete documentation of E835 device IDs, including:
- Overview of E835 controller variants (CC, C, L)
- Connection types (Backplane, QSFP, SFP)
- Device ID mappings table
- Usage examples
- Testing instructions

### [MFD_CONST_CHANGES.md](MFD_CONST_CHANGES.md)
Technical guide for integrating E835 device IDs into the upstream mfd-const package:
- Exact file locations and line numbers
- Before/after code snippets
- Verification commands
- Integration steps

### [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
Comprehensive summary of the E835 implementation:
- Changes implemented
- Files modified/created
- Test results
- Validation details
- Next steps for production deployment

## Quick Reference

### E835 Device IDs by Category

**Backplane Controllers:**
- 0x1248 (E835-CC)
- 0x1261 (E835-C)
- 0x1265 (E835-L)

**QSFP Controllers:**
- 0x1249 (E835-CC)
- 0x1262 (E835-C)
- 0x1266 (E835-L)

**SFP Controllers:**
- 0x124A (E835-CC)
- 0x1263 (E835-C)
- 0x1267 (E835-L)

All E835 device IDs are mapped to the **ice driver**.

## Testing

Run E835-specific tests:
```bash
pytest tests/unit/test_mfd_package_manager/test_e835_device_ids.py -v
```

## Dependencies

E835 support requires:
- mfd-const >= 0.24.0 (with E835 device IDs)
- mfd-typing >= 1.23.0
- mfd-package-manager >= 3.1.0

## Related Files

- Tests: `tests/unit/test_mfd_package_manager/test_e835_device_ids.py`
- Changelog: `CHANGELOG.md`
