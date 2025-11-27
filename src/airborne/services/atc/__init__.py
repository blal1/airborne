"""ATC services for AirBorne flight simulator.

Provides realistic Air Traffic Control simulation with dynamic ATIS,
flight phase awareness, and proper radio phraseology.
"""

from airborne.services.atc.atc_handler import (
    ATCHandler,
    ATCRequest,
    ATCRequestType,
    ATCResponse,
)
from airborne.services.atc.atis_generator import ATISAudioBuilder, DynamicATISGenerator
from airborne.services.atc.flight_phase import FlightPhase, FlightPhaseManager
from airborne.services.atc.phraseology import PhoneticConverter, PhraseBuilder

__all__ = [
    "ATCHandler",
    "ATCRequest",
    "ATCRequestType",
    "ATCResponse",
    "ATISAudioBuilder",
    "DynamicATISGenerator",
    "FlightPhase",
    "FlightPhaseManager",
    "PhoneticConverter",
    "PhraseBuilder",
]
