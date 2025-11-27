"""Taxiway graph and A* pathfinding for taxi routing.

Builds a graph from X-Plane Gateway taxi network data and provides
A* pathfinding to generate realistic taxi routes.

Typical usage:
    from airborne.services.atc.taxiway_graph import TaxiwayGraph

    graph = TaxiwayGraph.from_gateway_data(gateway_airport_data)
    route = graph.find_route(start_node_id, end_node_id)
    instructions = graph.route_to_instructions(route)
"""

import heapq
import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from airborne.services.atc.gateway_loader import GatewayAirportData

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """A node in the taxiway graph.

    Attributes:
        id: Unique node identifier.
        latitude: Node latitude.
        longitude: Node longitude.
        name: Optional node name.
        is_hold_short: Whether this is a runway hold short point.
        on_runway: Runway ID if this node is on a runway.
        neighbors: Adjacent node IDs with edge info.
    """

    id: int
    latitude: float
    longitude: float
    name: str = ""
    is_hold_short: bool = False
    on_runway: str = ""
    neighbors: dict[int, "GraphEdge"] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """An edge in the taxiway graph.

    Attributes:
        from_node: Starting node ID.
        to_node: Ending node ID.
        name: Taxiway name (e.g., "A", "B").
        distance: Edge distance in meters.
        is_runway: Whether this edge is on a runway.
        one_way: Whether this is one-way only.
        width_code: ICAO width code.
    """

    from_node: int
    to_node: int
    name: str
    distance: float
    is_runway: bool = False
    one_way: bool = False
    width_code: str = "E"


@dataclass
class RouteSegment:
    """A segment of a taxi route.

    Attributes:
        taxiway_name: Name of taxiway for this segment.
        node_ids: List of node IDs in this segment.
        distance: Total distance of segment in meters.
        is_runway_crossing: Whether this crosses a runway.
        hold_short_runway: Runway to hold short of (if applicable).
    """

    taxiway_name: str
    node_ids: list[int]
    distance: float
    is_runway_crossing: bool = False
    hold_short_runway: str = ""


@dataclass
class TaxiRoute:
    """Complete taxi route from start to destination.

    Attributes:
        segments: List of route segments.
        total_distance: Total route distance in meters.
        node_path: Complete list of node IDs.
        has_runway_crossing: Whether route crosses any runways.
    """

    segments: list[RouteSegment]
    total_distance: float
    node_path: list[int]
    has_runway_crossing: bool = False


class TaxiwayGraph:
    """Graph representation of airport taxiway network.

    Supports A* pathfinding to find optimal routes between
    any two points on the taxiway network.

    Examples:
        >>> graph = TaxiwayGraph.from_gateway_data(airport_data)
        >>> route = graph.find_route(start_node, runway_node)
        >>> print(f"Route: {route.total_distance:.0f}m via {len(route.segments)} segments")
    """

    def __init__(self) -> None:
        """Initialize empty taxiway graph."""
        self.nodes: dict[int, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._runway_nodes: set[int] = set()
        self._hold_short_nodes: dict[int, str] = {}  # node_id -> runway

    @classmethod
    def from_gateway_data(cls, data: "GatewayAirportData") -> "TaxiwayGraph":
        """Build graph from Gateway airport data.

        Args:
            data: GatewayAirportData with taxi nodes and edges.

        Returns:
            Populated TaxiwayGraph.

        Examples:
            >>> graph = TaxiwayGraph.from_gateway_data(kpao_data)
            >>> print(f"Graph has {len(graph.nodes)} nodes")
        """
        graph = cls()

        # Add nodes
        for node_id, taxi_node in data.taxi_nodes.items():
            graph_node = GraphNode(
                id=node_id,
                latitude=taxi_node.latitude,
                longitude=taxi_node.longitude,
                name=taxi_node.name,
                is_hold_short=taxi_node.is_hold_short,
                on_runway=taxi_node.on_runway,
            )
            graph.nodes[node_id] = graph_node

            if taxi_node.is_hold_short:
                graph._hold_short_nodes[node_id] = taxi_node.on_runway

        # Add edges (bidirectional unless one_way)
        for taxi_edge in data.taxi_edges:
            if taxi_edge.node_begin not in graph.nodes:
                continue
            if taxi_edge.node_end not in graph.nodes:
                continue

            # Calculate distance
            node1 = graph.nodes[taxi_edge.node_begin]
            node2 = graph.nodes[taxi_edge.node_end]
            distance = graph._haversine_distance(
                node1.latitude, node1.longitude, node2.latitude, node2.longitude
            )

            # Create edge
            edge = GraphEdge(
                from_node=taxi_edge.node_begin,
                to_node=taxi_edge.node_end,
                name=taxi_edge.name,
                distance=distance,
                is_runway=taxi_edge.is_runway,
                one_way=taxi_edge.one_way,
                width_code=taxi_edge.width_code,
            )
            graph.edges.append(edge)

            # Add to neighbor lists
            node1.neighbors[taxi_edge.node_end] = edge

            # Add reverse direction if not one-way
            if not taxi_edge.one_way:
                reverse_edge = GraphEdge(
                    from_node=taxi_edge.node_end,
                    to_node=taxi_edge.node_begin,
                    name=taxi_edge.name,
                    distance=distance,
                    is_runway=taxi_edge.is_runway,
                    one_way=False,
                    width_code=taxi_edge.width_code,
                )
                node2.neighbors[taxi_edge.node_begin] = reverse_edge

            # Track runway nodes
            if taxi_edge.is_runway:
                graph._runway_nodes.add(taxi_edge.node_begin)
                graph._runway_nodes.add(taxi_edge.node_end)

        logger.info(
            "Built taxiway graph: %d nodes, %d edges",
            len(graph.nodes),
            len(graph.edges),
        )

        return graph

    def find_route(
        self,
        start_node: int,
        end_node: int,
        avoid_runways: bool = True,
    ) -> TaxiRoute | None:
        """Find optimal route between two nodes using A*.

        Args:
            start_node: Starting node ID.
            end_node: Destination node ID.
            avoid_runways: If True, prefer routes that don't cross runways.

        Returns:
            TaxiRoute if path found, None otherwise.

        Examples:
            >>> route = graph.find_route(parking_node, runway_hold_node)
            >>> if route:
            ...     print(f"Distance: {route.total_distance:.0f}m")
        """
        if start_node not in self.nodes or end_node not in self.nodes:
            logger.warning("Invalid start or end node")
            return None

        # A* algorithm
        # Priority queue: (f_score, counter, node_id)
        counter = 0
        open_set: list[tuple[float, int, int]] = [(0, counter, start_node)]
        came_from: dict[int, int] = {}
        g_score: dict[int, float] = {start_node: 0}
        f_score: dict[int, float] = {start_node: self._heuristic(start_node, end_node)}

        while open_set:
            _, _, current = heapq.heappop(open_set)

            if current == end_node:
                # Reconstruct path
                path = self._reconstruct_path(came_from, current)
                return self._path_to_route(path)

            current_node = self.nodes[current]

            for neighbor_id, edge in current_node.neighbors.items():
                # Calculate cost
                cost = edge.distance

                # Penalize runway crossings if avoiding
                if avoid_runways and edge.is_runway:
                    cost += 1000  # Heavy penalty for runway crossing

                tentative_g = g_score[current] + cost

                if neighbor_id not in g_score or tentative_g < g_score[neighbor_id]:
                    came_from[neighbor_id] = current
                    g_score[neighbor_id] = tentative_g
                    f = tentative_g + self._heuristic(neighbor_id, end_node)
                    f_score[neighbor_id] = f
                    counter += 1
                    heapq.heappush(open_set, (f, counter, neighbor_id))

        logger.warning("No path found from %d to %d", start_node, end_node)
        return None

    def find_nearest_node(self, latitude: float, longitude: float) -> int | None:
        """Find the nearest graph node to a position.

        Args:
            latitude: Target latitude.
            longitude: Target longitude.

        Returns:
            Nearest node ID, or None if graph is empty.

        Examples:
            >>> node = graph.find_nearest_node(37.461, -122.115)
        """
        if not self.nodes:
            return None

        nearest_id = None
        nearest_dist = float("inf")

        for node_id, node in self.nodes.items():
            dist = self._haversine_distance(latitude, longitude, node.latitude, node.longitude)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_id = node_id

        return nearest_id

    def find_runway_hold_node(self, runway_id: str) -> int | None:
        """Find the hold short node for a runway.

        Args:
            runway_id: Runway identifier (e.g., "31", "09L").

        Returns:
            Hold short node ID, or None if not found.

        Examples:
            >>> hold_node = graph.find_runway_hold_node("31")
        """
        for node_id, runway in self._hold_short_nodes.items():
            if runway == runway_id:
                return node_id
        return None

    def find_runway_entry_nodes(self, runway_id: str) -> list[int]:
        """Find all entry points to a runway.

        Args:
            runway_id: Runway identifier.

        Returns:
            List of node IDs that provide runway access.
        """
        # Find nodes that are hold short for this runway
        # or are adjacent to runway nodes
        entry_nodes = []

        for node_id, runway in self._hold_short_nodes.items():
            if runway == runway_id or runway_id in runway:
                entry_nodes.append(node_id)

        return entry_nodes

    def route_to_instructions(self, route: TaxiRoute) -> list[str]:
        """Convert route to human-readable taxi instructions.

        Args:
            route: TaxiRoute to convert.

        Returns:
            List of instruction strings.

        Examples:
            >>> instructions = graph.route_to_instructions(route)
            >>> # ["Taxi via Alpha", "Turn right onto Bravo", "Hold short runway 31"]
        """
        if not route.segments:
            return []

        instructions = []
        prev_taxiway = ""

        for segment in route.segments:
            taxiway = segment.taxiway_name or "taxiway"

            if segment.hold_short_runway:
                instructions.append(f"Hold short runway {segment.hold_short_runway}")
            elif taxiway != prev_taxiway:
                if not prev_taxiway:
                    instructions.append(f"Taxi via {taxiway}")
                else:
                    instructions.append(f"Continue via {taxiway}")

            prev_taxiway = taxiway

        return instructions

    def route_to_taxiway_names(self, route: TaxiRoute) -> list[str]:
        """Extract unique taxiway names from route in order.

        Args:
            route: TaxiRoute to process.

        Returns:
            List of taxiway names in order traversed.

        Examples:
            >>> names = graph.route_to_taxiway_names(route)
            >>> # ["A", "B", "C"]
        """
        names = []
        prev_name = ""

        for segment in route.segments:
            if segment.taxiway_name and segment.taxiway_name != prev_name:
                names.append(segment.taxiway_name)
                prev_name = segment.taxiway_name

        return names

    def _heuristic(self, node_a: int, node_b: int) -> float:
        """Calculate heuristic distance between nodes (straight line).

        Args:
            node_a: First node ID.
            node_b: Second node ID.

        Returns:
            Estimated distance in meters.
        """
        a = self.nodes[node_a]
        b = self.nodes[node_b]
        return self._haversine_distance(a.latitude, a.longitude, b.latitude, b.longitude)

    def _reconstruct_path(self, came_from: dict[int, int], current: int) -> list[int]:
        """Reconstruct path from A* came_from dict.

        Args:
            came_from: Dictionary mapping node to previous node.
            current: End node.

        Returns:
            List of node IDs from start to end.
        """
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path

    def _path_to_route(self, path: list[int]) -> TaxiRoute:
        """Convert node path to TaxiRoute with segments.

        Args:
            path: List of node IDs.

        Returns:
            TaxiRoute with segments grouped by taxiway.
        """
        if len(path) < 2:
            return TaxiRoute(
                segments=[],
                total_distance=0,
                node_path=path,
                has_runway_crossing=False,
            )

        segments: list[RouteSegment] = []
        current_segment_nodes: list[int] = [path[0]]
        current_taxiway = ""
        current_distance = 0.0
        total_distance = 0.0
        has_runway_crossing = False

        for i in range(len(path) - 1):
            from_node = self.nodes[path[i]]
            to_node_id = path[i + 1]

            if to_node_id not in from_node.neighbors:
                continue

            edge = from_node.neighbors[to_node_id]

            # Check for taxiway change
            if edge.name != current_taxiway and current_taxiway:
                # Save current segment
                segments.append(
                    RouteSegment(
                        taxiway_name=current_taxiway,
                        node_ids=current_segment_nodes.copy(),
                        distance=current_distance,
                    )
                )
                current_segment_nodes = [path[i]]
                current_distance = 0.0

            current_taxiway = edge.name
            current_segment_nodes.append(to_node_id)
            current_distance += edge.distance
            total_distance += edge.distance

            if edge.is_runway:
                has_runway_crossing = True

            # Check for hold short
            if to_node_id in self._hold_short_nodes:
                runway = self._hold_short_nodes[to_node_id]
                segments.append(
                    RouteSegment(
                        taxiway_name=current_taxiway,
                        node_ids=current_segment_nodes.copy(),
                        distance=current_distance,
                        hold_short_runway=runway,
                    )
                )
                current_segment_nodes = [to_node_id]
                current_distance = 0.0

        # Add final segment if not empty
        if len(current_segment_nodes) > 1:
            segments.append(
                RouteSegment(
                    taxiway_name=current_taxiway,
                    node_ids=current_segment_nodes,
                    distance=current_distance,
                )
            )

        return TaxiRoute(
            segments=segments,
            total_distance=total_distance,
            node_path=path,
            has_runway_crossing=has_runway_crossing,
        )

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in meters.

        Args:
            lat1: First latitude.
            lon1: First longitude.
            lat2: Second latitude.
            lon2: Second longitude.

        Returns:
            Distance in meters.
        """
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))

        # Earth radius in meters
        radius_m = 6_371_000

        return c * radius_m
