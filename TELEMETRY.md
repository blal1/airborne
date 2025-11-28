# SQLite Telemetry System

The AirBorne flight simulator now includes a comprehensive SQLite-based telemetry logging system that records all flight data with millisecond precision timestamps.

## Features

- ✅ **Millisecond timestamps** - Precise timing for replay capability
- ✅ **Complete aircraft state** - Position, velocity, orientation, controls
- ✅ **Engine & propeller data** - RPM, power, thrust, efficiency, advance ratio
- ✅ **Aerodynamic forces** - Lift, drag (parasite/induced), thrust
- ✅ **Ground physics** - Rolling resistance, friction coefficients
- ✅ **Automatic buffering** - Efficient batch writes (~1 second buffer at 60fps)
- ✅ **SQL queries** - Analyze specific conditions or time periods
- ✅ **CSV export** - Export data for external analysis tools
- ✅ **Flight replay capability** - All data needed to reproduce flight

## Usage

### 1. Fly and Record

Telemetry logging is **automatic** - just start the simulator and fly:

```bash
uv run python -m airborne.main
```

The telemetry database will be created in `/tmp` with a timestamp:
```
/tmp/airborne_telemetry_20251027_123456.db
```

The path is logged at startup:
```
INFO - Telemetry logging to: /tmp/airborne_telemetry_20251027_123456.db
```

### 2. Analyze Results

After your flight, use the analysis script:

```bash
python scripts/analyze_telemetry.py /tmp/airborne_telemetry_20251027_123456.db
```

This will show:
- **Takeoff performance** - Time to rotation, thrust, drag, acceleration
- **Thrust curve** - Thrust vs airspeed with advance ratio and corrections
- **Flight summary** - Duration, max speeds, altitudes, forces

Example output:
```
📊 TAKEOFF PERFORMANCE
────────────────────────────────────────────────────────────────────────────────
✅ Reached rotation speed in 18.3 seconds
   Rotation speed: 55.2 knots
   Thrust at rotation: 1149.2 N
   Average thrust: 1087.5 N
   Average drag: 185.3 N
   Average acceleration: 0.67 m/s²

   Performance: 81.9% of realistic C172

📈 THRUST VS AIRSPEED CURVE
────────────────────────────────────────────────────────────────────────────────
Speed (kts)  │ Thrust (N) │ Drag (N) │ Net (N) │ J      │ Correction │ Samples
─────────────────────────────────────────────────────────────────────────────────
        0.0  │      860.3 │      0.0 │   860.3 │  0.000 │      1.450 │      120
        5.0  │     1283.5 │     25.8 │  1257.7 │  0.058 │      1.399 │     180
       10.0  │     1257.2 │     92.4 │  1164.8 │  0.116 │      1.348 │     210
       15.0  │     1120.8 │    194.7 │   926.1 │  0.174 │      1.296 │     185
       20.0  │     1186.4 │    332.1 │   854.3 │  0.232 │      1.245 │     165
       25.0  │     1149.2 │    508.3 │   640.9 │  0.291 │      1.194 │     142
```

### 3. Export to CSV

Export the entire dataset for analysis in Excel, Python, etc.:

```python
from airborne.telemetry import TelemetryAnalyzer

analyzer = TelemetryAnalyzer('/tmp/airborne_telemetry_20251027_123456.db')
analyzer.export_to_csv('flight_data.csv')
```

### 4. Custom SQL Queries

Query the database directly for specific analysis:

```python
from airborne.telemetry import TelemetryAnalyzer

analyzer = TelemetryAnalyzer('/tmp/airborne_telemetry_20251027_123456.db')

# Get thrust when airspeed is 20-25 knots
results = analyzer.query("""
    SELECT timestamp_ms, airspeed_kts, thrust_n, drag_total_n
    FROM telemetry
    WHERE airspeed_kts BETWEEN 20 AND 25
        AND throttle > 0.9
    ORDER BY timestamp_ms
""")

for row in results:
    print(f"Time: {row[0]}ms, Speed: {row[1]:.1f}kts, Thrust: {row[2]:.1f}N")
```

## Database Schema

The telemetry table includes (excerpt):

| Column | Type | Description |
|--------|------|-------------|
| `timestamp_ms` | INTEGER | Milliseconds since start |
| `timestamp_real` | REAL | Unix timestamp (ms precision) |
| `frame_count` | INTEGER | Frame number |
| `dt` | REAL | Delta time (seconds) |
| `airspeed_mps` | REAL | Airspeed (m/s) |
| `airspeed_kts` | REAL | Airspeed (knots) |
| `thrust_n` | REAL | Propeller thrust (Newtons) |
| `drag_total_n` | REAL | Total drag (Newtons) |
| `advance_ratio` | REAL | Propeller advance ratio (J) |
| `thrust_correction` | REAL | Momentum theory correction factor |
| `blend_factor` | REAL | Static/dynamic thrust blend |
| `acceleration_mps2` | REAL | Acceleration (m/s²) |

See `src/airborne/telemetry/telemetry_logger.py` for complete schema.

## Performance Impact

Telemetry logging is designed for minimal performance impact:
- **Buffered writes**: Data buffered in memory (~1 second at 60fps)
- **Batch inserts**: Single database transaction per buffer flush
- **Indexed columns**: Fast queries on timestamp, airspeed, on_ground
- **~0.1ms overhead**: Negligible impact on 60fps simulation

## Troubleshooting

### Database not found

Check the simulator logs for the telemetry path:
```bash
grep "Telemetry logging to" <simulator_log>
```

### No propeller data

If `thrust_n` is NULL, the propeller model may not be configured:
```sql
SELECT COUNT(*) FROM telemetry WHERE thrust_n IS NOT NULL;
```

### Missing force data

If `drag_total_n` or `lift_n` are NULL, the flight model may not be exposing force data. This is expected for some flight models.

## Examples

### Find when engine reached full power

```sql
SELECT timestamp_ms / 1000.0 as time_sec, engine_power_hp, engine_rpm
FROM telemetry
WHERE engine_power_hp > 170
ORDER BY timestamp_ms
LIMIT 1;
```

### Average acceleration during takeoff roll

```sql
SELECT AVG(acceleration_mps2) as avg_accel_mps2
FROM telemetry
WHERE on_ground = 1
    AND throttle > 0.9
    AND airspeed_kts < 55;
```

### Thrust at specific speeds

```sql
SELECT
    CAST(airspeed_kts / 5 AS INTEGER) * 5 as speed_bucket,
    AVG(thrust_n) as avg_thrust,
    AVG(drag_total_n) as avg_drag,
    COUNT(*) as samples
FROM telemetry
WHERE throttle > 0.9 AND thrust_n IS NOT NULL
GROUP BY speed_bucket
ORDER BY speed_bucket;
```

## Future Enhancements

Planned features:
- [ ] Real-time telemetry streaming to external tools
- [ ] Replay system to visualize recorded flights
- [ ] Comparison tool to analyze multiple flights
- [ ] Web-based telemetry viewer
- [ ] Export to common formats (KML, GPX, FDR)

## Technical Details

**Location**: `src/airborne/telemetry/`
- `telemetry_logger.py` - Core logging system
- `__init__.py` - Package exports

**Integration**: Physics plugin (`src/airborne/plugins/core/physics_plugin.py`)
- Logs data every frame after physics update
- Captures state from flight model, propeller, engine
- Automatically closes database on shutdown

**Database**: SQLite 3
- Location: `/tmp/airborne_telemetry_YYYYMMDD_HHMMSS.db`
- Schema version: 1.0
- Compatible with: sqlite3 CLI, DB Browser for SQLite, Python sqlite3 module
