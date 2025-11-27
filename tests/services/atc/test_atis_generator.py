"""Tests for dynamic ATIS generator."""

from datetime import UTC, datetime

import pytest

from airborne.services.atc.atis_generator import (
    INFORMATION_LETTERS,
    ATISAudioBuilder,
    ATISBroadcast,
    DynamicATISGenerator,
)
from airborne.services.weather import Weather, Wind


class TestDynamicATISGenerator:
    """Tests for DynamicATISGenerator class."""

    @pytest.fixture
    def generator(self) -> DynamicATISGenerator:
        """Create generator fixture."""
        gen = DynamicATISGenerator()
        gen.register_airport(
            "KPAO",
            "Palo Alto Airport",
            [("31", 310), ("13", 130)],
            tower_freq=118.6,
            ground_freq=121.7,
            atis_freq=127.35,
        )
        return gen

    @pytest.fixture
    def sample_weather(self) -> Weather:
        """Create sample weather fixture."""
        return Weather(
            icao="KPAO",
            observation_time=datetime(2024, 1, 15, 14, 55, 0, tzinfo=UTC),
            wind=Wind(direction=310, speed=8),
            visibility=10.0,
            sky=[],
            temperature=18,
            dewpoint=10,
            altimeter=30.05,
        )

    def test_generate_returns_broadcast(
        self, generator: DynamicATISGenerator, sample_weather: Weather
    ) -> None:
        """Test that generate returns ATISBroadcast."""
        broadcast = generator.generate("KPAO", weather=sample_weather)

        assert isinstance(broadcast, ATISBroadcast)
        assert broadcast.airport_icao == "KPAO"
        assert broadcast.airport_name == "Palo Alto Airport"

    def test_generate_includes_weather(
        self, generator: DynamicATISGenerator, sample_weather: Weather
    ) -> None:
        """Test that broadcast includes weather data."""
        broadcast = generator.generate("KPAO", weather=sample_weather)

        assert broadcast.weather == sample_weather
        assert "wind" in broadcast.text.lower()
        assert "visibility" in broadcast.text.lower()

    def test_generate_information_letter(
        self, generator: DynamicATISGenerator, sample_weather: Weather
    ) -> None:
        """Test information letter assignment."""
        broadcast = generator.generate("KPAO", weather=sample_weather)
        assert broadcast.information_letter in INFORMATION_LETTERS

    def test_generate_active_runway_from_wind(self, generator: DynamicATISGenerator) -> None:
        """Test active runway based on wind direction."""
        # Wind from 310 should favor runway 31
        weather_31 = Weather(
            icao="KPAO",
            observation_time=datetime.now(UTC),
            wind=Wind(direction=310, speed=15),
            visibility=10.0,
        )
        broadcast = generator.generate("KPAO", weather=weather_31)
        assert broadcast.active_runway == "31"

        # Wind from 130 should favor runway 13
        weather_13 = Weather(
            icao="KPAO",
            observation_time=datetime.now(UTC),
            wind=Wind(direction=130, speed=15),
            visibility=10.0,
        )
        # Force new letter to avoid cached result
        broadcast = generator.generate("KPAO", weather=weather_13, force_new_letter=True)
        assert broadcast.active_runway == "13"

    def test_generate_words_list(
        self, generator: DynamicATISGenerator, sample_weather: Weather
    ) -> None:
        """Test that generate produces word list with chunk IDs."""
        broadcast = generator.generate("KPAO", weather=sample_weather)

        assert len(broadcast.words) > 0
        # Should contain airport ICAO as chunk identifier (phrase-based audio)
        # The ICAO code maps to a single audio file containing the full airport name
        assert "KPAO" in broadcast.words
        # Should contain INFORMATION chunk ID (uppercase)
        assert "INFORMATION" in broadcast.words
        # Should contain phrase chunks (uppercase chunk IDs)
        assert "SKY_CLEAR" in broadcast.words or "SKY_CONDITION" in broadcast.words
        assert "LANDING_AND_DEPARTING_RUNWAY" in broadcast.words
        # Check split advise chunks
        assert "ADVISE_ON_INITIAL_CONTACT" in broadcast.words
        assert "YOU_HAVE_INFORMATION" in broadcast.words

    def test_letter_advances_on_weather_change(self, generator: DynamicATISGenerator) -> None:
        """Test that letter advances when weather changes significantly."""
        weather1 = Weather(
            icao="KPAO",
            observation_time=datetime.now(UTC),
            wind=Wind(direction=270, speed=10),
            visibility=10.0,
        )
        broadcast1 = generator.generate("KPAO", weather=weather1)
        letter1 = broadcast1.information_letter

        # Significant wind change should trigger new letter
        weather2 = Weather(
            icao="KPAO",
            observation_time=datetime.now(UTC),
            wind=Wind(direction=90, speed=20),  # 180 degree change + speed change
            visibility=10.0,
        )
        broadcast2 = generator.generate("KPAO", weather=weather2)
        letter2 = broadcast2.information_letter

        # Letter should have changed
        letter1_idx = INFORMATION_LETTERS.index(letter1)
        letter2_idx = INFORMATION_LETTERS.index(letter2)
        # Should be the next letter (wrapping around)
        expected_idx = (letter1_idx + 1) % len(INFORMATION_LETTERS)
        assert letter2_idx == expected_idx

    def test_unregistered_airport(self, generator: DynamicATISGenerator) -> None:
        """Test generating ATIS for unregistered airport uses defaults."""
        broadcast = generator.generate("KXYZ")

        assert broadcast.airport_icao == "KXYZ"
        assert "KXYZ Airport" in broadcast.airport_name

    def test_text_contains_required_elements(
        self, generator: DynamicATISGenerator, sample_weather: Weather
    ) -> None:
        """Test that ATIS text contains all required elements."""
        broadcast = generator.generate("KPAO", weather=sample_weather)
        text = broadcast.text.lower()

        # All required ATIS elements
        assert "palo alto airport" in text
        assert "information" in text
        assert "wind" in text
        assert "visibility" in text
        assert "temperature" in text
        assert "dewpoint" in text
        assert "altimeter" in text
        assert "runway" in text
        assert "advise" in text


class TestATISAudioBuilder:
    """Tests for ATISAudioBuilder class."""

    @pytest.fixture
    def builder(self) -> ATISAudioBuilder:
        """Create audio builder fixture."""
        return ATISAudioBuilder()

    def test_get_audio_files(self, builder: ATISAudioBuilder) -> None:
        """Test getting audio file paths."""
        words = ["wind", "three", "one", "zero"]
        files = builder.get_audio_files(words)

        # Should return list of paths (may be empty if files don't exist)
        assert isinstance(files, list)

    def test_has_all_audio(self, builder: ATISAudioBuilder) -> None:
        """Test checking for missing audio files."""
        words = ["alpha", "bravo", "charlie"]
        has_all, missing = builder.has_all_audio(words)

        # Returns tuple (bool, list)
        assert isinstance(has_all, bool)
        assert isinstance(missing, list)

    def test_generate_missing_audio_list(self, builder: ATISAudioBuilder) -> None:
        """Test generating list of missing audio."""
        words = ["some_fake_word_xyz", "another_fake_word"]
        to_generate = builder.generate_missing_audio_list(words)

        assert isinstance(to_generate, dict)
        # Should list the missing words
        assert len(to_generate) > 0
