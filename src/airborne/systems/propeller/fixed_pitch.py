"""Fixed-pitch propeller model.

This module implements a fixed-pitch propeller suitable for light aircraft
like the Cessna 172. Fixed-pitch props have a blade angle that cannot be
adjusted in flight, so efficiency varies significantly with airspeed.
"""

import math

from airborne.core.logging_system import get_logger
from airborne.systems.propeller.base import IPropeller

logger = get_logger(__name__)


class FixedPitchPropeller(IPropeller):
    """Fixed-pitch propeller model for piston aircraft.

    Models a propeller with fixed blade pitch angle, typical of light aircraft.
    Efficiency varies with advance ratio - optimal at one specific speed,
    less efficient at low/high speeds.

    Physics model:
    - Advance ratio: J = v / (n × D) where v=airspeed, n=rps, D=diameter
    - Static thrust (v≈0): T = sqrt(η × P × ρ × A)
    - Dynamic thrust (v>0): T = (η × P) / v
    - Efficiency η varies with J (peaks at cruise, drops at static/high speed)

    Examples:
        Cessna 172 propeller (75" diameter, climb pitch):
        >>> prop = FixedPitchPropeller(
        ...     diameter_m=1.905,
        ...     pitch_ratio=0.6,
        ...     efficiency_static=0.50,
        ...     efficiency_cruise=0.80
        ... )
        >>> # Static thrust (full power, v=0)
        >>> thrust = prop.calculate_thrust(
        ...     power_hp=180,
        ...     rpm=2700,
        ...     airspeed_mps=0.0,
        ...     air_density_kgm3=1.225
        ... )
        >>> print(f"Static thrust: {thrust:.0f} N")  # ~785 N (176 lbf)
    """

    def __init__(
        self,
        diameter_m: float,
        pitch_ratio: float = 0.6,
        efficiency_static: float = 0.50,
        efficiency_cruise: float = 0.80,
        cruise_advance_ratio: float = 0.6,
        static_thrust_multiplier: float = 1.45,
    ):
        """Initialize fixed-pitch propeller.

        Args:
            diameter_m: Propeller diameter in meters.
            pitch_ratio: Propeller pitch / diameter ratio (typical: 0.5-0.7).
            efficiency_static: Efficiency at zero airspeed (typical: 0.45-0.55).
            efficiency_cruise: Peak efficiency at cruise speed (typical: 0.75-0.85).
            cruise_advance_ratio: Advance ratio where efficiency peaks (typical: 0.5-0.7).
            static_thrust_multiplier: Empirical correction for momentum theory at low speeds.
                Momentum theory underestimates static thrust by ~30-40%. This multiplier
                corrects for that, fading to 1.0 at cruise speeds. Default: 1.45.

        Note:
            Pitch ratio determines optimal operating speed. Higher pitch = faster cruise,
            lower static thrust. Climb props use lower pitch (~0.5), cruise props higher (~0.7).

            The static_thrust_multiplier compensates for momentum theory's known limitation
            at static/low-speed conditions. Real propellers generate 30-40% more thrust than
            momentum theory predicts due to blade element effects not captured in the simplified model.
        """
        self.diameter = diameter_m
        self.pitch_ratio = pitch_ratio
        self.efficiency_static = efficiency_static
        self.efficiency_cruise = efficiency_cruise
        self.cruise_advance_ratio = cruise_advance_ratio
        self.static_thrust_multiplier = static_thrust_multiplier

        # Derived properties
        self.disc_area = math.pi * (diameter_m / 2.0) ** 2

        logger.info(
            f"FixedPitchPropeller initialized: D={diameter_m:.3f}m, "
            f"pitch_ratio={pitch_ratio:.2f}, "
            f"η_static={efficiency_static:.2f}, η_cruise={efficiency_cruise:.2f}, "
            f"static_multiplier={static_thrust_multiplier:.2f}"
        )

    def _get_static_thrust_correction(self, advance_ratio: float) -> float:
        """Calculate empirical correction for momentum theory at low speeds.

        Momentum theory underestimates thrust at static/low-speed conditions because
        it doesn't account for blade element effects. This correction factor is based
        on real propeller test data (NASA/NACA wind tunnel tests) and fades to 1.0
        at cruise speeds where momentum theory becomes accurate.

        Empirical data shows blade element effects persist to J≈0.6, not J=0.3.
        This correction keeps thrust realistic through the entire takeoff roll.

        Args:
            advance_ratio: Propeller advance ratio J = v / (n × D)

        Returns:
            Correction multiplier (1.0 = no correction, >1.0 = boost thrust)

        Note:
            Correction curve based on NACA propeller data:
            - J < 0.05 (static): Full multiplier (e.g., 1.45×)
            - 0.05 < J < 0.6 (takeoff/climb): Linear fade to 1.0
            - J ≥ 0.6 (cruise): No correction (1.0×)
        """
        if advance_ratio < 0.05:
            # Static/very low speed: apply full correction
            return self.static_thrust_multiplier
        elif advance_ratio < 0.8:
            # Takeoff/climb: linear fade from multiplier to 1.0
            # Extended to J=0.8 based on empirical propeller data showing
            # blade element effects persist through climb and into cruise
            # The correction accounts for 3D flow effects not captured in simple momentum theory
            fade_range = 0.8 - 0.05
            fade_progress = (advance_ratio - 0.05) / fade_range
            correction = (
                self.static_thrust_multiplier
                - (self.static_thrust_multiplier - 1.0) * fade_progress
            )
            return correction
        else:
            # High-speed cruise and above: no correction needed
            return 1.0

    def calculate_thrust(
        self,
        power_hp: float,
        rpm: float,
        airspeed_mps: float,
        air_density_kgm3: float,
    ) -> float:
        """Calculate thrust force in Newtons.

        Uses different formulas for static (v≈0) vs dynamic (v>0) conditions:
        - Static: T = sqrt(η_static × P × ρ × A) × correction - momentum theory with empirical correction
        - Dynamic: T = (η × P) / v - power-velocity relationship

        The static thrust multiplier corrects for momentum theory's underestimation at low speeds.

        Args:
            power_hp: Engine power output in horsepower.
            rpm: Engine/propeller RPM.
            airspeed_mps: True airspeed in meters per second.
            air_density_kgm3: Air density in kg/m³.

        Returns:
            Thrust force in Newtons.

        Note:
            Returns 0 if power or RPM is zero (engine not running).
        """
        # No thrust if engine not running
        if power_hp <= 0.0 or rpm <= 0.0:
            return 0.0

        # Convert horsepower to watts
        power_watts = power_hp * 745.7

        # Get propeller efficiency for current conditions
        efficiency = self.get_efficiency(airspeed_mps, rpm)

        # Calculate advance ratio for static thrust correction
        rps = rpm / 60.0 if rpm > 0 else 0.0
        advance_ratio = airspeed_mps / (rps * self.diameter) if rps > 0 else 0.0

        # Get static thrust correction (fades with speed)
        thrust_correction = self._get_static_thrust_correction(advance_ratio)

        # Calculate thrust based on airspeed regime
        if airspeed_mps < 1.0:
            # Static thrust: use momentum theory with empirical correction
            # T_static = sqrt(η × P × ρ × A) × correction
            # Where:
            #   η = propeller efficiency at static conditions
            #   P = power in Watts
            #   ρ = air density (kg/m³)
            #   A = propeller disc area (m²)
            #   correction = empirical multiplier for momentum theory limitation
            thrust = (
                math.sqrt(efficiency * power_watts * air_density_kgm3 * self.disc_area)
                * thrust_correction
            )
        else:
            # Dynamic thrust: Combined momentum and blade element theory
            # At low speeds, use momentum theory with correction
            # At high speeds, use power-velocity relationship

            # Momentum theory component (dominates at low speed)
            # Apply correction here too since we still need it at takeoff speeds
            thrust_momentum = (
                math.sqrt(efficiency * power_watts * air_density_kgm3 * self.disc_area)
                * thrust_correction
            )

            # Power-velocity component (dominates at high speed)
            # T = (η × P) / (v + v_induced)
            # Approximate v_induced from momentum theory: v_i = sqrt(T / (2 × ρ × A))
            # For simplicity, use a blended formula

            # Blended formula that transitions smoothly
            # At low v: thrust ≈ T_static
            # At high v: thrust ≈ (η × P) / v

            # Use empirical blend factor based on advance ratio
            rps = rpm / 60.0
            if rps > 0:
                advance_ratio = airspeed_mps / (rps * self.diameter)
            else:
                advance_ratio = 0

            # Blend between static and dynamic formulas smoothly
            # Keep static formula dominant through takeoff roll (J < 0.4)
            # since momentum theory (with correction) is more accurate at low speeds
            # At J < 0.20: mostly static formula (blend=0.05)
            # At J > 0.7: mostly dynamic formula (blend=0.90)
            # Smooth transition from 0.20 to 0.7
            if advance_ratio < 0.20:
                blend = 0.05  # 95% static, 5% dynamic - static formula dominates at low speed
            elif advance_ratio > 0.7:
                blend = 0.90  # 10% static, 90% dynamic - dynamic formula dominates at cruise
            else:
                # Linear interpolation from 0.05 to 0.90 over J=0.20 to J=0.7
                # This keeps momentum theory (which has proper correction) dominant through
                # the entire takeoff roll where it's more accurate than T=P/v
                blend = 0.05 + (advance_ratio - 0.20) * (0.90 - 0.05) / (0.7 - 0.20)

            # Dynamic thrust with induced velocity correction
            # The simple formula T = (η × P) / v is incorrect because it doesn't account for
            # induced velocity in the propeller slipstream.
            #
            # Corrected formula: T = (η × P) / (v + v_induced)
            # Where v_induced is estimated from momentum theory.
            #
            # From momentum theory: P = 2 × ρ × A × v_induced³
            # Therefore: v_induced = (P / (2 × ρ × A))^(1/3) at static
            #
            # However, v_induced decreases significantly with airspeed because the propeller
            # doesn't need to accelerate the air as much when there's incoming flow.
            # At static: v_induced ≈ 25-30 m/s for a 160 HP prop
            # At cruise: v_induced ≈ 5-8 m/s (much smaller due to incoming airflow)
            #
            # We scale v_induced down with advance ratio to model this physical effect.
            v_induced_static = (power_watts / (2.0 * air_density_kgm3 * self.disc_area)) ** (
                1.0 / 3.0
            )

            # Scale v_induced down with advance ratio - physically, induced velocity decreases
            # as the propeller has more incoming airflow to work with
            # At J=0: full v_induced (static)
            # At J=cruise: v_induced drops to ~20% of static value
            v_induced_scale = max(0.2, 1.0 - advance_ratio / self.cruise_advance_ratio * 0.8)
            v_induced = v_induced_static * v_induced_scale

            thrust_dynamic = (efficiency * power_watts) / (airspeed_mps + v_induced)

            # Blend the two methods
            thrust = (1.0 - blend) * thrust_momentum + blend * thrust_dynamic

            # Clamp to reasonable maximum
            # Real fixed-pitch propellers can produce 1.4-1.6× static thrust at J=0.2-0.3
            # Increased from 1.2× to 1.5× based on empirical propeller data
            max_thrust = thrust_momentum * 1.5
            thrust = min(thrust, max_thrust)

        # DIAGNOSTIC: Log propeller thrust calculation
        if not hasattr(self, "_thrust_log_counter"):
            self._thrust_log_counter = 0
        self._thrust_log_counter += 1

        # Log every 60 calls when receiving power (removed thrust threshold)
        if power_hp > 10.0 and self._thrust_log_counter % 60 == 0:
            import logging

            logger = logging.getLogger(__name__)

            # Calculate advance ratio for diagnostics
            rps = rpm / 60.0 if rpm > 0 else 0.0
            advance_ratio_diag = airspeed_mps / (rps * self.diameter) if rps > 0 else 0.0

            # Calculate blend info for diagnostic
            if airspeed_mps >= 1.0:
                if advance_ratio_diag < 0.20:  # Updated to match new threshold
                    blend_diag = 0.05
                elif advance_ratio_diag > 0.7:  # Updated to match new threshold
                    blend_diag = 0.90
                else:
                    blend_diag = 0.05 + (advance_ratio_diag - 0.20) * (0.90 - 0.05) / (0.7 - 0.20)
                logger.info(
                    f"[PROPELLER] power_in={power_hp:.1f}HP rpm={rpm:.0f} "
                    f"v={airspeed_mps:.1f}m/s η={efficiency:.3f} "
                    f"J={advance_ratio_diag:.3f} correction={thrust_correction:.3f} "
                    f"blend={blend_diag:.2f} THRUST={thrust:.1f}N"
                )
            else:
                logger.info(
                    f"[PROPELLER] power_in={power_hp:.1f}HP rpm={rpm:.0f} "
                    f"v={airspeed_mps:.1f}m/s η={efficiency:.3f} "
                    f"J={advance_ratio_diag:.3f} correction={thrust_correction:.3f} "
                    f"THRUST={thrust:.1f}N (static)"
                )

        return thrust

    def get_efficiency(self, airspeed_mps: float, rpm: float) -> float:
        """Get current propeller efficiency based on advance ratio.

        Efficiency curve for fixed-pitch propeller:
        - Low J (static, takeoff): Low efficiency (~0.50)
        - Optimal J (cruise): Peak efficiency (~0.80)
        - High J (high speed): Decreasing efficiency (prop stalling)

        Args:
            airspeed_mps: True airspeed in meters per second.
            rpm: Engine/propeller RPM.

        Returns:
            Propeller efficiency as fraction (0.0 to 1.0).

        Note:
            Uses simplified parabolic efficiency curve. Real propellers have
            complex efficiency maps based on blade design, Mach number, etc.
        """
        # No efficiency if not spinning
        if rpm <= 0.0:
            return 0.0

        # Calculate advance ratio: J = v / (n × D)
        # n = revolutions per second, D = diameter
        rps = rpm / 60.0
        advance_ratio = airspeed_mps / (rps * self.diameter) if rps > 0 else 0.0

        # Efficiency curve (simplified parabolic model)
        # Peaks at cruise_advance_ratio, drops off at low/high J
        if advance_ratio < 0.1:
            # Static or very low speed
            efficiency = self.efficiency_static
        elif advance_ratio < self.cruise_advance_ratio:
            # Accelerating to cruise - efficiency increases
            # Linear interpolation from static to cruise
            t = advance_ratio / self.cruise_advance_ratio
            efficiency = (
                self.efficiency_static + (self.efficiency_cruise - self.efficiency_static) * t
            )
        elif advance_ratio < self.cruise_advance_ratio * 1.5:
            # Near cruise - maintain peak efficiency
            efficiency = self.efficiency_cruise
        else:
            # High speed - prop begins to stall, efficiency drops
            # Quadratic falloff
            excess = advance_ratio - (self.cruise_advance_ratio * 1.5)
            falloff = min(0.5, excess * 0.3)  # Max 50% reduction
            efficiency = self.efficiency_cruise - falloff

        # Clamp to valid range
        return max(0.0, min(1.0, efficiency))

    def get_advance_ratio(self, airspeed_mps: float, rpm: float) -> float:
        """Get current advance ratio J = v / (n × D).

        Args:
            airspeed_mps: True airspeed in meters per second.
            rpm: Engine/propeller RPM.

        Returns:
            Advance ratio (dimensionless).

        Note:
            Advance ratio determines operating regime:
            - J < 0.2: Takeoff/climb
            - J = 0.5-0.7: Cruise
            - J > 1.0: High speed (propeller stalling)
        """
        if rpm <= 0:
            return 0.0

        rps = rpm / 60.0
        return airspeed_mps / (rps * self.diameter)
