"""Tests for METAR parser."""


import pytest

from airborne.services.weather.metar_parser import METARParser
from airborne.services.weather.models import SkyCondition


class TestMETARParser:
    """Tests for METARParser class."""

    @pytest.fixture
    def parser(self) -> METARParser:
        """Create parser fixture."""
        return METARParser()

    def test_parse_standard_metar(self, parser: METARParser) -> None:
        """Test parsing a standard METAR string."""
        metar = "KPAO 251756Z 32008KT 10SM CLR 18/08 A3002"
        weather = parser.parse(metar)

        assert weather is not None
        assert weather.icao == "KPAO"
        assert weather.wind.direction == 320
        assert weather.wind.speed == 8
        assert weather.visibility == 10.0
        assert weather.temperature == 18
        assert weather.dewpoint == 8
        assert abs(weather.altimeter - 30.02) < 0.01
        assert weather.is_simulated is False

    def test_parse_wind_with_gusts(self, parser: METARParser) -> None:
        """Test parsing wind with gusts."""
        metar = "KSFO 251756Z 27015G25KT 10SM FEW020 SCT200 15/08 A2992"
        weather = parser.parse(metar)

        assert weather is not None
        assert weather.wind.direction == 270
        assert weather.wind.speed == 15
        assert weather.wind.gust == 25

    def test_parse_variable_wind(self, parser: METARParser) -> None:
        """Test parsing variable wind."""
        metar = "KJFK 251756Z VRB05KT 10SM CLR 20/15 A3010"
        weather = parser.parse(metar)

        assert weather is not None
        assert weather.wind.direction == -1  # Variable
        assert weather.wind.speed == 5

    def test_parse_calm_wind(self, parser: METARParser) -> None:
        """Test parsing calm wind."""
        metar = "KLAX 251756Z 00000KT 10SM CLR 22/12 A2998"
        weather = parser.parse(metar)

        assert weather is not None
        assert weather.wind.is_calm is True

    def test_parse_cloud_layers(self, parser: METARParser) -> None:
        """Test parsing multiple cloud layers."""
        metar = "KSEA 251756Z 18012KT 10SM FEW030 SCT060 BKN120 14/10 A2985"
        weather = parser.parse(metar)

        assert weather is not None
        assert len(weather.sky) == 3
        assert weather.sky[0].condition == SkyCondition.FEW
        assert weather.sky[0].altitude == 3000
        assert weather.sky[1].condition == SkyCondition.SCATTERED
        assert weather.sky[1].altitude == 6000
        assert weather.sky[2].condition == SkyCondition.BROKEN
        assert weather.sky[2].altitude == 12000

    def test_parse_overcast(self, parser: METARParser) -> None:
        """Test parsing overcast layer."""
        metar = "KORD 251756Z 36015G22KT 5SM OVC008 10/08 A2975"
        weather = parser.parse(metar)

        assert weather is not None
        assert len(weather.sky) == 1
        assert weather.sky[0].condition == SkyCondition.OVERCAST
        assert weather.sky[0].altitude == 800
        assert weather.ceiling == 800

    def test_parse_negative_temp(self, parser: METARParser) -> None:
        """Test parsing negative temperatures."""
        metar = "KDEN 251756Z 27008KT 10SM CLR M05/M12 A3025"
        weather = parser.parse(metar)

        assert weather is not None
        assert weather.temperature == -5
        assert weather.dewpoint == -12

    def test_parse_remarks(self, parser: METARParser) -> None:
        """Test parsing remarks section."""
        metar = "KPAO 251756Z 32008KT 10SM CLR 18/08 A3002 RMK AO2 SLP165 T01780083"
        weather = parser.parse(metar)

        assert weather is not None
        assert "AO2" in weather.remarks

    def test_parse_invalid_metar(self, parser: METARParser) -> None:
        """Test parsing invalid METAR returns None."""
        assert parser.parse("") is None
        assert parser.parse("INVALID") is None
        assert parser.parse("ABC") is None

    def test_parse_fractional_visibility(self, parser: METARParser) -> None:
        """Test parsing fractional visibility."""
        metar = "KJFK 251756Z 09010KT 1/2SM FG OVC002 08/08 A2990"
        weather = parser.parse(metar)

        assert weather is not None
        assert weather.visibility == 0.5

    def test_parse_low_visibility(self, parser: METARParser) -> None:
        """Test parsing low visibility."""
        metar = "KSFO 251756Z 27005KT 3SM BR SCT010 BKN020 12/11 A2995"
        weather = parser.parse(metar)

        assert weather is not None
        assert weather.visibility == 3.0

    def test_raw_metar_preserved(self, parser: METARParser) -> None:
        """Test that raw METAR string is preserved."""
        metar = "KPAO 251756Z 32008KT 10SM CLR 18/08 A3002"
        weather = parser.parse(metar)

        assert weather is not None
        assert weather.raw_metar == metar
