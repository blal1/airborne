"""Position tracking system for aircraft ground operations.

This module provides real-time position awareness for aircraft on the ground,
detecting location types (parking, taxiway, runway, apron) and publishing
location change events for audio feedback and navigation cues.

Typical usage:
    from airborne.plugins.navigation.position_tracker import PositionTracker, LocationType

    tracker = PositionTracker(taxiway_graph, message_queue)
    tracker.update(current_position, current_heading)

    location_type, location_id = tracker.get_current_location()
    if location_type == LocationType.TAXIWAY:
        print(f"On taxiway {location_id}")
"""

import logging
import math
from collections import deque
from dataclasses import dataclass
from enum import Enum

from airborne.airports.taxiway import TaxiwayEdge, TaxiwayGraph, TaxiwayNode
from airborne.core.messaging import Message, MessagePriority, MessageQueue
from airborne.physics.vectors import Vector3


@dataclass
class ApproachingJunction:
    """Information about an approaching junction.

    Attributes:
        name: Name of the junction (taxiway or runway identifier).
        junction_type: Type of junction ("taxiway" or "runway").
        distance_m: Distance to junction in meters.
        direction: Relative direction ("left", "right", "ahead").
        position: Position of the junction.
    """

    name: str
    junction_type: str  # "taxiway" or "runway"
    distance_m: float
    direction: str  # "left", "right", "ahead"
    position: Vector3

logger = logging.getLogger(__name__)


class LocationType(Enum):
    """Type of location on the airport surface.

    Used to categorize where the aircraft currently is for providing
    appropriate audio cues and navigation guidance.
    """

    PARKING = "parking"  # At a parking position (gate, stand, ramp, tie-down)
    TAXIWAY = "taxiway"  # On a taxiway segment
    RUNWAY = "runway"  # On an active runway
    APRON = "apron"  # On apron/ramp area (not specific parking)
    GRASS = "grass"  # Off paved surface (grass, dirt)
    UNKNOWN = "unknown"  # Cannot determine location


@dataclass
class LocationEvent:
    """Event triggered when aircraft enters/exits a location.

    Attributes:
        location_type: Type of location (parking, taxiway, runway, etc.)
        location_id: Identifier of the location (node ID, taxiway name, etc.)
        previous_location_type: Previous location type
        previous_location_id: Previous location identifier
        position: Position where event occurred
        timestamp: Time of event (from update call)

    Examples:
        >>> event = LocationEvent(
        ...     location_type=LocationType.TAXIWAY,
        ...     location_id="A",
        ...     previous_location_type=LocationType.PARKING,
        ...     previous_location_id="G1",
        ...     position=Vector3(-122.0, 10.0, 37.5),
        ...     timestamp=12345.67
        ... )
    """

    location_type: LocationType
    location_id: str
    previous_location_type: LocationType
    previous_location_id: str
    position: Vector3
    timestamp: float


class PositionTracker:  # pylint: disable=too-many-instance-attributes
    """Tracks aircraft position on airport surface.

    Monitors aircraft position relative to taxiway graph to determine
    current location (parking, taxiway, runway, apron). Maintains position
    history and publishes location change events for audio feedback.

    Attributes:
        graph: Taxiway graph containing airport surface layout
        message_queue: Queue for publishing location events
        current_location_type: Current location type
        current_location_id: Current location identifier (node ID or name)
        position_history: Recent position history (max 100 entries)
        proximity_threshold_m: Distance threshold for node proximity (meters)

    Examples:
        >>> tracker = PositionTracker(taxiway_graph, message_queue)
        >>> tracker.update(Vector3(-122.0, 10.0, 37.5), 90.0)
        >>> location_type, location_id = tracker.get_current_location()
        >>> print(f"Currently at {location_type.value}: {location_id}")
    """

    def __init__(
        self,
        graph: TaxiwayGraph,
        message_queue: MessageQueue | None = None,
        proximity_threshold_m: float = 10.0,
    ) -> None:
        """Initialize position tracker.

        Args:
            graph: Taxiway graph for location detection
            message_queue: Optional message queue for event publishing
            proximity_threshold_m: Distance threshold for considering aircraft
                "at" a node (default 10 meters)
        """
        self.graph = graph
        self.message_queue = message_queue
        self.proximity_threshold_m = proximity_threshold_m

        # Current location state
        self.current_location_type = LocationType.UNKNOWN
        self.current_location_id = ""
        self.current_node_id: str | None = None

        # Position history (stores last 100 positions)
        self.position_history: deque[tuple[Vector3, float]] = deque(maxlen=100)

        # Last update timestamp
        self.last_update_time = 0.0

        logger.info(
            "PositionTracker initialized (proximity_threshold=%.1fm)", proximity_threshold_m
        )

    def update(self, position: Vector3, heading: float, timestamp: float = 0.0) -> None:
        """Update aircraft position and detect location changes.

        Args:
            position: Current aircraft position (x=lon, y=elev, z=lat)
            heading: Current aircraft heading in degrees
            timestamp: Current time (for event tracking)

        Examples:
            >>> tracker.update(Vector3(-122.0, 10.0, 37.5), 90.0, 12345.67)
        """
        self.last_update_time = timestamp

        # Store in history
        self.position_history.append((position, heading))

        # Find nearest node
        nearest_node_id, nearest_distance = self._find_nearest_node(position)

        if nearest_node_id is None:
            # No nodes in graph - location unknown
            self._update_location(LocationType.UNKNOWN, "", timestamp)
            return

        # Determine if we're close enough to be "at" this node
        if nearest_distance <= self.proximity_threshold_m:
            # We're at a specific node
            node = self.graph.nodes[nearest_node_id]
            location_type, location_id = self._classify_node(node)
            self._update_location(location_type, location_id, timestamp)
            self.current_node_id = nearest_node_id
        else:
            # We're between nodes - check if on an edge (taxiway segment)
            edge_result = self._find_nearest_edge(position)
            if edge_result:
                edge, distance = edge_result
                if distance <= self.proximity_threshold_m:
                    # On an edge
                    location_type, location_id = self._classify_edge(edge)
                    self._update_location(location_type, location_id, timestamp)
                    self.current_node_id = None
                else:
                    # Too far from any edge - probably on grass/unknown
                    self._update_location(LocationType.GRASS, "", timestamp)
                    self.current_node_id = None
            else:
                # No edges nearby - unknown location
                self._update_location(LocationType.UNKNOWN, "", timestamp)
                self.current_node_id = None

    def get_current_location(self) -> tuple[LocationType, str]:
        """Get current location type and identifier.

        Returns:
            Tuple of (location_type, location_id). Location ID may be empty string
            if no specific location identified.

        Examples:
            >>> location_type, location_id = tracker.get_current_location()
            >>> print(f"At {location_type.value}: {location_id}")
            At taxiway: A
        """
        return (self.current_location_type, self.current_location_id)

    def get_nearest_taxiway(self) -> str | None:
        """Get name of nearest taxiway.

        Returns:
            Taxiway name if on or near a taxiway, None otherwise.

        Examples:
            >>> taxiway = tracker.get_nearest_taxiway()
            >>> if taxiway:
            ...     print(f"Near taxiway {taxiway}")
        """
        if self.current_location_type == LocationType.TAXIWAY:
            return self.current_location_id

        # If not on a taxiway, find nearest taxiway edge
        if not self.position_history:
            return None

        current_position, _ = self.position_history[-1]
        edge_result = self._find_nearest_edge(current_position, edge_type="taxiway")

        if edge_result:
            edge, _ = edge_result
            return edge.name if edge.name else None

        return None

    def get_distance_to_next_intersection(self) -> float:
        """Calculate distance to next intersection along current path.

        Returns:
            Distance in meters to next intersection, or infinity if not on a path.

        Examples:
            >>> distance = tracker.get_distance_to_next_intersection()
            >>> print(f"Next intersection in {distance:.0f}m")
        """
        if not self.current_node_id or not self.position_history:
            return float("inf")

        current_position, heading = self.position_history[-1]

        # Find outgoing edges from current node
        outgoing_edges = self.graph.edges.get(self.current_node_id, [])

        if not outgoing_edges:
            return float("inf")

        # Find edge that matches our heading (within 45 degrees)
        best_edge = None
        min_heading_diff = 360.0

        current_node = self.graph.nodes[self.current_node_id]

        for edge in outgoing_edges:
            target_node = self.graph.nodes[edge.to_node]

            # Calculate heading to target node
            dx = (target_node.position.x - current_node.position.x) * 111000.0
            dz = (target_node.position.z - current_node.position.z) * 111000.0
            edge_heading = (math.degrees(math.atan2(dx, dz)) + 360) % 360

            # Check heading difference
            heading_diff = abs(edge_heading - heading)
            if heading_diff > 180:
                heading_diff = 360 - heading_diff

            if heading_diff < min_heading_diff and heading_diff < 45:
                min_heading_diff = heading_diff
                best_edge = edge

        if best_edge:
            # Calculate distance to next node
            target_node = self.graph.nodes[best_edge.to_node]
            return self._calculate_distance(current_position, target_node.position)

        return float("inf")

    def is_on_taxiway(self, taxiway_name: str) -> bool:
        """Check if aircraft is on a specific taxiway.

        Args:
            taxiway_name: Name of taxiway to check (e.g., "A", "B1")

        Returns:
            True if currently on the specified taxiway, False otherwise.

        Examples:
            >>> if tracker.is_on_taxiway("A"):
            ...     print("On taxiway Alpha")
        """
        return (
            self.current_location_type == LocationType.TAXIWAY
            and self.current_location_id == taxiway_name
        )

    def get_centerline_deviation(self) -> tuple[float, str] | None:
        """Calculate deviation from current taxiway/runway centerline.

        Determines how far the aircraft is from the centerline of the current
        taxiway or runway, and which direction (left or right).

        Returns:
            Tuple of (deviation_meters, direction) where direction is 'left' or 'right',
            or None if not on a taxiway/runway or cannot determine deviation.

        Examples:
            >>> deviation = tracker.get_centerline_deviation()
            >>> if deviation:
            ...     distance, direction = deviation
            ...     print(f"Drifting {direction} by {distance:.1f}m")
        """
        if self.current_location_type not in (LocationType.TAXIWAY, LocationType.RUNWAY):
            return None

        if not self.position_history:
            return None

        current_pos, _ = self.position_history[-1]

        # Find nearest edge (centerline segment)
        edge_result = self._find_nearest_edge(current_pos)
        if not edge_result:
            return None

        edge, distance = edge_result

        # Get nodes for this edge
        from_node = self.graph.nodes.get(edge.from_node)
        to_node = self.graph.nodes.get(edge.to_node)

        if not from_node or not to_node:
            return None

        # Determine if left or right of centerline using cross product
        side = self._get_side_of_line(current_pos, from_node.position, to_node.position)

        direction = "right" if side > 0 else "left"
        return (distance, direction)

    @staticmethod
    def _get_side_of_line(point: Vector3, line_start: Vector3, line_end: Vector3) -> float:
        """Determine which side of a line a point is on.

        Uses cross product to determine the side. When traveling from line_start
        to line_end, positive means point is to the right, negative means left.

        Args:
            point: Point to check
            line_start: Start of line segment
            line_end: End of line segment

        Returns:
            Positive if right of line, negative if left, zero if on line.
        """
        # Convert to meters for calculation
        dx = (line_end.x - line_start.x) * 111000.0
        dz = (line_end.z - line_start.z) * 111000.0
        px = (point.x - line_start.x) * 111000.0
        pz = (point.z - line_start.z) * 111000.0

        # Cross product: (line) × (point - start)
        # If positive, point is to the right of the line
        return dx * pz - dz * px

    def get_approaching_junctions(self, look_ahead_m: float = 100.0) -> list[ApproachingJunction]:
        """Get junctions ahead of current position.

        Finds taxiway and runway intersections that are ahead of the aircraft
        within the specified distance.

        Args:
            look_ahead_m: How far ahead to look for junctions (meters).

        Returns:
            List of approaching junctions sorted by distance.

        Examples:
            >>> junctions = tracker.get_approaching_junctions(100.0)
            >>> for j in junctions:
            ...     print(f"{j.name} {j.direction} in {j.distance_m:.0f}m")
        """
        if not self.position_history:
            return []

        current_pos, heading = self.position_history[-1]
        junctions: list[ApproachingJunction] = []
        seen_names: set[str] = set()

        # Find nodes ahead of us within look_ahead_m
        for node_id, node in self.graph.nodes.items():
            distance = self._calculate_distance(current_pos, node.position)
            if distance > look_ahead_m:
                continue

            # Check if node is ahead (within ±90° of heading)
            bearing = self._calculate_bearing(current_pos, node.position)
            heading_diff = self._normalize_heading_diff(bearing - heading)
            if abs(heading_diff) > 90:
                continue

            # Get connected taxiways/runways at this node (excluding current location)
            edges = self.graph.edges.get(node_id, [])
            for edge in edges:
                if not edge.name or edge.name == self.current_location_id:
                    continue
                if edge.name in seen_names:
                    continue

                # Determine junction type
                junction_type = "runway" if edge.edge_type == "runway" else "taxiway"

                # Determine relative direction
                direction = self._get_relative_direction(heading, bearing)

                junctions.append(
                    ApproachingJunction(
                        name=edge.name,
                        junction_type=junction_type,
                        distance_m=distance,
                        direction=direction,
                        position=node.position,
                    )
                )
                seen_names.add(edge.name)

        # Sort by distance
        junctions.sort(key=lambda j: j.distance_m)
        return junctions

    @staticmethod
    def _calculate_bearing(from_pos: Vector3, to_pos: Vector3) -> float:
        """Calculate bearing from one position to another.

        Args:
            from_pos: Starting position
            to_pos: Target position

        Returns:
            Bearing in degrees (0-360)
        """
        dx = (to_pos.x - from_pos.x) * 111000.0
        dz = (to_pos.z - from_pos.z) * 111000.0
        bearing = math.degrees(math.atan2(dx, dz))
        return (bearing + 360) % 360

    @staticmethod
    def _normalize_heading_diff(diff: float) -> float:
        """Normalize heading difference to -180 to +180 range.

        Args:
            diff: Raw heading difference

        Returns:
            Normalized difference (-180 to +180)
        """
        while diff > 180:
            diff -= 360
        while diff < -180:
            diff += 360
        return diff

    @staticmethod
    def _get_relative_direction(heading: float, bearing: float) -> str:
        """Determine relative direction (left/right/ahead) based on heading and bearing.

        Args:
            heading: Aircraft heading in degrees
            bearing: Bearing to target in degrees

        Returns:
            "left", "right", or "ahead"
        """
        diff = PositionTracker._normalize_heading_diff(bearing - heading)

        if abs(diff) < 30:
            return "ahead"
        elif diff < 0:
            return "left"
        else:
            return "right"

    def _find_nearest_node(self, position: Vector3) -> tuple[str | None, float]:
        """Find nearest node to position.

        Args:
            position: Position to search from

        Returns:
            Tuple of (node_id, distance_meters), or (None, inf) if no nodes
        """
        if not self.graph.nodes:
            return (None, float("inf"))

        nearest_id = None
        min_distance = float("inf")

        for node_id, node in self.graph.nodes.items():
            distance = self._calculate_distance(position, node.position)
            if distance < min_distance:
                min_distance = distance
                nearest_id = node_id

        return (nearest_id, min_distance)

    def _find_nearest_edge(
        self, position: Vector3, edge_type: str | None = None
    ) -> tuple[TaxiwayEdge, float] | None:
        """Find nearest edge to position.

        Args:
            position: Position to search from
            edge_type: Optional edge type filter (e.g., "taxiway", "runway")

        Returns:
            Tuple of (edge, distance_meters) if edge found, None otherwise
        """
        if not self.graph.edges:
            return None

        nearest_edge = None
        min_distance = float("inf")

        for edges in self.graph.edges.values():
            for edge in edges:
                # Filter by edge type if specified
                if edge_type and edge.edge_type != edge_type:
                    continue

                # Get nodes for this edge
                from_node = self.graph.nodes.get(edge.from_node)
                to_node = self.graph.nodes.get(edge.to_node)

                if not from_node or not to_node:
                    continue

                # Calculate distance from position to line segment
                distance = self._point_to_segment_distance(
                    position, from_node.position, to_node.position
                )

                if distance < min_distance:
                    min_distance = distance
                    nearest_edge = edge

        if nearest_edge:
            return (nearest_edge, min_distance)
        return None

    def _classify_node(self, node: TaxiwayNode) -> tuple[LocationType, str]:
        """Classify a node to determine location type.

        Args:
            node: Node to classify

        Returns:
            Tuple of (location_type, location_id)
        """
        # Check node type
        if node.node_type.startswith("parking_"):
            return (LocationType.PARKING, node.node_id)
        if node.node_type == "runway":
            return (LocationType.RUNWAY, node.name if node.name else node.node_id)
        if node.node_type == "intersection":
            # At an intersection - use connected edge names to determine taxiway
            edges = self.graph.edges.get(node.node_id, [])
            if edges and edges[0].name:
                return (LocationType.TAXIWAY, edges[0].name)
            return (LocationType.TAXIWAY, node.node_id)
        if node.node_type == "apron":
            return (LocationType.APRON, node.node_id)
        return (LocationType.UNKNOWN, node.node_id)

    def _classify_edge(self, edge: TaxiwayEdge) -> tuple[LocationType, str]:
        """Classify an edge to determine location type.

        Args:
            edge: Edge to classify

        Returns:
            Tuple of (location_type, location_id)
        """
        if edge.edge_type == "runway":
            return (LocationType.RUNWAY, edge.name if edge.name else edge.to_node)
        if edge.edge_type == "taxiway":
            return (LocationType.TAXIWAY, edge.name if edge.name else "")
        if edge.edge_type == "apron":
            return (LocationType.APRON, edge.name if edge.name else "")
        return (LocationType.UNKNOWN, "")

    def _update_location(self, new_type: LocationType, new_id: str, timestamp: float) -> None:
        """Update current location and publish event if changed.

        Args:
            new_type: New location type
            new_id: New location identifier
            timestamp: Current timestamp
        """
        # Check if location changed
        if new_type != self.current_location_type or new_id != self.current_location_id:
            # Get current position
            position = self.position_history[-1][0] if self.position_history else Vector3(0, 0, 0)

            # Create location event
            event = LocationEvent(
                location_type=new_type,
                location_id=new_id,
                previous_location_type=self.current_location_type,
                previous_location_id=self.current_location_id,
                position=position,
                timestamp=timestamp,
            )

            # Update state
            prev_type = self.current_location_type
            prev_id = self.current_location_id
            self.current_location_type = new_type
            self.current_location_id = new_id

            # Log the change
            logger.info(
                "Location changed: %s (%s) -> %s (%s)",
                prev_type.value,
                prev_id,
                new_type.value,
                new_id,
            )

            # Publish event
            self._publish_location_event(event)

    def _publish_location_event(self, event: LocationEvent) -> None:
        """Publish location change event to message queue.

        Args:
            event: Location event to publish
        """
        if not self.message_queue:
            return

        # Determine topic based on location type
        topic_map = {
            LocationType.TAXIWAY: "navigation.entered_taxiway",
            LocationType.RUNWAY: "navigation.entered_runway",
            LocationType.PARKING: "navigation.entered_parking",
            LocationType.APRON: "navigation.entered_apron",
        }

        topic = topic_map.get(event.location_type, "navigation.location_changed")

        # Create message
        message = Message(
            sender="position_tracker",
            recipients=["*"],  # Broadcast to all
            topic=topic,
            data={
                "location_type": event.location_type.value,
                "location_id": event.location_id,
                "previous_type": event.previous_location_type.value,
                "previous_id": event.previous_location_id,
                "position": {
                    "x": event.position.x,
                    "y": event.position.y,
                    "z": event.position.z,
                },
                "timestamp": event.timestamp,
            },
            priority=MessagePriority.HIGH,  # Location changes are important
        )

        self.message_queue.publish(message)
        logger.debug("Published location event: %s -> %s", topic, event.location_id)

    @staticmethod
    def _calculate_distance(pos1: Vector3, pos2: Vector3) -> float:
        """Calculate distance between two positions.

        Uses simple Euclidean distance with lat/lon to meters conversion.

        Args:
            pos1: First position (x=lon, y=elev, z=lat)
            pos2: Second position

        Returns:
            Distance in meters
        """
        # Convert lat/lon differences to meters (approximate)
        dx = (pos2.x - pos1.x) * 111000.0  # longitude to meters
        dz = (pos2.z - pos1.z) * 111000.0  # latitude to meters

        return float((dx * dx + dz * dz) ** 0.5)

    @staticmethod
    def _point_to_segment_distance(
        point: Vector3, segment_start: Vector3, segment_end: Vector3
    ) -> float:
        """Calculate distance from point to line segment.

        Args:
            point: Point to measure from
            segment_start: Start of line segment
            segment_end: End of line segment

        Returns:
            Distance in meters
        """
        # Convert to 2D (x, z) for ground operations
        px, pz = point.x * 111000.0, point.z * 111000.0
        sx, sz = segment_start.x * 111000.0, segment_start.z * 111000.0
        ex, ez = segment_end.x * 111000.0, segment_end.z * 111000.0

        # Vector from start to end
        dx = ex - sx
        dz = ez - sz

        # If segment has zero length, return distance to start point
        length_sq = dx * dx + dz * dz
        if length_sq < 1e-10:
            return float(((px - sx) ** 2 + (pz - sz) ** 2) ** 0.5)

        # Calculate projection parameter t
        t = max(0, min(1, ((px - sx) * dx + (pz - sz) * dz) / length_sq))

        # Calculate closest point on segment
        closest_x = sx + t * dx
        closest_z = sz + t * dz

        # Return distance to closest point
        return float(((px - closest_x) ** 2 + (pz - closest_z) ** 2) ** 0.5)
