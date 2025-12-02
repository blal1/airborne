"""Performance Display (FMC) for aircraft performance calculations.

This module provides a multi-page display system showing:
- Weight & Balance (total weight, CG, station breakdown)
- V-speeds (stall, rotation, climb speeds)
- Takeoff Performance (distances, climb rate)

Navigation:
- F4: Open/close performance display
- Up/Down: Navigate between pages
- Enter: Open page submenu
- ESC: Close display
"""

from typing import Any

from airborne.core.i18n import t
from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic
from airborne.systems.performance.performance_calculator import PerformanceCalculator
from airborne.systems.weight_balance.weight_balance_system import WeightBalanceSystem
from airborne.ui.menu import Menu, MenuOption

logger = get_logger(__name__)


class PerformanceDisplay:
    """Multi-page performance display system (FMC/PFD).

    Displays aircraft performance data across multiple pages:
    1. Weight & Balance (W&B)
    2. V-speeds
    3. Takeoff Performance

    Responsibilities:
    - Display current weight and CG data
    - Calculate and show V-speeds for current weight
    - Calculate and show takeoff distances and climb rates
    - TTS announcements for navigation and values

    Examples:
        >>> display = PerformanceDisplay(wb_system, perf_calc, message_queue)
        >>> display.open()  # Opens to page 1 (Weight & Balance)
        >>> display.next_page()  # Move to page 2 (V-speeds)
        >>> display.read_current_page()  # Announce page content via TTS
    """

    def __init__(
        self,
        wb_system: WeightBalanceSystem | None,
        perf_calculator: PerformanceCalculator | None,
        message_queue: MessageQueue | None = None,
    ):
        """Initialize performance display.

        Args:
            wb_system: Weight and balance system instance.
            perf_calculator: Performance calculator instance.
            message_queue: Message queue for TTS announcements.
        """
        self.wb_system = wb_system
        self.perf_calculator = perf_calculator
        self._message_queue = message_queue

        self._state = "CLOSED"  # CLOSED, OPEN
        self._current_page = 1  # 1=W&B, 2=V-speeds, 3=Takeoff
        self._total_pages = 3

        # Create page menus
        self._wb_menu: WeightBalanceMenu | None = None
        self._vspeeds_menu: VSpeedsMenu | None = None
        self._takeoff_menu: TakeoffMenu | None = None

        if wb_system and perf_calculator:
            self._wb_menu = WeightBalanceMenu(wb_system, message_queue)
            self._vspeeds_menu = VSpeedsMenu(wb_system, perf_calculator, message_queue)
            self._takeoff_menu = TakeoffMenu(wb_system, perf_calculator, message_queue)

        logger.info("PerformanceDisplay initialized with 3 pages")

    def open(self) -> bool:
        """Open the performance display.

        Returns:
            True if opened successfully, False otherwise.
        """
        if self._state == "OPEN":
            logger.warning("PerformanceDisplay already open")
            return False

        if not self.wb_system or not self.perf_calculator:
            logger.warning("PerformanceDisplay missing systems (W&B or PerformanceCalculator)")
            self._speak(t("fmc.not_available"))
            return False

        self._state = "OPEN"
        self._current_page = 1
        logger.info("PerformanceDisplay opened to page 1")

        # Announce opening with page title
        self._speak(f"{t('fmc.opened')}, {t('fmc.page_1')}, {t('fmc.wb_title')}", interrupt=True)

        return True

    def close(self) -> bool:
        """Close the performance display.

        Returns:
            True if closed successfully, False otherwise.
        """
        if self._state == "CLOSED":
            return False

        self._state = "CLOSED"
        logger.info("PerformanceDisplay closed")

        self._speak(t("fmc.closed"), interrupt=True)

        return True

    def next_page(self) -> bool:
        """Navigate to next page.

        Returns:
            True if moved to next page, False if at last page.
        """
        if self._state != "OPEN":
            return False

        if self._current_page < self._total_pages:
            self._current_page += 1
            logger.debug(f"PerformanceDisplay: page {self._current_page}")
            self._announce_page()
            return True

        return False

    def previous_page(self) -> bool:
        """Navigate to previous page.

        Returns:
            True if moved to previous page, False if at first page.
        """
        if self._state != "OPEN":
            return False

        if self._current_page > 1:
            self._current_page -= 1
            logger.debug(f"PerformanceDisplay: page {self._current_page}")
            self._announce_page()
            return True

        return False

    def read_current_page(self) -> bool:
        """Open submenu for current page.

        Returns:
            True if menu opened successfully, False otherwise.
        """
        if self._state != "OPEN":
            return False

        # Open the appropriate menu
        if self._current_page == 1 and self._wb_menu:
            return self._wb_menu.open()
        elif self._current_page == 2 and self._vspeeds_menu:
            return self._vspeeds_menu.open()
        elif self._current_page == 3 and self._takeoff_menu:
            return self._takeoff_menu.open()

        return False

    def is_open(self) -> bool:
        """Check if display is open.

        Returns:
            True if open, False otherwise.
        """
        return self._state == "OPEN"

    def get_current_page(self) -> int:
        """Get current page number.

        Returns:
            Current page number (1-3).
        """
        return self._current_page

    def get_active_menu(self) -> Menu | None:
        """Get currently active menu.

        Returns:
            Active menu instance or None if no menu is open.
        """
        if self._wb_menu and self._wb_menu.is_open():
            return self._wb_menu
        if self._vspeeds_menu and self._vspeeds_menu.is_open():
            return self._vspeeds_menu
        if self._takeoff_menu and self._takeoff_menu.is_open():
            return self._takeoff_menu
        return None

    def has_active_menu(self) -> bool:
        """Check if any page menu is currently open.

        Returns:
            True if a menu is open, False otherwise.
        """
        return self.get_active_menu() is not None

    def close_active_menu(self) -> bool:
        """Close the currently active menu.

        Returns:
            True if a menu was closed, False if no menu was open.
        """
        active_menu = self.get_active_menu()
        if active_menu:
            active_menu.close()
            return True
        return False

    # Page-specific reading methods

    def _read_weight_balance_page(self) -> None:
        """Read Weight & Balance page data via TTS."""
        if not self.wb_system:
            return

        # Calculate current data
        total_weight = self.wb_system.calculate_total_weight()
        cg = self.wb_system.calculate_cg()
        within_limits, status_msg = self.wb_system.is_within_limits()

        # Build TTS message
        weight_speech = self._number_to_speech(int(round(total_weight / 10.0) * 10))
        cg_speech = self._number_to_speech(int(cg))
        status_text = t("fmc.wb_within_limits") if within_limits else t("fmc.wb_out_of_limits")

        message = (
            f"{t('fmc.wb_title')}. "
            f"{t('fmc.wb_total_weight')} {weight_speech} {t('fmc.pounds')}. "
            f"{t('fmc.wb_cg_position')} {cg_speech} {t('fmc.inches')}. "
            f"{status_text}."
        )

        self._speak(message, interrupt=True)

        logger.info(f"Read W&B: {total_weight:.0f} lbs, CG={cg:.1f} in, {status_msg}")

    def _read_vspeeds_page(self) -> None:
        """Read V-speeds page data via TTS."""
        if not self.wb_system or not self.perf_calculator:
            return

        # Calculate V-speeds
        weight = self.wb_system.calculate_total_weight()
        vspeeds = self.perf_calculator.calculate_vspeeds(weight)

        # Build TTS message
        weight_speech = self._number_to_speech(int(round(weight / 10.0) * 10))
        knots = t("fmc.knots")

        message = (
            f"{t('fmc.vs_title')}. "
            f"{t('fmc.vs_weight')} {weight_speech} {t('fmc.pounds')}. "
            f"{t('fmc.vs_vstall')} {int(vspeeds.v_s)} {knots}. "
            f"{t('fmc.vs_vr')} {int(vspeeds.v_r)} {knots}. "
            f"{t('fmc.vs_vx')} {int(vspeeds.v_x)} {knots}. "
            f"{t('fmc.vs_vy')} {int(vspeeds.v_y)} {knots}."
        )

        self._speak(message, interrupt=True)

        logger.info(
            f"Read V-speeds: V_S={vspeeds.v_s:.0f}, V_R={vspeeds.v_r:.0f}, "
            f"V_X={vspeeds.v_x:.0f}, V_Y={vspeeds.v_y:.0f} KIAS"
        )

    def _read_takeoff_page(self) -> None:
        """Read Takeoff Performance page data via TTS."""
        if not self.wb_system or not self.perf_calculator:
            return

        # Calculate takeoff performance
        weight = self.wb_system.calculate_total_weight()
        takeoff = self.perf_calculator.calculate_takeoff_distance(weight)
        climb_rate = self.perf_calculator.calculate_climb_rate(weight)

        # Build TTS message
        weight_speech = self._number_to_speech(int(round(weight / 10.0) * 10))
        feet = t("fmc.feet")

        message = (
            f"{t('fmc.to_title')}. "
            f"{t('fmc.to_weight')} {weight_speech} {t('fmc.pounds')}. "
            f"{t('fmc.to_ground_roll')} {self._number_to_speech(int(takeoff.ground_roll_ft))} {feet}. "
            f"{t('fmc.to_distance_50')} {self._number_to_speech(int(takeoff.distance_50ft))} {feet}. "
            f"{t('fmc.to_climb_rate')} {self._number_to_speech(int(climb_rate))} {t('fmc.fpm')}."
        )

        self._speak(message, interrupt=True)

        logger.info(
            f"Read takeoff: ground_roll={takeoff.ground_roll_ft:.0f} ft, "
            f"distance_50={takeoff.distance_50ft:.0f} ft, climb={climb_rate:.0f} fpm"
        )

    def _announce_page(self) -> None:
        """Announce current page number and title via TTS."""
        if self._current_page == 1:
            self._speak(f"{t('fmc.page_1')}, {t('fmc.wb_title')}", interrupt=True)
        elif self._current_page == 2:
            self._speak(f"{t('fmc.page_2')}, {t('fmc.vs_title')}", interrupt=True)
        elif self._current_page == 3:
            self._speak(f"{t('fmc.page_3')}, {t('fmc.to_title')}", interrupt=True)

    # Helper methods for TTS

    def _number_to_speech(self, number: int) -> str:
        """Convert number to speakable string.

        Args:
            number: Integer number.

        Returns:
            String representation of the number for TTS.
        """
        # TTS engines can speak numbers directly
        return str(number)

    def _speak(
        self,
        message: str | list[str],
        priority: str = "high",
        interrupt: bool = False,
    ) -> None:
        """Speak message via TTS.

        Args:
            message: Message text or list of texts to speak.
            priority: Priority level (high, normal, low).
            interrupt: Whether to interrupt current speech.
        """
        if not self._message_queue:
            return

        # Handle list of messages by joining them
        if isinstance(message, list):
            text = " ".join(str(m) for m in message if m)
        else:
            text = message

        if not text:
            return

        self._message_queue.publish(
            Message(
                sender="performance_display",
                recipients=["*"],
                topic=MessageTopic.TTS_SPEAK,
                data={"text": text, "priority": priority, "interrupt": interrupt},
                priority=MessagePriority.HIGH if priority == "high" else MessagePriority.NORMAL,
            )
        )


class WeightBalanceMenu(Menu):
    """Menu for Weight & Balance page."""

    def __init__(
        self,
        wb_system: WeightBalanceSystem,
        message_queue: MessageQueue | None = None,
    ):
        """Initialize W&B menu.

        Args:
            wb_system: Weight and balance system.
            message_queue: Message queue for TTS.
        """
        super().__init__(message_queue=message_queue, sender_name="weight_balance_menu")
        self.wb_system = wb_system

    def _build_options(self, context: Any) -> list[MenuOption]:
        """Build menu options for W&B page."""
        total_weight = self.wb_system.calculate_total_weight()
        cg = self.wb_system.calculate_cg()
        within_limits, status_msg = self.wb_system.is_within_limits()

        weight_label = f"{t('fmc.wb_total_weight')}: {total_weight:.0f} lbs"
        cg_label = f"{t('fmc.wb_cg_position')}: {cg:.1f} inches"
        status_text = t("fmc.wb_within_limits") if within_limits else t("fmc.wb_out_of_limits")

        return [
            MenuOption(
                key="1",
                label=weight_label,
                message_key=f"{t('fmc.wb_total_weight')} {int(round(total_weight / 10.0) * 10)} {t('fmc.pounds')}",
                data={"value": total_weight, "type": "weight"},
            ),
            MenuOption(
                key="2",
                label=cg_label,
                message_key=f"{t('fmc.wb_cg_position')} {int(cg)} {t('fmc.inches')}",
                data={"value": cg, "type": "cg"},
            ),
            MenuOption(
                key="3",
                label=f"Status: {status_msg}",
                message_key=status_text,
                data={"within_limits": within_limits},
            ),
        ]

    def _handle_selection(self, option: MenuOption) -> None:
        """Handle menu option selection."""
        # Speak the message_key which already contains the full translated message
        self._speak(option.message_key, interrupt=True)

    def _get_menu_opened_message(self) -> str:
        """Get TTS message for menu opened."""
        return t("fmc.wb_title")

    def _get_menu_closed_message(self) -> str:
        """Get TTS message for menu closed."""
        return t("common.menu_closed")

    def _get_invalid_option_message(self) -> str:
        """Get TTS message for invalid option."""
        return t("common.invalid_option")


class VSpeedsMenu(Menu):
    """Menu for V-speeds page."""

    def __init__(
        self,
        wb_system: WeightBalanceSystem,
        perf_calculator: PerformanceCalculator,
        message_queue: MessageQueue | None = None,
    ):
        """Initialize V-speeds menu.

        Args:
            wb_system: Weight and balance system.
            perf_calculator: Performance calculator.
            message_queue: Message queue for TTS.
        """
        super().__init__(message_queue=message_queue, sender_name="vspeeds_menu")
        self.wb_system = wb_system
        self.perf_calculator = perf_calculator

    def _build_options(self, context: Any) -> list[MenuOption]:
        """Build menu options for V-speeds page."""
        weight = self.wb_system.calculate_total_weight()
        vspeeds = self.perf_calculator.calculate_vspeeds(weight)
        knots = t("fmc.knots")

        return [
            MenuOption(
                key="1",
                label=f"V-Stall: {vspeeds.v_s:.0f} KIAS",
                message_key=f"{t('fmc.vs_vstall')} {int(vspeeds.v_s)} {knots}",
                data={"value": vspeeds.v_s, "type": "vspeed"},
            ),
            MenuOption(
                key="2",
                label=f"V-Rotate: {vspeeds.v_r:.0f} KIAS",
                message_key=f"{t('fmc.vs_vr')} {int(vspeeds.v_r)} {knots}",
                data={"value": vspeeds.v_r, "type": "vspeed"},
            ),
            MenuOption(
                key="3",
                label=f"V-X (Best Angle): {vspeeds.v_x:.0f} KIAS",
                message_key=f"{t('fmc.vs_vx')} {int(vspeeds.v_x)} {knots}",
                data={"value": vspeeds.v_x, "type": "vspeed"},
            ),
            MenuOption(
                key="4",
                label=f"V-Y (Best Rate): {vspeeds.v_y:.0f} KIAS",
                message_key=f"{t('fmc.vs_vy')} {int(vspeeds.v_y)} {knots}",
                data={"value": vspeeds.v_y, "type": "vspeed"},
            ),
        ]

    def _handle_selection(self, option: MenuOption) -> None:
        """Handle menu option selection."""
        # Speak the message_key which already contains the full translated message
        self._speak(option.message_key, interrupt=True)

    def _get_menu_opened_message(self) -> str:
        """Get TTS message for menu opened."""
        return t("fmc.vs_title")

    def _get_menu_closed_message(self) -> str:
        """Get TTS message for menu closed."""
        return t("common.menu_closed")

    def _get_invalid_option_message(self) -> str:
        """Get TTS message for invalid option."""
        return t("common.invalid_option")


class TakeoffMenu(Menu):
    """Menu for Takeoff Performance page."""

    def __init__(
        self,
        wb_system: WeightBalanceSystem,
        perf_calculator: PerformanceCalculator,
        message_queue: MessageQueue | None = None,
    ):
        """Initialize takeoff menu.

        Args:
            wb_system: Weight and balance system.
            perf_calculator: Performance calculator.
            message_queue: Message queue for TTS.
        """
        super().__init__(message_queue=message_queue, sender_name="takeoff_menu")
        self.wb_system = wb_system
        self.perf_calculator = perf_calculator

    def _build_options(self, context: Any) -> list[MenuOption]:
        """Build menu options for takeoff page."""
        weight = self.wb_system.calculate_total_weight()
        takeoff = self.perf_calculator.calculate_takeoff_distance(weight)
        climb_rate = self.perf_calculator.calculate_climb_rate(weight)
        feet = t("fmc.feet")

        return [
            MenuOption(
                key="1",
                label=f"Ground Roll: {takeoff.ground_roll_ft:.0f} ft",
                message_key=f"{t('fmc.to_ground_roll')} {int(takeoff.ground_roll_ft)} {feet}",
                data={"value": takeoff.ground_roll_ft, "type": "distance"},
            ),
            MenuOption(
                key="2",
                label=f"Distance to 50ft: {takeoff.distance_50ft:.0f} ft",
                message_key=f"{t('fmc.to_distance_50')} {int(takeoff.distance_50ft)} {feet}",
                data={"value": takeoff.distance_50ft, "type": "distance"},
            ),
            MenuOption(
                key="3",
                label=f"Climb Rate: {climb_rate:.0f} fpm",
                message_key=f"{t('fmc.to_climb_rate')} {int(climb_rate)} {t('fmc.fpm')}",
                data={"value": climb_rate, "type": "climb_rate"},
            ),
        ]

    def _handle_selection(self, option: MenuOption) -> None:
        """Handle menu option selection."""
        # Speak the message_key which already contains the full translated message
        self._speak(option.message_key, interrupt=True)

    def _get_menu_opened_message(self) -> str:
        """Get TTS message for menu opened."""
        return t("fmc.to_title")

    def _get_menu_closed_message(self) -> str:
        """Get TTS message for menu closed."""
        return t("common.menu_closed")

    def _get_invalid_option_message(self) -> str:
        """Get TTS message for invalid option."""
        return t("common.invalid_option")
