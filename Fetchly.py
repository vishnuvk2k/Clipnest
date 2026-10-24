"""Entry point used by PyInstaller and for running from source: python Fetchly.py"""

import sys

from fetchly.app import main

if __name__ == "__main__":
    sys.exit(main())
