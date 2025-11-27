"""Tests for aviation phraseology helpers."""

import pytest

from airborne.services.atc.phraseology import PhoneticConverter, PhraseBuilder


class TestPhoneticConverter:
    """Tests for PhoneticConverter class."""

    def test_letter_to_phonetic(self) -> None:
        """Test letter to phonetic conversion."""
        assert PhoneticConverter.letter_to_phonetic("A") == "alpha"
        assert PhoneticConverter.letter_to_phonetic("b") == "bravo"
        assert PhoneticConverter.letter_to_phonetic("Z") == "zulu"

    def test_digit_to_phonetic(self) -> None:
        """Test digit to phonetic conversion."""
        assert PhoneticConverter.digit_to_phonetic("0") == "zero"
        assert PhoneticConverter.digit_to_phonetic("9") == "niner"
        assert PhoneticConverter.digit_to_phonetic("5") == "five"

    def test_callsign_to_phonetic(self) -> None:
        """Test callsign conversion."""
        result = PhoneticConverter.callsign_to_phonetic("N123AB")
        assert result == ["november", "one", "two", "three", "alpha", "bravo"]

    def test_callsign_to_phonetic_short(self) -> None:
        """Test short callsign conversion."""
        result = PhoneticConverter.callsign_to_phonetic("3AB")
        assert result == ["three", "alpha", "bravo"]

    def test_number_to_individual_digits(self) -> None:
        """Test number to digit conversion."""
        result = PhoneticConverter.number_to_individual_digits(320)
        assert result == ["three", "two", "zero"]

    def test_frequency_to_phonetic(self) -> None:
        """Test frequency conversion."""
        result = PhoneticConverter.frequency_to_phonetic(121.5)
        assert "point" in result
        assert result[0] == "one"
        assert result[1] == "two"
        assert result[2] == "one"
        assert result[3] == "point"
        assert result[4] == "five"

    def test_runway_to_phonetic_simple(self) -> None:
        """Test simple runway conversion."""
        result = PhoneticConverter.runway_to_phonetic("31")
        assert result == ["three", "one"]

    def test_runway_to_phonetic_with_suffix(self) -> None:
        """Test runway with L/R/C suffix."""
        result = PhoneticConverter.runway_to_phonetic("27L")
        assert result == ["two", "seven", "left"]

        result = PhoneticConverter.runway_to_phonetic("09R")
        assert result == ["zero", "niner", "right"]

        result = PhoneticConverter.runway_to_phonetic("18C")
        assert result == ["one", "eight", "center"]

    def test_altitude_to_words_low(self) -> None:
        """Test low altitude conversion."""
        result = PhoneticConverter.altitude_to_words(500)
        assert "five" in result
        assert "hundred" in result
        assert "feet" in result

    def test_altitude_to_words_high(self) -> None:
        """Test high altitude conversion."""
        result = PhoneticConverter.altitude_to_words(3500)
        assert "three" in result
        assert "thousand" in result
        assert "five" in result
        assert "hundred" in result
        assert "feet" in result

    def test_altitude_to_words_flight_level(self) -> None:
        """Test flight level conversion."""
        result = PhoneticConverter.altitude_to_words(25000, use_flight_level=True)
        assert "flight" in result
        assert "level" in result


class TestPhraseBuilder:
    """Tests for PhraseBuilder class."""

    @pytest.fixture
    def builder(self) -> PhraseBuilder:
        """Create phrase builder fixture."""
        return PhraseBuilder()

    def test_build_callsign_phrase(self, builder: PhraseBuilder) -> None:
        """Test callsign phrase building."""
        result = builder.build_callsign_phrase("N123AB")
        assert "text" in result
        assert "words" in result
        assert "audio_files" in result
        assert "november" in result["text"]

    def test_build_callsign_abbreviated(self, builder: PhraseBuilder) -> None:
        """Test abbreviated callsign phrase."""
        result = builder.build_callsign_phrase("N123AB", abbreviated=True)
        assert len(result["words"]) == 3
        assert result["words"] == ["three", "alpha", "bravo"]

    def test_build_wind_phrase_calm(self, builder: PhraseBuilder) -> None:
        """Test calm wind phrase."""
        result = builder.build_wind_phrase(0, 0)
        assert "calm" in result["text"]
        assert "WIND_CALM" in result["words"]  # Chunk ID

    def test_build_wind_phrase_normal(self, builder: PhraseBuilder) -> None:
        """Test normal wind phrase."""
        result = builder.build_wind_phrase(270, 15)
        assert "WIND" in result["words"]  # Chunk ID
        assert "AT" in result["words"]  # Chunk ID

    def test_build_wind_phrase_with_gusts(self, builder: PhraseBuilder) -> None:
        """Test gusty wind phrase."""
        result = builder.build_wind_phrase(320, 20, gust=30)
        assert "GUSTING" in result["words"]  # Chunk ID

    def test_build_wind_phrase_variable(self, builder: PhraseBuilder) -> None:
        """Test variable wind phrase."""
        result = builder.build_wind_phrase(-1, 5)
        assert "WIND_VARIABLE" in result["words"]  # Chunk ID

    def test_build_visibility_phrase_good(self, builder: PhraseBuilder) -> None:
        """Test good visibility phrase."""
        result = builder.build_visibility_phrase(10.0)
        assert "VISIBILITY" in result["words"]  # Chunk ID
        assert "one" in result["words"]
        assert "zero" in result["words"]

    def test_build_visibility_phrase_low(self, builder: PhraseBuilder) -> None:
        """Test low visibility phrase."""
        result = builder.build_visibility_phrase(0.5)
        assert "half" in result["words"]

    def test_build_altimeter_phrase(self, builder: PhraseBuilder) -> None:
        """Test altimeter phrase."""
        result = builder.build_altimeter_phrase(30.12)
        assert "ALTIMETER" in result["words"]  # Chunk ID
        # Should have digits 3, 0, 1, 2
        assert "three" in result["words"]
        assert "zero" in result["words"]

    def test_build_runway_phrase_departing(self, builder: PhraseBuilder) -> None:
        """Test runway phrase for departing."""
        result = builder.build_runway_phrase("31", departing=True)
        assert "departing" in result["words"]
        assert "RUNWAY" in result["words"]  # Chunk ID

    def test_build_runway_phrase_landing(self, builder: PhraseBuilder) -> None:
        """Test runway phrase for landing."""
        result = builder.build_runway_phrase("27L", departing=False)
        assert "landing" in result["words"]
        assert "left" in result["words"]

    def test_build_time_phrase(self, builder: PhraseBuilder) -> None:
        """Test time phrase building."""
        result = builder.build_time_phrase(14, 55)
        assert "ZULU" in result["words"]  # Chunk ID
        assert "TIME" in result["words"]  # Chunk ID
        # Should have TIME, 1, 4, 5, 5, ZULU
        assert result["words"][1:5] == ["one", "four", "five", "five"]
