"""Configure optional GDAL/PROJ locations without machine-specific paths."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def configure_geospatial_environment() -> None:
    prefix = Path(sys.prefix)
    for candidate in (prefix / "Library" / "share" / "proj", prefix / "share" / "proj"):
        if candidate.is_dir():
            # Prefer the active Python environment over unrelated system GIS
            # installations (for example a PostGIS PROJ database).
            os.environ["PROJ_LIB"] = str(candidate)
            os.environ["PROJ_DATA"] = str(candidate)
            break

    for candidate in (prefix / "Library" / "lib" / "gdalplugins", prefix / "lib" / "gdalplugins"):
        if candidate.is_dir():
            os.environ["GDAL_DRIVER_PATH"] = str(candidate)
            break
