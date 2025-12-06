"""
Tire Temperature Predictor (Main Coordinator)

Coordinates all 4 prediction layers with confidence-based blending.
Always provides predictions, learns automatically, stays under 100MB.
"""

import time
import logging
import threading
from typing import Dict, Optional, List
from collections import deque

from tire_physics_model import TirePhysicsModel
from tire_pattern_learner import TirePatternLearner
from tire_model_trainer import TireModelTrainer
from tire_data_collector import TireDataCollector
from storage_manager import StorageManager


class TirePredictor:
    """
    Main tire temperature prediction coordinator.

    Blends 4 layers:
    1. Physics (always active, ±15-20°F)
    2. Car patterns (±5-10°F improvement)
    3. Track patterns (±3-5°F improvement)
    4. ML models (±5-10°F with data)

    Learns automatically, provides actionable advice.
    """

    def __init__(self):
        """Initialize the tire predictor system."""
        # Initialize all layers
        self.physics_model = TirePhysicsModel()
        self.pattern_learner = TirePatternLearner()
        self.model_trainer = TireModelTrainer()
        self.data_collector = TireDataCollector()
        self.storage_manager = StorageManager()

        # Current state
        self.current_car: Optional[str] = None
        self.current_track: Optional[str] = None
        self.loaded_models: Dict = {}

        # Predictions and history
        self.current_predictions = self._empty_predictions()
        self.temp_history = {tire: {zone: deque(maxlen=30) for zone in ['L', 'C', 'R']}
                            for tire in ['LF', 'RF', 'LR', 'RR']}
        self.last_actual_temps = {}

        # Training queue and background thread
        self.training_queue: List[str] = []
        self.training_lock = threading.Lock()
        self.training_thread: Optional[threading.Thread] = None
        self.should_stop_training = False

        # Performance tracking
        self.prediction_times = deque(maxlen=100)

        logging.info("TirePredictor initialized")

    def start_session(self, car_name: str, track_name: str) -> None:
        """
        Start a new prediction session.

        Args:
            car_name: Name of the car
            track_name: Name of the track
        """
        self.current_car = car_name
        self.current_track = track_name

        # Start data collection
        self.data_collector.start_session(car_name, track_name)

        # Load models for this car
        self.loaded_models = self.model_trainer.load_models(car_name)

        # Reset physics model
        self.physics_model.reset()

        # Clear history
        for tire in self.temp_history:
            for zone in self.temp_history[tire]:
                self.temp_history[tire][zone].clear()

        logging.info(f"Started prediction session: {car_name} @ {track_name}")
        logging.info(f"Loaded {len(self.loaded_models)} ML models")

    def end_session(self) -> None:
        """End the current session and trigger learning."""
        if not self.current_car:
            return

        # Stop data collection and save session
        session_file = self.data_collector.end_session()

        if session_file:
            # Learn patterns from session
            self.pattern_learner.learn_from_session(Path(session_file))

            # Queue training if we have enough new data
            self._queue_training(self.current_car)

        # Check storage and cleanup if needed
        stats = self.storage_manager.get_storage_stats()
        if stats.get('needs_cleanup'):
            logging.info("Storage cleanup needed")
            self.storage_manager.check_and_cleanup()

        # Reset state
        self.current_car = None
        self.current_track = None
        self.loaded_models = {}

        logging.info("Session ended")

    def predict(self, telemetry: Dict) -> Dict:
        """
        Predict tire temperatures from current telemetry.

        Args:
            telemetry: Current telemetry data

        Returns:
            Dict with predictions, confidence, trends, and advice
        """
        start_time = time.time()

        # Collect sample for training
        if self.data_collector.is_recording:
            self.data_collector.collect_sample(telemetry)

        # Get predictions from all layers
        physics_pred = self._get_physics_prediction(telemetry)
        pattern_adj, pattern_conf = self._get_pattern_adjustment(telemetry)
        ml_pred, ml_conf = self._get_ml_prediction(telemetry)

        # Blend predictions
        final_pred = self._blend_predictions(
            physics_pred, pattern_adj, ml_pred, pattern_conf, ml_conf
        )

        # Calculate confidence
        final_pred['confidence'] = self._calculate_confidence(
            pattern_conf, ml_conf, telemetry
        )

        # Add trends
        final_pred['trends'] = self._calculate_trends(final_pred['temps'])

        # Add actionable advice
        final_pred['advice'] = self._generate_advice(
            final_pred['temps'], final_pred['trends'], telemetry
        )

        # Update history
        self._update_history(final_pred['temps'])

        # Track performance
        pred_time = (time.time() - start_time) * 1000  # ms
        self.prediction_times.append(pred_time)

        self.current_predictions = final_pred

        return final_pred

    def _get_physics_prediction(self, telemetry: Dict) -> Dict:
        """Get Layer 1 physics prediction."""
        return self.physics_model.predict(telemetry)

    def _get_pattern_adjustment(self, telemetry: Dict) -> tuple:
        """Get Layers 2-3 pattern adjustments."""
        if not self.current_car or not self.current_track:
            return self._empty_adjustments(), 0.0

        adjustment = self.pattern_learner.get_pattern_adjustment(
            self.current_car, self.current_track, telemetry
        )

        confidence = adjustment.get('confidence', 0.0)
        return adjustment, confidence

    def _get_ml_prediction(self, telemetry: Dict) -> tuple:
        """Get Layer 4 ML prediction."""
        if not self.loaded_models or not telemetry:
            return self._empty_predictions(), 0.0

        # Extract features from telemetry
        features = self.model_trainer._telemetry_to_features(
            telemetry,
            telemetry.get('lap_num', 0),
            telemetry.get('stint_time', 0)
        )

        if not features:
            return self._empty_predictions(), 0.0

        # Predict
        prediction = self.model_trainer.predict(self.loaded_models, features)

        confidence = prediction.get('confidence', 0.0)
        return prediction, confidence

    def _blend_predictions(self, physics: Dict, pattern_adj: Dict,
                           ml_pred: Dict, pattern_conf: float,
                           ml_conf: float) -> Dict:
        """
        Blend all prediction layers with confidence weighting.

        Weights:
        - Physics: 0.3 (always baseline)
        - Patterns: 0.2 × confidence
        - Track: 0.2 × confidence (in pattern_adj)
        - ML: 0.3 × confidence
        """
        blended = {
            'temps': {
                'LF': {'L': 0, 'C': 0, 'R': 0},
                'RF': {'L': 0, 'C': 0, 'R': 0},
                'LR': {'L': 0, 'C': 0, 'R': 0},
                'RR': {'L': 0, 'C': 0, 'R': 0}
            }
        }

        for tire in ['LF', 'RF', 'LR', 'RR']:
            for zone in ['L', 'C', 'R']:
                # Physics baseline (30%)
                physics_temp = physics.get(tire, {}).get(zone, 70)
                physics_weight = 0.3

                # Pattern adjustment (20% × confidence)
                pattern_adjustment = pattern_adj.get(tire, {}).get(zone, 0)
                pattern_weight = 0.2 * pattern_conf

                # ML prediction (30% × confidence)
                ml_temp = ml_pred.get(tire, {}).get(zone, 0)
                ml_weight = 0.3 * ml_conf

                # Weighted blend
                total_weight = physics_weight + pattern_weight + ml_weight

                if total_weight > 0:
                    blended_temp = (
                        physics_temp * physics_weight +
                        (physics_temp + pattern_adjustment) * pattern_weight +
                        ml_temp * ml_weight
                    ) / total_weight
                else:
                    blended_temp = physics_temp

                # Clamp to reasonable range
                blended_temp = max(60, min(blended_temp, 300))

                blended['temps'][tire][zone] = round(blended_temp, 1)

        return blended

    def _calculate_confidence(self, pattern_conf: float, ml_conf: float,
                             telemetry: Dict) -> float:
        """
        Calculate overall prediction confidence.

        Factors:
        - Pattern confidence (40%)
        - ML confidence (40%)
        - Stint progress (20% - lower confidence later in stint)
        """
        # Pattern and ML confidence (average)
        model_conf = (pattern_conf + ml_conf) / 2.0

        # Stint progress factor (confidence decreases with stint length)
        stint_time = telemetry.get('stint_time', 0)
        max_stint_time = 1200  # 20 minutes
        stint_factor = max(0, 1 - stint_time / max_stint_time)

        # Has actual temps recently?
        has_recent_actual = len(self.last_actual_temps) > 0
        actual_factor = 0.1 if has_recent_actual else 0.0

        # Weighted confidence
        confidence = (
            model_conf * 0.70 +
            stint_factor * 0.20 +
            actual_factor * 0.10
        )

        return max(0.0, min(confidence, 1.0))

    def _calculate_trends(self, temps: Dict) -> Dict:
        """
        Calculate temperature trends for each tire.

        Returns:
        - trend: 'heating_fast', 'heating', 'stable', 'cooling', 'cooling_fast'
        - rate: °F per lap
        """
        trends = {}

        for tire in ['LF', 'RF', 'LR', 'RR']:
            # Get average temp for tire
            tire_temps = temps.get(tire, {})
            current_avg = sum(tire_temps.values()) / len(tire_temps)

            # Get history
            history = []
            for zone in ['L', 'C', 'R']:
                if self.temp_history[tire][zone]:
                    history.extend(list(self.temp_history[tire][zone]))

            if len(history) >= 10:
                # Calculate rate of change
                recent = history[-5:]
                older = history[-10:-5]

                recent_avg = sum(recent) / len(recent)
                older_avg = sum(older) / len(older)

                rate = (recent_avg - older_avg) / 5.0  # Per sample (lap)

                # Classify trend
                if rate > 5:
                    trend = 'heating_fast'
                    symbol = '⬆⬆'
                elif rate > 2:
                    trend = 'heating'
                    symbol = '⬆'
                elif rate < -5:
                    trend = 'cooling_fast'
                    symbol = '⬇⬇'
                elif rate < -2:
                    trend = 'cooling'
                    symbol = '⬇'
                else:
                    trend = 'stable'
                    symbol = '→'

                trends[tire] = {
                    'trend': trend,
                    'rate': round(rate, 1),
                    'symbol': symbol
                }
            else:
                trends[tire] = {
                    'trend': 'unknown',
                    'rate': 0,
                    'symbol': '?'
                }

        return trends

    def _generate_advice(self, temps: Dict, trends: Dict, telemetry: Dict) -> List[str]:
        """Generate actionable advice based on predictions."""
        advice = []

        # Check for overheating fronts
        lf_avg = sum(temps['LF'].values()) / 3
        rf_avg = sum(temps['RF'].values()) / 3

        if lf_avg > 230 or rf_avg > 230:
            if trends['LF']['trend'] in ['heating', 'heating_fast']:
                laps_to_pit = max(1, int((250 - lf_avg) / max(trends['LF']['rate'], 1)))
                advice.append(f"⚠ Fronts overheating - pit in {laps_to_pit}-{laps_to_pit+2} laps")

        # Check for cold tires
        all_temps = []
        for tire_temps in temps.values():
            all_temps.extend(tire_temps.values())
        avg_temp = sum(all_temps) / len(all_temps)

        if avg_temp < 150:
            advice.append("❄ Tires cold - push harder to build temp")

        # Check for imbalance
        if abs(lf_avg - rf_avg) > 15:
            advice.append("⚖ Front temp imbalance - check setup")

        return advice

    def _update_history(self, temps: Dict) -> None:
        """Update temperature history."""
        for tire in ['LF', 'RF', 'LR', 'RR']:
            for zone in ['L', 'C', 'R']:
                temp = temps.get(tire, {}).get(zone, 0)
                if temp > 0:
                    self.temp_history[tire][zone].append(temp)

    def calibrate_with_actual(self, actual_temps: Dict) -> None:
        """
        Calibrate predictions with actual measured temps.

        Args:
            actual_temps: Actual temps from iRacing (in pit)
        """
        self.last_actual_temps = actual_temps

        # Calibrate physics model
        self.physics_model.calibrate(actual_temps)

        logging.info("Calibrated with actual temperatures")

    def _queue_training(self, car: str) -> None:
        """Queue model training for a car."""
        with self.training_lock:
            if car not in self.training_queue:
                self.training_queue.append(car)

        # Start training thread if not running
        if not self.training_thread or not self.training_thread.is_alive():
            self._start_training_thread()

    def _start_training_thread(self) -> None:
        """Start background training thread."""
        def training_worker():
            while not self.should_stop_training:
                with self.training_lock:
                    if not self.training_queue:
                        break
                    car = self.training_queue.pop(0)

                logging.info(f"Background training for {car}")
                self.model_trainer.train_models(car)

                time.sleep(1)  # Breathe

        self.training_thread = threading.Thread(target=training_worker)
        self.training_thread.daemon = True
        self.training_thread.start()

    def _empty_predictions(self) -> Dict:
        """Return empty prediction structure."""
        return {
            'temps': {
                'LF': {'L': 70, 'C': 70, 'R': 70},
                'RF': {'L': 70, 'C': 70, 'R': 70},
                'LR': {'L': 70, 'C': 70, 'R': 70},
                'RR': {'L': 70, 'C': 70, 'R': 70}
            },
            'confidence': 0.0,
            'trends': {},
            'advice': []
        }

    def _empty_adjustments(self) -> Dict:
        """Return empty adjustment structure."""
        return {
            'LF': {'L': 0, 'C': 0, 'R': 0},
            'RF': {'L': 0, 'C': 0, 'R': 0},
            'LR': {'L': 0, 'C': 0, 'R': 0},
            'RR': {'L': 0, 'C': 0, 'R': 0}
        }

    def get_stats(self) -> Dict:
        """Get system statistics."""
        storage_stats = self.storage_manager.get_storage_stats()
        pattern_stats = self.pattern_learner.get_pattern_stats()

        avg_pred_time = (sum(self.prediction_times) / len(self.prediction_times)
                        if self.prediction_times else 0)

        return {
            'session': {
                'car': self.current_car,
                'track': self.current_track,
                'active': self.data_collector.is_recording
            },
            'storage': storage_stats,
            'patterns': pattern_stats,
            'models': {
                'loaded': len(self.loaded_models),
                'car': self.current_car
            },
            'performance': {
                'avg_prediction_time_ms': round(avg_pred_time, 2),
                'samples_collected': len(self.prediction_times)
            }
        }

    def shutdown(self) -> None:
        """Shutdown the predictor system."""
        self.should_stop_training = True

        if self.training_thread and self.training_thread.is_alive():
            self.training_thread.join(timeout=5)

        if self.data_collector.is_recording:
            self.end_session()

        logging.info("TirePredictor shutdown complete")
