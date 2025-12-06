"""
Tire Temperature Data Collector

Collects real-time telemetry at 1Hz during sessions and records ground truth
temps at pit entry. Compresses and stores session data efficiently.
"""

import time
import json
import gzip
import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path


class TireDataCollector:
    """
    Collects and stores tire telemetry data during iRacing sessions.

    Records at 1Hz with pit entry ground truth for training tire temp models.
    """

    def __init__(self, data_dir: str = 'data/sessions'):
        """
        Initialize the data collector.

        Args:
            data_dir: Directory to store session data files
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.current_session: Optional[Dict] = None
        self.telemetry_buffer: List[Dict] = []
        self.last_sample_time: float = 0
        self.sample_interval: float = 1.0  # 1Hz sampling

        self.is_recording: bool = False
        self.session_start_time: Optional[float] = None
        self.last_pit_road_state: bool = False

        self.car_id: Optional[str] = None
        self.track_id: Optional[str] = None
        self.session_id: Optional[str] = None

        logging.info("TireDataCollector initialized")

    def should_sample(self) -> bool:
        """Check if enough time has passed for next sample."""
        current_time = time.time()
        if current_time - self.last_sample_time >= self.sample_interval:
            self.last_sample_time = current_time
            return True
        return False

    def start_session(self, car_name: str, track_name: str) -> None:
        """
        Start a new recording session.

        Args:
            car_name: Name/ID of the car
            track_name: Name/ID of the track
        """
        if self.is_recording:
            # Save previous session before starting new one
            self.end_session()

        self.car_id = self._sanitize_name(car_name)
        self.track_id = self._sanitize_name(track_name)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_start_time = time.time()

        self.current_session = {
            'session_id': self.session_id,
            'car': self.car_id,
            'track': self.track_id,
            'start_time': self.session_start_time,
            'telemetry': [],
            'pit_entries': [],
            'metadata': {}
        }

        self.telemetry_buffer = []
        self.is_recording = True
        self.last_pit_road_state = False

        logging.info(f"Started session: {self.car_id} @ {self.track_id}")

    def collect_sample(self, ir_data) -> None:
        """
        Collect a telemetry sample from iRacing.

        Args:
            ir_data: iRacing SDK data object
        """
        if not self.is_recording or not self.should_sample():
            return

        try:
            # Get current state
            on_pit_road = bool(ir_data['OnPitRoad'])

            # Detect pit entry (transition from track to pit)
            if on_pit_road and not self.last_pit_road_state:
                self._record_pit_entry(ir_data)

            self.last_pit_road_state = on_pit_road

            # Collect telemetry sample
            sample = self._extract_telemetry(ir_data)
            if sample:
                self.telemetry_buffer.append(sample)

                # Flush buffer periodically (every 60 samples = 1 minute)
                if len(self.telemetry_buffer) >= 60:
                    self._flush_buffer()

        except Exception as e:
            logging.error(f"Error collecting sample: {e}")

    def _extract_telemetry(self, ir_data) -> Optional[Dict]:
        """
        Extract relevant telemetry data from iRacing.

        Args:
            ir_data: iRacing SDK data object

        Returns:
            Telemetry sample dict or None if invalid
        """
        try:
            # Basic session info
            lap_num = int(ir_data['Lap'] or 0)
            lap_pct = float(ir_data['LapDistPct'] or 0.0)
            session_time = float(ir_data['SessionTime'] or 0.0)
            stint_time = session_time - (self.session_start_time or 0)

            # Driver inputs
            throttle = float(ir_data['Throttle'] or 0.0)
            brake = float(ir_data['Brake'] or 0.0)
            clutch = float(ir_data['Clutch'] or 0.0)
            steering = float(ir_data['SteeringWheelAngle'] or 0.0)

            # Vehicle dynamics
            speed = float(ir_data['Speed'] or 0.0) * 3.6  # m/s to km/h
            lateral_accel = float(ir_data['LatAccel'] or 0.0)
            long_accel = float(ir_data['LongAccel'] or 0.0)
            vert_accel = float(ir_data['VertAccel'] or 0.0)

            # Suspension (shock deflection as proxy for load)
            lf_shock = float(ir_data['LFshockDefl'] or 0.0)
            rf_shock = float(ir_data['RFshockDefl'] or 0.0)
            lr_shock = float(ir_data['LRshockDefl'] or 0.0)
            rr_shock = float(ir_data['RRshockDefl'] or 0.0)

            # Environment
            track_temp = float(ir_data['TrackTempCrew'] or 75.0)
            air_temp = float(ir_data['AirTemp'] or 70.0)

            # Tire wear (0.0 = new, 1.0 = worn out)
            tire_wear = {
                'LF': self._get_avg_wear(ir_data, 'LF'),
                'RF': self._get_avg_wear(ir_data, 'RF'),
                'LR': self._get_avg_wear(ir_data, 'LR'),
                'RR': self._get_avg_wear(ir_data, 'RR')
            }

            sample = {
                'timestamp': time.time(),
                'lap_num': lap_num,
                'lap_pct': lap_pct,
                'stint_time': stint_time,
                'inputs': {
                    'throttle': throttle,
                    'brake': brake,
                    'clutch': clutch,
                    'steering': steering,
                    'speed': speed
                },
                'loads': {
                    'LF_shock': lf_shock,
                    'RF_shock': rf_shock,
                    'LR_shock': lr_shock,
                    'RR_shock': rr_shock
                },
                'g_forces': {
                    'lateral': lateral_accel,
                    'longitudinal': long_accel,
                    'vertical': vert_accel
                },
                'environment': {
                    'track_temp': track_temp,
                    'air_temp': air_temp
                },
                'tire_wear': tire_wear
            }

            return sample

        except Exception as e:
            logging.error(f"Error extracting telemetry: {e}")
            return None

    def _get_avg_wear(self, ir_data, tire: str) -> float:
        """Get average wear across tire zones."""
        try:
            left = float(ir_data[f'{tire}wearL'] or 0.0)
            middle = float(ir_data[f'{tire}wearM'] or 0.0)
            right = float(ir_data[f'{tire}wearR'] or 0.0)
            return (left + middle + right) / 3.0
        except:
            return 0.0

    def _record_pit_entry(self, ir_data) -> None:
        """
        Record ground truth tire temperatures at pit entry.

        Args:
            ir_data: iRacing SDK data object
        """
        try:
            session_time = float(ir_data['SessionTime'] or 0.0)
            lap_num = int(ir_data['Lap'] or 0)

            # Get tire temperatures
            temps = {
                'LF': {
                    'L': float(ir_data['LFtempCL'] or 0.0),
                    'C': float(ir_data['LFtempCM'] or 0.0),
                    'R': float(ir_data['LFtempCR'] or 0.0)
                },
                'RF': {
                    'L': float(ir_data['RFtempCL'] or 0.0),
                    'C': float(ir_data['RFtempCM'] or 0.0),
                    'R': float(ir_data['RFtempCR'] or 0.0)
                },
                'LR': {
                    'L': float(ir_data['LRtempCL'] or 0.0),
                    'C': float(ir_data['LRtempCM'] or 0.0),
                    'R': float(ir_data['LRtempCR'] or 0.0)
                },
                'RR': {
                    'L': float(ir_data['RRtempCL'] or 0.0),
                    'C': float(ir_data['RRtempCM'] or 0.0),
                    'R': float(ir_data['RRtempCR'] or 0.0)
                }
            }

            # Get tire wear
            wear = {
                'LF': {
                    'L': float(ir_data['LFwearL'] or 0.0),
                    'M': float(ir_data['LFwearM'] or 0.0),
                    'R': float(ir_data['LFwearR'] or 0.0)
                },
                'RF': {
                    'L': float(ir_data['RFwearL'] or 0.0),
                    'M': float(ir_data['RFwearM'] or 0.0),
                    'R': float(ir_data['RFwearR'] or 0.0)
                },
                'LR': {
                    'L': float(ir_data['LRwearL'] or 0.0),
                    'M': float(ir_data['LRwearM'] or 0.0),
                    'R': float(ir_data['LRwearR'] or 0.0)
                },
                'RR': {
                    'L': float(ir_data['RRwearL'] or 0.0),
                    'M': float(ir_data['RRwearM'] or 0.0),
                    'R': float(ir_data['RRwearR'] or 0.0)
                }
            }

            # Calculate stint statistics
            stint_duration = session_time - (self.session_start_time or 0)
            avg_lap_time = stint_duration / max(lap_num, 1) if lap_num > 0 else 0

            pit_entry = {
                'pit_entry_time': time.time(),
                'session_time': session_time,
                'stint_duration': stint_duration,
                'total_laps': lap_num,
                'avg_lap_time': avg_lap_time,
                'temps': temps,
                'wear': wear
            }

            if self.current_session:
                self.current_session['pit_entries'].append(pit_entry)

            logging.info(f"Recorded pit entry at lap {lap_num}")

        except Exception as e:
            logging.error(f"Error recording pit entry: {e}")

    def _flush_buffer(self) -> None:
        """Flush telemetry buffer to current session."""
        if self.current_session and self.telemetry_buffer:
            self.current_session['telemetry'].extend(self.telemetry_buffer)
            self.telemetry_buffer = []

    def end_session(self) -> Optional[str]:
        """
        End the current session and save to disk.

        Returns:
            Path to saved session file or None if no session active
        """
        if not self.is_recording or not self.current_session:
            return None

        # Flush any remaining telemetry
        self._flush_buffer()

        # Add end timestamp
        self.current_session['end_time'] = time.time()
        self.current_session['duration'] = (
            self.current_session['end_time'] -
            self.current_session['start_time']
        )

        # Add metadata
        self.current_session['metadata'] = {
            'total_samples': len(self.current_session['telemetry']),
            'pit_entries': len(self.current_session['pit_entries']),
            'has_ground_truth': len(self.current_session['pit_entries']) > 0
        }

        # Save to disk
        filepath = self._save_session(self.current_session)

        # Reset state
        self.is_recording = False
        self.current_session = None
        self.telemetry_buffer = []

        logging.info(f"Session ended and saved to: {filepath}")
        return filepath

    def _save_session(self, session_data: Dict) -> str:
        """
        Save session data to compressed JSON file.

        Args:
            session_data: Session data dictionary

        Returns:
            Path to saved file
        """
        filename = f"{session_data['car']}_{session_data['track']}_{session_data['session_id']}.json.gz"
        filepath = self.data_dir / filename

        with gzip.open(filepath, 'wt', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2)

        # Log file size
        size_kb = filepath.stat().st_size / 1024
        logging.info(f"Saved session: {filename} ({size_kb:.1f} KB)")

        return str(filepath)

    def _sanitize_name(self, name: str) -> str:
        """Sanitize car/track name for use in filename."""
        import re
        # Remove special characters, replace spaces with underscores
        sanitized = re.sub(r'[^\w\s-]', '', name)
        sanitized = re.sub(r'[-\s]+', '_', sanitized)
        return sanitized.lower()

    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about current session."""
        if not self.current_session:
            return {'active': False}

        return {
            'active': True,
            'car': self.car_id,
            'track': self.track_id,
            'duration': time.time() - (self.session_start_time or 0),
            'samples': len(self.current_session['telemetry']) + len(self.telemetry_buffer),
            'pit_entries': len(self.current_session['pit_entries'])
        }
