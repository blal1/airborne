"""Frequency announcement for audio-only radio interface.

Provides audio feedback for frequency changes, radio operations, and tuning
using the cockpit voice and modular speech components.

Examples:
    >>> announcer = FrequencyAnnouncer(tts_provider)
    >>> announcer.announce_com1_active(121.5)
    # Plays: "COM one active one two one decimal five"
"""

from typing import Any

from airborne.plugins.radio.callsign_builder import CallsignBuilder


class FrequencyAnnouncer:
    """Announces radio frequencies and operations via cockpit voice.

    Provides audio feedback for frequency changes in audio-only interface.
    Uses modular speech components to build announcements.

    The announcer uses the cockpit voice (Samantha) for all radio feedback,
    and the CallsignBuilder to pronounce frequencies digit-by-digit.

    Examples:
        >>> announcer = FrequencyAnnouncer(tts_provider)
        >>> announcer.announce_com1_active(121.5)
        >>> announcer.announce_swap("COM1")
        >>> announcer.announce_tuning_mode("COM1")
    """

    def __init__(self, tts_provider: Any):
        """Initialize frequency announcer.

        Args:
            tts_provider: AudioSpeechProvider instance for speech playback.
        """
        self.tts = tts_provider
        self.builder = CallsignBuilder(voice="pilot")  # Will use for number building

    def announce_com1_active(self, frequency: float) -> None:
        """Announce COM1 active frequency.

        Args:
            frequency: Frequency in MHz (e.g., 121.5)

        Audio output:
            "COM one active one two one decimal five"
        """
        # Play: "COM"
        self._speak_file("cockpit", "COM")
        # Play: "one"
        self._speak_file("cockpit", "MSG_DIGIT_1")
        # Play: "active"
        self._speak_file("cockpit", "ACTIVE")

        # Play frequency digits
        freq_files = self.builder.build_frequency(frequency)
        for file in freq_files:
            self._speak_file("pilot", file)

    def announce_com2_active(self, frequency: float) -> None:
        """Announce COM2 active frequency.

        Args:
            frequency: Frequency in MHz (e.g., 119.0)

        Audio output:
            "COM two active one one nine decimal zero"
        """
        self._speak_file("cockpit", "COM")
        self._speak_file("cockpit", "MSG_DIGIT_2")
        self._speak_file("cockpit", "ACTIVE")

        freq_files = self.builder.build_frequency(frequency)
        for file in freq_files:
            self._speak_file("pilot", file)

    def announce_com1_standby(self, frequency: float) -> None:
        """Announce COM1 standby frequency.

        Args:
            frequency: Frequency in MHz

        Audio output:
            "COM one standby one one eight decimal three"
        """
        self._speak_file("cockpit", "COM")
        self._speak_file("cockpit", "MSG_DIGIT_1")
        self._speak_file("cockpit", "STANDBY")

        freq_files = self.builder.build_frequency(frequency)
        for file in freq_files:
            self._speak_file("pilot", file)

    def announce_com2_standby(self, frequency: float) -> None:
        """Announce COM2 standby frequency.

        Args:
            frequency: Frequency in MHz

        Audio output:
            "COM two standby one two one decimal five"
        """
        self._speak_file("cockpit", "COM")
        self._speak_file("cockpit", "MSG_DIGIT_2")
        self._speak_file("cockpit", "STANDBY")

        freq_files = self.builder.build_frequency(frequency)
        for file in freq_files:
            self._speak_file("pilot", file)

    def announce_swap(self, radio: str) -> None:
        """Announce frequency swap.

        Args:
            radio: "COM1" or "COM2"

        Audio output:
            "COM one swapped"
        """
        self._speak_file("cockpit", "COM")

        if radio == "COM1":
            self._speak_file("cockpit", "MSG_DIGIT_1")
        else:
            self._speak_file("cockpit", "MSG_DIGIT_2")

        self._speak_file("cockpit", "SWAPPED")

    def announce_tuning_mode(self, radio: str, mode: str = "active") -> None:
        """Announce entering tuning mode.

        Args:
            radio: "COM1" or "COM2"
            mode: "active" or "standby"

        Audio output:
            "Tuning COM one active"
        """
        self._speak_file("cockpit", "TUNED")
        self._speak_file("cockpit", "COM")

        if radio == "COM1":
            self._speak_file("cockpit", "MSG_DIGIT_1")
        else:
            self._speak_file("cockpit", "MSG_DIGIT_2")

        if mode == "active":
            self._speak_file("cockpit", "ACTIVE")
        else:
            self._speak_file("cockpit", "STANDBY")

    def announce_frequency_step(self, direction: str = "up") -> None:
        """Announce frequency tuning step (subtle beep).

        Args:
            direction: "up" or "down" (currently unused, could add different beeps)

        Note:
            This could play a short beep sound instead of speech.
            For now, we'll skip audio to avoid clutter.
        """
        # Could add beep sounds here if available
        # For now, silent to avoid too much audio feedback
        pass

    def announce_radio_selected(self, radio: str) -> None:
        """Announce radio selection.

        Args:
            radio: "COM1" or "COM2"

        Audio output:
            "COM one selected"
        """
        self._speak_file("cockpit", "COM")

        if radio == "COM1":
            self._speak_file("cockpit", "MSG_DIGIT_1")
        else:
            self._speak_file("cockpit", "MSG_DIGIT_2")

        self._speak_file("cockpit", "SELECTED")

    def announce_active_radio(self, radio: str, frequency: float) -> None:
        """Announce active radio and its frequency (short form).

        Args:
            radio: "COM1" or "COM2"
            frequency: Frequency in MHz (e.g., 121.5)

        Audio output:
            "COM one, one two one decimal five"
        """
        # Play: "COM"
        self._speak_file("cockpit", "COM")

        # Play: "one" or "two"
        if radio == "COM1":
            self._speak_file("cockpit", "MSG_DIGIT_1")
        else:
            self._speak_file("cockpit", "MSG_DIGIT_2")

        # Play frequency digits
        freq_files = self.builder.build_frequency(frequency)
        for file in freq_files:
            self._speak_file("pilot", file)

    def _speak_file(self, voice_dir: str, filename: str) -> None:
        """Queue audio file for playback.

        Args:
            voice_dir: Voice directory ("cockpit", "pilot", etc.)
            filename: Base filename without extension

        Note:
            The TTS provider will handle queuing and sequential playback.
        """
        # The AudioSpeechProvider expects message keys, not file paths
        # We need to queue files by constructing the proper message key
        # For now, we'll use the filename as the key and rely on the
        # speech system to find it

        # Construct message key
        # For cockpit files: filename is the key
        # For pilot files: filename is the key
        msg_key = filename

        # Queue for playback
        if self.tts:
            self.tts.speak(msg_key)
