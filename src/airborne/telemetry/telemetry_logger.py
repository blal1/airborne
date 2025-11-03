"""SQLite telemetry logger for flight data recording and replay.

This module provides comprehensive telemetry logging to SQLite database with
millisecond precision timestamps. The data can be used for:
- Flight analysis and debugging
- Performance testing
- Flight replay
- Physics model validation
"""

import sqlite3
import time
from datetime import datetime
from typing import Any

from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class TelemetryLogger:
    """Records flight telemetry to SQLite database for analysis and replay.

    Captures complete aircraft state at high frequency with millisecond timestamps.
    Data is buffered and written in batches for performance.
    """

    def __init__(self, db_path: str | None = None, buffer_size: int = 100):
        """Initialize telemetry logger.

        Args:
            db_path: Path to SQLite database file. If None, creates in /tmp
            buffer_size: Number of records to buffer before writing to disk
        """
        if db_path is None:
            # Create timestamped database in /tmp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            db_path = f"/tmp/airborne_telemetry_{timestamp}.db"

        self.db_path = db_path
        self.buffer_size = buffer_size
        self.buffer = []
        self.start_time = time.time()
        self.frame_count = 0

        # Create database and schema
        self._init_database()

        logger.info(f"TelemetryLogger initialized: {self.db_path}")

    def _init_database(self):
        """Create database schema for telemetry data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Main telemetry table with millisecond timestamps
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                -- Timing (millisecond precision)
                timestamp_ms INTEGER NOT NULL,  -- Milliseconds since start
                timestamp_real REAL NOT NULL,   -- Unix timestamp with ms precision
                frame_count INTEGER NOT NULL,
                dt REAL,                        -- Delta time since last frame (seconds)

                -- Position and orientation
                position_x REAL,
                position_y REAL,
                position_z REAL,
                latitude REAL,
                longitude REAL,
                altitude_m REAL,
                heading_deg REAL,
                pitch_deg REAL,
                roll_deg REAL,

                -- Velocity
                velocity_x REAL,
                velocity_y REAL,
                velocity_z REAL,
                airspeed_mps REAL,
                airspeed_kts REAL,
                groundspeed_mps REAL,
                vertical_speed_mps REAL,
                vertical_speed_fpm REAL,

                -- State flags
                on_ground INTEGER,
                parking_brake INTEGER,
                gear_down INTEGER,

                -- Control inputs
                throttle REAL,
                aileron REAL,
                elevator REAL,
                rudder REAL,
                flaps REAL,
                mixture REAL,
                brake REAL,

                -- Trim settings
                pitch_trim REAL,
                rudder_trim REAL,

                -- Engine
                engine_running INTEGER,
                engine_rpm REAL,
                engine_power_hp REAL,
                engine_power_watts REAL,
                fuel_flow_gph REAL,
                fuel_remaining_gallons REAL,

                -- Propeller (if available)
                propeller_rpm REAL,
                advance_ratio REAL,
                propeller_efficiency REAL,
                thrust_correction REAL,
                blend_factor REAL,
                thrust_n REAL,

                -- Aerodynamic forces
                lift_n REAL,
                drag_parasite_n REAL,
                drag_induced_n REAL,
                drag_total_n REAL,
                lift_coefficient REAL,
                angle_of_attack_deg REAL,

                -- Ground forces
                rolling_resistance_n REAL,
                ground_friction_coeff REAL,

                -- Net forces and acceleration
                net_force_x REAL,
                net_force_y REAL,
                net_force_z REAL,
                acceleration_x REAL,
                acceleration_y REAL,
                acceleration_z REAL,
                acceleration_mps2 REAL,

                -- Environmental
                air_density_kgm3 REAL,
                temperature_c REAL,
                pressure_hpa REAL,
                wind_speed_mps REAL,
                wind_direction_deg REAL,

                -- Electrical (if available)
                battery_voltage REAL,
                battery_current_amps REAL,
                alternator_amps REAL,

                -- Performance metrics
                g_force REAL,
                bank_angle_deg REAL,
                slip_angle_deg REAL
            )
        """)

        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON telemetry(timestamp_ms)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_airspeed
            ON telemetry(airspeed_kts)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_on_ground
            ON telemetry(on_ground)
        """)

        # Metadata table for flight session info
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Force vectors table for detailed physics debugging
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS forces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                -- Timing (link to main telemetry table)
                timestamp_ms INTEGER NOT NULL,
                frame_count INTEGER NOT NULL,

                -- Individual force vectors (N)
                thrust_x REAL,
                thrust_y REAL,
                thrust_z REAL,
                thrust_mag REAL,

                drag_x REAL,
                drag_y REAL,
                drag_z REAL,
                drag_mag REAL,

                lift_x REAL,
                lift_y REAL,
                lift_z REAL,
                lift_mag REAL,

                weight_x REAL,
                weight_y REAL,
                weight_z REAL,
                weight_mag REAL,

                -- External forces (ground, wind, etc)
                external_x REAL,
                external_y REAL,
                external_z REAL,
                external_mag REAL,

                -- Total force vector
                total_x REAL,
                total_y REAL,
                total_z REAL,
                total_mag REAL,

                -- Calculated acceleration from forces
                accel_from_forces_x REAL,
                accel_from_forces_y REAL,
                accel_from_forces_z REAL,
                accel_from_forces_mag REAL,

                -- Actual state acceleration (for comparison)
                actual_accel_x REAL,
                actual_accel_y REAL,
                actual_accel_z REAL,
                actual_accel_mag REAL
            )
        """)

        # Create index on timestamp for force table
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_forces_timestamp
            ON forces(timestamp_ms)
        """)

        # Store session metadata
        session_start = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT OR REPLACE INTO metadata (key, value)
            VALUES ('session_start', ?)
        """,
            (session_start,),
        )

        conn.commit()
        conn.close()

        logger.info("Telemetry database schema created")

    def log(self, data: dict[str, Any]):
        """Log a telemetry data point.

        Args:
            data: Dictionary containing telemetry values. Keys should match
                  column names in the telemetry table.
        """
        self.frame_count += 1
        current_time = time.time()
        elapsed_ms = int((current_time - self.start_time) * 1000)

        # Add timing data
        data["timestamp_ms"] = elapsed_ms
        data["timestamp_real"] = current_time
        data["frame_count"] = self.frame_count

        # Add to buffer
        self.buffer.append(data)

        # Flush if buffer is full
        if len(self.buffer) >= self.buffer_size:
            self.flush()

    def log_forces(self, force_data: dict[str, Any]):
        """Log detailed force vector data to the forces table.

        Args:
            force_data: Dictionary with force vector components and magnitudes.
                       Expected keys include: thrust_x/y/z, drag_x/y/z, etc.
        """
        current_time = time.time()
        elapsed_ms = int((current_time - self.start_time) * 1000)

        # Add timing data
        force_data["timestamp_ms"] = elapsed_ms
        force_data["frame_count"] = self.frame_count

        # Write directly to database (forces are less frequent, no buffering)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get columns from data
        columns = sorted(force_data.keys())
        placeholders = ",".join(["?" for _ in columns])
        columns_str = ",".join(columns)
        values = [force_data.get(col) for col in columns]

        cursor.execute(f"INSERT INTO forces ({columns_str}) VALUES ({placeholders})", values)

        conn.commit()
        conn.close()

    def flush(self):
        """Write buffered data to database."""
        if not self.buffer:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all unique columns from buffer
        all_columns = set()
        for record in self.buffer:
            all_columns.update(record.keys())

        columns = sorted(all_columns)
        placeholders = ",".join(["?" for _ in columns])
        columns_str = ",".join(columns)

        # Insert all buffered records
        for record in self.buffer:
            values = [record.get(col) for col in columns]
            cursor.execute(f"INSERT INTO telemetry ({columns_str}) VALUES ({placeholders})", values)

        conn.commit()
        conn.close()

        logger.debug(f"Flushed {len(self.buffer)} telemetry records to database")
        self.buffer.clear()

    def close(self):
        """Flush remaining data and close logger."""
        self.flush()
        logger.info(f"TelemetryLogger closed: {self.frame_count} frames logged to {self.db_path}")

    def query(self, sql: str, params: tuple = ()):
        """Execute a SQL query and return results.

        Args:
            sql: SQL query string
            params: Query parameters (for parameterized queries)

        Returns:
            List of tuples containing query results
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(sql, params)
        results = cursor.fetchall()
        conn.close()
        return results

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics for the flight.

        Returns:
            Dictionary containing flight summary statistics
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get overall stats
        cursor.execute("""
            SELECT
                COUNT(*) as frame_count,
                MIN(timestamp_ms) as start_ms,
                MAX(timestamp_ms) as end_ms,
                MAX(airspeed_kts) as max_airspeed_kts,
                MAX(altitude_m) as max_altitude_m,
                MAX(thrust_n) as max_thrust_n,
                AVG(thrust_n) as avg_thrust_n,
                MAX(acceleration_mps2) as max_acceleration_mps2,
                AVG(acceleration_mps2) as avg_acceleration_mps2
            FROM telemetry
        """)

        summary = dict(cursor.fetchone())

        # Calculate flight duration
        if summary["end_ms"] and summary["start_ms"]:
            summary["duration_seconds"] = (summary["end_ms"] - summary["start_ms"]) / 1000.0

        conn.close()
        return summary


class TelemetryAnalyzer:
    """Analyzes telemetry data from SQLite database.

    Provides convenience methods for common analysis tasks like finding
    takeoff performance, thrust curves, etc.
    """

    def __init__(self, db_path: str):
        """Initialize analyzer with database path.

        Args:
            db_path: Path to telemetry SQLite database
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def get_takeoff_performance(self) -> dict[str, Any]:
        """Analyze takeoff roll performance.

        Returns:
            Dictionary with takeoff metrics (time to rotation, distances, etc.)
        """
        cursor = self.conn.cursor()

        # Find start of takeoff (throttle > 90%, on ground)
        cursor.execute("""
            SELECT MIN(timestamp_ms) as start_ms
            FROM telemetry
            WHERE throttle > 0.9 AND on_ground = 1
        """)
        start_ms = cursor.fetchone()["start_ms"]

        if not start_ms:
            return {"error": "No takeoff data found"}

        # Find rotation speed (55 knots for C172)
        cursor.execute(
            """
            SELECT
                timestamp_ms,
                airspeed_kts,
                thrust_n,
                acceleration_mps2
            FROM telemetry
            WHERE timestamp_ms >= ?
                AND on_ground = 1
                AND airspeed_kts >= 55
            ORDER BY timestamp_ms
            LIMIT 1
        """,
            (start_ms,),
        )

        rotation_data = cursor.fetchone()

        if not rotation_data:
            # Get max airspeed reached during ground roll
            cursor.execute(
                """
                SELECT
                    MAX(airspeed_kts) as max_airspeed,
                    MAX(timestamp_ms) as end_ms
                FROM telemetry
                WHERE timestamp_ms >= ? AND on_ground = 1
            """,
                (start_ms,),
            )
            max_data = cursor.fetchone()

            time_to_max = (max_data["end_ms"] - start_ms) / 1000.0

            return {
                "rotation_achieved": False,
                "max_airspeed_kts": max_data["max_airspeed"],
                "time_to_max_seconds": time_to_max,
                "note": "Did not reach rotation speed (55 knots)",
            }

        time_to_rotation = (rotation_data["timestamp_ms"] - start_ms) / 1000.0

        # Get average thrust and acceleration during takeoff roll
        cursor.execute(
            """
            SELECT
                AVG(thrust_n) as avg_thrust,
                AVG(drag_total_n) as avg_drag,
                AVG(acceleration_mps2) as avg_acceleration
            FROM telemetry
            WHERE timestamp_ms BETWEEN ? AND ?
                AND on_ground = 1
        """,
            (start_ms, rotation_data["timestamp_ms"]),
        )

        avgs = cursor.fetchone()

        return {
            "rotation_achieved": True,
            "time_to_rotation_seconds": time_to_rotation,
            "rotation_speed_kts": rotation_data["airspeed_kts"],
            "thrust_at_rotation_n": rotation_data["thrust_n"],
            "avg_thrust_n": avgs["avg_thrust"],
            "avg_drag_n": avgs["avg_drag"],
            "avg_acceleration_mps2": avgs["avg_acceleration"],
        }

    def get_thrust_curve(self, speed_increment_kts: float = 5.0) -> list:
        """Get thrust vs airspeed curve.

        Args:
            speed_increment_kts: Group speeds into buckets of this size

        Returns:
            List of dicts with speed and average thrust data
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT
                CAST(airspeed_kts / ? AS INTEGER) * ? as speed_bucket,
                AVG(airspeed_kts) as avg_airspeed_kts,
                AVG(thrust_n) as avg_thrust_n,
                AVG(drag_total_n) as avg_drag_n,
                AVG(advance_ratio) as avg_advance_ratio,
                AVG(thrust_correction) as avg_thrust_correction,
                AVG(blend_factor) as avg_blend_factor,
                COUNT(*) as sample_count
            FROM telemetry
            WHERE thrust_n IS NOT NULL AND throttle > 0.9
            GROUP BY speed_bucket
            ORDER BY speed_bucket
        """,
            (speed_increment_kts, speed_increment_kts),
        )

        return [dict(row) for row in cursor.fetchall()]

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics for the flight.

        Returns:
            Dictionary containing flight summary statistics
        """
        cursor = self.conn.cursor()

        # Get overall stats
        cursor.execute("""
            SELECT
                COUNT(*) as frame_count,
                MIN(timestamp_ms) as start_ms,
                MAX(timestamp_ms) as end_ms,
                MAX(airspeed_kts) as max_airspeed_kts,
                MAX(altitude_m) as max_altitude_m,
                MAX(thrust_n) as max_thrust_n,
                AVG(thrust_n) as avg_thrust_n,
                MAX(acceleration_mps2) as max_acceleration_mps2,
                AVG(acceleration_mps2) as avg_acceleration_mps2
            FROM telemetry
        """)

        summary = dict(cursor.fetchone())

        # Calculate flight duration
        if summary["end_ms"] and summary["start_ms"]:
            summary["duration_seconds"] = (summary["end_ms"] - summary["start_ms"]) / 1000.0

        return summary

    def export_to_csv(self, csv_path: str, columns: list | None = None):
        """Export telemetry data to CSV file.

        Args:
            csv_path: Output CSV file path
            columns: List of columns to export (None = all columns)
        """
        import csv

        cursor = self.conn.cursor()

        if columns:
            columns_str = ",".join(columns)
            cursor.execute(f"SELECT {columns_str} FROM telemetry ORDER BY timestamp_ms")
        else:
            cursor.execute("SELECT * FROM telemetry ORDER BY timestamp_ms")

        rows = cursor.fetchall()

        if not rows:
            logger.warning("No data to export")
            return

        # Get column names
        column_names = [description[0] for description in cursor.description]

        # Write CSV
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(column_names)
            writer.writerows(rows)

        logger.info(f"Exported {len(rows)} rows to {csv_path}")

    def close(self):
        """Close database connection."""
        self.conn.close()
