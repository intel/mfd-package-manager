# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: MIT
"""Generate sphinx docs."""

import os
import shutil
import logging

from sphinx.ext import apidoc
from sphinx.cmd import build


apidoc.main(["-e", "-o", "mfd_package_manager", os.path.join("..", "mfd_package_manager")])

build.main(["-b", "html", ".", "build/html"])

logging.info("Cleaning folders from build process...")
shutil.rmtree("mfd_package_manager")
