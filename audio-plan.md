# Audio Facade Refactor Plan

## Overview

This plan addresses architectural issues in the audio system where `MenuRunner` bypasses the established audio patterns and directly manipulates FMOD objects. The solution introduces an `AudioFacade` that provides a clean, unified API for all audio consumers.

## Problem Statement

### Current Issues

1. **MenuRunner leaks FMOD implementation details**
   - Stores raw `_menu_music_sound` and `_menu_music_channel` objects
   - Manually implements fade logic each frame
   - Creates its own `pyfmodex.System()` bypassing `FMODEngine`

2. **ATCAudioManager accesses engine internals**
   - Uses `_audio_engine._system` and `_audio_engine._channels` directly
   - No public API for effect application

3. **No music player abstraction**
   - No built-in fade in/out support
   - No crossfade between tracks
   - Streaming music requires manual channel management

4. **Effects applied per-channel manually**
   - `RadioEffectFilter` requires raw FMOD channel access
   - No named effect registry

5. **No category-based volume control**
   - Cannot adjust "all engine sounds" or "all voice" independently

---

## Solution Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Consumers                                        │
│                                                                               │
│  MenuRunner            AudioPlugin                    ATCAudioManager         │
│  ───────────           ───────────                    ───────────────         │
│  audio.play_music()    audio.play_sfx()               audio.play_sfx()       │
│  audio.fade_out()      audio.play_sfx_bytes()         (with radio effect)    │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            AudioFacade                                        │
│                                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ MusicPlayer  │  │  SFXPlayer   │  │EffectManager │  │VolumeManager │     │
│  │              │  │              │  │              │  │              │     │
│  │ - play()     │  │ - play()     │  │ - register() │  │ Categories:  │     │
│  │ - stop()     │  │ - play_bytes │  │ - get()      │  │ - music      │     │
│  │ - fade_to()  │  │ - effects    │  │ - apply()    │  │ - engine     │     │
│  │ - crossfade  │  │              │  │              │  │ - environment│     │
│  │ - update()   │  │              │  │              │  │ - ui         │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  │ - cockpit    │     │
│                                                         │ - atc        │     │
│                                                         │ - pilot      │     │
│                                                         │ - cue        │     │
│                                                         │ - master     │     │
│                                                         └──────────────┘     │
│                                │                                              │
│                    ┌───────────┴───────────┐                                 │
│                    ▼                       ▼                                  │
│              FMODEngine              IAudioEngine                            │
│              (enhanced)              (interface)                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Volume Categories

Game-relevant audio categories for independent volume control:

| Category | Description | Examples |
|----------|-------------|----------|
| `master` | Global master volume | All audio |
| `music` | Background music | Menu music, ambient music |
| `engine` | Aircraft engine sounds | Engine idle, startup, shutdown |
| `environment` | Environmental sounds | Wind, rain, rolling/tire sounds |
| `ui` | UI feedback sounds | Click sounds, menu navigation |
| `cockpit` | Cockpit voice/announcements | Instrument readouts, warnings, stall warning |
| `atc` | ATC radio communications | Tower, ground, approach voices |
| `pilot` | Pilot radio communications | Player's radio transmissions |
| `cue` | Navigation/proximity cues | Beeps, proximity alerts, orientation tones |

### Volume Hierarchy

```
master (1.0)
├── music (0.7)
├── engine (1.0)
├── environment (1.0)
├── ui (0.8)
├── cockpit (1.0)
├── atc (1.0)
├── pilot (1.0)
└── cue (1.0)
```

Final volume = `master * category * sound_volume`

---

## Task Breakdown

Tasks are organized for parallel execution where possible. Each task is self-contained and can be assigned to Sonnet 4.5.

### Legend

- **[P]** = Can be parallelized with other [P] tasks in same phase
- **[S]** = Sequential, depends on previous tasks
- **File**: Primary file(s) to create/modify
- **Deps**: Task dependencies (must complete first)

---

## Phase 1: FMODEngine Public Accessors

**Goal**: Expose necessary internals through clean public API

### Task 1.1 [P] - Add get_channel method
**File**: `src/airborne/audio/engine/fmod_engine.py`
**Deps**: None

Add method to FMODEngine:
```python
def get_channel(self, source_id: int) -> Any | None:
    """Get the FMOD channel for a source ID.

    Used by effect managers to apply DSP effects to channels.

    Args:
        source_id: Source ID from play_2d/play_3d.

    Returns:
        FMOD channel object or None if not found/stopped.
    """
    return self._channels.get(source_id)
```

### Task 1.2 [P] - Add get_system method
**File**: `src/airborne/audio/engine/fmod_engine.py`
**Deps**: None

Add method to FMODEngine:
```python
def get_system(self) -> Any | None:
    """Get the FMOD system instance.

    Used by effect managers to create DSP effects.

    Returns:
        FMOD System object or None if not initialized.
    """
    return self._system if self._initialized else None
```

### Task 1.3 [S] - Add tests for new methods
**File**: `tests/audio/engine/test_fmod_engine.py`
**Deps**: 1.1, 1.2

Add tests:
- `test_get_channel_returns_valid_channel`
- `test_get_channel_returns_none_for_invalid_id`
- `test_get_channel_returns_none_for_stopped`
- `test_get_system_returns_system_when_initialized`
- `test_get_system_returns_none_when_not_initialized`

---

## Phase 2: IAudioEffect Protocol and EffectManager

**Goal**: Create effect abstraction and registry

### Task 2.1 [P] - Create IAudioEffect protocol
**File**: `src/airborne/audio/effects/base.py`
**Deps**: None

Create new file with:
```python
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class IAudioEffect(Protocol):
    """Protocol for audio effects that can be applied to channels."""

    def apply_to_channel(self, channel: Any) -> None:
        """Apply effect DSP chain to a channel."""
        ...

    def remove_from_channel(self, channel: Any) -> None:
        """Remove effect DSP chain from a channel."""
        ...

    def is_enabled(self) -> bool:
        """Check if effect is enabled."""
        ...

    def shutdown(self) -> None:
        """Release DSP resources."""
        ...
```

### Task 2.2 [P] - Create EffectManager class
**File**: `src/airborne/audio/effects/effect_manager.py`
**Deps**: None (can use forward reference for IAudioEffect)

Create new file with EffectManager:
- `__init__(self, audio_engine: IAudioEngine)`
- `register(self, name: str, effect: IAudioEffect) -> None`
- `unregister(self, name: str) -> None`
- `get(self, name: str) -> IAudioEffect | None`
- `apply_effects(self, source_id: int, effect_names: list[str]) -> None`
- `remove_effects(self, source_id: int, effect_names: list[str]) -> None`
- `shutdown(self) -> None`

### Task 2.3 [S] - Update effects __init__.py
**File**: `src/airborne/audio/effects/__init__.py`
**Deps**: 2.1, 2.2

Export new types:
```python
from airborne.audio.effects.base import IAudioEffect
from airborne.audio.effects.effect_manager import EffectManager
from airborne.audio.effects.radio_filter import RadioEffectFilter

__all__ = ["IAudioEffect", "EffectManager", "RadioEffectFilter"]
```

### Task 2.4 [S] - Add EffectManager tests
**File**: `tests/audio/effects/test_effect_manager.py`
**Deps**: 2.1, 2.2

Add tests:
- `test_register_and_get_effect`
- `test_unregister_effect`
- `test_get_returns_none_for_unknown`
- `test_apply_effects_to_source`
- `test_remove_effects_from_source`
- `test_shutdown_releases_all_effects`

### Task 2.5 [S] - Verify RadioEffectFilter implements IAudioEffect
**File**: `src/airborne/audio/effects/radio_filter.py`
**Deps**: 2.1

Add runtime check or type annotation if needed. RadioEffectFilter already has the required methods.

---

## Phase 3: VolumeManager

**Goal**: Category-based volume control

### Task 3.1 [P] - Create AudioCategory enum
**File**: `src/airborne/audio/volume_manager.py`
**Deps**: None

```python
from enum import Enum

class AudioCategory(Enum):
    """Audio categories for volume control."""
    MASTER = "master"
    MUSIC = "music"
    ENGINE = "engine"
    ENVIRONMENT = "environment"
    UI = "ui"
    COCKPIT = "cockpit"
    ATC = "atc"
    PILOT = "pilot"
    CUE = "cue"
```

### Task 3.2 [S] - Create VolumeManager class
**File**: `src/airborne/audio/volume_manager.py`
**Deps**: 3.1

Add VolumeManager class:
- `__init__(self)` - initialize with default volumes
- `set_volume(self, category: AudioCategory, volume: float) -> None`
- `get_volume(self, category: AudioCategory) -> float`
- `get_effective_volume(self, category: AudioCategory) -> float`
- `on_volume_changed(self, callback: Callable) -> None`
- `remove_callback(self, callback: Callable) -> None`
- `save_to_dict(self) -> dict[str, float]`
- `load_from_dict(self, data: dict[str, float]) -> None`

### Task 3.3 [S] - Add VolumeManager tests
**File**: `tests/audio/test_volume_manager.py`
**Deps**: 3.2

Add tests:
- `test_default_volumes`
- `test_set_and_get_volume`
- `test_volume_clamped_to_0_1`
- `test_effective_volume_includes_master`
- `test_volume_change_callback_called`
- `test_remove_callback`
- `test_save_to_dict`
- `test_load_from_dict`

---

## Phase 4: MusicPlayer

**Goal**: Streaming music with fade support

### Task 4.1 [P] - Create FadeState enum and MusicHandle
**File**: `src/airborne/audio/music_player.py`
**Deps**: None

```python
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from airborne.audio.engine.base import IAudioEngine

class FadeState(Enum):
    NONE = auto()
    FADING_IN = auto()
    FADING_OUT = auto()
    CROSSFADING = auto()

@dataclass
class MusicHandle:
    source_id: int
    path: str
    target_volume: float
    _engine: "IAudioEngine"

    def is_playing(self) -> bool: ...
    def get_volume(self) -> float: ...
```

### Task 4.2 [S] - Create MusicPlayer class - core methods
**File**: `src/airborne/audio/music_player.py`
**Deps**: 4.1, Phase 3 (VolumeManager)

Implement:
- `__init__(self, audio_engine, volume_manager)`
- `play(self, path, volume, loop, fade_in) -> MusicHandle`
- `stop(self, fade_out) -> None`
- `is_playing(self) -> bool`
- `shutdown(self) -> None`

### Task 4.3 [S] - Create MusicPlayer class - fade methods
**File**: `src/airborne/audio/music_player.py`
**Deps**: 4.2

Implement:
- `fade_to(self, volume, duration) -> None`
- `crossfade_to(self, path, duration, volume) -> MusicHandle`
- `is_fading(self) -> bool`
- `update(self, dt) -> None` - process fade state

### Task 4.4 [S] - Add MusicPlayer tests
**File**: `tests/audio/test_music_player.py`
**Deps**: 4.3

Add tests:
- `test_play_music_starts_playback`
- `test_play_with_fade_in`
- `test_stop_immediately`
- `test_stop_with_fade_out`
- `test_fade_to_changes_volume`
- `test_crossfade_transitions_tracks`
- `test_update_processes_fade_in`
- `test_update_processes_fade_out`
- `test_is_fading_returns_correct_state`
- `test_volume_category_applied`

---

## Phase 5: SFXPlayer

**Goal**: One-shot sound effects with effect chain support

### Task 5.1 [P] - Create SFXHandle dataclass
**File**: `src/airborne/audio/sfx_player.py`
**Deps**: None

```python
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from airborne.audio.engine.base import IAudioEngine
    from airborne.audio.volume_manager import AudioCategory

@dataclass
class SFXHandle:
    source_id: int
    category: "AudioCategory"
    _engine: "IAudioEngine"

    def is_playing(self) -> bool: ...
    def stop(self) -> None: ...
```

### Task 5.2 [S] - Create SFXPlayer class - play methods
**File**: `src/airborne/audio/sfx_player.py`
**Deps**: 5.1, Phase 2 (EffectManager), Phase 3 (VolumeManager)

Implement:
- `__init__(self, audio_engine, volume_manager, effect_manager)`
- `play(self, path, category, volume, pitch, effects) -> SFXHandle`
- `play_from_bytes(self, audio_bytes, name, category, volume, pitch, effects) -> SFXHandle`
- `play_looping(self, path, category, volume, pitch) -> SFXHandle`

### Task 5.3 [S] - Create SFXPlayer class - control methods
**File**: `src/airborne/audio/sfx_player.py`
**Deps**: 5.2

Implement:
- `update_volume(self, handle, volume) -> None`
- `update_pitch(self, handle, pitch) -> None`
- `stop(self, handle) -> None`

### Task 5.4 [S] - Add SFXPlayer tests
**File**: `tests/audio/test_sfx_player.py`
**Deps**: 5.3

Add tests:
- `test_play_sound_effect`
- `test_play_with_effects`
- `test_play_from_bytes`
- `test_play_looping`
- `test_update_volume`
- `test_update_pitch`
- `test_stop_sound`
- `test_category_volume_applied`
- `test_handle_is_playing`

---

## Phase 6: AudioFacade

**Goal**: Unified entry point combining all components

### Task 6.1 [S] - Create AudioFacade class - initialization
**File**: `src/airborne/audio/facade.py`
**Deps**: Phase 2, 3, 4, 5

Implement:
- `__init__(self)`
- `initialize(self, audio_engine) -> None`
- `shutdown(self) -> None`
- `update(self, dt) -> None`
- `get_engine(self) -> IAudioEngine`

### Task 6.2 [S] - Add AudioFacade music methods
**File**: `src/airborne/audio/facade.py`
**Deps**: 6.1

Implement:
- `play_music(self, path, volume, loop, fade_in) -> MusicHandle`
- `stop_music(self, fade_out) -> None`
- `fade_music(self, volume, duration) -> None`
- `crossfade_music(self, path, duration, volume) -> MusicHandle`
- `music_is_playing(self) -> bool`
- `music_is_fading(self) -> bool`

### Task 6.3 [S] - Add AudioFacade SFX methods
**File**: `src/airborne/audio/facade.py`
**Deps**: 6.1

Implement:
- `play_sfx(self, path, category, volume, pitch, effects) -> SFXHandle`
- `play_sfx_from_bytes(self, audio_bytes, name, category, volume, effects) -> SFXHandle`
- `play_sfx_looping(self, path, category, volume, pitch) -> SFXHandle`
- `update_sfx_volume(self, handle, volume) -> None`
- `update_sfx_pitch(self, handle, pitch) -> None`
- `stop_sfx(self, handle) -> None`

### Task 6.4 [S] - Add AudioFacade effect and volume methods
**File**: `src/airborne/audio/facade.py`
**Deps**: 6.1

Implement:
- `register_effect(self, name, effect) -> None`
- `unregister_effect(self, name) -> None`
- `set_volume(self, category, volume) -> None`
- `get_volume(self, category) -> float`
- `get_volume_manager(self) -> VolumeManager`

### Task 6.5 [S] - Add AudioFacade tests
**File**: `tests/audio/test_facade.py`
**Deps**: 6.2, 6.3, 6.4

Add tests:
- `test_initialize_and_shutdown`
- `test_play_music_with_fade`
- `test_stop_music_with_fade`
- `test_crossfade_music`
- `test_play_sfx`
- `test_play_sfx_with_effects`
- `test_play_sfx_from_bytes`
- `test_category_volume_control`
- `test_register_and_use_effect`
- `test_update_processes_fades`

---

## Phase 7: Migrate MenuRunner

**Goal**: Replace raw FMOD usage with AudioFacade

### Task 7.1 [S] - Remove old audio fields from MenuRunner
**File**: `src/airborne/ui/menus/menu_runner.py`
**Deps**: Phase 6

Remove fields:
- `self._fmod_system`
- `self._menu_music_sound`
- `self._menu_music_channel`
- `self._menu_music_fading`
- `self._menu_music_fade_start`
- `self._menu_music_fade_duration`
- `self._menu_music_volume`

Add field:
- `self._audio: AudioFacade`

### Task 7.2 [S] - Update MenuRunner audio initialization
**File**: `src/airborne/ui/menus/menu_runner.py`
**Deps**: 7.1

Update `_initialize_audio()` to create and initialize AudioFacade.

### Task 7.3 [S] - Update MenuRunner music playback
**File**: `src/airborne/ui/menus/menu_runner.py`
**Deps**: 7.2

Replace:
- `_start_menu_music()` → use `self._audio.play_music()`
- `_start_menu_music_fadeout()` → use `self._audio.stop_music(fade_out=...)`
- Remove `_update_menu_music_fade()` (handled by facade)
- Remove `_stop_menu_music()` (handled by facade)

### Task 7.4 [S] - Update MenuRunner sound effects
**File**: `src/airborne/ui/menus/menu_runner.py`
**Deps**: 7.2

Replace click sound and TTS playback:
- `_play_sound()` → use `self._audio.play_sfx()`
- `_play_tts_audio_sync()` → use `self._audio.play_sfx_from_bytes()`

### Task 7.5 [S] - Update MenuRunner main loop
**File**: `src/airborne/ui/menus/menu_runner.py`
**Deps**: 7.3, 7.4

Update `_run_loop()`:
- Add `self._audio.update(dt)` call
- Check `self._audio.music_is_fading()` for fade completion

### Task 7.6 [S] - Update MenuRunner shutdown
**File**: `src/airborne/ui/menus/menu_runner.py`
**Deps**: 7.2

Update `_shutdown()`:
- Call `self._audio.shutdown()`
- Remove old FMOD cleanup

### Task 7.7 [S] - Test MenuRunner changes
**File**: Manual testing + `tests/ui/menus/test_menu_runner.py`
**Deps**: 7.1-7.6

Verify:
- Menu music plays on startup with fade in
- Menu music fades out when "Fly" selected
- Click sounds work
- TTS playback works
- No errors in logs

---

## Phase 8: Migrate ATCAudioManager

**Goal**: Use public engine methods instead of internals

### Task 8.1 [S] - Replace _system access in ATCAudioManager
**File**: `src/airborne/audio/atc/atc_audio.py`
**Deps**: Phase 1

Replace:
```python
# Before
if hasattr(self._audio_engine, "_system"):
    self._radio_filter = RadioEffectFilter(self._audio_engine._system, radio_config)

# After
system = self._audio_engine.get_system()
if system:
    self._radio_filter = RadioEffectFilter(system, radio_config)
```

### Task 8.2 [S] - Replace _channels access in ATCAudioManager
**File**: `src/airborne/audio/atc/atc_audio.py`
**Deps**: Phase 1

Replace all occurrences:
```python
# Before
self._current_voice_channel = self._audio_engine._channels.get(source_id)

# After
self._current_voice_channel = self._audio_engine.get_channel(source_id)
```

### Task 8.3 [S] - Test ATCAudioManager changes
**File**: Manual testing + existing tests
**Deps**: 8.1, 8.2

Verify:
- ATC messages play with radio effect
- ATC messages play without effect when disabled
- No attribute access errors

---

## Phase 9: Migrate AudioPlugin to AudioFacade

**Goal**: Use AudioFacade internally for consistent volume category support

### Task 9.1 [S] - Add AudioFacade field to AudioPlugin
**File**: `src/airborne/plugins/audio/audio_plugin.py`
**Deps**: Phase 6

Add field and modify `__init__`:
- `self._audio_facade: AudioFacade | None = None`

### Task 9.2 [S] - Initialize AudioFacade in AudioPlugin
**File**: `src/airborne/plugins/audio/audio_plugin.py`
**Deps**: 9.1

In `initialize()`:
- Create AudioFacade
- Initialize with existing audio_engine
- Register "radio" effect from ATCAudioManager config

### Task 9.3 [S] - Map message handlers to facade - TTS
**File**: `src/airborne/plugins/audio/audio_plugin.py`
**Deps**: 9.2

Update `handle_message()` for `TTS_SPEAK`:
- Use `self._audio_facade.play_sfx_from_bytes()` with category `AudioCategory.COCKPIT`

### Task 9.4 [S] - Map message handlers to facade - click sounds
**File**: `src/airborne/plugins/audio/audio_plugin.py`
**Deps**: 9.2

Update `handle_message()` for `audio.play_click`:
- Use `self._audio_facade.play_sfx()` with category `AudioCategory.UI`

### Task 9.5 [S] - Update SoundManager calls - engine sounds
**File**: `src/airborne/plugins/audio/audio_plugin.py`
**Deps**: 9.2

For engine sounds, wind, rolling:
- Keep SoundManager for complex game logic (pitch variation, sequences)
- OR migrate to facade with `AudioCategory.ENGINE` / `AudioCategory.ENVIRONMENT`

Decision: Keep SoundManager for engine/environment sounds as they have specialized logic. Use facade for simple one-shot sounds.

### Task 9.6 [S] - Update SoundManager calls - simple sounds
**File**: `src/airborne/plugins/audio/audio_plugin.py`
**Deps**: 9.2

Migrate to facade:
- Gear sounds → `play_sfx(..., category=AudioCategory.UI)`
- Flaps sounds → `play_sfx(..., category=AudioCategory.UI)`
- Brake sounds → `play_sfx(..., category=AudioCategory.UI)`
- Battery sounds → `play_sfx(..., category=AudioCategory.UI)`

### Task 9.7 [S] - Add facade update call
**File**: `src/airborne/plugins/audio/audio_plugin.py`
**Deps**: 9.2

In `update()`:
- Add `self._audio_facade.update(dt)` call

### Task 9.8 [S] - Update shutdown
**File**: `src/airborne/plugins/audio/audio_plugin.py`
**Deps**: 9.2

In `shutdown()`:
- Call `self._audio_facade.shutdown()`

### Task 9.9 [S] - Test AudioPlugin changes
**File**: Manual testing + existing tests
**Deps**: 9.1-9.8

Verify:
- All sounds play correctly
- Volume categories work
- No regressions in game audio

---

## File Summary

### New Files

| File | Phase | Purpose |
|------|-------|---------|
| `src/airborne/audio/effects/base.py` | 2 | `IAudioEffect` protocol |
| `src/airborne/audio/effects/effect_manager.py` | 2 | Named effect registry |
| `src/airborne/audio/volume_manager.py` | 3 | Category-based volume control |
| `src/airborne/audio/music_player.py` | 4 | Music playback with fading |
| `src/airborne/audio/sfx_player.py` | 5 | Sound effect playback |
| `src/airborne/audio/facade.py` | 6 | Unified audio API |
| `tests/audio/effects/test_effect_manager.py` | 2 | Effect manager tests |
| `tests/audio/test_volume_manager.py` | 3 | Volume manager tests |
| `tests/audio/test_music_player.py` | 4 | Music player tests |
| `tests/audio/test_sfx_player.py` | 5 | SFX player tests |
| `tests/audio/test_facade.py` | 6 | Facade integration tests |

### Modified Files

| File | Phase | Changes |
|------|-------|---------|
| `src/airborne/audio/engine/fmod_engine.py` | 1 | Add `get_channel()`, `get_system()` |
| `src/airborne/audio/effects/__init__.py` | 2 | Export new types |
| `src/airborne/ui/menus/menu_runner.py` | 7 | Use AudioFacade |
| `src/airborne/audio/atc/atc_audio.py` | 8 | Use public engine methods |
| `src/airborne/plugins/audio/audio_plugin.py` | 9 | Use AudioFacade internally |

---

## Parallel Execution Guide

Tasks can be executed in parallel as follows:

### Round 1 (No dependencies)
- Task 1.1, 1.2 (Phase 1)
- Task 2.1, 2.2 (Phase 2)
- Task 3.1 (Phase 3)
- Task 4.1 (Phase 4)
- Task 5.1 (Phase 5)

### Round 2 (After Round 1)
- Task 1.3 (needs 1.1, 1.2)
- Task 2.3, 2.4, 2.5 (needs 2.1, 2.2)
- Task 3.2 (needs 3.1)

### Round 3 (After Round 2)
- Task 3.3 (needs 3.2)
- Task 4.2 (needs 4.1, 3.2)

### Round 4 (After Round 3)
- Task 4.3 (needs 4.2)
- Task 5.2 (needs 5.1, 2.2, 3.2)

### Round 5 (After Round 4)
- Task 4.4 (needs 4.3)
- Task 5.3 (needs 5.2)

### Round 6 (After Round 5)
- Task 5.4 (needs 5.3)
- Task 6.1 (needs all Phase 2-5)

### Round 7 (After Round 6)
- Task 6.2, 6.3, 6.4 (can parallel, need 6.1)

### Round 8 (After Round 7)
- Task 6.5 (needs 6.2, 6.3, 6.4)

### Round 9 (After Phase 6)
- Phase 7 tasks (sequential)
- Phase 8 tasks (can parallel with Phase 7)

### Round 10 (After Phase 7, 8)
- Phase 9 tasks (sequential)

---

## Success Criteria

### Phase 1
- [ ] `FMODEngine.get_channel()` returns valid channel for active source
- [ ] `FMODEngine.get_channel()` returns None for stopped source
- [ ] `FMODEngine.get_system()` returns system when initialized
- [ ] All existing tests pass

### Phase 2
- [ ] Effects can be registered by name
- [ ] Effects can be applied to sources by name
- [ ] `RadioEffectFilter` works with `EffectManager`
- [ ] All tests pass

### Phase 3
- [ ] Volume can be set per category
- [ ] Effective volume includes master
- [ ] Volume changes trigger callbacks
- [ ] All tests pass

### Phase 4
- [ ] Music plays with optional fade in
- [ ] Music stops with optional fade out
- [ ] Crossfade transitions between tracks
- [ ] `update()` processes fade state
- [ ] All tests pass

### Phase 5
- [ ] Sound effects play one-shot
- [ ] Sound effects can have effects applied
- [ ] Sound effects respect volume categories
- [ ] `play_from_bytes()` works for TTS
- [ ] All tests pass

### Phase 6
- [ ] `AudioFacade` provides unified API
- [ ] All components integrate correctly
- [ ] Integration tests pass

### Phase 7
- [ ] `MenuRunner` uses `AudioFacade`
- [ ] Menu music plays with fade
- [ ] Menu music fades out on "Fly"
- [ ] Click sounds work
- [ ] TTS playback works
- [ ] No raw FMOD objects in MenuRunner
- [ ] All tests pass

### Phase 8
- [ ] `ATCAudioManager` uses public engine methods
- [ ] Radio effects still work
- [ ] No `_system` or `_channels` access
- [ ] All tests pass

### Phase 9
- [ ] `AudioPlugin` uses `AudioFacade` internally
- [ ] Volume categories applied to sounds
- [ ] All game audio works correctly
- [ ] No regressions
- [ ] All tests pass

---

## Notes

- Each task should be committed separately with descriptive message
- Run `uv run ruff format . && uv run ruff check . --fix` after each task
- Run `uv run mypy src` to check types
- Run `uv run pytest` to verify no regressions
- Maintain backward compatibility during migration
- SoundManager remains for complex game-specific logic (engine pitch variation, sound sequences)
- AudioFacade is for general audio needs; specialized logic stays in existing components
