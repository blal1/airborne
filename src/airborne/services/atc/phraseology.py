"""Aviation phraseology helpers for ATC communications.

Provides utilities for converting callsigns, numbers, and other
aviation terminology into proper radio phraseology.
"""

from dataclasses import dataclass
from typing import ClassVar


@dataclass
class PhoneticConverter:
    """Convert characters and numbers to ICAO phonetic alphabet.

    The ICAO phonetic alphabet is used in aviation radio communications
    to ensure clarity. Numbers also have specific pronunciations
    (e.g., 9 = "niner").
    """

    # ICAO phonetic alphabet for letters
    PHONETIC_LETTERS: ClassVar[dict[str, str]] = {
        "A": "alpha",
        "B": "bravo",
        "C": "charlie",
        "D": "delta",
        "E": "echo",
        "F": "foxtrot",
        "G": "golf",
        "H": "hotel",
        "I": "india",
        "J": "juliett",
        "K": "kilo",
        "L": "lima",
        "M": "mike",
        "N": "november",
        "O": "oscar",
        "P": "papa",
        "Q": "quebec",
        "R": "romeo",
        "S": "sierra",
        "T": "tango",
        "U": "uniform",
        "V": "victor",
        "W": "whiskey",
        "X": "x-ray",
        "Y": "yankee",
        "Z": "zulu",
    }

    # Aviation number pronunciations
    PHONETIC_NUMBERS: ClassVar[dict[str, str]] = {
        "0": "zero",
        "1": "one",
        "2": "two",
        "3": "three",
        "4": "four",
        "5": "five",
        "6": "six",
        "7": "seven",
        "8": "eight",
        "9": "niner",
    }

    @classmethod
    def letter_to_phonetic(cls, letter: str) -> str:
        """Convert a single letter to phonetic equivalent.

        Args:
            letter: Single character to convert.

        Returns:
            Phonetic word for the letter.
        """
        return cls.PHONETIC_LETTERS.get(letter.upper(), letter)

    @classmethod
    def digit_to_phonetic(cls, digit: str) -> str:
        """Convert a single digit to phonetic equivalent.

        Args:
            digit: Single digit character.

        Returns:
            Phonetic word for the digit.
        """
        return cls.PHONETIC_NUMBERS.get(digit, digit)

    @classmethod
    def callsign_to_phonetic(cls, callsign: str) -> list[str]:
        """Convert an aircraft callsign to phonetic words.

        Args:
            callsign: Aircraft callsign (e.g., "N123AB").

        Returns:
            List of phonetic words for the callsign.
        """
        words = []
        for char in callsign.upper():
            if char.isalpha():
                words.append(cls.letter_to_phonetic(char))
            elif char.isdigit():
                words.append(cls.digit_to_phonetic(char))
        return words

    @classmethod
    def number_to_individual_digits(cls, number: int) -> list[str]:
        """Convert a number to individual digit phonetics.

        Used for frequencies, headings, altitudes spoken digit-by-digit.

        Args:
            number: Integer to convert.

        Returns:
            List of phonetic words for each digit.
        """
        return [cls.digit_to_phonetic(d) for d in str(abs(number))]

    @classmethod
    def frequency_to_phonetic(cls, frequency: float) -> list[str]:
        """Convert a radio frequency to phonetic words.

        Args:
            frequency: Frequency in MHz (e.g., 121.5).

        Returns:
            List of phonetic words including "point" for decimal.
        """
        freq_str = f"{frequency:.3f}"
        words = []
        for char in freq_str:
            if char == ".":
                words.append("point")
            else:
                words.append(cls.digit_to_phonetic(char))
        return words

    @classmethod
    def runway_to_phonetic(cls, runway: str) -> list[str]:
        """Convert a runway designation to phonetic words.

        Args:
            runway: Runway identifier (e.g., "31L", "09R", "27").

        Returns:
            List of phonetic words for the runway.
        """
        words = []
        for char in runway.upper():
            if char.isdigit():
                words.append(cls.digit_to_phonetic(char))
            elif char == "L":
                words.append("left")
            elif char == "R":
                words.append("right")
            elif char == "C":
                words.append("center")
        return words

    @classmethod
    def altitude_to_words(cls, altitude: int, use_flight_level: bool = False) -> list[str]:
        """Convert altitude to spoken words.

        Args:
            altitude: Altitude in feet.
            use_flight_level: If True and altitude >= 18000, use flight level.

        Returns:
            List of words for the altitude.
        """
        if use_flight_level and altitude >= 18000:
            fl = altitude // 100
            return ["flight", "level"] + cls.number_to_individual_digits(fl)

        words = []
        if altitude >= 1000:
            thousands = altitude // 1000
            remainder = altitude % 1000
            words.append(cls.PHONETIC_NUMBERS.get(str(thousands), str(thousands)))
            words.append("thousand")
            if remainder > 0:
                hundreds = remainder // 100
                if hundreds > 0:
                    words.append(cls.PHONETIC_NUMBERS.get(str(hundreds), str(hundreds)))
                    words.append("hundred")
        else:
            hundreds = altitude // 100
            if hundreds > 0:
                words.append(cls.PHONETIC_NUMBERS.get(str(hundreds), str(hundreds)))
                words.append("hundred")
        words.append("feet")
        return words


class PhraseBuilder:
    """Build ATC phrases from components.

    Assembles proper aviation phraseology from individual words
    and returns both text and audio file references.
    """

    def __init__(self, audio_base_path: str = "data/speech/en") -> None:
        """Initialize phrase builder.

        Args:
            audio_base_path: Base path for audio files.
        """
        self.audio_base_path = audio_base_path
        self.converter = PhoneticConverter()

    def build_callsign_phrase(self, callsign: str, abbreviated: bool = False) -> dict:
        """Build a callsign phrase.

        Args:
            callsign: Aircraft callsign.
            abbreviated: If True, use abbreviated form (e.g., "three alpha bravo").

        Returns:
            Dict with 'text' and 'audio_files' keys.
        """
        phonetic_words = PhoneticConverter.callsign_to_phonetic(callsign)

        if abbreviated and len(phonetic_words) > 3:
            # Use last 3 characters for abbreviated callsign
            phonetic_words = phonetic_words[-3:]

        return {
            "text": " ".join(phonetic_words),
            "words": phonetic_words,
            "audio_files": [self._get_audio_file(word) for word in phonetic_words],
        }

    def build_wind_phrase(self, direction: int, speed: int, gust: int | None = None) -> dict:
        """Build a wind announcement phrase.

        Args:
            direction: Wind direction in degrees.
            gust: Gust speed in knots, or None.

        Returns:
            Dict with 'text' and 'audio_files' keys.
        """
        if speed == 0:
            return {
                "text": "wind calm",
                "words": ["WIND_CALM"],
                "audio_files": [self._get_audio_file("WIND_CALM")],
            }

        if direction == -1:
            dir_words = ["WIND_VARIABLE"]
            words = dir_words
        else:
            dir_words = PhoneticConverter.number_to_individual_digits(direction)
            # Pad to 3 digits
            while len(dir_words) < 3:
                dir_words.insert(0, "zero")
            words = ["WIND"] + dir_words

        speed_words = PhoneticConverter.number_to_individual_digits(speed)
        words += ["AT"] + speed_words

        if gust:
            gust_words = PhoneticConverter.number_to_individual_digits(gust)
            words += ["GUSTING"] + gust_words

        return {
            "text": " ".join(w.lower() if w.isupper() else w for w in words),
            "words": words,
            "audio_files": [self._get_audio_file(word) for word in words],
        }

    def build_visibility_phrase(self, visibility: float) -> dict:
        """Build a visibility announcement phrase.

        Args:
            visibility: Visibility in statute miles.

        Returns:
            Dict with 'text' and 'audio_files' keys.
        """
        if visibility >= 10:
            words = ["VISIBILITY", "one", "zero", "MILES"]
        elif visibility >= 1:
            vis_int = int(visibility)
            vis_words = PhoneticConverter.number_to_individual_digits(vis_int)
            words = ["VISIBILITY"] + vis_words + ["MILES"]
        else:
            # Less than 1 mile - use fractions
            if visibility <= 0.25:
                words = ["VISIBILITY", "one", "quarter", "mile"]
            elif visibility <= 0.5:
                words = ["VISIBILITY", "one", "half", "mile"]
            elif visibility <= 0.75:
                words = ["VISIBILITY", "three", "quarters", "mile"]
            else:
                words = ["VISIBILITY", "less", "than", "one", "mile"]

        return {
            "text": " ".join(w.lower() if w.isupper() else w for w in words),
            "words": words,
            "audio_files": [self._get_audio_file(word) for word in words],
        }

    def build_altimeter_phrase(self, pressure: float, pressure_unit: str = "inHg") -> dict:
        """Build an altimeter/QNH setting phrase.

        Args:
            pressure: Pressure setting (inches Hg or hPa depending on unit).
            pressure_unit: "inHg" for US altimeter, "hPa" for European QNH.

        Returns:
            Dict with 'text' and 'audio_files' keys.
        """
        if pressure_unit == "hPa":
            # QNH in hectopascals: "QNH one zero one two"
            qnh_int = int(pressure)
            digits = PhoneticConverter.number_to_individual_digits(qnh_int)
            words = ["QNH"] + digits
            text = f"QNH {' '.join(d for d in digits)}"
        else:
            # US altimeter in inches Hg: "altimeter three zero one two"
            # Format as four digits (e.g., 30.12 -> 3012)
            alt_int = int(pressure * 100)
            digits = PhoneticConverter.number_to_individual_digits(alt_int)
            words = ["ALTIMETER"] + digits
            text = f"altimeter {' '.join(d for d in digits)}"

        return {
            "text": text,
            "words": words,
            "audio_files": [self._get_audio_file(word) for word in words],
        }

    def build_runway_phrase(self, runway: str, departing: bool = True) -> dict:
        """Build a runway announcement phrase.

        Args:
            runway: Runway identifier.
            departing: If True, include "departing", else "landing".

        Returns:
            Dict with 'text' and 'audio_files' keys.
        """
        runway_words = PhoneticConverter.runway_to_phonetic(runway)
        action = "departing" if departing else "landing"

        words = [action, "RUNWAY"] + runway_words

        return {
            "text": " ".join(w.lower() if w.isupper() else w for w in words),
            "words": words,
            "audio_files": [self._get_audio_file(word) for word in words],
        }

    def build_time_phrase(self, hours: int, minutes: int) -> dict:
        """Build a time announcement phrase (Zulu time).

        Args:
            hours: Hours (0-23).
            minutes: Minutes (0-59).

        Returns:
            Dict with 'text' and 'audio_files' keys.
        """
        hour_words = PhoneticConverter.number_to_individual_digits(hours)
        minute_words = PhoneticConverter.number_to_individual_digits(minutes)

        # Pad to 2 digits each
        while len(hour_words) < 2:
            hour_words.insert(0, "zero")
        while len(minute_words) < 2:
            minute_words.insert(0, "zero")

        words = ["TIME"] + hour_words + minute_words + ["ZULU"]

        return {
            "text": " ".join(w.lower() if w.isupper() else w for w in words),
            "words": words,
            "audio_files": [self._get_audio_file(word) for word in words],
        }

    def _get_audio_file(self, word: str) -> str:
        """Get the audio file path for a word.

        Args:
            word: Word to get audio for.

        Returns:
            Path to the audio file.
        """
        # Map common words to their audio files
        word_lower = word.lower()

        # Check for phonetic alphabet
        if word_lower in PhoneticConverter.PHONETIC_LETTERS.values():
            return f"{self.audio_base_path}/atc/atis/{word_lower.upper()}.ogg"

        # Check for numbers
        digit_map = {v: k for k, v in PhoneticConverter.PHONETIC_NUMBERS.items()}
        if word_lower in digit_map:
            return f"{self.audio_base_path}/atc/atis/MSG_NUMBER_{digit_map[word_lower]}.ogg"

        # Default - assume file exists with word name
        return f"{self.audio_base_path}/atc/atis/{word_lower}.ogg"
