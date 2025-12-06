import irsdk
import os
import logging
import yaml
from typing import Dict, List, Optional, Union, Any

# Import tire prediction system
try:
    from core.tire_predictor import TirePredictor
    TIRE_PREDICTION_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Tire prediction not available: {e}")
    TIRE_PREDICTION_AVAILABLE = False

class DataProvider:
    """
    Provides telemetry data from iRacing.
    
    This class manages the connection to the iRacing SDK and handles
    retrieval of telemetry data and lap times for overlays.
    """

    def __init__(self) -> None:
        """
        Initialize the DataProvider with default values.
        """
        self.ir_sdk = irsdk.IRSDK()
        self.is_connected = False
        self.lap_times: List[float] = []

        # Tire prediction system
        self.tire_predictor = None
        if TIRE_PREDICTION_AVAILABLE:
            try:
                self.tire_predictor = TirePredictor()
                logging.info("Tire prediction system initialized")
            except Exception as e:
                logging.error(f"Error initializing tire predictor: {e}")

        # Session tracking for predictor
        self.current_session_num = -1
        self.current_car_name = None
        self.current_track_name = None

        logging.debug(f"DataProvider initialized. Current working directory: {os.getcwd()}")

    def connect(self) -> bool:
        """
        Establish connection to iRacing.
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        if not self.is_connected:
            self.is_connected = self.ir_sdk.startup()
            if self.is_connected:
                logging.info("Connected to iRacing")
            else:
                logging.warning("Failed to connect to iRacing")
        return self.is_connected

    def disconnect(self) -> None:
        """
        Disconnect from iRacing and clean up resources.
        """
        if self.is_connected:
            self.ir_sdk.shutdown()
            self.is_connected = False
            logging.info("Disconnected from iRacing")

    def get_telemetry_data(self) -> Dict[str, Union[float, int]]:
        """
        Retrieve telemetry data from iRacing.
        
        Returns:
            Dict[str, Union[float, int]]: Dictionary containing telemetry values
                or empty dict if not connected or error occurs
        """
        if not self.is_connected:
            logging.debug("Not connected to iRacing")
            return {}
            
        try:
            self.ir_sdk.freeze_var_buffer_latest()
            return self._extract_data()
        except (TypeError, ValueError, KeyError) as e:
            logging.error(f"Error processing telemetry data: {e}")
            return self._get_default_telemetry()
        except Exception as e:
            logging.error(f"Unexpected error in get_telemetry_data: {e}")
            return {}
    
    def _extract_data(self) -> Dict[str, float | int]:
        """
        Returns one dict that contains both the "live telemetry" numbers
        you were already broadcasting **and** the extra overlay metrics
        (front lap/best time, lap_delta, target pace or best‑gap).

        Keys that are *unused* for a particular session type are present
        with value 0.0, so the websocket payload is always predictable.
        """

        speed_kmh = float(self.ir_sdk['Speed'] or 0.0) * 3.6
        gear      = int(self.ir_sdk['Gear'] or 0)
        throttle  = float(self.ir_sdk['Throttle'] or 0.0)
        brake     = float(self.ir_sdk['Brake'] or 0.0)

        clutch_raw = self.ir_sdk['Clutch']       
        clutch     = 1.0 - float(clutch_raw) if clutch_raw is not None else 1.0

        steering = float(self.ir_sdk['SteeringWheelAngle'] or 0.0)

        base = {
            "speed": speed_kmh,
            "gear": gear,
            "throttle": throttle,
            "brake": brake,
            "clutch": clutch,
            "steering_wheel_angle": steering,
        }
        
        return {**base, **self._compute_overlay_metrics()}

    def _compute_overlay_metrics(self) -> Dict[str, float]:
        """
        Pulls together:
        • front_last_lap_time / front_best_lap_time
        • lap_delta
        • target_pace  (race)   OR   best‑lap delta  (practice/qualy)
        Always returns the three fields so the client has a fixed schema.
        """

        me_idx  = int(self.ir_sdk['PlayerCarIdx'])
        my_last = float(self.ir_sdk['LapLastLapTime']  or -1.0)
        my_best = float(self.ir_sdk['CarIdxBestLapTime'][me_idx] or -1.0)

        if my_last <= 0.0:
            return self._default_front_data()   # we haven't set a lap yet

        session_type = self._current_session_type().lower()

        if session_type == 'race':
            est = self.ir_sdk['CarIdxEstTime']
            if not est:
                return self._default_front_data()

            front_idx, gap_sec = None, None
            for idx, g in enumerate(est):
                if g and g > 0 and (gap_sec is None or g < gap_sec):
                    front_idx, gap_sec = idx, g

            if front_idx is None:
                return self._default_front_data()

            front_last = float(self.ir_sdk['CarIdxLastLapTime'][front_idx] or -1.0)
            if front_last <= 0.0:
                return self._default_front_data()

            lap_delta = front_last - my_last

            sess_laps_remain = int(self.ir_sdk['SessionLapsRemain'])
            if 0 < sess_laps_remain < 32000:
                laps_left = max(sess_laps_remain, 1)
            else:
                secs_left = float(self.ir_sdk['SessionTimeRemain'])
                laps_left = max(int(secs_left / max(my_last, 1e-9)), 1)

            target_pace = my_last - (gap_sec / laps_left) * 1.10

            return {
                "front_last_lap_time": round(front_last, 3),
                "lap_delta":           round(lap_delta, 3),
                "target_pace":         round(max(target_pace, 0.0), 3),
                "session_type":        session_type,
            }

        best_array = self.ir_sdk['CarIdxBestLapTime']
        if not best_array:
            return self._default_front_data()

        standings = sorted(
            [(idx, t) for idx, t in enumerate(best_array) if t and t > 0],
            key=lambda x: x[1]
        )

        my_pos = next((i for i, (idx, _) in enumerate(standings) if idx == me_idx), None)
        if my_pos is None or my_pos == 0:
            return self._default_front_data()   

        front_idx, front_best = standings[my_pos - 1]
        best_delta = my_best - front_best
        
        front_last = float(self.ir_sdk['CarIdxLastLapTime'][front_idx] or -1.0)
        lap_delta  = (front_last - my_last) if front_last > 0 else 0.0

        return {
            "front_best_lap_time": round(front_best, 3),
            "target_pace":          round(lap_delta, 3),
            "lap_delta":         round(best_delta, 3),
            "session_type":        "practice",
        }

    
    def _current_session_type(self) -> str:
        """
        Return the current session type ('Race', 'Qualify', 'Practice', …).

        Works whether irsdk delivers SessionInfo as:
        • a YAML string  **or**
        • an already‑parsed dict
        """
        try:
            sess_num = int(self.ir_sdk['SessionNum'])

            raw = self.ir_sdk['SessionInfo']
            # iRacing 2024.4+ may give us a dict already
            if isinstance(raw, dict):
                info = raw
            else:
                info = yaml.safe_load(raw or "") or {}

            for sess in info.get('Sessions', []):
                if int(sess.get('SessionNum', -1)) == sess_num:
                    return str(sess.get('SessionType', 'Race'))
        except Exception as e:
            logging.debug(f"Could not parse SessionInfo: {e}")

        # default so the overlay logic still works
        return 'Race'
    
    def _default_front_data(self) -> Dict[str, float]:
        """Return zeroed values when we can't compute the real ones."""
        return {"front_last_lap_time": 0.0, "lap_delta": 0.0, "target_pace": 0.0}
    
    def _get_default_telemetry(self) -> Dict[str, Union[float, int]]:
        """
        Provide default telemetry values when data cannot be retrieved.
        
        Returns:
            Dict[str, Union[float, int]]: Default telemetry values
        """
        return {
            'speed': 0.0,
            'gear': 0,
            'throttle': 0.0,
            'brake': 0.0,
            'clutch': 1.0,
            'steering_wheel_angle': 0.0
        }
    
    def get_lap_times(self) -> List[float]:
        """
        Retrieve the last 10 lap times from iRacing.
        
        Updates internal lap times list and returns all stored times.
        
        Returns:
            List[float]: List of up to 10 most recent lap times or empty list if not connected
        """
        if not self.is_connected:
            logging.debug("Not connected to iRacing")
            return []
        
        try:
            self._update_lap_times()
            return self.lap_times
        except (TypeError, ValueError, KeyError) as e:
            logging.error(f"Error processing lap times: {e}")
            return self.lap_times
        except Exception as e:
            logging.error(f"Unexpected error in get_lap_times: {e}")
            return []
    
    def _update_lap_times(self) -> None:
        """
        Update the stored lap times with new data from iRacing.
        """
        current_lap = self.ir_sdk['Lap']
        
        if not isinstance(current_lap, (int, float)) or current_lap is None:
            return
        
        current_lap = int(current_lap)
        lap_time = self.ir_sdk['LapCurrentLapTime']
        
        if not isinstance(lap_time, (int, float)) or lap_time is None:
            lap_time = 0.0
        
        lap_time = float(lap_time)
        
        if current_lap > len(self.lap_times):
            self.lap_times.append(lap_time)
            if len(self.lap_times) > 10:
                self.lap_times.pop(0)

    def get_standings_data(self) -> Dict[str, Any]:
        """
        Retrieve standings data for the relative standings overlay.

        Returns a dict containing:
        - player_idx: Player's car index
        - standings: List of driver standings with position, name, class, etc.
        - session_type: Current session type
        - is_multiclass: Whether this is a multiclass race

        Returns:
            Dict[str, Any]: Standings data or empty dict if not connected
        """
        if not self.is_connected:
            logging.debug("Not connected to iRacing")
            return {}

        try:
            self.ir_sdk.freeze_var_buffer_latest()
            return self._extract_standings()
        except Exception as e:
            logging.error(f"Error extracting standings data: {e}")
            return {}

    def _extract_standings(self) -> Dict[str, Any]:
        """
        Extract and compute standings information from iRacing telemetry.

        Calculates:
        - Current race positions
        - Driver information from SessionInfo
        - Time intervals between cars
        - Position deltas from race start
        - Lap counts and pit status
        """
        # Get player car index
        player_idx = int(self.ir_sdk['PlayerCarIdx'])

        # Get session info
        session_type = self._current_session_type()

        # Parse SessionInfo for driver metadata
        raw_session_info = self.ir_sdk['SessionInfo']
        if isinstance(raw_session_info, dict):
            session_info = raw_session_info
        else:
            session_info = yaml.safe_load(raw_session_info or "") or {}

        # Build driver info lookup
        driver_info = {}
        for driver in session_info.get('DriverInfo', {}).get('Drivers', []):
            car_idx = int(driver.get('CarIdx', -1))
            if car_idx >= 0:
                driver_info[car_idx] = {
                    'name': driver.get('UserName', 'Unknown'),
                    'car_class_short': driver.get('CarClassShortName', ''),
                    'car_class_color': driver.get('CarClassColor', 0xFFFFFF),
                    'car_number': driver.get('CarNumber', ''),
                }

        # Determine if multiclass
        unique_classes = set(d['car_class_short'] for d in driver_info.values() if d['car_class_short'])
        is_multiclass = len(unique_classes) > 1

        # Get telemetry arrays
        positions = self.ir_sdk['CarIdxPosition']
        lap_dist_pct = self.ir_sdk['CarIdxLapDistPct']
        last_lap_times = self.ir_sdk['CarIdxLastLapTime']
        lap_counts = self.ir_sdk['CarIdxLap']
        track_surface = self.ir_sdk['CarIdxTrackSurface']
        on_pit_road = self.ir_sdk['CarIdxOnPitRoad']

        # License and iRating arrays
        license_strings = self.ir_sdk['CarIdxLicString']
        iratings = self.ir_sdk['CarIdxIRating']

        # Get starting positions for delta calculation
        starting_positions = self._get_starting_positions(session_info)

        # Build standings list
        standings = []

        for idx in range(len(positions) if positions else 0):
            # Skip if not on track (NotInWorld = -1)
            if track_surface and track_surface[idx] == -1:
                continue

            position = positions[idx] if positions else 0

            # Skip invalid positions
            if position <= 0:
                continue

            # Get driver info
            driver = driver_info.get(idx, {
                'name': f'Car {idx}',
                'car_class_short': '',
                'car_class_color': 0xFFFFFF,
                'car_number': str(idx),
            })

            # Calculate position delta from start
            start_pos = starting_positions.get(idx, position)
            position_delta = start_pos - position  # Positive = gained positions

            # Get last lap time
            last_lap = last_lap_times[idx] if last_lap_times and last_lap_times[idx] > 0 else 0.0

            # Get lap count
            lap = lap_counts[idx] if lap_counts else 0

            # Check pit status
            in_pit = bool(on_pit_road[idx]) if on_pit_road else False

            # Get license and iRating
            license_str = license_strings[idx] if license_strings else ''
            irating = int(iratings[idx]) if iratings and iratings[idx] > 0 else 0

            # Get lap distance percentage for interval calculation
            dist_pct = lap_dist_pct[idx] if lap_dist_pct else 0.0

            standings.append({
                'car_idx': idx,
                'position': position,
                'driver_name': driver['name'],
                'car_number': driver['car_number'],
                'car_class': driver['car_class_short'],
                'car_class_color': driver['car_class_color'],
                'license': license_str,
                'irating': irating,
                'last_lap_time': round(last_lap, 3) if last_lap > 0 else 0.0,
                'lap_count': lap,
                'in_pit': in_pit,
                'position_delta': position_delta,
                'lap_dist_pct': dist_pct,
                'is_player': idx == player_idx,
            })

        # Sort by position
        standings.sort(key=lambda x: x['position'])

        # Calculate intervals (time gap to car ahead)
        standings = self._calculate_intervals(standings)

        return {
            'player_idx': player_idx,
            'standings': standings,
            'session_type': session_type,
            'is_multiclass': is_multiclass,
        }

    def _get_starting_positions(self, session_info: Dict) -> Dict[int, int]:
        """
        Extract starting grid positions from SessionInfo.

        Args:
            session_info: Parsed SessionInfo YAML

        Returns:
            Dict mapping car_idx to starting position
        """
        starting_positions = {}

        try:
            session_num = int(self.ir_sdk['SessionNum'])

            for session in session_info.get('Sessions', []):
                if int(session.get('SessionNum', -1)) == session_num:
                    results = session.get('ResultsPositions', [])

                    # If this is a race, try to get grid from qualifying results
                    if session.get('SessionType', '').lower() == 'race' and not results:
                        # Look for qualifying session results
                        for prev_session in session_info.get('Sessions', []):
                            if prev_session.get('SessionType', '').lower() in ['qualify', 'qualifying']:
                                results = prev_session.get('ResultsPositions', [])
                                break

                    # Get starting positions from results
                    for result in results:
                        car_idx = int(result.get('CarIdx', -1))
                        position = int(result.get('Position', -1))
                        if car_idx >= 0 and position >= 0:
                            starting_positions[car_idx] = position + 1  # Position is 0-indexed

                    break
        except Exception as e:
            logging.debug(f"Could not extract starting positions: {e}")

        return starting_positions

    def _calculate_intervals(self, standings: List[Dict]) -> List[Dict]:
        """
        Calculate time intervals between cars.

        For cars on the same lap, estimate time gap based on lap distance percentage.
        For lapped cars, show lap deficit.

        Args:
            standings: List of driver standings sorted by position

        Returns:
            List of standings with 'interval' field added
        """
        for i, driver in enumerate(standings):
            if i == 0:
                # Leader has no interval
                driver['interval'] = 'LEADER'
                driver['interval_seconds'] = 0.0
            else:
                car_ahead = standings[i - 1]

                # Check lap difference
                lap_diff = car_ahead['lap_count'] - driver['lap_count']

                if lap_diff > 0:
                    # Lapped
                    driver['interval'] = f"+{lap_diff} LAP" if lap_diff == 1 else f"+{lap_diff} LAPS"
                    driver['interval_seconds'] = 999.0  # Large number for sorting
                elif lap_diff < 0:
                    # Car ahead is lapped (shouldn't happen in sorted order, but handle it)
                    driver['interval'] = f"-{abs(lap_diff)} LAP" if abs(lap_diff) == 1 else f"-{abs(lap_diff)} LAPS"
                    driver['interval_seconds'] = -999.0
                else:
                    # Same lap - estimate time gap using lap distance percentage and last lap time
                    dist_diff = car_ahead['lap_dist_pct'] - driver['lap_dist_pct']

                    if dist_diff < 0:
                        dist_diff += 1.0  # Wrapped around

                    # Use car ahead's last lap time to estimate gap
                    if car_ahead['last_lap_time'] > 0:
                        gap_seconds = dist_diff * car_ahead['last_lap_time']
                        driver['interval'] = f"+{gap_seconds:.3f}s"
                        driver['interval_seconds'] = gap_seconds
                    else:
                        driver['interval'] = "---"
                        driver['interval_seconds'] = 0.0

        return standings

    def get_tire_data(self) -> Dict[str, Any]:
        """
        Retrieve tire temperature, wear, and pressure data.

        Returns:
            Dict[str, Any]: Tire data including temperatures, wear, pressure, and status
                or empty dict if not connected or error occurs
        """
        if not self.is_connected:
            logging.debug("Not connected to iRacing")
            return {}

        try:
            self.ir_sdk.freeze_var_buffer_latest()
            return self._extract_tire_data()
        except Exception as e:
            logging.error(f"Error extracting tire data: {e}")
            return {}

    def _extract_tire_data(self) -> Dict[str, Any]:
        """
        Extract tire temperature, wear, and pressure information from iRacing telemetry.

        Returns:
            Dict with tire data including temperatures, wear, pressure, and pit status
        """
        # Check if player is in pit
        in_pit = bool(self.ir_sdk['OnPitRoad'])

        # Get tire temperatures (these may be None if not in pit for some car classes)
        temperatures = {
            'LF': {
                'L': self._safe_get_float('LFtempCL'),
                'C': self._safe_get_float('LFtempCM'),
                'R': self._safe_get_float('LFtempCR')
            },
            'RF': {
                'L': self._safe_get_float('RFtempCL'),
                'C': self._safe_get_float('RFtempCM'),
                'R': self._safe_get_float('RFtempCR')
            },
            'LR': {
                'L': self._safe_get_float('LRtempCL'),
                'C': self._safe_get_float('LRtempCM'),
                'R': self._safe_get_float('LRtempCR')
            },
            'RR': {
                'L': self._safe_get_float('RRtempCL'),
                'C': self._safe_get_float('RRtempCM'),
                'R': self._safe_get_float('RRtempCR')
            }
        }

        # Get tire wear (0.0 = new, 1.0 = completely worn)
        wear = {
            'LF': {
                'L': self._safe_get_float('LFwearL'),
                'M': self._safe_get_float('LFwearM'),
                'R': self._safe_get_float('LFwearR')
            },
            'RF': {
                'L': self._safe_get_float('RFwearL'),
                'M': self._safe_get_float('RFwearM'),
                'R': self._safe_get_float('RFwearR')
            },
            'LR': {
                'L': self._safe_get_float('LRwearL'),
                'M': self._safe_get_float('LRwearM'),
                'R': self._safe_get_float('LRwearR')
            },
            'RR': {
                'L': self._safe_get_float('RRwearL'),
                'M': self._safe_get_float('RRwearM'),
                'R': self._safe_get_float('RRwearR')
            }
        }

        # Get tire pressure
        pressure = {
            'LF': self._safe_get_float('LFpressure'),
            'RF': self._safe_get_float('RFpressure'),
            'LR': self._safe_get_float('LRpressure'),
            'RR': self._safe_get_float('RRpressure')
        }

        # Check if temperature data is actually available
        # Some car classes only update temps in pits
        data_available = self._check_temp_data_available(temperatures)

        return {
            'temperatures': temperatures,
            'wear': wear,
            'pressure': pressure,
            'in_pit': in_pit,
            'data_available': data_available
        }

    def _safe_get_float(self, key: str) -> Optional[float]:
        """
        Safely get a float value from iRacing SDK.

        Args:
            key: The telemetry key to retrieve

        Returns:
            Float value or None if not available
        """
        try:
            value = self.ir_sdk[key]
            if value is not None and value > 0:
                return float(value)
            return None
        except (KeyError, TypeError, ValueError):
            return None

    def _check_temp_data_available(self, temperatures: Dict) -> bool:
        """
        Check if temperature data is actually updating.

        Some car classes only update tire temps when in pit lane.

        Args:
            temperatures: Temperature data dict

        Returns:
            True if temp data appears to be available
        """
        # Check if any temperature value is non-zero
        for tire_data in temperatures.values():
            for temp in tire_data.values():
                if temp is not None and temp > 0:
                    return True
        return False

    def get_tire_predictions(self) -> Dict[str, Any]:
        """
        Get tire temperature predictions from prediction system.

        Returns:
            Dict with predicted temps, confidence, trends, and advice
        """
        if not self.tire_predictor or not self.is_connected:
            return {}

        try:
            # Check for session changes
            self._check_session_change()

            # Get current telemetry for prediction
            telemetry = self._extract_prediction_telemetry()

            if not telemetry:
                return {}

            # Get predictions
            predictions = self.tire_predictor.predict(telemetry)

            # If in pit, calibrate with actual temps
            if self.ir_sdk['OnPitRoad']:
                actual_temps = self._get_actual_temps()
                if actual_temps:
                    self.tire_predictor.calibrate_with_actual(actual_temps)
                    # Include actual temps in response
                    predictions['actual_temps'] = actual_temps
                    predictions['in_pit'] = True
            else:
                predictions['in_pit'] = False

            return predictions

        except Exception as e:
            logging.error(f"Error getting tire predictions: {e}")
            return {}

    def _check_session_change(self) -> None:
        """Check if session has changed and update prediction session."""
        try:
            session_num = int(self.ir_sdk['SessionNum'] or -1)

            # Session changed?
            if session_num != self.current_session_num:
                # End old session
                if self.current_session_num >= 0 and self.tire_predictor:
                    logging.info(f"Session ended: {self.current_session_num}")
                    self.tire_predictor.end_session()

                # Start new session
                if session_num >= 0:
                    car_name = self._get_car_name()
                    track_name = self._get_track_name()

                    if car_name and track_name and self.tire_predictor:
                        self.tire_predictor.start_session(car_name, track_name)
                        self.current_car_name = car_name
                        self.current_track_name = track_name
                        logging.info(f"Session started: {car_name} @ {track_name}")

                self.current_session_num = session_num

        except Exception as e:
            logging.error(f"Error checking session change: {e}")

    def _get_car_name(self) -> Optional[str]:
        """Get current car name from SessionInfo."""
        try:
            player_idx = int(self.ir_sdk['PlayerCarIdx'])
            session_info = self.ir_sdk['SessionInfo']

            if isinstance(session_info, dict):
                info = session_info
            else:
                info = yaml.safe_load(session_info or "") or {}

            drivers = info.get('DriverInfo', {}).get('Drivers', [])
            for driver in drivers:
                if int(driver.get('CarIdx', -1)) == player_idx:
                    return driver.get('CarScreenName', 'Unknown')

            return None
        except:
            return None

    def _get_track_name(self) -> Optional[str]:
        """Get current track name from SessionInfo."""
        try:
            session_info = self.ir_sdk['SessionInfo']

            if isinstance(session_info, dict):
                info = session_info
            else:
                info = yaml.safe_load(session_info or "") or {}

            weekend_info = info.get('WeekendInfo', {})
            return weekend_info.get('TrackDisplayName', 'Unknown')

        except:
            return None

    def _extract_prediction_telemetry(self) -> Optional[Dict]:
        """
        Extract telemetry data for tire prediction.

        Similar to _extract_telemetry but includes all fields needed for prediction.
        """
        try:
            self.ir_sdk.freeze_var_buffer_latest()

            # Reuse existing extraction methods
            telemetry_data = self._extract_data()

            # Add additional fields for prediction
            telemetry_data['lap_num'] = int(self.ir_sdk['Lap'] or 0)
            telemetry_data['lap_pct'] = float(self.ir_sdk['LapDistPct'] or 0.0)

            # Calculate stint time
            session_time = float(self.ir_sdk['SessionTime'] or 0.0)
            # For now, use session time as stint time (could track pit stops for accuracy)
            telemetry_data['stint_time'] = session_time

            # Add structured data expected by predictor
            telemetry_data['timestamp'] = __import__('time').time()

            telemetry_data['inputs'] = {
                'throttle': telemetry_data.get('throttle', 0.0),
                'brake': telemetry_data.get('brake', 0.0),
                'clutch': telemetry_data.get('clutch', 0.0),
                'steering': telemetry_data.get('steering_wheel_angle', 0.0),
                'speed': telemetry_data.get('speed', 0.0)
            }

            telemetry_data['g_forces'] = {
                'lateral': float(self.ir_sdk['LatAccel'] or 0.0),
                'longitudinal': float(self.ir_sdk['LongAccel'] or 0.0),
                'vertical': float(self.ir_sdk['VertAccel'] or 0.0)
            }

            telemetry_data['loads'] = {
                'LF_shock': float(self.ir_sdk['LFshockDefl'] or 0.0),
                'RF_shock': float(self.ir_sdk['RFshockDefl'] or 0.0),
                'LR_shock': float(self.ir_sdk['LRshockDefl'] or 0.0),
                'RR_shock': float(self.ir_sdk['RRshockDefl'] or 0.0)
            }

            telemetry_data['environment'] = {
                'track_temp': float(self.ir_sdk['TrackTempCrew'] or 75.0),
                'air_temp': float(self.ir_sdk['AirTemp'] or 70.0)
            }

            telemetry_data['tire_wear'] = {
                'LF': (float(self.ir_sdk['LFwearL'] or 0.0) +
                       float(self.ir_sdk['LFwearM'] or 0.0) +
                       float(self.ir_sdk['LFwearR'] or 0.0)) / 3.0,
                'RF': (float(self.ir_sdk['RFwearL'] or 0.0) +
                       float(self.ir_sdk['RFwearM'] or 0.0) +
                       float(self.ir_sdk['RFwearR'] or 0.0)) / 3.0,
                'LR': (float(self.ir_sdk['LRwearL'] or 0.0) +
                       float(self.ir_sdk['LRwearM'] or 0.0) +
                       float(self.ir_sdk['LRwearR'] or 0.0)) / 3.0,
                'RR': (float(self.ir_sdk['RRwearL'] or 0.0) +
                       float(self.ir_sdk['RRwearM'] or 0.0) +
                       float(self.ir_sdk['RRwearR'] or 0.0)) / 3.0
            }

            return telemetry_data

        except Exception as e:
            logging.error(f"Error extracting prediction telemetry: {e}")
            return None

    def _get_actual_temps(self) -> Optional[Dict]:
        """Get actual tire temperatures (when in pit)."""
        try:
            return {
                'LF': {
                    'L': float(self.ir_sdk['LFtempCL'] or 0.0),
                    'C': float(self.ir_sdk['LFtempCM'] or 0.0),
                    'R': float(self.ir_sdk['LFtempCR'] or 0.0)
                },
                'RF': {
                    'L': float(self.ir_sdk['RFtempCL'] or 0.0),
                    'C': float(self.ir_sdk['RFtempCM'] or 0.0),
                    'R': float(self.ir_sdk['RFtempCR'] or 0.0)
                },
                'LR': {
                    'L': float(self.ir_sdk['LRtempCL'] or 0.0),
                    'C': float(self.ir_sdk['LRtempCM'] or 0.0),
                    'R': float(self.ir_sdk['LRtempCR'] or 0.0)
                },
                'RR': {
                    'L': float(self.ir_sdk['RRtempCL'] or 0.0),
                    'C': float(self.ir_sdk['RRtempCM'] or 0.0),
                    'R': float(self.ir_sdk['RRtempCR'] or 0.0)
                }
            }
        except:
            return None