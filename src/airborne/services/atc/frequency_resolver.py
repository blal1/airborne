"""Frequency resolver for ATC communications.

Resolves radio frequencies for airports by checking multiple sources:
1. X-Plane Gateway data (most accurate)
2. OurAirports CSV database
3. CTAF/Unicom fallback (122.8 MHz for uncontrolled airports)

Typical usage:
    from airborne.services.atc.frequency_resolver import FrequencyResolver

    resolver = FrequencyResolver(gateway_loader, airport_database)
    tower_freq = resolver.get_tower_frequency("KPAO")
    ground_freq = resolver.get_ground_frequency("KPAO")
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from airborne.airports.database import AirportDatabase
    from airborne.services.atc.gateway_loader import GatewayAirportLoader

logger = logging.getLogger(__name__)


class FrequencyType(Enum):
    """Radio frequency types for aviation."""

    ATIS = "atis"
    GROUND = "ground"
    TOWER = "tower"
    APPROACH = "approach"
    DEPARTURE = "departure"
    CLEARANCE = "clearance"
    UNICOM = "unicom"
    CTAF = "ctaf"
    FSS = "fss"
    CENTER = "center"


# Default frequencies for uncontrolled airports
DEFAULT_CTAF = 122.8  # Common CTAF/Unicom frequency
DEFAULT_UNICOM = 122.8
DEFAULT_MULTICOM = 122.9  # For airports without other frequencies


@dataclass
class ResolvedFrequency:
    """A resolved radio frequency.

    Attributes:
        type: Frequency type.
        frequency_mhz: Frequency in MHz.
        name: Descriptive name.
        source: Data source (gateway, csv, fallback).
        is_fallback: Whether this is a fallback frequency.
    """

    type: FrequencyType
    frequency_mhz: float
    name: str
    source: str
    is_fallback: bool = False


@dataclass
class AirportFrequencies:
    """Complete set of frequencies for an airport.

    Attributes:
        icao: Airport ICAO code.
        atis: ATIS frequency.
        ground: Ground control frequency.
        tower: Tower frequency.
        approach: Approach control frequency.
        departure: Departure control frequency.
        clearance: Clearance delivery frequency.
        ctaf: CTAF frequency (for uncontrolled airports).
        is_towered: Whether airport has tower control.
    """

    icao: str
    atis: ResolvedFrequency | None = None
    ground: ResolvedFrequency | None = None
    tower: ResolvedFrequency | None = None
    approach: ResolvedFrequency | None = None
    departure: ResolvedFrequency | None = None
    clearance: ResolvedFrequency | None = None
    ctaf: ResolvedFrequency | None = None
    is_towered: bool = False


class FrequencyResolver:
    """Resolve radio frequencies for airports.

    Combines data from multiple sources to provide the best available
    frequency information for any airport.

    Examples:
        >>> resolver = FrequencyResolver(gateway_loader, airport_db)
        >>> freqs = resolver.get_all_frequencies("KPAO")
        >>> print(f"Tower: {freqs.tower.frequency_mhz:.3f} MHz")
    """

    def __init__(
        self,
        gateway_loader: "GatewayAirportLoader | None" = None,
        airport_database: "AirportDatabase | None" = None,
    ) -> None:
        """Initialize frequency resolver.

        Args:
            gateway_loader: X-Plane Gateway data loader.
            airport_database: OurAirports CSV database.
        """
        self._gateway_loader = gateway_loader
        self._airport_database = airport_database
        self._cache: dict[str, AirportFrequencies] = {}

    def get_all_frequencies(self, icao: str) -> AirportFrequencies:
        """Get all frequencies for an airport.

        Args:
            icao: Airport ICAO code.

        Returns:
            AirportFrequencies with all available frequencies.

        Examples:
            >>> freqs = resolver.get_all_frequencies("KPAO")
            >>> if freqs.is_towered:
            ...     print(f"Tower: {freqs.tower.frequency_mhz}")
        """
        icao = icao.upper()

        # Check cache
        if icao in self._cache:
            return self._cache[icao]

        # Build frequency set
        freqs = AirportFrequencies(icao=icao)

        # Try Gateway data first (most accurate)
        gateway_freqs = self._get_gateway_frequencies(icao)
        if gateway_freqs:
            self._apply_frequencies(freqs, gateway_freqs, "gateway")

        # Fill gaps from CSV database
        csv_freqs = self._get_csv_frequencies(icao)
        if csv_freqs:
            self._apply_frequencies(freqs, csv_freqs, "csv", fill_gaps_only=True)

        # Apply fallbacks for uncontrolled airports
        self._apply_fallbacks(freqs)

        # Determine if towered
        freqs.is_towered = freqs.tower is not None and not freqs.tower.is_fallback

        # Cache result
        self._cache[icao] = freqs

        return freqs

    def get_tower_frequency(self, icao: str) -> float | None:
        """Get tower frequency for an airport.

        Args:
            icao: Airport ICAO code.

        Returns:
            Tower frequency in MHz, or None if uncontrolled.

        Examples:
            >>> freq = resolver.get_tower_frequency("KPAO")
            >>> if freq:
            ...     print(f"Contact tower on {freq:.3f}")
        """
        freqs = self.get_all_frequencies(icao)
        if freqs.tower and not freqs.tower.is_fallback:
            return freqs.tower.frequency_mhz
        return None

    def get_ground_frequency(self, icao: str) -> float | None:
        """Get ground control frequency for an airport.

        Args:
            icao: Airport ICAO code.

        Returns:
            Ground frequency in MHz, or None if no ground control.

        Examples:
            >>> freq = resolver.get_ground_frequency("KPAO")
            >>> if freq:
            ...     print(f"Contact ground on {freq:.3f}")
        """
        freqs = self.get_all_frequencies(icao)
        if freqs.ground and not freqs.ground.is_fallback:
            return freqs.ground.frequency_mhz
        return None

    def get_atis_frequency(self, icao: str) -> float | None:
        """Get ATIS frequency for an airport.

        Args:
            icao: Airport ICAO code.

        Returns:
            ATIS frequency in MHz, or None if no ATIS.

        Examples:
            >>> freq = resolver.get_atis_frequency("KPAO")
            >>> if freq:
            ...     print(f"Listen to ATIS on {freq:.3f}")
        """
        freqs = self.get_all_frequencies(icao)
        if freqs.atis:
            return freqs.atis.frequency_mhz
        return None

    def get_ctaf_frequency(self, icao: str) -> float:
        """Get CTAF frequency for an airport.

        For towered airports, returns tower frequency.
        For uncontrolled airports, returns CTAF (defaulting to 122.8).

        Args:
            icao: Airport ICAO code.

        Returns:
            CTAF frequency in MHz.

        Examples:
            >>> freq = resolver.get_ctaf_frequency("1O2")  # Uncontrolled
            >>> print(f"Announce on CTAF {freq:.3f}")
        """
        freqs = self.get_all_frequencies(icao)

        # For towered airports, CTAF is usually tower frequency
        if freqs.is_towered and freqs.tower:
            return freqs.tower.frequency_mhz

        # For uncontrolled, use CTAF or fallback
        if freqs.ctaf:
            return freqs.ctaf.frequency_mhz

        return DEFAULT_CTAF

    def get_approach_frequency(self, icao: str) -> float | None:
        """Get approach control frequency for an airport.

        Args:
            icao: Airport ICAO code.

        Returns:
            Approach frequency in MHz, or None if no approach control.
        """
        freqs = self.get_all_frequencies(icao)
        if freqs.approach:
            return freqs.approach.frequency_mhz
        return None

    def is_towered(self, icao: str) -> bool:
        """Check if airport is towered.

        Args:
            icao: Airport ICAO code.

        Returns:
            True if airport has active tower control.

        Examples:
            >>> if resolver.is_towered("KPAO"):
            ...     print("Contact tower for landing clearance")
            ... else:
            ...     print("Self-announce on CTAF")
        """
        freqs = self.get_all_frequencies(icao)
        return freqs.is_towered

    def _get_gateway_frequencies(self, icao: str) -> list[tuple[FrequencyType, float, str]] | None:
        """Get frequencies from X-Plane Gateway.

        Args:
            icao: Airport ICAO code.

        Returns:
            List of (type, frequency_mhz, name) tuples, or None.
        """
        if not self._gateway_loader:
            return None

        data = self._gateway_loader.get_airport(icao)
        if not data or not data.frequencies:
            return None

        result = []
        for freq in data.frequencies:
            freq_type = self._map_gateway_freq_type(freq.type)
            if freq_type:
                result.append((freq_type, freq.frequency_mhz, freq.name))

        return result if result else None

    def _get_csv_frequencies(self, icao: str) -> list[tuple[FrequencyType, float, str]] | None:
        """Get frequencies from CSV database.

        Args:
            icao: Airport ICAO code.

        Returns:
            List of (type, frequency_mhz, name) tuples, or None.
        """
        if not self._airport_database:
            return None

        csv_freqs = self._airport_database.get_frequencies(icao)
        if not csv_freqs:
            return None

        result = []
        for freq in csv_freqs:
            freq_type = self._map_csv_freq_type(freq.freq_type.name)
            if freq_type:
                result.append((freq_type, freq.frequency_mhz, freq.description))

        return result if result else None

    def _apply_frequencies(
        self,
        freqs: AirportFrequencies,
        freq_list: list[tuple[FrequencyType, float, str]],
        source: str,
        fill_gaps_only: bool = False,
    ) -> None:
        """Apply frequencies to AirportFrequencies object.

        Args:
            freqs: Target AirportFrequencies to update.
            freq_list: List of frequencies to apply.
            source: Source name (gateway, csv, fallback).
            fill_gaps_only: If True, only fill missing frequencies.
        """
        for freq_type, freq_mhz, name in freq_list:
            resolved = ResolvedFrequency(
                type=freq_type,
                frequency_mhz=freq_mhz,
                name=name,
                source=source,
                is_fallback=False,
            )

            # Map to attribute
            attr_name = freq_type.value
            current = getattr(freqs, attr_name, None)

            # Apply if not fill_gaps_only, or if current is None
            if not fill_gaps_only or current is None:
                setattr(freqs, attr_name, resolved)

    def _apply_fallbacks(self, freqs: AirportFrequencies) -> None:
        """Apply fallback frequencies for uncontrolled airports.

        Args:
            freqs: AirportFrequencies to update with fallbacks.
        """
        # If no tower, this is uncontrolled - set CTAF
        if freqs.tower is None:
            freqs.ctaf = ResolvedFrequency(
                type=FrequencyType.CTAF,
                frequency_mhz=DEFAULT_CTAF,
                name="CTAF",
                source="fallback",
                is_fallback=True,
            )

    @staticmethod
    def _map_gateway_freq_type(type_str: str) -> FrequencyType | None:
        """Map Gateway frequency type string to FrequencyType.

        Args:
            type_str: Gateway type string (ATIS, TOWER, etc.).

        Returns:
            FrequencyType or None if unknown.
        """
        mapping = {
            "ATIS": FrequencyType.ATIS,
            "GROUND": FrequencyType.GROUND,
            "TOWER": FrequencyType.TOWER,
            "APPROACH": FrequencyType.APPROACH,
            "DEPARTURE": FrequencyType.DEPARTURE,
            "CLEARANCE": FrequencyType.CLEARANCE,
            "UNICOM": FrequencyType.UNICOM,
        }
        return mapping.get(type_str.upper())

    @staticmethod
    def _map_csv_freq_type(type_str: str) -> FrequencyType | None:
        """Map CSV frequency type string to FrequencyType.

        Args:
            type_str: CSV type string (TWR, GND, etc.).

        Returns:
            FrequencyType or None if unknown.
        """
        mapping = {
            "ATIS": FrequencyType.ATIS,
            "GND": FrequencyType.GROUND,
            "TWR": FrequencyType.TOWER,
            "APPROACH": FrequencyType.APPROACH,
            "DEPARTURE": FrequencyType.DEPARTURE,
            "CLEARANCE": FrequencyType.CLEARANCE,
            "UNICOM": FrequencyType.UNICOM,
            "CTAF": FrequencyType.CTAF,
        }
        return mapping.get(type_str.upper())

    def clear_cache(self, icao: str | None = None) -> None:
        """Clear frequency cache.

        Args:
            icao: Specific airport to clear, or None to clear all.
        """
        if icao:
            self._cache.pop(icao.upper(), None)
        else:
            self._cache.clear()
