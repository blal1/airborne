"""Callsign builder for aviation phonetic alphabet.

Converts callsigns and numbers to audio file paths using the ICAO phonetic alphabet
and aviation number pronunciation.

Examples:
    >>> builder = CallsignBuilder()
    >>> builder.build_callsign("N123AB")
    ['data/speech/en/pilot/NOVEMBER.ogg', 'data/speech/en/pilot/MSG_NUMBER_1.ogg', ...]
"""

from pathlib import Path


class CallsignBuilder:
    """Build phonetic callsigns from registration numbers.

    Converts aircraft callsigns into sequences of audio file paths that can be
    played sequentially to pronounce the callsign using ICAO phonetic alphabet.

    The builder uses pre-generated audio files from data/speech/en/{voice}/
    and supports both pilot and ATC voices.

    Examples:
        >>> builder = CallsignBuilder(voice="pilot")
        >>> files = builder.build_callsign("N123AB")
        >>> # Returns list of OGG file paths to play in sequence
        >>> # ["NOVEMBER.ogg", "MSG_NUMBER_1.ogg", "MSG_NUMBER_2.ogg", ...]
    """

    # ICAO phonetic alphabet mapping
    PHONETIC_MAP = {
        "A": "ALPHA",
        "B": "BRAVO",
        "C": "CHARLIE",
        "D": "DELTA",
        "E": "ECHO",
        "F": "FOXTROT",
        "G": "GOLF",
        "H": "HOTEL",
        "I": "INDIA",
        "J": "JULIETT",  # ICAO spelling with two T's
        "K": "KILO",
        "L": "LIMA",
        "M": "MIKE",
        "N": "NOVEMBER",
        "O": "OSCAR",
        "P": "PAPA",
        "Q": "QUEBEC",
        "R": "ROMEO",
        "S": "SIERRA",
        "T": "TANGO",
        "U": "UNIFORM",
        "V": "VICTOR",
        "W": "WHISKEY",
        "X": "XRAY",
        "Y": "YANKEE",
        "Z": "ZULU",
    }

    # Digit mapping (0-8 use standard pronunciation, 9 uses "NINER")
    DIGIT_FILES = {
        "0": "MSG_NUMBER_0",
        "1": "MSG_NUMBER_1",
        "2": "MSG_NUMBER_2",
        "3": "MSG_NUMBER_3",
        "4": "MSG_NUMBER_4",
        "5": "MSG_NUMBER_5",
        "6": "MSG_NUMBER_6",
        "7": "MSG_NUMBER_7",
        "8": "MSG_NUMBER_8",
        "9": "NINER",  # Aviation pronunciation
    }

    def __init__(self, voice: str = "pilot", base_path: Path | None = None):
        """Initialize callsign builder.

        Args:
            voice: Voice directory to use ("pilot", "tower", "ground", "approach")
            base_path: Base speech directory (default: data/speech/en)
        """
        self.voice = voice
        if base_path is None:
            self.base_path = Path("data/speech/en")
        else:
            self.base_path = Path(base_path)

        # Determine voice directory
        if voice in ["tower", "ground", "approach"]:
            self.voice_dir = self.base_path / "atc" / voice
        else:
            self.voice_dir = self.base_path / voice

    def build_callsign(self, callsign: str) -> list[str]:
        """Convert callsign to list of audio file basenames.

        Args:
            callsign: Aircraft callsign (e.g., "N123AB", "C-GABC")

        Returns:
            List of audio file basenames for sequential playback.

        Examples:
            >>> builder.build_callsign("N123AB")
            ['NOVEMBER', 'MSG_NUMBER_1', 'MSG_NUMBER_2', 'MSG_NUMBER_3', 'ALPHA', 'BRAVO']
        """
        files = []
        callsign = callsign.upper().strip()

        for char in callsign:
            if char in self.PHONETIC_MAP:
                files.append(self.PHONETIC_MAP[char])
            elif char in self.DIGIT_FILES:
                files.append(self.DIGIT_FILES[char])
            # Skip spaces, hyphens, and other characters

        return files

    def build_frequency(self, frequency: float) -> list[str]:
        """Convert frequency to audio file basenames.

        Args:
            frequency: Radio frequency in MHz (e.g., 121.5)

        Returns:
            List of audio file basenames.

        Examples:
            >>> builder.build_frequency(121.5)
            ['MSG_NUMBER_1', 'MSG_NUMBER_2', 'MSG_NUMBER_1', 'DECIMAL', 'MSG_NUMBER_5']
            >>> builder.build_frequency(118.3)
            ['MSG_NUMBER_1', 'MSG_NUMBER_1', 'MSG_NUMBER_8', 'DECIMAL', 'MSG_NUMBER_3']
        """
        files = []
        freq_str = f"{frequency:.3f}"  # Format to 3 decimal places (e.g., "121.500")

        for char in freq_str:
            if char == ".":
                files.append("DECIMAL")
            elif char in self.DIGIT_FILES:
                files.append(self.DIGIT_FILES[char])

        return files

    def build_altitude(self, altitude: int, use_feet: bool = True) -> list[str]:
        """Convert altitude to audio file basenames.

        Aviation altitude is read in hundreds/thousands.

        Args:
            altitude: Altitude in feet (e.g., 2500)
            use_feet: If True, reads as aviation altitude (thousands/hundreds)

        Returns:
            List of audio file basenames.

        Examples:
            >>> builder.build_altitude(2500)
            ['MSG_NUMBER_2', 'THOUSAND', 'MSG_NUMBER_5', 'HUNDRED']
            >>> builder.build_altitude(1000)
            ['MSG_NUMBER_1', 'THOUSAND']
            >>> builder.build_altitude(500)
            ['MSG_NUMBER_5', 'HUNDRED']
        """
        files = []

        if not use_feet:
            # Just spell out the number digit by digit
            for char in str(altitude):
                if char in self.DIGIT_FILES:
                    files.append(self.DIGIT_FILES[char])
            return files

        # Aviation altitude pronunciation
        if altitude >= 1000:
            thousands = altitude // 1000
            files.append(self.DIGIT_FILES[str(thousands)])
            files.append("THOUSAND")
            altitude = altitude % 1000

        if altitude >= 100:
            hundreds = altitude // 100
            files.append(self.DIGIT_FILES[str(hundreds)])
            files.append("HUNDRED")

        return files

    def build_heading(self, heading: int) -> list[str]:
        """Convert heading to audio file basenames.

        Headings are read as three digits (e.g., 090, 180, 270).

        Args:
            heading: Magnetic heading in degrees (0-359)

        Returns:
            List of audio file basenames.

        Examples:
            >>> builder.build_heading(90)
            ['MSG_NUMBER_0', 'NINER', 'MSG_NUMBER_0']
            >>> builder.build_heading(180)
            ['MSG_NUMBER_1', 'MSG_NUMBER_8', 'MSG_NUMBER_0']
        """
        files = []
        # Normalize heading to 0-359
        heading = heading % 360
        # Format as 3 digits (e.g., 090)
        heading_str = f"{heading:03d}"

        for char in heading_str:
            files.append(self.DIGIT_FILES[char])

        return files

    def build_runway(self, runway: str) -> list[str]:
        """Convert runway designation to audio file basenames.

        Args:
            runway: Runway designation (e.g., "31", "09L", "27R")

        Returns:
            List of audio file basenames.

        Examples:
            >>> builder.build_runway("31")
            ['MSG_NUMBER_3', 'MSG_NUMBER_1']
            >>> builder.build_runway("09L")
            ['MSG_NUMBER_0', 'NINER', 'LIMA']  # "Zero niner left"
        """
        files = []
        runway = runway.upper()

        for char in runway:
            if char in self.DIGIT_FILES:
                files.append(self.DIGIT_FILES[char])
            elif char in self.PHONETIC_MAP:
                files.append(self.PHONETIC_MAP[char])

        return files

    def get_file_paths(self, filenames: list[str]) -> list[Path]:
        """Convert list of filenames to full file paths.

        Args:
            filenames: List of audio file basenames

        Returns:
            List of Path objects to the actual audio files.

        Examples:
            >>> files = builder.build_callsign("N123AB")
            >>> paths = builder.get_file_paths(files)
            >>> # Returns [Path("data/speech/en/pilot/NOVEMBER.ogg"), ...]
        """
        paths = []
        for filename in filenames:
            path = self.voice_dir / f"{filename}.ogg"
            paths.append(path)
        return paths
