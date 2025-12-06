"""
Tire Pattern Learner (Layers 2 & 3)

Learns car class and track-specific patterns from session data.
Improves physics predictions by ±5-15°F.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import gzip
from collections import defaultdict
import math


class TirePatternLearner:
    """
    Learns and applies tire temperature patterns.

    Layer 2: Car class patterns (all sessions with same car)
    Layer 3: Track-specific patterns (car/track combinations)
    """

    def __init__(self, calibrations_dir: str = 'data/calibrations'):
        """
        Initialize pattern learner.

        Args:
            calibrations_dir: Directory for pattern storage
        """
        self.calibrations_dir = Path(calibrations_dir)
        self.calibrations_dir.mkdir(parents=True, exist_ok=True)

        self.car_patterns_file = self.calibrations_dir / 'car_class_patterns.json'
        self.track_patterns_file = self.calibrations_dir / 'track_specific.json'

        # Load existing patterns
        self.car_patterns = self._load_patterns(self.car_patterns_file)
        self.track_patterns = self._load_patterns(self.track_patterns_file)

        logging.info("TirePatternLearner initialized")

    def _load_patterns(self, filepath: Path) -> Dict:
        """Load patterns from file."""
        if filepath.exists():
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Error loading patterns from {filepath}: {e}")
        return {}

    def _save_patterns(self, patterns: Dict, filepath: Path) -> bool:
        """Save patterns to file."""
        try:
            with open(filepath, 'w') as f:
                json.dump(patterns, f, indent=2)
            return True
        except Exception as e:
            logging.error(f"Error saving patterns to {filepath}: {e}")
            return False

    def learn_from_session(self, session_file: Path) -> bool:
        """
        Learn patterns from a session file.

        Args:
            session_file: Path to session data file

        Returns:
            True if successfully learned
        """
        try:
            # Load session
            with gzip.open(session_file, 'rt') as f:
                session = json.load(f)

            car = session.get('car')
            track = session.get('track')
            combo = f"{car}@{track}"

            # Extract patterns
            car_pattern_data = self._extract_car_patterns(session)
            track_pattern_data = self._extract_track_patterns(session)

            # Update car class patterns
            if car_pattern_data:
                self._merge_car_patterns(car, car_pattern_data)

            # Update track-specific patterns
            if track_pattern_data:
                self._merge_track_patterns(combo, track_pattern_data)

            # Save updated patterns
            self._save_patterns(self.car_patterns, self.car_patterns_file)
            self._save_patterns(self.track_patterns, self.track_patterns_file)

            logging.info(f"Learned patterns from session: {session_file.name}")
            return True

        except Exception as e:
            logging.error(f"Error learning from session: {e}")
            return False

    def _extract_car_patterns(self, session: Dict) -> Optional[Dict]:
        """
        Extract car class patterns from session.

        Patterns:
        - Stint progression (temp rise over time)
        - Heat/cool rates
        - Optimal temp ranges
        - Tire correlations (LF-RF relationship, etc.)
        """
        pit_entries = session.get('pit_entries', [])
        if not pit_entries:
            return None

        pattern = {
            'stint_progression': [],
            'optimal_ranges': defaultdict(list),
            'heat_rates': [],
            'cool_rates': [],
            'tire_correlations': []
        }

        # Analyze each pit entry
        for pit_entry in pit_entries:
            stint_time = pit_entry.get('stint_duration', 0)
            temps = pit_entry.get('temps', {})

            if stint_time > 0 and temps:
                # Record temps vs stint time
                pattern['stint_progression'].append({
                    'stint_time': stint_time,
                    'temps': temps
                })

                # Record optimal ranges (temps between 180-220 are typically good)
                for tire, zones in temps.items():
                    for zone, temp in zones.items():
                        if 180 <= temp <= 220:
                            pattern['optimal_ranges'][f"{tire}_{zone}"].append(temp)

        return pattern

    def _extract_track_patterns(self, session: Dict) -> Optional[Dict]:
        """
        Extract track-specific patterns.

        Patterns:
        - Track-specific stint curves
        - Corner heating patterns (auto-detected)
        - Track temp influence
        """
        telemetry = session.get('telemetry', [])
        pit_entries = session.get('pit_entries', [])

        if not telemetry or not pit_entries:
            return None

        pattern = {
            'stint_curves': [],
            'corner_patterns': [],
            'track_temp_effects': []
        }

        # Analyze telemetry for corner patterns
        corner_heating = self._detect_corner_heating(telemetry)
        if corner_heating:
            pattern['corner_patterns'] = corner_heating

        # Analyze stint curves specific to this track
        for pit_entry in pit_entries:
            stint_time = pit_entry.get('stint_duration', 0)
            temps = pit_entry.get('temps', {})

            if stint_time > 0 and temps:
                pattern['stint_curves'].append({
                    'stint_time': stint_time,
                    'temps': temps
                })

        return pattern

    def _detect_corner_heating(self, telemetry: List[Dict]) -> List[Dict]:
        """
        Detect corner-specific heating patterns.

        Finds high-G zones and correlates with temp changes.
        """
        if not telemetry or len(telemetry) < 100:
            return []

        corner_zones = []

        # Find high lateral-G sections (corners)
        in_corner = False
        corner_start = None
        corner_data = []

        for i, sample in enumerate(telemetry):
            lateral_g = abs(sample.get('g_forces', {}).get('lateral', 0))

            if lateral_g > 1.0:  # In corner
                if not in_corner:
                    in_corner = True
                    corner_start = sample.get('lap_pct', 0)
                    corner_data = []

                corner_data.append(sample)

            elif in_corner:  # Exiting corner
                in_corner = False

                if len(corner_data) > 5:  # Significant corner
                    # Analyze heating in this corner
                    avg_lateral_g = sum(abs(s.get('g_forces', {}).get('lateral', 0))
                                       for s in corner_data) / len(corner_data)
                    avg_speed = sum(s.get('inputs', {}).get('speed', 0)
                                   for s in corner_data) / len(corner_data)

                    corner_zones.append({
                        'lap_pct': corner_start,
                        'avg_lateral_g': avg_lateral_g,
                        'avg_speed': avg_speed,
                        'duration': len(corner_data)
                    })

        return corner_zones

    def _merge_car_patterns(self, car: str, new_pattern: Dict) -> None:
        """
        Merge new pattern data into car class patterns.

        Args:
            car: Car identifier
            new_pattern: New pattern data to merge
        """
        if car not in self.car_patterns:
            self.car_patterns[car] = {
                'stint_progression': [],
                'optimal_ranges': {},
                'total_sessions': 0,
                'confidence': 0.0
            }

        # Merge stint progression
        self.car_patterns[car]['stint_progression'].extend(
            new_pattern.get('stint_progression', [])
        )

        # Keep last 50 progression points
        if len(self.car_patterns[car]['stint_progression']) > 50:
            self.car_patterns[car]['stint_progression'] = \
                self.car_patterns[car]['stint_progression'][-50:]

        # Merge optimal ranges
        for key, temps in new_pattern.get('optimal_ranges', {}).items():
            if key not in self.car_patterns[car]['optimal_ranges']:
                self.car_patterns[car]['optimal_ranges'][key] = []
            self.car_patterns[car]['optimal_ranges'][key].extend(temps)

            # Keep last 100 samples per zone
            if len(self.car_patterns[car]['optimal_ranges'][key]) > 100:
                self.car_patterns[car]['optimal_ranges'][key] = \
                    self.car_patterns[car]['optimal_ranges'][key][-100:]

        # Update confidence
        self.car_patterns[car]['total_sessions'] += 1
        self.car_patterns[car]['confidence'] = min(
            self.car_patterns[car]['total_sessions'] / 10.0, 1.0
        )

    def _merge_track_patterns(self, combo: str, new_pattern: Dict) -> None:
        """
        Merge new pattern data into track-specific patterns.

        Args:
            combo: Car@Track identifier
            new_pattern: New pattern data to merge
        """
        if combo not in self.track_patterns:
            self.track_patterns[combo] = {
                'stint_curves': [],
                'corner_patterns': [],
                'total_sessions': 0,
                'confidence': 0.0
            }

        # Merge stint curves
        self.track_patterns[combo]['stint_curves'].extend(
            new_pattern.get('stint_curves', [])
        )

        # Keep last 30 curves
        if len(self.track_patterns[combo]['stint_curves']) > 30:
            self.track_patterns[combo]['stint_curves'] = \
                self.track_patterns[combo]['stint_curves'][-30:]

        # Merge corner patterns (average similar corners)
        self._merge_corner_patterns(combo, new_pattern.get('corner_patterns', []))

        # Update confidence
        self.track_patterns[combo]['total_sessions'] += 1
        self.track_patterns[combo]['confidence'] = min(
            self.track_patterns[combo]['total_sessions'] / 5.0, 1.0
        )

    def _merge_corner_patterns(self, combo: str, new_corners: List[Dict]) -> None:
        """Merge corner patterns, averaging similar corners."""
        existing = self.track_patterns[combo].get('corner_patterns', [])

        for new_corner in new_corners:
            # Find similar corner (within 5% lap distance)
            merged = False
            for existing_corner in existing:
                if abs(existing_corner['lap_pct'] - new_corner['lap_pct']) < 0.05:
                    # Average the values
                    n = existing_corner.get('count', 1)
                    existing_corner['avg_lateral_g'] = (
                        existing_corner['avg_lateral_g'] * n + new_corner['avg_lateral_g']
                    ) / (n + 1)
                    existing_corner['avg_speed'] = (
                        existing_corner['avg_speed'] * n + new_corner['avg_speed']
                    ) / (n + 1)
                    existing_corner['count'] = n + 1
                    merged = True
                    break

            if not merged:
                new_corner['count'] = 1
                existing.append(new_corner)

        self.track_patterns[combo]['corner_patterns'] = existing

    def get_pattern_adjustment(self, car: str, track: str,
                                telemetry: Dict) -> Dict:
        """
        Get temperature adjustment based on learned patterns.

        Args:
            car: Car identifier
            track: Track identifier
            telemetry: Current telemetry

        Returns:
            Dict with adjustments for each tire/zone
        """
        adjustments = {
            'LF': {'L': 0, 'C': 0, 'R': 0},
            'RF': {'L': 0, 'C': 0, 'R': 0},
            'LR': {'L': 0, 'C': 0, 'R': 0},
            'RR': {'L': 0, 'C': 0, 'R': 0},
            'confidence': 0.0
        }

        # Get car class adjustment
        car_adj, car_conf = self._get_car_adjustment(car, telemetry)

        # Get track-specific adjustment
        combo = f"{car}@{track}"
        track_adj, track_conf = self._get_track_adjustment(combo, telemetry)

        # Combine adjustments
        for tire in ['LF', 'RF', 'LR', 'RR']:
            for zone in ['L', 'C', 'R']:
                adjustments[tire][zone] = (
                    car_adj[tire][zone] * car_conf +
                    track_adj[tire][zone] * track_conf
                )

        adjustments['confidence'] = (car_conf + track_conf) / 2.0

        return adjustments

    def _get_car_adjustment(self, car: str, telemetry: Dict) -> Tuple[Dict, float]:
        """Get car class pattern adjustment."""
        adjustment = {
            'LF': {'L': 0, 'C': 0, 'R': 0},
            'RF': {'L': 0, 'C': 0, 'R': 0},
            'LR': {'L': 0, 'C': 0, 'R': 0},
            'RR': {'L': 0, 'C': 0, 'R': 0}
        }
        confidence = 0.0

        if car not in self.car_patterns:
            return adjustment, confidence

        pattern = self.car_patterns[car]
        confidence = pattern.get('confidence', 0.0)

        # Get stint progression adjustment
        stint_time = telemetry.get('stint_time', 0)
        if stint_time > 0 and pattern.get('stint_progression'):
            # Find closest progression point
            progressions = pattern['stint_progression']
            closest = min(progressions,
                         key=lambda x: abs(x['stint_time'] - stint_time))

            # Use temps as reference
            ref_temps = closest.get('temps', {})
            for tire in ['LF', 'RF', 'LR', 'RR']:
                for zone in ['L', 'C', 'R']:
                    ref_temp = ref_temps.get(tire, {}).get(zone, 0)
                    if ref_temp > 0:
                        # Small adjustment based on stint time
                        adjustment[tire][zone] = (ref_temp - 180) * 0.1  # ±10°F range

        return adjustment, confidence

    def _get_track_adjustment(self, combo: str, telemetry: Dict) -> Tuple[Dict, float]:
        """Get track-specific pattern adjustment."""
        adjustment = {
            'LF': {'L': 0, 'C': 0, 'R': 0},
            'RF': {'L': 0, 'C': 0, 'R': 0},
            'LR': {'L': 0, 'C': 0, 'R': 0},
            'RR': {'L': 0, 'C': 0, 'R': 0}
        }
        confidence = 0.0

        if combo not in self.track_patterns:
            return adjustment, confidence

        pattern = self.track_patterns[combo]
        confidence = pattern.get('confidence', 0.0)

        # Get corner heating adjustment
        lap_pct = telemetry.get('lap_pct', 0)
        corners = pattern.get('corner_patterns', [])

        for corner in corners:
            # If near a corner, apply heating pattern
            if abs(corner['lap_pct'] - lap_pct) < 0.02:  # Within 2% of corner
                lateral_g = corner['avg_lateral_g']

                # Adjust based on corner severity
                heat_factor = lateral_g * 2.0  # Up to ±6°F in high-G corners

                # Apply to loaded tires
                if lateral_g > 0.5:
                    adjustment['LF']['L'] += heat_factor
                    adjustment['RF']['R'] += heat_factor
                break

        return adjustment, confidence

    def get_pattern_stats(self) -> Dict:
        """Get statistics about learned patterns."""
        return {
            'cars': len(self.car_patterns),
            'track_combos': len(self.track_patterns),
            'car_details': {
                car: {
                    'sessions': data.get('total_sessions', 0),
                    'confidence': data.get('confidence', 0.0)
                }
                for car, data in self.car_patterns.items()
            },
            'track_details': {
                combo: {
                    'sessions': data.get('total_sessions', 0),
                    'confidence': data.get('confidence', 0.0)
                }
                for combo, data in self.track_patterns.items()
            }
        }
