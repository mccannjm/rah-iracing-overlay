document.addEventListener("DOMContentLoaded", function() {
    // Configuration
    const CONFIG = {
        carsAhead: 5,
        carsBehind: 5,
        alwaysShowLeader: true,
        updateThrottle: 100, // ms between UI updates
    };

    // State
    let socket = null;
    let lastUpdate = 0;
    let currentData = null;
    let lapTimingData = null;
    let isConnected = false;
    let currentMode = 'standings'; // 'standings' or 'lap_timing'

    // DOM elements
    const standingsContent = document.getElementById('standingsContent');
    const sessionInfo = document.getElementById('sessionInfo');
    const connectionStatus = document.getElementById('connectionStatus');
    const statusIndicator = connectionStatus.querySelector('.status-indicator');
    const statusText = connectionStatus.querySelector('.status-text');

    // Initialize Socket.IO connection
    function initializeSocket() {
        socket = io('/standings', {
            reconnection: true,
            reconnectionAttempts: Infinity,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            timeout: 20000
        });

        socket.on('connect', function() {
            console.log('Connected to standings namespace');
            isConnected = true;
            updateConnectionStatus('connected', 'Connected');
        });

        socket.on('disconnect', function() {
            console.log('Disconnected from standings namespace');
            isConnected = false;
            updateConnectionStatus('disconnected', 'Disconnected');
        });

        socket.on('standings_update', function(data) {
            if (!data || typeof data !== 'object') {
                console.error('Invalid standings data received:', data);
                return;
            }

            currentData = data;

            // Determine mode based on session type
            const sessionType = data.session_type ? data.session_type.toLowerCase() : 'race';
            if (sessionType === 'race') {
                currentMode = 'standings';
            } else {
                currentMode = 'lap_timing'; // practice or qualifying
            }

            // Throttle UI updates
            const now = Date.now();
            if (now - lastUpdate >= CONFIG.updateThrottle) {
                if (currentMode === 'standings') {
                    updateStandings(data);
                }
                lastUpdate = now;
            }
        });

        socket.on('lap_timing_update', function(data) {
            if (!data || typeof data !== 'object') {
                console.error('Invalid lap timing data received:', data);
                return;
            }

            lapTimingData = data;

            // Throttle UI updates
            const now = Date.now();
            if (now - lastUpdate >= CONFIG.updateThrottle) {
                if (currentMode === 'lap_timing') {
                    updateLapTiming(data);
                }
                lastUpdate = now;
            }
        });

        socket.on('connect_error', function(error) {
            console.error('Connection error:', error);
            updateConnectionStatus('error', 'Connection Error');
        });
    }

    // Update connection status indicator
    function updateConnectionStatus(status, text) {
        statusIndicator.className = 'status-indicator status-' + status;
        statusText.textContent = text;
    }

    // Update standings display
    function updateStandings(data) {
        // Validate data structure
        if (!data.standings || !Array.isArray(data.standings)) {
            console.error('Invalid standings array:', data);
            return;
        }

        // Update session type
        if (data.session_type) {
            sessionInfo.textContent = data.session_type.toUpperCase();
        }

        // Filter standings for relative view
        const filteredStandings = filterRelativeStandings(data.standings, data.player_idx);

        // Render standings
        renderStandings(filteredStandings, data.player_idx, data.is_multiclass);
    }

    // Filter standings to show relative view
    function filterRelativeStandings(standings, playerIdx) {
        if (!standings || standings.length === 0) {
            return [];
        }

        // Find player position in standings
        const playerIndex = standings.findIndex(driver => driver.car_idx === playerIdx);

        if (playerIndex === -1) {
            // Player not found, show full standings
            return standings;
        }

        const filtered = [];

        // Always include leader if configured
        if (CONFIG.alwaysShowLeader && playerIndex !== 0) {
            filtered.push(standings[0]);
        }

        // Calculate range
        let startIdx = Math.max(playerIndex - CONFIG.carsAhead, 1); // Skip leader if already added
        let endIdx = Math.min(playerIndex + CONFIG.carsBehind + 1, standings.length);

        // Adjust if player is near top
        if (playerIndex <= CONFIG.carsAhead) {
            startIdx = CONFIG.alwaysShowLeader ? 1 : 0;
            endIdx = Math.min(playerIndex + CONFIG.carsBehind + (CONFIG.carsAhead - playerIndex) + 1, standings.length);
        }

        // Adjust if player is near bottom
        if (playerIndex >= standings.length - CONFIG.carsBehind) {
            const deficit = CONFIG.carsBehind - (standings.length - playerIndex - 1);
            startIdx = Math.max(playerIndex - CONFIG.carsAhead - deficit, CONFIG.alwaysShowLeader ? 1 : 0);
        }

        // Add drivers in range
        for (let i = startIdx; i < endIdx; i++) {
            filtered.push(standings[i]);
        }

        // Remove duplicates (in case leader was added twice)
        const seen = new Set();
        return filtered.filter(driver => {
            if (seen.has(driver.car_idx)) {
                return false;
            }
            seen.add(driver.car_idx);
            return true;
        });
    }

    // Render standings rows
    function renderStandings(standings, playerIdx, isMulticlass) {
        // Clear existing content
        standingsContent.innerHTML = '';

        if (!standings || standings.length === 0) {
            standingsContent.innerHTML = '<div class="no-data">No standings data available</div>';
            return;
        }

        standings.forEach(driver => {
            const row = createStandingRow(driver, driver.car_idx === playerIdx, isMulticlass);
            standingsContent.appendChild(row);
        });
    }

    // Create a standing row element
    function createStandingRow(driver, isPlayer, isMulticlass) {
        const row = document.createElement('div');
        row.className = 'standing-row';

        // Add player highlight
        if (isPlayer) {
            row.classList.add('player-row');
        }

        // Add pit status
        if (driver.in_pit) {
            row.classList.add('in-pit');
        }

        // Position
        const posCell = document.createElement('div');
        posCell.className = 'col-pos';
        posCell.textContent = driver.position || '-';
        row.appendChild(posCell);

        // Driver name
        const nameCell = document.createElement('div');
        nameCell.className = 'col-name';
        nameCell.textContent = driver.driver_name || 'Unknown';
        nameCell.title = driver.driver_name || 'Unknown';
        row.appendChild(nameCell);

        // Car class
        const classCell = document.createElement('div');
        classCell.className = 'col-class';
        classCell.textContent = driver.car_class || '-';
        if (isMulticlass && driver.car_class_color) {
            classCell.style.color = '#' + driver.car_class_color.toString(16).padStart(6, '0');
        }
        row.appendChild(classCell);

        // License
        const licenseCell = document.createElement('div');
        licenseCell.className = 'col-license';
        licenseCell.textContent = formatLicense(driver.license);
        row.appendChild(licenseCell);

        // iRating
        const iratingCell = document.createElement('div');
        iratingCell.className = 'col-irating';
        iratingCell.textContent = driver.irating > 0 ? formatNumber(driver.irating) : '-';
        row.appendChild(iratingCell);

        // Last lap time
        const lastLapCell = document.createElement('div');
        lastLapCell.className = 'col-lastlap';
        lastLapCell.textContent = driver.last_lap_time > 0 ? formatTime(driver.last_lap_time) : '-';
        row.appendChild(lastLapCell);

        // Interval
        const intervalCell = document.createElement('div');
        intervalCell.className = 'col-interval';
        intervalCell.textContent = driver.interval || '-';
        row.appendChild(intervalCell);

        // Position delta
        const deltaCell = document.createElement('div');
        deltaCell.className = 'col-delta';
        const delta = driver.position_delta || 0;
        if (delta > 0) {
            deltaCell.textContent = '+' + delta;
            deltaCell.classList.add('delta-positive');
        } else if (delta < 0) {
            deltaCell.textContent = delta;
            deltaCell.classList.add('delta-negative');
        } else {
            deltaCell.textContent = '—';
            deltaCell.classList.add('delta-neutral');
        }
        row.appendChild(deltaCell);

        return row;
    }

    // Format license string (shorten if needed)
    function formatLicense(license) {
        if (!license) return '-';

        // Extract class and safety rating (e.g., "A 4.50" -> "A4.5")
        const match = license.match(/([A-R])\s*([\d.]+)/);
        if (match) {
            const licClass = match[1];
            const sr = parseFloat(match[2]);
            return licClass + sr.toFixed(1);
        }

        return license;
    }

    // Format time in seconds to MM:SS.mmm
    function formatTime(seconds) {
        if (!seconds || seconds <= 0) return '-';

        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;

        if (minutes > 0) {
            return minutes + ':' + secs.toFixed(3).padStart(6, '0');
        } else {
            return secs.toFixed(3) + 's';
        }
    }

    // Format number with thousands separator
    function formatNumber(num) {
        if (!num || isNaN(num)) return '-';
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    // Format session time remaining
    function formatSessionTime(seconds) {
        if (!seconds || seconds <= 0) return '-';

        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        } else {
            return `${minutes}:${secs.toString().padStart(2, '0')}`;
        }
    }

    // Update lap timing display for practice/qualifying sessions
    function updateLapTiming(data) {
        // Update session type
        if (data.session_type) {
            sessionInfo.textContent = data.session_type.toUpperCase();
        }

        // Clear standings content and show lap timing
        standingsContent.innerHTML = '';

        // Create lap timing container
        const timingContainer = document.createElement('div');
        timingContainer.className = 'lap-timing-container';

        // Session info section
        const sessionSection = document.createElement('div');
        sessionSection.className = 'timing-section';
        sessionSection.innerHTML = `
            <div class="timing-header">SESSION INFO</div>
            <div class="timing-row">
                <span class="timing-label">Time Remaining:</span>
                <span class="timing-value">${formatSessionTime(data.session_time_remain)}</span>
            </div>
            <div class="timing-row">
                <span class="timing-label">Current Lap:</span>
                <span class="timing-value">${data.current_lap || 0}</span>
            </div>
        `;
        timingContainer.appendChild(sessionSection);

        // Lap times section
        const lapTimesSection = document.createElement('div');
        lapTimesSection.className = 'timing-section';

        let bestTimeHtml = '';
        if (data.best_lap_time > 0) {
            bestTimeHtml = `
                <div class="timing-row timing-highlight">
                    <span class="timing-label">Best Lap:</span>
                    <span class="timing-value timing-best">${formatTime(data.best_lap_time)}</span>
                </div>
            `;
        } else {
            bestTimeHtml = `
                <div class="timing-row timing-highlight">
                    <span class="timing-label">Best Lap:</span>
                    <span class="timing-value">-</span>
                </div>
            `;
        }

        let lastTimeHtml = '';
        if (data.last_lap_time > 0) {
            const deltaClass = data.delta_to_best > 0 ? 'delta-negative' : data.delta_to_best < 0 ? 'delta-positive' : 'delta-neutral';
            const deltaText = data.delta_to_best > 0 ? `+${data.delta_to_best.toFixed(3)}` : data.delta_to_best.toFixed(3);
            lastTimeHtml = `
                <div class="timing-row">
                    <span class="timing-label">Last Lap:</span>
                    <span class="timing-value">${formatTime(data.last_lap_time)} <span class="${deltaClass}">(${deltaText})</span></span>
                </div>
            `;
        } else {
            lastTimeHtml = `
                <div class="timing-row">
                    <span class="timing-label">Last Lap:</span>
                    <span class="timing-value">-</span>
                </div>
            `;
        }

        let currentTimeHtml = '';
        if (data.current_lap_time > 0) {
            currentTimeHtml = `
                <div class="timing-row">
                    <span class="timing-label">Current Lap:</span>
                    <span class="timing-value timing-current">${formatTime(data.current_lap_time)}</span>
                </div>
            `;
        } else {
            currentTimeHtml = `
                <div class="timing-row">
                    <span class="timing-label">Current Lap:</span>
                    <span class="timing-value">-</span>
                </div>
            `;
        }

        lapTimesSection.innerHTML = `
            <div class="timing-header">LAP TIMES</div>
            ${bestTimeHtml}
            ${lastTimeHtml}
            ${currentTimeHtml}
        `;
        timingContainer.appendChild(lapTimesSection);

        standingsContent.appendChild(timingContainer);
    }

    // Initialize the overlay
    initializeSocket();

    // Show initial loading state
    updateConnectionStatus('connecting', 'Connecting...');
});
