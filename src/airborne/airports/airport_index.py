"""Airport index for fast searching and autocomplete.

This module provides a searchable index of airports from the OurAirports
database, supporting search by ICAO code, IATA code, name, and city.

Typical usage:
    from airborne.airports.airport_index import AirportIndex

    index = AirportIndex()
    index.load()  # Load from CSV

    # Search by partial ICAO
    results = index.search("LFP")  # Returns LFPG, LFPO, LFPB, etc.

    # Search by city name
    results = index.search("Paris")  # Returns CDG, Orly, Le Bourget

    # Get specific airport
    airport = index.get("LFPG")
"""

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AirportInfo:
    """Basic airport information for menu display.

    Attributes:
        icao: ICAO code (e.g., "LFPG").
        iata: IATA code (e.g., "CDG"), may be empty.
        name: Airport name.
        city: City/municipality name.
        country: ISO country code (e.g., "FR").
        latitude: Latitude in degrees.
        longitude: Longitude in degrees.
        elevation_ft: Elevation in feet.
        airport_type: Type (large_airport, medium_airport, small_airport, etc.).
    """

    icao: str
    iata: str
    name: str
    city: str
    country: str
    latitude: float
    longitude: float
    elevation_ft: float
    airport_type: str

    def display_name(self) -> str:
        """Get display name for menu/autocomplete.

        Returns:
            Formatted string like "LFPG - Paris Charles de Gaulle (CDG)".
        """
        parts = [self.icao, "-", self.name]
        if self.iata:
            parts.append(f"({self.iata})")
        return " ".join(parts)

    def short_name(self) -> str:
        """Get short display name.

        Returns:
            Formatted string like "LFPG - Paris CDG".
        """
        if self.iata:
            return f"{self.icao} - {self.city} {self.iata}"
        return f"{self.icao} - {self.name}"


class AirportIndex:
    """Searchable airport index with autocomplete support.

    Loads airports from OurAirports CSV and provides fast search by:
    - ICAO code (prefix match)
    - IATA code (prefix match)
    - Airport name (substring match)
    - City name (substring match)

    The index prioritizes larger airports in search results.
    """

    # Airport type priority (lower = higher priority)
    TYPE_PRIORITY = {
        "large_airport": 0,
        "medium_airport": 1,
        "small_airport": 2,
        "seaplane_base": 3,
        "heliport": 4,
        "balloonport": 5,
        "closed": 6,
    }

    def __init__(self, data_dir: Path | str | None = None) -> None:
        """Initialize airport index.

        Args:
            data_dir: Directory containing airports.csv.
                     Defaults to data/airports.
        """
        if data_dir is None:
            # Default to data/airports relative to project root
            self._data_dir = Path(__file__).parent.parent.parent.parent / "data" / "airports"
        else:
            self._data_dir = Path(data_dir)

        self._airports: dict[str, AirportInfo] = {}  # ICAO -> AirportInfo
        self._iata_index: dict[str, str] = {}  # IATA -> ICAO
        self._loaded = False

    def load(self, csv_path: Path | str | None = None) -> bool:
        """Load airports from CSV file.

        Args:
            csv_path: Path to airports.csv. Defaults to data_dir/airports.csv.

        Returns:
            True if loaded successfully.
        """
        if csv_path is None:
            csv_path = self._data_dir / "airports.csv"
        else:
            csv_path = Path(csv_path)

        if not csv_path.exists():
            logger.error("Airport CSV not found: %s", csv_path)
            return False

        try:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # Skip airports without ICAO code
                    icao = row.get("icao_code", "").strip()
                    if not icao:
                        # Try ident as fallback for some airports
                        ident = row.get("ident", "").strip()
                        if ident and len(ident) == 4 and ident.isalnum():
                            icao = ident.upper()
                        else:
                            continue

                    icao = icao.upper()

                    # Parse elevation
                    try:
                        elevation = float(row.get("elevation_ft") or 0)
                    except (ValueError, TypeError):
                        elevation = 0

                    # Parse coordinates
                    try:
                        latitude = float(row.get("latitude_deg") or 0)
                        longitude = float(row.get("longitude_deg") or 0)
                    except (ValueError, TypeError):
                        latitude = 0
                        longitude = 0

                    airport = AirportInfo(
                        icao=icao,
                        iata=row.get("iata_code", "").strip(),
                        name=row.get("name", "").strip(),
                        city=row.get("municipality", "").strip(),
                        country=row.get("iso_country", "").strip(),
                        latitude=latitude,
                        longitude=longitude,
                        elevation_ft=elevation,
                        airport_type=row.get("type", "").strip(),
                    )

                    self._airports[icao] = airport

                    # Build IATA index
                    if airport.iata:
                        self._iata_index[airport.iata.upper()] = icao

            self._loaded = True
            logger.info("Loaded %d airports from %s", len(self._airports), csv_path)
            return True

        except Exception as e:
            logger.error("Failed to load airports: %s", e)
            return False

    def get(self, icao: str) -> AirportInfo | None:
        """Get airport by ICAO code.

        Args:
            icao: ICAO code (case-insensitive).

        Returns:
            AirportInfo if found, None otherwise.
        """
        return self._airports.get(icao.upper())

    def get_by_iata(self, iata: str) -> AirportInfo | None:
        """Get airport by IATA code.

        Args:
            iata: IATA code (case-insensitive).

        Returns:
            AirportInfo if found, None otherwise.
        """
        icao = self._iata_index.get(iata.upper())
        if icao:
            return self._airports.get(icao)
        return None

    def search(
        self,
        query: str,
        limit: int = 10,
        airport_types: list[str] | None = None,
    ) -> list[AirportInfo]:
        """Search airports by query string.

        Searches ICAO code, IATA code, name, and city.
        Results are sorted by relevance and airport size.

        Args:
            query: Search query (case-insensitive).
            limit: Maximum number of results to return.
            airport_types: Optional list of types to include.
                          Defaults to large and medium airports only.

        Returns:
            List of matching AirportInfo objects.
        """
        if not query:
            return []

        query_upper = query.upper()
        query_lower = query.lower()

        if airport_types is None:
            # Default to larger airports for better UX
            airport_types = ["large_airport", "medium_airport", "small_airport"]

        results: list[tuple[int, AirportInfo]] = []

        for airport in self._airports.values():
            # Filter by type
            if airport.airport_type not in airport_types:
                continue

            score = self._match_score(airport, query_upper, query_lower)
            if score > 0:
                results.append((score, airport))

        # Sort by score (higher is better), then by airport type priority
        results.sort(
            key=lambda x: (
                -x[0],  # Higher score first
                self.TYPE_PRIORITY.get(x[1].airport_type, 10),
            )
        )

        return [airport for _, airport in results[:limit]]

    def _match_score(
        self,
        airport: AirportInfo,
        query_upper: str,
        query_lower: str,
    ) -> int:
        """Calculate match score for an airport.

        Args:
            airport: Airport to score.
            query_upper: Uppercase query.
            query_lower: Lowercase query.

        Returns:
            Match score (0 = no match, higher = better match).
        """
        score = 0

        # ICAO exact match (highest priority)
        if airport.icao == query_upper:
            score += 1000

        # ICAO prefix match
        elif airport.icao.startswith(query_upper):
            score += 100 + (10 - len(query_upper))  # Longer prefix = better

        # IATA exact match
        if airport.iata and airport.iata.upper() == query_upper:
            score += 500

        # IATA prefix match
        elif airport.iata and airport.iata.upper().startswith(query_upper):
            score += 50

        # City exact match
        if airport.city and airport.city.lower() == query_lower:
            score += 200

        # City prefix match
        elif airport.city and airport.city.lower().startswith(query_lower):
            score += 80

        # City contains query
        elif airport.city and query_lower in airport.city.lower():
            score += 30

        # Name contains query
        if airport.name and query_lower in airport.name.lower():
            score += 20

        # Country match (for short codes like "FR", "US")
        if len(query_upper) == 2 and airport.country == query_upper:
            # Don't boost single countries too much
            score += 5

        return score

    def get_all_icao_codes(self) -> list[str]:
        """Get all ICAO codes.

        Returns:
            Sorted list of all ICAO codes.
        """
        return sorted(self._airports.keys())

    def get_airports_in_country(
        self,
        country_code: str,
        airport_types: list[str] | None = None,
    ) -> list[AirportInfo]:
        """Get all airports in a country.

        Args:
            country_code: ISO country code (e.g., "FR", "US").
            airport_types: Optional list of types to include.

        Returns:
            List of airports sorted by type priority.
        """
        country_upper = country_code.upper()

        if airport_types is None:
            airport_types = ["large_airport", "medium_airport", "small_airport"]

        results = [
            airport
            for airport in self._airports.values()
            if airport.country == country_upper and airport.airport_type in airport_types
        ]

        # Sort by type priority, then by name
        results.sort(
            key=lambda x: (
                self.TYPE_PRIORITY.get(x.airport_type, 10),
                x.name,
            )
        )

        return results

    @property
    def is_loaded(self) -> bool:
        """Check if index is loaded."""
        return self._loaded

    @property
    def airport_count(self) -> int:
        """Get number of loaded airports."""
        return len(self._airports)


# Global singleton instance
_global_index: AirportIndex | None = None


def get_airport_index() -> AirportIndex:
    """Get the global airport index singleton.

    Loads the index on first access.

    Returns:
        AirportIndex instance.
    """
    global _global_index
    if _global_index is None:
        _global_index = AirportIndex()
        _global_index.load()
    return _global_index
