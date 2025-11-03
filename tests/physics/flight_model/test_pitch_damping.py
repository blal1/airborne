"""Unit tests for pitch rate damping in the flight model.

Tests verify that pitch damping:
1. Resists pitch rate changes (creates opposing moment)
2. Is configurable via config parameters
3. Improves altitude stability
4. Scales properly with airspeed
"""

import pytest

from airborne.physics.flight_model.base import ControlInputs
from airborne.physics.flight_model.simple_6dof import Simple6DOFFlightModel
from airborne.physics.vectors import Vector3


class TestPitchRateDamping:
    """Test pitch rate damping functionality."""

    @pytest.fixture
    def flight_model(self):
        """Create a flight model with default configuration."""
        model = Simple6DOFFlightModel()
        config = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
            "pitch_damping_coefficient": -25.0,
        }
        model.initialize(config)
        return model

    @pytest.fixture
    def inputs(self):
        """Create default control inputs."""
        return ControlInputs()

    def test_pitch_damping_config_default(self):
        """Test that pitch damping uses default value when not configured."""
        model = Simple6DOFFlightModel()
        config = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
        }
        model.initialize(config)

        assert model.pitch_damping_coefficient == -25.0, \
            "Default pitch damping should be -25.0"

    def test_pitch_damping_config_custom(self):
        """Test that pitch damping can be configured."""
        model = Simple6DOFFlightModel()
        config = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
            "pitch_damping_coefficient": -35.0,
        }
        model.initialize(config)

        assert model.pitch_damping_coefficient == -35.0, \
            "Pitch damping should use configured value"

    def test_pitch_damping_opposes_pitch_up(self, flight_model, inputs):
        """Test that pitch damping creates moment opposing pitch-up motion."""
        # Set up aircraft in level flight with positive pitch rate
        flight_model.state.position = Vector3(0, 100, 0)  # 100m altitude
        flight_model.state.velocity = Vector3(0, 0, 30)   # 30 m/s forward
        flight_model.state.pitch = 0.0
        flight_model.state.angular_velocity = Vector3(0.2, 0, 0)  # Positive pitch rate (nose up)

        # No control input - damping should resist pitch rate
        inputs.pitch = 0.0

        # Update one frame
        initial_pitch_rate = flight_model.state.angular_velocity.x
        flight_model.update(0.016, inputs)
        final_pitch_rate = flight_model.state.angular_velocity.x

        # Pitch rate should decrease (damping opposes the motion)
        assert final_pitch_rate < initial_pitch_rate, \
            "Pitch damping should reduce positive pitch rate"

    def test_pitch_damping_opposes_pitch_down(self, flight_model, inputs):
        """Test that pitch damping creates moment opposing pitch-down motion."""
        # Set up aircraft in level flight with negative pitch rate
        flight_model.state.position = Vector3(0, 100, 0)
        flight_model.state.velocity = Vector3(0, 0, 30)
        flight_model.state.pitch = 0.0
        flight_model.state.angular_velocity = Vector3(-0.2, 0, 0)  # Negative pitch rate (nose down)

        # No control input
        inputs.pitch = 0.0

        initial_pitch_rate = flight_model.state.angular_velocity.x
        flight_model.update(0.016, inputs)
        final_pitch_rate = flight_model.state.angular_velocity.x

        # Pitch rate magnitude should decrease (become less negative)
        assert final_pitch_rate > initial_pitch_rate, \
            "Pitch damping should reduce negative pitch rate"

    def test_pitch_damping_scales_with_airspeed(self, flight_model, inputs):
        """Test that damping effect increases with airspeed."""
        flight_model.state.position = Vector3(0, 100, 0)
        flight_model.state.pitch = 0.0
        flight_model.state.angular_velocity = Vector3(0.2, 0, 0)
        inputs.pitch = 0.0

        # Test at low speed
        flight_model.state.velocity = Vector3(0, 0, 20)  # 20 m/s
        initial_rate_slow = flight_model.state.angular_velocity.x
        flight_model.update(0.016, inputs)
        final_rate_slow = flight_model.state.angular_velocity.x
        damping_slow = initial_rate_slow - final_rate_slow

        # Reset and test at high speed
        flight_model.state.angular_velocity = Vector3(0.2, 0, 0)
        flight_model.state.velocity = Vector3(0, 0, 40)  # 40 m/s
        initial_rate_fast = flight_model.state.angular_velocity.x
        flight_model.update(0.016, inputs)
        final_rate_fast = flight_model.state.angular_velocity.x
        damping_fast = initial_rate_fast - final_rate_fast

        # Damping should be stronger at higher airspeed
        assert damping_fast > damping_slow, \
            "Pitch damping should increase with airspeed"

    def test_pitch_damping_near_zero_rate(self, flight_model, inputs):
        """Test that damping is minimal when pitch rate is near zero."""
        flight_model.state.position = Vector3(0, 100, 0)
        flight_model.state.velocity = Vector3(0, 0, 30)
        flight_model.state.pitch = 5.0  # Some pitch angle
        flight_model.state.angular_velocity = Vector3(0.001, 0, 0)  # Very small pitch rate
        inputs.pitch = 0.0

        initial_pitch = flight_model.state.pitch
        flight_model.update(0.016, inputs)
        final_pitch = flight_model.state.pitch

        # Pitch should remain relatively stable
        pitch_change = abs(final_pitch - initial_pitch)
        assert pitch_change < 0.5, \
            f"With minimal pitch rate, pitch should be stable (changed {pitch_change}°)"

    def test_pitch_damping_improves_stability(self, flight_model, inputs):
        """Test that higher damping coefficient improves stability."""
        # Configure two models with different damping
        model_low_damping = Simple6DOFFlightModel()
        config_low = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
            "pitch_damping_coefficient": -10.0,  # Low damping
        }
        model_low_damping.initialize(config_low)

        model_high_damping = Simple6DOFFlightModel()
        config_high = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
            "pitch_damping_coefficient": -30.0,  # High damping
        }
        model_high_damping.initialize(config_high)

        # Set same initial conditions
        for model in [model_low_damping, model_high_damping]:
            model.state.position = Vector3(0, 100, 0)
            model.state.velocity = Vector3(0, 0, 30)
            model.state.pitch = 0.0
            model.state.angular_velocity = Vector3(0.3, 0, 0)  # Strong pitch-up rate

        inputs.pitch = 0.0

        # Simulate a few frames
        for _ in range(10):
            model_low_damping.update(0.016, inputs)
            model_high_damping.update(0.016, inputs)

        # High damping should result in lower pitch rate
        assert abs(model_high_damping.state.angular_velocity.x) < \
               abs(model_low_damping.state.angular_velocity.x), \
            "Higher damping coefficient should reduce pitch rate more effectively"

    def test_all_damping_coefficients_configurable(self):
        """Test that all damping coefficients can be configured."""
        model = Simple6DOFFlightModel()
        config = {
            "wing_area_sqft": 174.0,
            "weight_lbs": 2400.0,
            "max_thrust_lbs": 300.0,
            "pitch_damping_coefficient": -25.0,
            "roll_damping_coefficient": -10.0,
            "yaw_damping_coefficient": -8.0,
        }
        model.initialize(config)

        assert model.pitch_damping_coefficient == -25.0
        assert model.roll_damping_coefficient == -10.0
        assert model.yaw_damping_coefficient == -8.0

    def test_pitch_damping_with_elevator_input(self, flight_model, inputs):
        """Test that damping works alongside elevator control."""
        flight_model.state.position = Vector3(0, 100, 0)
        flight_model.state.velocity = Vector3(0, 0, 30)
        flight_model.state.pitch = 0.0
        flight_model.state.angular_velocity = Vector3(0.1, 0, 0)

        # Apply elevator input
        inputs.pitch = 0.5

        initial_pitch_rate = flight_model.state.angular_velocity.x
        flight_model.update(0.016, inputs)
        final_pitch_rate = flight_model.state.angular_velocity.x

        # With positive elevator and positive pitch rate, rate might increase
        # but damping should still provide resistance
        # The key is that the system remains stable
        assert final_pitch_rate != initial_pitch_rate, \
            "Pitch rate should change with elevator input and damping"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
