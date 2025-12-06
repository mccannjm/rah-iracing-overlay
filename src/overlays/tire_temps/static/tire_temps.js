// Tire Temperatures Overlay
const socket = io('/tire_temps');

let config = {
    temperature_unit: 'F',
    show_wear: true,
    show_pressure: true,
    temp_ranges: {
        cold: 150,
        optimal_min: 150,
        optimal_max: 200,
        hot: 200,
        critical: 230
    },
    reminder: {
        enabled: true,
        dismissible: true,
        permanently_dismissed: false
    },
    prediction: {
        enabled: true,
        display_mode: 'detailed',  // 'detailed', 'at-a-glance', 'visual'
        show_trends: true,
        show_advice: true,
        show_confidence: true
    }
};

let reminderDismissed = false;
let currentPredictions = null;
let currentActualData = null;

// Socket.IO connection events
socket.on('connect', () => {
    console.log('Connected to tire temps namespace');
});

socket.on('disconnect', () => {
    console.log('Disconnected from tire temps namespace');
    showNoDataState();
});

// Listen for tire data updates (actual temps from pit)
socket.on('tire_data_update', (data) => {
    if (!data) {
        showNoDataState();
        return;
    }

    currentActualData = data;
    updateTireDisplay(data, null);
    handleReminderVisibility(data);
});

// Listen for tire prediction updates
socket.on('tire_predictions_update', (data) => {
    if (!data || !config.prediction.enabled) {
        return;
    }

    currentPredictions = data;

    // If we don't have actual data, use predictions (but still pass actualData for pressure)
    if (!currentActualData || !currentActualData.data_available) {
        updateTireDisplay(currentActualData, data);
    } else {
        // We have actual data, but still update trends and advice
        updatePredictionInfo(data);
    }
});

function updateTireDisplay(actualData, predictionData) {
    const tireDisplay = document.getElementById('tire-display');
    const noDataState = document.getElementById('no-data-state');

    // Determine which data to use
    const useActual = actualData && actualData.data_available;
    const usePrediction = !useActual && predictionData;

    if (!useActual && !usePrediction) {
        showNoDataState();
        return;
    }

    // Hide no data state and show tire display
    noDataState.style.display = 'none';
    tireDisplay.style.display = 'block';

    const tires = ['LF', 'RF', 'LR', 'RR'];
    const zones = ['L', 'C', 'R'];

    // Update temperatures for each tire
    tires.forEach(tire => {
        zones.forEach(zone => {
            if (useActual) {
                const temp = actualData.temperatures?.[tire]?.[zone];
                updateZoneTemp(tire, zone, temp, false, null);
            } else if (usePrediction) {
                const temp = predictionData.temps?.[tire]?.[zone];
                updateZoneTemp(tire, zone, temp, true, null);
            }
        });

        // Update trend for tire (shown in label)
        if (usePrediction && config.prediction.show_trends) {
            const trend = predictionData.trends?.[tire];
            updateTireTrend(tire, trend);
        } else {
            updateTireTrend(tire, null);
        }

        // Update confidence border for predictions
        if (usePrediction && config.prediction.show_confidence) {
            const confidence = predictionData.confidence || 0;
            updateTireConfidence(tire, confidence);
        } else {
            // Reset confidence border
            updateTireConfidence(tire, null);
        }

        // Update pressure (always try to show if available)
        if (actualData && actualData.pressure && config.show_pressure) {
            const pressure = actualData.pressure[tire];
            updatePressure(tire, pressure);
        }

        // Update wear (only from actual data)
        if (useActual && actualData.wear && config.show_wear) {
            ['L', 'M', 'R'].forEach(wearZone => {
                const wear = actualData.wear[tire]?.[wearZone];
                updateWear(tire, wearZone, wear);
            });
        }
    });

    // Update status
    const statusElement = document.getElementById('data-status');
    if (useActual) {
        if (actualData.in_pit) {
            statusElement.textContent = 'In Pit - Live Data';
            statusElement.style.color = '#2ecc71';
        } else {
            statusElement.textContent = 'On Track - Limited Data';
            statusElement.style.color = '#f39c12';
        }
    } else if (usePrediction) {
        const confidence = Math.round((predictionData.confidence || 0) * 100);
        statusElement.textContent = `Predicted Temps (${confidence}% confidence)`;
        statusElement.style.color = getConfidenceColor(predictionData.confidence);
    }

    // Update prediction info (trends and advice)
    if (predictionData) {
        updatePredictionInfo(predictionData);
    }
}

function updateZoneTemp(tire, zone, temp, isPrediction) {
    const tempElement = document.getElementById(`temp-${tire}-${zone}`);

    if (!tempElement) return;

    if (temp === null || temp === undefined || temp <= 0) {
        tempElement.textContent = '---';
        tempElement.className = 'temp-value';
        return;
    }

    // Convert to configured unit if needed
    let displayTemp = temp;
    if (config.temperature_unit === 'C') {
        displayTemp = (temp - 32) * 5/9;
    }

    tempElement.textContent = Math.round(displayTemp) + '°';

    // Apply color coding based on temperature ranges
    const tempClass = getTempClass(temp);
    let className = `temp-value ${tempClass}`;

    // Add prediction class if showing predicted temps
    if (isPrediction) {
        className += ' temp-predicted';
    }

    tempElement.className = className;
}

function updateTireTrend(tire, trend) {
    const tireLabel = document.querySelector(`.tire-quadrant[data-tire="${tire}"] .tire-label`);
    if (!tireLabel) return;

    if (!trend || !trend.symbol) {
        // Reset to just tire name
        tireLabel.textContent = tire;
        return;
    }

    // Add trend symbol next to tire name
    tireLabel.textContent = `${tire} ${trend.symbol}`;
}

function getTempClass(temp) {
    if (temp < config.temp_ranges.cold) {
        return 'temp-cold';
    } else if (temp >= config.temp_ranges.cold && temp < config.temp_ranges.optimal_min) {
        return 'temp-warming';
    } else if (temp >= config.temp_ranges.optimal_min && temp <= config.temp_ranges.optimal_max) {
        return 'temp-optimal';
    } else if (temp > config.temp_ranges.optimal_max && temp < config.temp_ranges.critical) {
        return 'temp-hot';
    } else {
        return 'temp-critical';
    }
}

function updatePressure(tire, pressure) {
    const pressureElement = document.getElementById(`pressure-${tire}`);

    if (!pressureElement) return;

    if (pressure === null || pressure === undefined || pressure <= 0) {
        pressureElement.textContent = '--- psi';
        return;
    }

    pressureElement.textContent = pressure.toFixed(1) + ' psi';
}

function updateWear(tire, zone, wear) {
    const wearElement = document.getElementById(`wear-${tire}-${zone}`);

    if (!wearElement) return;

    if (wear === null || wear === undefined) {
        wearElement.style.width = '0%';
        return;
    }

    // Wear is 0-1, convert to percentage
    const wearPercent = (1 - wear) * 100;
    wearElement.style.width = wearPercent + '%';

    // Color based on wear level
    if (wearPercent > 70) {
        wearElement.style.backgroundColor = '#2ecc71'; // Green - good
    } else if (wearPercent > 40) {
        wearElement.style.backgroundColor = '#f39c12'; // Orange - moderate
    } else {
        wearElement.style.backgroundColor = '#e74c3c'; // Red - worn
    }
}

function showNoDataState() {
    const tireDisplay = document.getElementById('tire-display');
    const noDataState = document.getElementById('no-data-state');

    tireDisplay.style.display = 'none';
    noDataState.style.display = 'flex';
}

function updateTireConfidence(tire, confidence) {
    const tireQuadrant = document.querySelector(`.tire-quadrant[data-tire="${tire}"]`);
    if (!tireQuadrant) return;

    if (confidence === null || confidence === undefined) {
        // Reset to default border
        tireQuadrant.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        tireQuadrant.style.boxShadow = 'none';
        return;
    }

    // Set border color based on confidence
    const color = getConfidenceColor(confidence);
    tireQuadrant.style.borderColor = color;
    tireQuadrant.style.boxShadow = `0 0 15px ${color}40`;  // 40 = 25% opacity in hex
}

function getConfidenceColor(confidence) {
    if (confidence >= 0.8) {
        return '#2ecc71';  // Green
    } else if (confidence >= 0.5) {
        return '#f39c12';  // Yellow/Orange
    } else if (confidence >= 0.2) {
        return '#e67e22';  // Orange
    } else {
        return '#e74c3c';  // Red
    }
}

function updatePredictionInfo(predictionData) {
    if (!predictionData) return;

    // Update advice if enabled
    if (config.prediction.show_advice) {
        updateAdvice(predictionData.advice || []);
    }
}

function updateAdvice(adviceList) {
    const adviceContainer = document.getElementById('advice-container');
    if (!adviceContainer) return;

    if (!adviceList || adviceList.length === 0) {
        adviceContainer.style.display = 'none';
        return;
    }

    adviceContainer.style.display = 'block';
    adviceContainer.innerHTML = adviceList.map(advice =>
        `<div class="advice-item">${advice}</div>`
    ).join('');
}

function handleReminderVisibility(data) {
    const reminder = document.getElementById('tire-reminder');

    if (!config.reminder.enabled || config.reminder.permanently_dismissed || reminderDismissed) {
        reminder.style.display = 'none';
        return;
    }

    // Show reminder if data is not available (not in pit)
    if (!data.data_available && !data.in_pit) {
        reminder.style.display = 'flex';
    } else {
        reminder.style.display = 'none';
    }
}

// Event listeners for reminder buttons
document.getElementById('dismiss-reminder')?.addEventListener('click', () => {
    reminderDismissed = true;
    document.getElementById('tire-reminder').style.display = 'none';
});

document.getElementById('dont-show-reminder')?.addEventListener('click', () => {
    config.reminder.permanently_dismissed = true;
    document.getElementById('tire-reminder').style.display = 'none';

    // Save to backend
    fetch('/update_overlay_settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            folder_name: 'tire_temps',
            config: config
        })
    }).catch(err => console.error('Error saving reminder preference:', err));
});

// Initialize
console.log('Tire Temperatures overlay loaded');
