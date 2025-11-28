# Multi-Airport ATC Implementation Plan

This document outlines the implementation plan for making ATC work with all airports in the database, with support for realistic taxi routing and multi-language phraseology.

---

## Design Decisions Summary

| Decision | Choice |
|----------|--------|
| ATC Scope | Full ATC with realistic taxi routing |
| Taxiway Data Source | X-Plane apt.dat (GPL, Python parser available) |
| Frequency Fallback | Unicom/CTAF 122.8 MHz for uncontrolled airports |
| Runway Selection | Wind direction + aircraft type (length requirements) |
| Message System | Phrase chunks (natural flow, not word-by-word) |
| Localization | Language directories (`en/`, `fr/`), same filenames, language-aware phrase builder |

### Language-Specific Notes

- **French**: Uses "unité" for 1 (not "un"), "neuf" for 9 (no "niner")
- **French units**: QNH in hPa (not inHg), altitudes in meters for some contexts
- **French terminology**: "piste" (runway), "autorisé" (cleared), etc.

---

## Phase 1: Data Infrastructure

**Goal**: Load airport data dynamically from database and X-Plane apt.dat files.

### Task 1.1: X-Plane apt.dat Parser Integration

- Install `xplane_airports` package or implement minimal parser
- Parse apt.dat for:
  - Airport metadata (name, elevation, transition altitude)
  - Runway data (dimensions, headings, surface type)
  - Taxiway nodes and edges (for routing)
  - Parking positions (gates, ramps)
  - Frequencies (tower, ground, ATIS, approach)
- Create `AptDatLoader` class in `src/airborne/services/atc/apt_dat_loader.py`

### Task 1.2: Airport Data Model Enhancement

- Extend `Airport` dataclass with:
  - `taxiway_graph: TaxiwayGraph` - Node/edge graph for taxi routing
  - `parking_positions: list[ParkingPosition]` - Gates and ramps
  - `transition_altitude: int` - For flight level calculations
- Create `TaxiwayGraph` class:
  - `nodes: dict[str, TaxiwayNode]` - Named nodes with lat/lon
  - `edges: list[TaxiwayEdge]` - Connections with names and widths
  - `find_route(from_node, to_node) -> list[TaxiwaySegment]` - A* pathfinding

### Task 1.3: Frequency Fallback System

- Create `FrequencyResolver` class:
  - Look up frequencies from apt.dat first
  - Fall back to database frequencies
  - Default to 122.8 MHz (CTAF/Unicom) if none found
- Determine airport type (towered vs uncontrolled) from frequency availability

### Task 1.4: Runway Selection Logic

- Create `RunwaySelector` class:
  - Input: wind direction/speed, aircraft type, available runways
  - Calculate headwind component for each runway
  - Filter by minimum runway length for aircraft type
  - Select runway with best headwind component
- Aircraft type categories:
  - Light GA: 2000ft minimum
  - Heavy GA: 3000ft minimum
  - Turboprop: 4000ft minimum
  - Jet: 5000ft+ minimum

---

## Phase 2: Phrase Chunk System

**Goal**: Replace word-by-word audio with natural phrase chunks.

### Task 2.1: Phrase Chunk Architecture

- Create `PhraseChunk` dataclass:
  ```python
  @dataclass
  class PhraseChunk:
      id: str              # e.g., "cleared_to_land"
      text: str            # Display text: "cleared to land"
      audio_file: str      # Filename: "cleared_to_land.ogg"
      language: str        # "en", "fr"
  ```
- Create `PhraseLibrary` class:
  - Load chunks from YAML config per language
  - Validate all audio files exist
  - Provide lookup by chunk ID

### Task 2.2: Language-Aware Phrase Builder

- Refactor `PhraseBuilder` to support:
  - Language parameter (default: "en")
  - Chunk-based phrase construction
  - Language-specific number pronunciation
  - Unit conversions per language
- Phrase template system:
  ```yaml
  # config/phrases_en.yaml
  taxi_clearance:
    pattern: ["{callsign}", "taxi_to", "runway", "{runway}", "via", "{taxiways}"]

  # config/phrases_fr.yaml
  taxi_clearance:
    pattern: ["{callsign}", "roulez_vers", "piste", "{runway}", "via", "{taxiways}"]
  ```

### Task 2.3: Number Pronunciation per Language

- Create `NumberPronouncer` class with language support:
  ```python
  # English
  NUMBERS_EN = {"0": "zero", "1": "one", ..., "9": "niner"}

  # French
  NUMBERS_FR = {"0": "zéro", "1": "unité", ..., "9": "neuf"}
  ```
- Handle special cases:
  - Frequencies: digit-by-digit with "decimal"/"point"
  - Altitudes: thousands/hundreds grouping
  - Headings: always 3 digits
  - Runways: 2 digits + optional L/R/C

### Task 2.4: Audio Chunk Generation Script

- Update `generate_speech.py` to generate phrase chunks:
  - Read chunk definitions from YAML
  - Generate audio for each chunk per language
  - Validate completeness (all chunks have audio)
- Chunk categories:
  - Static phrases: "cleared to land", "hold short", "taxi to"
  - Connectors: "via", "and", "then"
  - Units: "thousand", "hundred", "feet", "knots"
  - Phonetic alphabet: full set per language
  - Numbers: 0-9 per language

---

## Phase 3: Dynamic ATC Handler

**Goal**: Remove KPAO hardcoding, make ATC work with any airport.

### Task 3.1: Refactor ATCHandler Initialization

- Remove hardcoded KPAO references:
  - `airport_icao="KPAO"` default
  - `airport_name="Palo Alto Airport"` default
  - Hardcoded runway "31"
  - Hardcoded FREQUENCIES dict
- Accept airport from:
  - `--from-airport` CLI argument
  - Scenario configuration
  - Flight plan departure airport

### Task 3.2: Dynamic ATIS Generation

- Refactor `DynamicATISGenerator`:
  - Load airport data dynamically
  - Use `RunwaySelector` for active runway
  - Use `FrequencyResolver` for frequencies
  - Generate ATIS with actual airport name/info
- Remove hardcoded runway database dict

### Task 3.3: Dynamic Taxi Instructions

- Refactor taxi clearance generation:
  - Use `TaxiwayGraph.find_route()` for taxi routing
  - Generate progressive taxi instructions
  - Support "hold short" at runway crossings
- Taxi instruction format:
  - Full route: "Taxi to runway 31 via Alpha, Bravo, Charlie"
  - Progressive: "Taxi via Alpha", then "Continue via Bravo", etc.

### Task 3.4: Frequency Management

- Refactor radio frequency handling:
  - Load frequencies from `FrequencyResolver`
  - Support frequency handoffs (ground → tower)
  - Handle uncontrolled airports (CTAF only)
- Update `RadioPlugin` to use dynamic frequencies

---

## Phase 4: Taxiway Routing

**Goal**: Implement A* pathfinding for realistic taxi routes.

### Task 4.1: Taxiway Graph Construction

- Build graph from apt.dat data:
  - Nodes: taxiway intersections, runway hold points, parking positions
  - Edges: taxiway segments with names, widths, one-way flags
- Handle special nodes:
  - Runway hold short lines
  - Hotspots (complex intersections)
  - ILS critical areas

### Task 4.2: A* Pathfinding Implementation

- Implement `TaxiwayGraph.find_route()`:
  - A* algorithm with distance heuristic
  - Prefer wider taxiways for larger aircraft
  - Avoid runway crossings when possible
  - Respect one-way taxiways
- Return `list[TaxiwaySegment]` with names for instructions

### Task 4.3: Taxi Route Verbalization

- Convert route to audio instructions:
  - Group consecutive segments on same taxiway
  - Insert "hold short runway XX" at crossings
  - Handle unnamed taxiways ("continue straight")
- Example output:
  - Route: [A1, A2, A3, B1, B2, RWY_CROSS, C1]
  - Audio: "Taxi via Alpha, Bravo, hold short runway 27, then Charlie"

### Task 4.4: Progressive Taxi System

- Implement segment-by-segment instructions:
  - Initial: first 2-3 segments
  - Progressive: next segment when approaching
  - Position awareness via aircraft location
- Trigger next instruction based on:
  - Distance to next waypoint
  - Time since last instruction

---

## Phase 5: Multi-Language Support

**Goal**: Full French language support with proper phraseology.

### Task 5.1: French Phrase Library

- Create `config/phrases_fr.yaml`:
  - All phrase chunks in French
  - French aviation terminology
  - Proper French sentence structure
- Key translations:
  - "runway" → "piste"
  - "cleared to land" → "autorisé atterrissage"
  - "taxi to" → "roulez vers"
  - "hold short" → "maintenez avant"
  - "contact tower" → "contactez tour"

### Task 5.2: French Number Pronunciation

- Implement French number rules:
  - 1 = "unité" (aviation specific)
  - 9 = "neuf" (no "niner" in French)
  - Normal French numbers otherwise
- Handle French frequency format:
  - "cent vingt et un point cinq" (121.5)

### Task 5.3: French Unit Conversions

- QNH in hectopascals (hPa):
  - Convert from inHg: `hPa = inHg * 33.8639`
  - Round to nearest whole number
  - "QNH mille treize" (1013 hPa)
- Visibility in meters/kilometers when appropriate

### Task 5.4: French Audio Generation

- Generate French audio files:
  - Same filenames as English
  - Placed in `data/speech/fr/` directory
  - Use French TTS voice (e.g., "Thomas" on macOS)
- Validate completeness against English set

### Task 5.5: Language Selection System

- Add language configuration:
  - Global setting in config
  - Per-airport override (e.g., French airports use French)
  - Manual override option
- Automatic selection based on:
  - Airport country code
  - User preference
  - Aircraft registration country

---

## Phase 6: Integration and Testing

**Goal**: Ensure all components work together reliably.

### Task 6.1: Integration Tests

- Test complete ATC flow for multiple airports:
  - KPAO (original, towered, US)
  - KSFO (large, multiple runways, US)
  - LFLY (French, towered)
  - Small uncontrolled airport (CTAF only)
- Verify:
  - Correct frequencies loaded
  - Proper runway selection
  - Valid taxi routes generated
  - Audio plays correctly

### Task 6.2: Edge Case Handling

- Handle missing data gracefully:
  - Airport not in apt.dat
  - No taxiway data available
  - Missing audio files
- Fallback behaviors:
  - Generic taxi instructions if no graph
  - Skip ATC if no frequencies
  - English fallback if language missing

### Task 6.3: Performance Optimization

- Cache loaded airport data
- Precompute common taxi routes
- Lazy load taxiway graphs (on demand)
- Profile audio loading performance

### Task 6.4: Documentation

- Document ATC system architecture
- API documentation for phrase builder
- Guide for adding new languages
- Troubleshooting common issues

---

## File Structure

```
src/airborne/
├── services/
│   └── atc/
│       ├── apt_dat_loader.py      # X-Plane apt.dat parser
│       ├── taxiway_graph.py       # Graph + A* pathfinding
│       ├── frequency_resolver.py  # Frequency lookup with fallbacks
│       ├── runway_selector.py     # Wind-based runway selection
│       ├── phrase_library.py      # Chunk-based phrase system
│       ├── number_pronouncer.py   # Language-aware numbers
│       ├── atis_generator.py      # (refactored) Dynamic ATIS
│       ├── atc_handler.py         # (refactored) Dynamic ATC
│       └── phraseology.py         # (refactored) Language-aware
│
config/
├── phrases_en.yaml                # English phrase chunks
├── phrases_fr.yaml                # French phrase chunks
├── speech.yaml                    # (updated) Multi-language config
│
data/
├── apt.dat                        # X-Plane airport data (downloaded)
└── speech/
    ├── en/                        # English audio
    │   ├── atc/
    │   ├── cockpit/
    │   └── pilot/
    └── fr/                        # French audio
        ├── atc/
        ├── cockpit/
        └── pilot/
```

---

## Dependencies

### New Python Packages

```toml
# pyproject.toml additions
[project.dependencies]
xplane-airports = "^1.0"  # Or implement minimal parser
```

### Data Files

- **X-Plane apt.dat**: Download from data.x-plane.com (GPL)
- **French TTS voice**: macOS "Thomas" or similar

---

## Success Criteria

### Phase 1 Complete When:
- [x] apt.dat parser loads airport data (GatewayAirportLoader via X-Plane Gateway API)
- [x] TaxiwayGraph built from apt.dat (with A* pathfinding)
- [x] FrequencyResolver returns correct frequencies (with fallbacks)
- [x] RunwaySelector picks appropriate runway (wind + aircraft type)

**Status: COMPLETE** (2025-11-25)

### Phase 2 Complete When:
- [x] Phrase chunks play smoothly (no word-by-word) - PhraseLibrary created
- [x] NumberPronouncer handles all formats - English and French support
- [ ] Audio generation script creates chunks (pending)

**Status: PARTIAL** - Core architecture complete, audio generation pending

### Phase 3 Complete When:
- [x] ATC works at any airport (no hardcoding) - ATCHandler refactored
- [x] ATIS generates dynamically - Uses RunwaySelector
- [x] Taxi instructions use real taxiway names - TaxiwayGraph integration

**Status: COMPLETE** (2025-11-25)

### Phase 4 Complete When:
- [x] A* pathfinding generates valid routes - TaxiwayGraph.find_route()
- [x] Progressive taxi instructions work - route_to_instructions()
- [x] Hold short instructions at runway crossings - RouteSegment.hold_short_runway

**Status: COMPLETE** (2025-11-25)

### Phase 5 Complete When:
- [ ] French phraseology complete
- [ ] French audio files generated
- [ ] Language auto-selection works

**Status: NOT STARTED** - Core infrastructure ready

### Phase 6 Complete When:
- [x] All integration tests pass (68 tests)
- [x] Edge cases handled gracefully (fallbacks in place)
- [ ] Documentation complete

**Status: PARTIAL** - Tests pass, documentation pending

---

## Estimated Complexity

| Phase | Complexity | Key Challenge |
|-------|------------|---------------|
| Phase 1 | Medium | apt.dat parsing, graph construction |
| Phase 2 | Medium | Chunk system design, audio generation |
| Phase 3 | Low | Refactoring existing code |
| Phase 4 | High | A* pathfinding, taxi verbalization |
| Phase 5 | Medium | French phraseology accuracy |
| Phase 6 | Low | Testing and polish |

---

## Notes

- Start with Phase 1 and 2 in parallel (no dependencies)
- Phase 3 can begin once Phase 1 data loading works
- Phase 4 is the most complex - may need iteration
- Phase 5 can proceed independently once Phase 2 chunk system is ready
- Consider generating a "missing audio" report before Phase 5
