"""Airport database and navigation systems.

This module provides functionality for working with airport data from
the X-Plane Scenery Gateway, including spatial queries, runway information,
parking positions, taxiways, and frequencies.

Typical usage:
    from airborne.airports import AirportDatabase

    db = AirportDatabase()
    airport = db.get_airport("KPAO")  # Loads on-demand from Gateway
    parking = db.get_parking("KPAO")
"""

from airborne.airports.classifier import AirportCategory, AirportClassifier
from airborne.airports.database import (
    Airport,
    AirportDatabase,
    AirportType,
    Frequency,
    FrequencyType,
    ParkingPosition,
    Runway,
    SurfaceType,
)
from airborne.airports.spatial_index import SpatialIndex
from airborne.airports.taxiway import TaxiwayEdge, TaxiwayGraph, TaxiwayNode
from airborne.airports.taxiway_generator import TaxiwayGenerator

__all__ = [
    "Airport",
    "AirportCategory",
    "AirportClassifier",
    "AirportDatabase",
    "AirportType",
    "Frequency",
    "FrequencyType",
    "ParkingPosition",
    "Runway",
    "SpatialIndex",
    "SurfaceType",
    "TaxiwayEdge",
    "TaxiwayGenerator",
    "TaxiwayGraph",
    "TaxiwayNode",
]
