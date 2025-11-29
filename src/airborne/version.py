"""Version information for AirBorne.

This module provides version information read from the VERSION file
in the project root, with fallback for packaged distributions.
"""

from pathlib import Path

# Version info
__version__ = "0.1.0"  # Fallback version
__author__ = "Yannick Mauray"
__license__ = "MIT"
__copyright__ = "Copyright (c) 2024-2025 Yannick Mauray"


def get_version() -> str:
    """Get the current version string.

    Reads from VERSION file in project root or falls back to __version__.

    Returns:
        Version string (e.g., "0.1.0").
    """
    # Try to read from VERSION file (development mode)
    version_paths = [
        Path(__file__).parent.parent.parent.parent / "VERSION",  # src/airborne -> root
        Path(__file__).parent.parent.parent / "VERSION",  # For packaged apps
        Path("VERSION"),  # Current directory
    ]

    for version_path in version_paths:
        if version_path.exists():
            try:
                return version_path.read_text().strip()
            except Exception:
                pass

    return __version__


def get_about_info() -> dict[str, str]:
    """Get complete about information.

    Returns:
        Dictionary with version, author, license, and copyright.
    """
    return {
        "name": "AirBorne",
        "version": get_version(),
        "author": __author__,
        "license": __license__,
        "copyright": __copyright__,
        "description": "Blind-Accessible Flight Simulator",
    }
