# CHANGELOG

<!-- version list -->

## Unreleased

### Features

- Add support for E835 controller device IDs (Backplane, QSFP, SFP)
  - Added 9 new device IDs for E835-CC, E835-C, and E835-L variants
  - Device IDs: 0x1248, 0x1249, 0x124A, 0x1261, 0x1262, 0x1263, 0x1265, 0x1266, 0x1267
  - All new IDs mapped to ice driver in mfd-const package
  - Comprehensive test suite added for E835 device IDs
  - Documentation added for E835 controllers

## v3.0.0 (2025-07-11)

### Features

- Initial commit
  ([`c29fa0d`](https://github.com/intel/mfd-package-manager/commit/c29fa0d7c37061360616c9eb1b82d50acb2ce0b9))

### Breaking Changes

- Removing DevCon binaries