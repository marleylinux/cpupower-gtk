#!/usr/bin/env python3
"""Application entry point for cpupower-gtk"""
import sys
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

import init_gi  # noqa: F401, E402
from main import CpupowerApp

if __name__ == "__main__":
    app = CpupowerApp()
    sys.exit(app.run(sys.argv))
