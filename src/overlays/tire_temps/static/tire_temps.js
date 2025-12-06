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
    }
};

let reminderDismissed = false;

// Socket.IO connection events
socket.on('connect', () => {
    console.log('Connected to tire temps namespace');
});

socket.on('disconnect', () => {
    console.log('Disconnected from tire temps namespace');
    showNoDataState();
});

// Listen for tire data updates
socket.on('tire_data_update', (data) => {
    if (!data) {
        showNoDataState();
        return;
    }

    updateTireDisplay(data);
    handleReminderVisibility(data);
});

function updateTireDisplay(data) {
    const tireDisplay = document.getElementById('tire-display');
    const noDataState = document.getElementById('no-data-state');

    if (!data || !data.data_available) {
        showNoDataState();
        return;
    }

    // Hide no data state and show tire display
    noDataState.style.display = 'none';
    tireDisplay.style.display = 'block';

    // Update temperatures for each tire
    const tires = ['LF', 'RF', 'LR', 'RR'];
    const zones = ['L', 'C', 'R'];

    tires.forEach(tire => {
        zones.forEach(zone => {
            const temp = data.temperatures?.[tire]?.[zone];
            updateZoneTemp(tire, zone, temp);
        });

        // Update pressure
        if (data.pressure && config.show_pressure) {
            const pressure = data.pressure[tire];
            updatePressure(tire, pressure);
        }

        // Update wear
        if (data.wear && config.show_wear) {
            const wearZones = zone === 'C' ? 'M' : zone;
            ['L', 'M', 'R'].forEach(wearZone => {
                const wear = data.wear[tire]?.[wearZone];
                updateWear(tire, wearZone, wear);
            });
        }
    });

    // Update status
    const statusElement = document.getElementById('data-status');
    if (data.in_pit) {
        statusElement.textContent = 'In Pit - Live Data';
        statusElement.style.color = '#2ecc71';
    } else {
        statusElement.textContent = 'On Track - Limited Data';
        statusElement.style.color = '#f39c12';
    }
}

function updateZoneTemp(tire, zone, temp) {
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
    tempElement.className = `temp-value ${tempClass}`;
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
