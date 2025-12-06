"""
Storage Manager with Data Synthesis

Manages tire prediction data storage with intelligent synthesis and cleanup.
Maintains <100MB while preserving model accuracy through data distillation.
"""

import os
import json
import gzip
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import shutil


class StorageManager:
    """
    Manages storage of tire prediction data with synthesis.

    Keeps storage under 100MB by synthesizing raw data into compact
    representations before deletion.
    """

    def __init__(self, data_dir: str = 'data'):
        """
        Initialize storage manager.

        Args:
            data_dir: Base data directory
        """
        self.data_dir = Path(data_dir)
        self.sessions_dir = self.data_dir / 'sessions'
        self.models_dir = self.data_dir / 'models'
        self.calibrations_dir = self.data_dir / 'calibrations'

        # Storage limits (bytes)
        self.max_total_size = 100 * 1024 * 1024  # 100MB
        self.warning_threshold = 80 * 1024 * 1024  # 80MB

        # Retention policy
        self.min_sessions_per_combo = 3
        self.session_retention_days = 30
        self.model_retention_days = 60

        # Initialize paths
        self._ensure_directories()

        logging.info("StorageManager initialized")

    def _ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.calibrations_dir.mkdir(parents=True, exist_ok=True)

    def get_storage_stats(self) -> Dict:
        """
        Get current storage statistics.

        Returns:
            Dict with storage info
        """
        total_size = 0
        sessions_size = 0
        models_size = 0
        calibrations_size = 0
        session_count = 0
        model_count = 0

        # Count sessions
        for session_file in self.sessions_dir.glob('*.json.gz'):
            size = session_file.stat().st_size
            sessions_size += size
            total_size += size
            session_count += 1

        # Count models
        for model_file in self.models_dir.glob('*.pkl'):
            size = model_file.stat().st_size
            models_size += size
            total_size += size
            model_count += 1

        # Count calibrations
        for cal_file in self.calibrations_dir.glob('*.json'):
            size = cal_file.stat().st_size
            calibrations_size += size
            total_size += size

        return {
            'total_mb': total_size / (1024 * 1024),
            'sessions_mb': sessions_size / (1024 * 1024),
            'models_mb': models_size / (1024 * 1024),
            'calibrations_mb': calibrations_size / (1024 * 1024),
            'session_count': session_count,
            'model_count': model_count,
            'usage_percent': (total_size / self.max_total_size) * 100,
            'needs_cleanup': total_size > self.warning_threshold
        }

    def check_and_cleanup(self, force: bool = False) -> Dict:
        """
        Check storage and cleanup if needed.

        Args:
            force: Force cleanup even if under threshold

        Returns:
            Dict with cleanup results
        """
        stats = self.get_storage_stats()

        if not force and not stats['needs_cleanup']:
            return {'cleaned': False, 'reason': 'under_threshold', 'stats': stats}

        logging.info(f"Starting cleanup - Current usage: {stats['total_mb']:.1f}MB")

        # Run cleanup procedures
        results = {
            'cleaned': True,
            'before_mb': stats['total_mb'],
            'synthesized_sessions': 0,
            'deleted_sessions': 0,
            'deleted_models': 0
        }

        # 1. Synthesize and cleanup old sessions
        synthesized, deleted = self._cleanup_sessions()
        results['synthesized_sessions'] = synthesized
        results['deleted_sessions'] = deleted

        # 2. Cleanup old models
        deleted_models = self._cleanup_models()
        results['deleted_models'] = deleted_models

        # Get new stats
        new_stats = self.get_storage_stats()
        results['after_mb'] = new_stats['total_mb']
        results['freed_mb'] = results['before_mb'] - results['after_mb']
        results['stats'] = new_stats

        logging.info(f"Cleanup complete - Freed {results['freed_mb']:.1f}MB")

        return results

    def _cleanup_sessions(self) -> Tuple[int, int]:
        """
        Cleanup old sessions with synthesis.

        Returns:
            Tuple of (synthesized_count, deleted_count)
        """
        synthesized = 0
        deleted = 0

        # Group sessions by car/track combo
        sessions_by_combo = self._group_sessions()

        for combo, session_files in sessions_by_combo.items():
            # Sort by date (newest first)
            session_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            # Keep minimum recent sessions
            sessions_to_keep = session_files[:self.min_sessions_per_combo]
            sessions_to_process = session_files[self.min_sessions_per_combo:]

            for session_file in sessions_to_process:
                # Check age
                age_days = (datetime.now().timestamp() - session_file.stat().st_mtime) / 86400

                if age_days > self.session_retention_days:
                    # Synthesize before deleting
                    if self._synthesize_session(session_file, combo):
                        synthesized += 1

                    # Delete original
                    session_file.unlink()
                    deleted += 1
                    logging.debug(f"Deleted old session: {session_file.name}")

        return synthesized, deleted

    def _group_sessions(self) -> Dict[str, List[Path]]:
        """
        Group session files by car/track combination.

        Returns:
            Dict mapping combo to list of session files
        """
        sessions_by_combo = {}

        for session_file in self.sessions_dir.glob('*.json.gz'):
            # Parse filename: car_track_timestamp.json.gz
            parts = session_file.stem.replace('.json', '').split('_')
            if len(parts) >= 2:
                # Reconstruct car and track (may have underscores)
                # Last part is timestamp, second to last might be part of timestamp
                timestamp_start = -1
                for i in range(len(parts) - 1, -1, -1):
                    if parts[i].isdigit() and len(parts[i]) == 8:  # YYYYMMDD
                        timestamp_start = i
                        break

                if timestamp_start > 0:
                    car = '_'.join(parts[:timestamp_start // 2 + 1])
                    track = '_'.join(parts[timestamp_start // 2 + 1:timestamp_start])
                    combo = f"{car}@{track}"

                    if combo not in sessions_by_combo:
                        sessions_by_combo[combo] = []
                    sessions_by_combo[combo].append(session_file)

        return sessions_by_combo

    def _synthesize_session(self, session_file: Path, combo: str) -> bool:
        """
        Synthesize session data into compact form before deletion.

        Args:
            session_file: Path to session file
            combo: Car/track combo identifier

        Returns:
            True if successfully synthesized
        """
        try:
            # Load session
            with gzip.open(session_file, 'rt') as f:
                session = json.load(f)

            # Load or create synthesized data store
            synth_file = self.calibrations_dir / 'synthesized_training_data.json'
            if synth_file.exists():
                with open(synth_file, 'r') as f:
                    synth_data = json.load(f)
            else:
                synth_data = {}

            if combo not in synth_data:
                synth_data[combo] = {
                    'synthetic_samples': [],
                    'total_source_sessions': 0,
                    'confidence': 0.0,
                    'last_updated': datetime.now().isoformat()
                }

            # Extract key data points from session
            samples = self._extract_synthetic_samples(session)

            # Add to synthesized data
            synth_data[combo]['synthetic_samples'].extend(samples)
            synth_data[combo]['total_source_sessions'] += 1

            # Limit sample count (keep most representative)
            if len(synth_data[combo]['synthetic_samples']) > 100:
                synth_data[combo]['synthetic_samples'] = self._select_representative_samples(
                    synth_data[combo]['synthetic_samples'], 100
                )

            # Update confidence
            synth_data[combo]['confidence'] = min(
                synth_data[combo]['total_source_sessions'] / 10.0, 1.0
            )
            synth_data[combo]['last_updated'] = datetime.now().isoformat()

            # Save synthesized data
            with open(synth_file, 'w') as f:
                json.dump(synth_data, f, indent=2)

            return True

        except Exception as e:
            logging.error(f"Error synthesizing session: {e}")
            return False

    def _extract_synthetic_samples(self, session: Dict) -> List[Dict]:
        """
        Extract representative synthetic samples from session.

        Args:
            session: Session data

        Returns:
            List of synthetic samples
        """
        samples = []

        telemetry = session.get('telemetry', [])
        pit_entries = session.get('pit_entries', [])

        if not telemetry or not pit_entries:
            return samples

        # Get environment
        env = session['metadata'].get('environment', {})

        # Extract samples at key points in stint
        for pit_entry in pit_entries:
            total_laps = pit_entry.get('total_laps', 0)
            if total_laps == 0:
                continue

            # Sample at lap 1, mid-stint, and pre-pit
            sample_laps = [1, total_laps // 2, total_laps]

            for lap_num in sample_laps:
                # Find telemetry near this lap
                lap_telemetry = [t for t in telemetry if t.get('lap_num') == lap_num]

                if lap_telemetry:
                    # Average inputs over lap
                    avg_telemetry = self._average_telemetry(lap_telemetry)

                    # Get target temps from pit entry
                    target_temps = pit_entry.get('temps', {})

                    sample = {
                        'lap': lap_num,
                        'stint_time': avg_telemetry.get('stint_time', 0),
                        'track_temp': env.get('track_temp', 75),
                        'avg_throttle': avg_telemetry.get('inputs', {}).get('throttle', 0),
                        'avg_brake': avg_telemetry.get('inputs', {}).get('brake', 0),
                        'avg_speed': avg_telemetry.get('inputs', {}).get('speed', 0),
                        'avg_lateral_g': abs(avg_telemetry.get('g_forces', {}).get('lateral', 0)),
                        'tire_wear': avg_telemetry.get('tire_wear', {}),
                        'target_temps': target_temps
                    }

                    samples.append(sample)

        return samples

    def _average_telemetry(self, telemetry_points: List[Dict]) -> Dict:
        """Average telemetry data points."""
        if not telemetry_points:
            return {}

        avg = {}
        n = len(telemetry_points)

        # Initialize structure from first point
        first = telemetry_points[0]

        # Average numeric values
        for key in ['stint_time']:
            avg[key] = sum(t.get(key, 0) for t in telemetry_points) / n

        # Average inputs
        avg['inputs'] = {
            'throttle': sum(t.get('inputs', {}).get('throttle', 0) for t in telemetry_points) / n,
            'brake': sum(t.get('inputs', {}).get('brake', 0) for t in telemetry_points) / n,
            'speed': sum(t.get('inputs', {}).get('speed', 0) for t in telemetry_points) / n,
        }

        # Average g-forces
        avg['g_forces'] = {
            'lateral': sum(t.get('g_forces', {}).get('lateral', 0) for t in telemetry_points) / n,
        }

        # Use last tire wear
        avg['tire_wear'] = telemetry_points[-1].get('tire_wear', {})

        return avg

    def _select_representative_samples(self, samples: List[Dict], max_count: int) -> List[Dict]:
        """
        Select most representative samples.

        Args:
            samples: List of samples
            max_count: Maximum number to keep

        Returns:
            Filtered list of samples
        """
        if len(samples) <= max_count:
            return samples

        # Sort by stint time for even distribution
        sorted_samples = sorted(samples, key=lambda x: x.get('stint_time', 0))

        # Select evenly spaced samples
        step = len(sorted_samples) / max_count
        selected = [sorted_samples[int(i * step)] for i in range(max_count)]

        return selected

    def _cleanup_models(self) -> int:
        """
        Cleanup old model files.

        Returns:
            Number of models deleted
        """
        deleted = 0

        for model_file in self.models_dir.glob('*.pkl'):
            age_days = (datetime.now().timestamp() - model_file.stat().st_mtime) / 86400

            if age_days > self.model_retention_days:
                model_file.unlink()
                deleted += 1
                logging.debug(f"Deleted old model: {model_file.name}")

        return deleted

    def get_recent_sessions(self, car: Optional[str] = None,
                            track: Optional[str] = None,
                            limit: int = 10) -> List[Path]:
        """
        Get recent session files.

        Args:
            car: Filter by car (optional)
            track: Filter by track (optional)
            limit: Maximum number to return

        Returns:
            List of session file paths
        """
        sessions = list(self.sessions_dir.glob('*.json.gz'))

        # Filter by car/track if specified
        if car:
            sessions = [s for s in sessions if car.lower() in s.name.lower()]
        if track:
            sessions = [s for s in sessions if track.lower() in s.name.lower()]

        # Sort by modification time (newest first)
        sessions.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        return sessions[:limit]
