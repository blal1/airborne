"""Altimeter instrument manager.

Handles altimeter setting (QNH/barometric pressure) and pressure altitude calculations.
Supports both inHg (US) and hPa (metric/ICAO) units.

Typical usage:
    altimeter = AltimeterManager()
    altimeter.set_value(29.92)  # Set to standard pressure
    indicated_alt = altimeter.get_indicated_altitude(true_altitude_ft)
"""

from airborne.core.i18n import t
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)

# Standard atmospheric pressure
STANDARD_PRESSURE_INHG = 29.92
STANDARD_PRESSURE_HPA = 1013.25

# Conversion factors
INHG_TO_HPA = 33.8639
HPA_TO_INHG = 1.0 / INHG_TO_HPA

# Altimeter setting ranges
MIN_INHG = 27.50
MAX_INHG = 31.50
MIN_HPA = 931  # ~27.50 inHg
MAX_HPA = 1067  # ~31.50 inHg

# Step sizes for knob adjustment
STEP_INHG = 0.01
STEP_HPA = 1


class AltimeterManager:
    """Manages altimeter setting and pressure altitude calculations.

    The altimeter setting affects indicated altitude readings. Standard
    pressure is 29.92 inHg (1013.25 hPa).

    Attributes:
        setting_inhg: Current altimeter setting in inches of mercury.
        unit: Current display unit ("inHg" or "hPa").
    """

    def __init__(self, initial_inhg: float = STANDARD_PRESSURE_INHG) -> None:
        """Initialize altimeter with standard pressure.

        Args:
            initial_inhg: Initial setting in inHg (default: 29.92).
        """
        self._setting_inhg = initial_inhg
        self._unit = "inHg"  # Default to US units
        self._input_buffer = ""  # For numeric direct entry
        logger.info(f"Altimeter initialized: {self._setting_inhg:.2f} inHg")

    @property
    def setting_inhg(self) -> float:
        """Get current setting in inHg."""
        return self._setting_inhg

    @property
    def setting_hpa(self) -> float:
        """Get current setting in hPa."""
        return self._setting_inhg * INHG_TO_HPA

    @property
    def unit(self) -> str:
        """Get current display unit."""
        return self._unit

    def set_unit(self, unit: str) -> None:
        """Set display unit.

        Args:
            unit: "inHg" or "hPa".
        """
        if unit in ("inHg", "hPa"):
            self._unit = unit
            logger.debug(f"Altimeter unit set to {unit}")

    def toggle_unit(self) -> str:
        """Toggle between inHg and hPa.

        Returns:
            New unit string.
        """
        self._unit = "hPa" if self._unit == "inHg" else "inHg"
        logger.debug(f"Altimeter unit toggled to {self._unit}")
        return self._unit

    def set_value(self, value: float, unit: str | None = None) -> bool:
        """Set altimeter value.

        Args:
            value: Pressure value.
            unit: Unit of the value ("inHg" or "hPa"). If None, uses current unit.

        Returns:
            True if value was set successfully.
        """
        unit = unit or self._unit

        # Convert to inHg for internal storage
        inhg = value * HPA_TO_INHG if unit == "hPa" else value

        # Validate range
        if MIN_INHG <= inhg <= MAX_INHG:
            self._setting_inhg = inhg
            logger.info(f"Altimeter set to {inhg:.2f} inHg ({inhg * INHG_TO_HPA:.0f} hPa)")
            return True

        logger.warning(f"Altimeter value {value} {unit} out of range")
        return False

    def set_from_input(self, input_str: str) -> bool:
        """Set altimeter from numeric input string with auto-detection.

        Auto-detects unit based on value:
        - Values > 1100: treated as hPa (e.g., "1013" -> 1013 hPa)
        - Values < 3500: treated as inHg * 100 (e.g., "2992" -> 29.92 inHg)

        Args:
            input_str: Numeric string (e.g., "2992" or "1013").

        Returns:
            True if value was set successfully.
        """
        try:
            value = int(input_str)

            if value > 1100:
                # Treat as hPa
                return self.set_value(float(value), "hPa")
            elif value >= 2700 and value <= 3150:
                # Treat as inHg * 100 (e.g., 2992 -> 29.92)
                return self.set_value(value / 100.0, "inHg")
            else:
                logger.warning(f"Altimeter input {input_str} not recognized")
                return False

        except ValueError:
            logger.warning(f"Invalid altimeter input: {input_str}")
            return False

    def increase(self) -> float:
        """Increase altimeter setting by one step.

        Step size depends on current unit:
        - inHg: +0.01
        - hPa: +1 (converted to inHg)

        Returns:
            New value in current unit.
        """
        step_inhg = STEP_HPA * HPA_TO_INHG if self._unit == "hPa" else STEP_INHG
        new_inhg = min(MAX_INHG, self._setting_inhg + step_inhg)
        self._setting_inhg = new_inhg
        return self.get_display_value()

    def decrease(self) -> float:
        """Decrease altimeter setting by one step.

        Step size depends on current unit:
        - inHg: -0.01
        - hPa: -1 (converted to inHg)

        Returns:
            New value in current unit.
        """
        step_inhg = STEP_HPA * HPA_TO_INHG if self._unit == "hPa" else STEP_INHG
        new_inhg = max(MIN_INHG, self._setting_inhg - step_inhg)
        self._setting_inhg = new_inhg
        return self.get_display_value()

    def get_display_value(self) -> float:
        """Get current value in display unit.

        Returns:
            Value in current unit (inHg or hPa).
        """
        if self._unit == "hPa":
            return round(self._setting_inhg * INHG_TO_HPA)
        else:
            return round(self._setting_inhg, 2)

    def get_display_string(self) -> str:
        """Get formatted display string with unit.

        Returns:
            Formatted string like "29.92 inches" or "1013 hectopascals".
        """
        value = self.get_display_value()
        if self._unit == "hPa":
            return t("cockpit.altimeter_hpa", value=int(value))
        else:
            return t("cockpit.altimeter_inhg", value=f"{value:.2f}")

    def get_indicated_altitude(self, true_altitude_ft: float) -> float:
        """Calculate indicated altitude from true altitude.

        Uses the standard lapse rate: 1 inch Hg = 1000 feet.

        Args:
            true_altitude_ft: True (geometric) altitude in feet.

        Returns:
            Indicated altitude in feet.
        """
        # Pressure altitude correction
        # When altimeter is set higher than actual pressure, indicated altitude is lower
        # Formula: indicated = true + (setting - standard) * 1000
        pressure_correction = (self._setting_inhg - STANDARD_PRESSURE_INHG) * 1000.0
        return true_altitude_ft + pressure_correction

    def get_pressure_altitude(self, indicated_altitude_ft: float) -> float:
        """Calculate pressure altitude from indicated altitude.

        Pressure altitude is the altitude in standard atmosphere
        (altimeter set to 29.92).

        Args:
            indicated_altitude_ft: Indicated altitude in feet.

        Returns:
            Pressure altitude in feet.
        """
        pressure_correction = (self._setting_inhg - STANDARD_PRESSURE_INHG) * 1000.0
        return indicated_altitude_ft - pressure_correction

    # Input buffer methods for direct numeric entry
    def clear_input_buffer(self) -> None:
        """Clear the numeric input buffer."""
        self._input_buffer = ""

    def add_digit(self, digit: str) -> str:
        """Add a digit to the input buffer.

        Args:
            digit: Single digit character '0'-'9'.

        Returns:
            Current input buffer contents.
        """
        if digit.isdigit() and len(self._input_buffer) < 4:
            self._input_buffer += digit
        return self._input_buffer

    def get_input_buffer(self) -> str:
        """Get current input buffer contents."""
        return self._input_buffer

    def confirm_input(self) -> bool:
        """Confirm and apply the input buffer value.

        Returns:
            True if value was applied successfully.
        """
        if self._input_buffer:
            result = self.set_from_input(self._input_buffer)
            self._input_buffer = ""
            return result
        return False
