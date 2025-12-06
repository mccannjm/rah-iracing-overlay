# Race Standings Overlay

A real-time relative standings overlay for iRacing that displays race positions dynamically around the player's current position.

## Features

### Data Display
- **Position**: Current race position
- **Driver Name**: From SessionInfo (DriverInfo.Drivers[idx].UserName)
- **Car Class**: From SessionInfo (DriverInfo.Drivers[idx].CarClassShortName)
- **License**: CarIdxLicString (formatted as "A4.5")
- **iRating**: CarIdxIRating
- **Last Lap Time**: CarIdxLastLapTime (formatted as MM:SS.mmm)
- **Interval/Gap**: Time delta to car ahead (or laps down)
- **Delta**: Position change since race start (+3, -2, etc.)

### Relative View
- **Always shows P1** (race leader) at the top
- **Shows 5 cars ahead** of player
- **Highlights player's car** with golden background
- **Shows 5 cars behind** player
- **Dynamic adjustment**:
  - If player in top 5: shows more cars behind
  - If player in bottom 5: shows more cars ahead

### Visual Features
- **Color coding**:
  - Green delta: positions gained since start
  - Red delta: positions lost since start
  - Car class colors for multiclass racing
  - Player row: golden highlight
- **Pit status**: Orange border and "PIT" label for cars on pit road
- **Smooth updates**: Throttled to 100ms for performance
- **Connection indicator**: Shows real-time Socket.IO connection status

## Configuration

You can customize the overlay by editing the configuration in `standings.js`:

```javascript
const CONFIG = {
    carsAhead: 5,        // Number of cars to show ahead of player
    carsBehind: 5,       // Number of cars to show behind player
    alwaysShowLeader: true,  // Always show P1 at top
    updateThrottle: 100, // ms between UI updates
};
```

### Window Properties

Edit `properties.json` to change default window size and position:

```json
{
    "resolution": {
        "width": 600,    // Window width in pixels
        "height": 800    // Window height in pixels
    },
    "position": {
        "x": 100,        // Default X position
        "y": 100         // Default Y position
    }
}
```

## Technical Details

### Backend (data_provider.py)
- **`get_standings_data()`**: Main method that retrieves standings
- **`_extract_standings()`**: Parses SessionInfo YAML and telemetry arrays
- **`_get_starting_positions()`**: Extracts starting grid from SessionInfo
- **`_calculate_intervals()`**: Computes time gaps between cars

### Frontend (standings.js)
- **Socket.IO Connection**: Connects to `/standings` namespace
- **Relative View Filtering**: `filterRelativeStandings()` calculates visible range
- **UI Rendering**: `renderStandings()` updates DOM efficiently
- **Update Throttling**: Limits UI updates to reduce performance impact

### Styling (standings.css)
- **Grid Layout**: CSS Grid for consistent column alignment
- **Responsive**: Adjusts for smaller screens
- **GPU Acceleration**: Uses `transform: translateZ(0)` for smooth rendering
- **Backdrop Blur**: Semi-transparent background with blur effect

## Data Flow

```
iRacing SDK
    ↓
DataProvider.get_standings_data()
    ↓
WebInterface._process_telemetry_data()
    ↓
SocketIO.emit('standings_update', namespace='/standings')
    ↓
standings.js receives data
    ↓
Filter relative standings
    ↓
Update DOM
```

## Interval Calculation

The overlay calculates time gaps between cars using:

1. **Same Lap**: Uses `CarIdxLapDistPct` and last lap time to estimate gap
   - `gap = (dist_ahead - dist_player) * last_lap_time_ahead`

2. **Lapped Cars**: Shows lap deficit
   - "+1 LAP", "+2 LAPS", etc.

3. **Leader**: Shows "LEADER" text

## Position Delta Calculation

Position delta shows how many positions gained/lost since race start:

1. **Starting Positions**: Extracted from SessionInfo `ResultsPositions`
2. **Current Position**: From `CarIdxPosition` telemetry array
3. **Delta**: `start_pos - current_pos`
   - Positive (green): Gained positions
   - Negative (red): Lost positions
   - Zero: No change

## Session Types

The overlay adapts to different session types:

- **Race**: Shows race positions and time gaps
- **Qualifying**: Shows positions based on best lap times
- **Practice**: Shows positions based on lap times

## Multiclass Racing

For multiclass races:
- Car class colors are applied from SessionInfo
- All drivers shown in overall position order
- Class abbreviations displayed (GT3, LMP2, etc.)

## Performance

- **Update Rate**: Backend emits data at ~30 FPS
- **UI Throttle**: Frontend updates limited to 10 FPS (100ms)
- **Efficient DOM Updates**: Only modified rows are updated
- **GPU Acceleration**: CSS transforms for smooth rendering

## Troubleshooting

### Overlay Not Showing
1. Check that iRacing is running
2. Verify Socket.IO connection (check connection indicator)
3. Check browser console for errors (F12)

### Incorrect Positions
1. Verify you're in a session (not in pits/garage)
2. Wait for race to start (positions may be invalid before green flag)

### Performance Issues
1. Increase `updateThrottle` in CONFIG (e.g., 200ms)
2. Reduce `carsAhead` and `carsBehind` to show fewer cars

## Customization Examples

### Show More Cars
```javascript
const CONFIG = {
    carsAhead: 8,
    carsBehind: 8,
    // ...
};
```

### Hide Leader When Not Nearby
```javascript
const CONFIG = {
    alwaysShowLeader: false,
    // ...
};
```

### Change Player Highlight Color
Edit `standings.css`:
```css
.standing-row.player-row {
    background: rgba(0, 212, 255, 0.15);  /* Blue instead of gold */
    border-left-color: #00d4ff;
}
```

## File Structure

```
standings/
├── standings.html          # HTML template
├── properties.json         # Overlay metadata and config
├── README.md              # This file
└── static/
    ├── standings.js       # Socket.IO client and UI logic
    ├── standings.css      # Styling
    └── images/            # Optional preview images
```

## Credits

Built following the iRacing overlay architecture established in this project.
