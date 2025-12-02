"""Network plugins for Airborne Flight Simulator.

This package contains network-related plugins including:
- RemoteControlPlugin: WebSocket server for remote aircraft control and telemetry
"""

from airborne.plugins.network.remote_control_plugin import RemoteControlPlugin

__all__ = ["RemoteControlPlugin"]
