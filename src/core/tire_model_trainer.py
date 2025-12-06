"""
Tire Temperature ML Model Trainer (Layer 4)

Trains GradientBoosting models for tire temperature prediction.
12 models per car (4 tires × 3 zones).
"""

import pickle
import gzip
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score


class TireModelTrainer:
    """
    Trains and manages ML models for tire temperature prediction.

    Uses GradientBoostingRegressor with automatic training after sessions.
    """

    def __init__(self, models_dir: str = 'data/models',
                 sessions_dir: str = 'data/sessions'):
        """
        Initialize model trainer.

        Args:
            models_dir: Directory for saved models
            sessions_dir: Directory with session data
        """
        self.models_dir = Path(models_dir)
        self.sessions_dir = Path(sessions_dir)

        self.models_dir.mkdir(parents=True, exist_ok=True)

        # Model hyperparameters
        self.model_params = {
            'n_estimators': 100,
            'learning_rate': 0.1,
            'max_depth': 4,
            'min_samples_split': 10,
            'min_samples_leaf': 4,
            'subsample': 0.8,
            'random_state': 42
        }

        # Training requirements
        self.min_samples_for_training = 50
        self.validation_split = 0.2

        logging.info("TireModelTrainer initialized")

    def train_models(self, car: str, force_retrain: bool = False) -> Dict:
        """
        Train models for a specific car.

        Args:
            car: Car identifier
            force_retrain: Force retraining even if models exist

        Returns:
            Dict with training results
        """
        start_time = time.time()

        logging.info(f"Training models for {car}")

        # Load training data
        features, targets = self._load_training_data(car)

        if len(features) < self.min_samples_for_training:
            logging.warning(f"Insufficient data for {car}: {len(features)} samples")
            return {
                'success': False,
                'reason': 'insufficient_data',
                'samples': len(features)
            }

        # Train models for each tire/zone
        results = {
            'car': car,
            'models_trained': 0,
            'models_improved': 0,
            'samples': len(features),
            'metrics': {}
        }

        for tire in ['LF', 'RF', 'LR', 'RR']:
            for zone in ['L', 'C', 'R']:
                model_key = f"{tire}_{zone}"

                # Get target temps for this tire/zone
                zone_targets = self._extract_zone_targets(targets, tire, zone)

                if len(zone_targets) < self.min_samples_for_training:
                    continue

                # Train model
                model, metrics = self._train_single_model(features, zone_targets)

                if model:
                    # Check if better than existing
                    should_save = force_retrain or self._is_model_better(
                        car, model_key, metrics
                    )

                    if should_save:
                        self._save_model(car, model_key, model, metrics)
                        results['models_improved'] += 1

                    results['models_trained'] += 1
                    results['metrics'][model_key] = metrics

        training_time = time.time() - start_time
        results['training_time'] = training_time

        logging.info(
            f"Training complete for {car}: "
            f"{results['models_trained']} trained, "
            f"{results['models_improved']} improved "
            f"in {training_time:.1f}s"
        )

        return results

    def _load_training_data(self, car: str) -> Tuple[np.ndarray, List[Dict]]:
        """
        Load and prepare training data for a car.

        Args:
            car: Car identifier

        Returns:
            Tuple of (features, targets) where targets is list of temp dicts
        """
        all_features = []
        all_targets = []

        # Find all sessions for this car
        session_files = list(self.sessions_dir.glob(f"{car}_*.json.gz"))

        logging.info(f"Loading {len(session_files)} sessions for {car}")

        for session_file in session_files:
            try:
                with gzip.open(session_file, 'rt') as f:
                    session = json.load(f)

                # Extract features and targets from session
                features, targets = self._extract_features_targets(session)

                all_features.extend(features)
                all_targets.extend(targets)

            except Exception as e:
                logging.error(f"Error loading session {session_file}: {e}")

        # Convert to numpy array
        if all_features:
            features_array = np.array(all_features)
        else:
            features_array = np.array([]).reshape(0, 0)

        logging.info(f"Loaded {len(all_features)} training samples")

        return features_array, all_targets

    def _extract_features_targets(self, session: Dict) -> Tuple[List, List]:
        """
        Extract features and targets from a session.

        Features: lap_num, stint_time, track_temp, avg inputs, wear, etc.
        Targets: actual temps from pit entries
        """
        features = []
        targets = []

        telemetry = session.get('telemetry', [])
        pit_entries = session.get('pit_entries', [])

        if not telemetry or not pit_entries:
            return features, targets

        # For each pit entry, use telemetry from last lap
        for pit_entry in pit_entries:
            lap_num = pit_entry.get('total_laps', 0)
            stint_time = pit_entry.get('stint_duration', 0)

            # Get telemetry from last lap before pit
            last_lap_telemetry = [t for t in telemetry if t.get('lap_num') == lap_num]

            if not last_lap_telemetry:
                continue

            # Average telemetry over last lap
            avg_telemetry = self._average_telemetry(last_lap_telemetry)

            # Extract features
            feature_vec = self._telemetry_to_features(
                avg_telemetry, lap_num, stint_time
            )

            # Get target temps
            target_temps = pit_entry.get('temps', {})

            if feature_vec and target_temps:
                features.append(feature_vec)
                targets.append(target_temps)

        return features, targets

    def _average_telemetry(self, telemetry_points: List[Dict]) -> Dict:
        """Average telemetry over multiple points."""
        if not telemetry_points:
            return {}

        n = len(telemetry_points)

        avg = {
            'inputs': {
                'throttle': sum(t.get('inputs', {}).get('throttle', 0) for t in telemetry_points) / n,
                'brake': sum(t.get('inputs', {}).get('brake', 0) for t in telemetry_points) / n,
                'speed': sum(t.get('inputs', {}).get('speed', 0) for t in telemetry_points) / n,
            },
            'g_forces': {
                'lateral': sum(abs(t.get('g_forces', {}).get('lateral', 0)) for t in telemetry_points) / n,
                'longitudinal': sum(t.get('g_forces', {}).get('longitudinal', 0) for t in telemetry_points) / n,
            },
            'environment': telemetry_points[-1].get('environment', {}),
            'tire_wear': telemetry_points[-1].get('tire_wear', {})
        }

        return avg

    def _telemetry_to_features(self, telemetry: Dict, lap_num: int,
                                stint_time: float) -> List[float]:
        """
        Convert telemetry to feature vector.

        Features (15 total):
        - lap_num
        - stint_time
        - track_temp
        - air_temp
        - avg_throttle
        - avg_brake
        - avg_speed
        - avg_lateral_g
        - avg_long_g
        - LF_wear, RF_wear, LR_wear, RR_wear
        - stint_minutes
        - laps_per_minute
        """
        try:
            inputs = telemetry.get('inputs', {})
            g_forces = telemetry.get('g_forces', {})
            env = telemetry.get('environment', {})
            wear = telemetry.get('tire_wear', {})

            stint_minutes = stint_time / 60.0
            laps_per_minute = lap_num / max(stint_minutes, 0.1)

            features = [
                float(lap_num),
                float(stint_time),
                float(env.get('track_temp', 75.0)),
                float(env.get('air_temp', 70.0)),
                float(inputs.get('throttle', 0.0)),
                float(inputs.get('brake', 0.0)),
                float(inputs.get('speed', 0.0)),
                float(g_forces.get('lateral', 0.0)),
                float(g_forces.get('longitudinal', 0.0)),
                float(wear.get('LF', 1.0)),
                float(wear.get('RF', 1.0)),
                float(wear.get('LR', 1.0)),
                float(wear.get('RR', 1.0)),
                float(stint_minutes),
                float(laps_per_minute)
            ]

            return features

        except Exception as e:
            logging.error(f"Error creating feature vector: {e}")
            return []

    def _extract_zone_targets(self, targets: List[Dict], tire: str,
                               zone: str) -> np.ndarray:
        """Extract target temperatures for specific tire/zone."""
        zone_targets = []

        for target in targets:
            temp = target.get(tire, {}).get(zone, 0)
            if temp > 0:  # Valid temperature
                zone_targets.append(temp)
            else:
                zone_targets.append(np.nan)  # Will be filtered

        # Filter out invalid values
        zone_targets = np.array(zone_targets)
        valid_targets = zone_targets[~np.isnan(zone_targets)]

        return valid_targets

    def _train_single_model(self, features: np.ndarray,
                            targets: np.ndarray) -> Tuple[Optional[object], Dict]:
        """
        Train a single GradientBoosting model.

        Args:
            features: Feature array
            targets: Target array

        Returns:
            Tuple of (model, metrics)
        """
        try:
            # Filter out samples with missing targets
            valid_mask = ~np.isnan(targets)
            X = features[valid_mask]
            y = targets[valid_mask]

            if len(X) < self.min_samples_for_training:
                return None, {'error': 'insufficient_samples'}

            # Split data (temporal - oldest for training, newest for validation)
            split_idx = int(len(X) * (1 - self.validation_split))
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]

            # Train model
            model = GradientBoostingRegressor(**self.model_params)
            model.fit(X_train, y_train)

            # Evaluate
            train_pred = model.predict(X_train)
            val_pred = model.predict(X_val)

            metrics = {
                'train_mae': mean_absolute_error(y_train, train_pred),
                'val_mae': mean_absolute_error(y_val, val_pred),
                'train_r2': r2_score(y_train, train_pred),
                'val_r2': r2_score(y_val, val_pred),
                'n_samples': len(X)
            }

            return model, metrics

        except Exception as e:
            logging.error(f"Error training model: {e}")
            return None, {'error': str(e)}

    def _is_model_better(self, car: str, model_key: str, new_metrics: Dict) -> bool:
        """
        Check if new model is better than existing.

        Args:
            car: Car identifier
            model_key: Model key (e.g., 'LF_L')
            new_metrics: Metrics from new model

        Returns:
            True if new model is better or no existing model
        """
        model_path = self.models_dir / f"{car}_{model_key}.pkl"

        if not model_path.exists():
            return True  # No existing model

        try:
            # Load existing model metadata
            with open(model_path, 'rb') as f:
                saved_data = pickle.load(f)

            old_metrics = saved_data.get('metrics', {})
            old_mae = old_metrics.get('val_mae', float('inf'))
            new_mae = new_metrics.get('val_mae', float('inf'))

            # New model is better if lower MAE
            return new_mae < old_mae

        except Exception as e:
            logging.error(f"Error checking existing model: {e}")
            return True  # If error, replace

    def _save_model(self, car: str, model_key: str, model: object,
                    metrics: Dict) -> bool:
        """
        Save model to disk.

        Args:
            car: Car identifier
            model_key: Model key
            model: Trained model
            metrics: Model metrics

        Returns:
            True if saved successfully
        """
        try:
            model_path = self.models_dir / f"{car}_{model_key}.pkl"

            model_data = {
                'model': model,
                'metrics': metrics,
                'car': car,
                'model_key': model_key,
                'trained_at': time.time()
            }

            with open(model_path, 'wb') as f:
                pickle.dump(model_data, f)

            size_kb = model_path.stat().st_size / 1024
            logging.info(f"Saved model: {car}_{model_key}.pkl ({size_kb:.1f} KB)")

            return True

        except Exception as e:
            logging.error(f"Error saving model: {e}")
            return False

    def load_models(self, car: str) -> Dict[str, object]:
        """
        Load all models for a car.

        Args:
            car: Car identifier

        Returns:
            Dict mapping model_key to model object
        """
        models = {}

        for tire in ['LF', 'RF', 'LR', 'RR']:
            for zone in ['L', 'C', 'R']:
                model_key = f"{tire}_{zone}"
                model_path = self.models_dir / f"{car}_{model_key}.pkl"

                if model_path.exists():
                    try:
                        with open(model_path, 'rb') as f:
                            model_data = pickle.load(f)
                        models[model_key] = model_data

                    except Exception as e:
                        logging.error(f"Error loading model {model_key}: {e}")

        logging.info(f"Loaded {len(models)} models for {car}")
        return models

    def predict(self, models: Dict, features: List[float]) -> Dict:
        """
        Predict temperatures using trained models.

        Args:
            models: Dict of loaded models
            features: Feature vector

        Returns:
            Dict with predicted temps and confidence
        """
        predictions = {
            'LF': {'L': 0, 'C': 0, 'R': 0},
            'RF': {'L': 0, 'C': 0, 'R': 0},
            'LR': {'L': 0, 'C': 0, 'R': 0},
            'RR': {'L': 0, 'C': 0, 'R': 0},
            'confidence': 0.0
        }

        if not models or not features:
            return predictions

        try:
            features_array = np.array(features).reshape(1, -1)
            confidence_sum = 0
            models_used = 0

            for tire in ['LF', 'RF', 'LR', 'RR']:
                for zone in ['L', 'C', 'R']:
                    model_key = f"{tire}_{zone}"

                    if model_key in models:
                        model_data = models[model_key]
                        model = model_data['model']
                        metrics = model_data.get('metrics', {})

                        # Predict
                        pred = model.predict(features_array)[0]
                        predictions[tire][zone] = float(pred)

                        # Calculate confidence from validation MAE
                        mae = metrics.get('val_mae', 50)
                        # Lower MAE = higher confidence
                        conf = max(0, 1 - mae / 50)
                        confidence_sum += conf
                        models_used += 1

            # Average confidence
            if models_used > 0:
                predictions['confidence'] = confidence_sum / models_used

        except Exception as e:
            logging.error(f"Error in prediction: {e}")

        return predictions

    def get_model_stats(self, car: str) -> Dict:
        """Get statistics about models for a car."""
        stats = {
            'car': car,
            'models': {},
            'total_models': 0,
            'avg_accuracy': 0.0
        }

        models = self.load_models(car)
        mae_sum = 0

        for model_key, model_data in models.items():
            metrics = model_data.get('metrics', {})
            stats['models'][model_key] = {
                'val_mae': metrics.get('val_mae', 0),
                'val_r2': metrics.get('val_r2', 0),
                'n_samples': metrics.get('n_samples', 0)
            }
            mae_sum += metrics.get('val_mae', 0)

        stats['total_models'] = len(models)
        if len(models) > 0:
            stats['avg_accuracy'] = mae_sum / len(models)

        return stats
