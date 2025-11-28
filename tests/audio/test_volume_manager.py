"""Tests for volume manager."""

import pytest

from airborne.audio.volume_manager import VolumeManager


class TestVolumeManager:
    """Test suite for VolumeManager class."""

    @pytest.fixture
    def vol_mgr(self) -> VolumeManager:
        """Create VolumeManager instance."""
        return VolumeManager()

    def test_initial_master_volume(self, vol_mgr: VolumeManager) -> None:
        """Test master volume initializes to 1.0."""
        assert vol_mgr.get_master_volume() == 1.0

    def test_initial_category_volumes(self, vol_mgr: VolumeManager) -> None:
        """Test all category volumes initialize to 1.0."""
        categories = ["music", "engine", "environment", "ui", "cockpit", "atc", "pilot", "cue"]
        for category in categories:
            assert vol_mgr.get_category_volume(category) == 1.0  # type: ignore[arg-type]

    def test_set_master_volume(self, vol_mgr: VolumeManager) -> None:
        """Test setting master volume."""
        vol_mgr.set_master_volume(0.5)
        assert vol_mgr.get_master_volume() == 0.5

    def test_set_master_volume_clamps_low(self, vol_mgr: VolumeManager) -> None:
        """Test master volume clamps to minimum 0.0."""
        vol_mgr.set_master_volume(-0.5)
        assert vol_mgr.get_master_volume() == 0.0

    def test_set_master_volume_clamps_high(self, vol_mgr: VolumeManager) -> None:
        """Test master volume clamps to maximum 1.0."""
        vol_mgr.set_master_volume(1.5)
        assert vol_mgr.get_master_volume() == 1.0

    def test_set_category_volume(self, vol_mgr: VolumeManager) -> None:
        """Test setting category volume."""
        vol_mgr.set_category_volume("music", 0.7)
        assert vol_mgr.get_category_volume("music") == 0.7

    def test_set_category_volume_clamps_low(self, vol_mgr: VolumeManager) -> None:
        """Test category volume clamps to minimum 0.0."""
        vol_mgr.set_category_volume("music", -0.3)
        assert vol_mgr.get_category_volume("music") == 0.0

    def test_set_category_volume_clamps_high(self, vol_mgr: VolumeManager) -> None:
        """Test category volume clamps to maximum 1.0."""
        vol_mgr.set_category_volume("music", 2.0)
        assert vol_mgr.get_category_volume("music") == 1.0

    def test_get_unknown_category_defaults_to_one(self, vol_mgr: VolumeManager) -> None:
        """Test unknown category returns 1.0."""
        assert vol_mgr.get_category_volume("unknown") == 1.0  # type: ignore[arg-type]

    def test_get_final_volume_default(self, vol_mgr: VolumeManager) -> None:
        """Test final volume with default settings is 1.0."""
        assert vol_mgr.get_final_volume("music") == 1.0

    def test_get_final_volume_with_master(self, vol_mgr: VolumeManager) -> None:
        """Test final volume applies master volume."""
        vol_mgr.set_master_volume(0.5)
        assert vol_mgr.get_final_volume("music") == 0.5

    def test_get_final_volume_with_category(self, vol_mgr: VolumeManager) -> None:
        """Test final volume applies category volume."""
        vol_mgr.set_category_volume("music", 0.6)
        assert vol_mgr.get_final_volume("music") == 0.6

    def test_get_final_volume_hierarchical(self, vol_mgr: VolumeManager) -> None:
        """Test final volume is master * category."""
        vol_mgr.set_master_volume(0.8)
        vol_mgr.set_category_volume("music", 0.5)
        assert vol_mgr.get_final_volume("music") == pytest.approx(0.4)

    def test_master_affects_all_categories(self, vol_mgr: VolumeManager) -> None:
        """Test master volume affects all categories."""
        vol_mgr.set_master_volume(0.5)
        vol_mgr.set_category_volume("music", 0.8)
        vol_mgr.set_category_volume("engine", 0.6)

        assert vol_mgr.get_final_volume("music") == pytest.approx(0.4)
        assert vol_mgr.get_final_volume("engine") == pytest.approx(0.3)

    def test_mute_via_master(self, vol_mgr: VolumeManager) -> None:
        """Test muting via master volume."""
        vol_mgr.set_master_volume(0.0)
        vol_mgr.set_category_volume("music", 1.0)

        assert vol_mgr.get_final_volume("music") == 0.0

    def test_mute_via_category(self, vol_mgr: VolumeManager) -> None:
        """Test muting via category volume."""
        vol_mgr.set_master_volume(1.0)
        vol_mgr.set_category_volume("music", 0.0)

        assert vol_mgr.get_final_volume("music") == 0.0

    def test_independent_categories(self, vol_mgr: VolumeManager) -> None:
        """Test categories are independent."""
        vol_mgr.set_category_volume("music", 0.5)
        vol_mgr.set_category_volume("engine", 0.8)

        assert vol_mgr.get_category_volume("music") == 0.5
        assert vol_mgr.get_category_volume("engine") == 0.8

    def test_all_categories_supported(self, vol_mgr: VolumeManager) -> None:
        """Test all defined categories work correctly."""
        categories = ["music", "engine", "environment", "ui", "cockpit", "atc", "pilot", "cue"]

        for i, category in enumerate(categories):
            volume = (i + 1) * 0.1
            vol_mgr.set_category_volume(category, volume)  # type: ignore[arg-type]
            assert vol_mgr.get_category_volume(category) == pytest.approx(volume)  # type: ignore[arg-type]
