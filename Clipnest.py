"""Entry point used by PyInstaller and for running from source: python Clipnest.py"""

import sys

from clipnest.app import main

if __name__ == "__main__":
    sys.exit(main())
