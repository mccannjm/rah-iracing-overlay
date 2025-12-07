/**
 * Shared Socket.IO utilities for overlay connections.
 *
 * Provides consistent connection configuration and reconnection handling
 * across all overlay JavaScript files.
 */

/**
 * Default Socket.IO connection options for overlays.
 */
const DEFAULT_SOCKET_OPTIONS = {
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 20000
};

/**
 * Creates a Socket.IO connection with standard options and event handlers.
 *
 * @param {string} namespace - The Socket.IO namespace (e.g., '/standings')
 * @param {Object} callbacks - Optional callback functions
 * @param {Function} callbacks.onConnect - Called when connection is established
 * @param {Function} callbacks.onDisconnect - Called when connection is lost
 * @param {Function} callbacks.onError - Called on connection error
 * @param {Function} callbacks.onReconnect - Called when reconnection succeeds
 * @returns {Object} - Object containing socket and connection state helpers
 */
function createOverlaySocket(namespace, callbacks = {}) {
    const socket = io(namespace, DEFAULT_SOCKET_OPTIONS);

    let isConnected = false;
    let reconnectTimer = null;

    socket.on('connect', function() {
        console.log(`Connected to ${namespace} namespace`);
        isConnected = true;
        clearTimeout(reconnectTimer);
        if (callbacks.onConnect) callbacks.onConnect();
    });

    socket.on('disconnect', function() {
        console.log(`Disconnected from ${namespace} namespace`);
        isConnected = false;
        if (callbacks.onDisconnect) callbacks.onDisconnect();

        // Manual reconnection fallback
        reconnectTimer = setTimeout(function() {
            if (!isConnected) {
                console.log('Manually attempting to reconnect...');
                socket.connect();
            }
        }, 3000);
    });

    socket.on('error', function(error) {
        console.error('Socket error:', error);
        if (callbacks.onError) callbacks.onError(error);
    });

    socket.on('reconnect_attempt', function() {
        console.log('Attempting to reconnect...');
    });

    socket.on('reconnect', function(attemptNumber) {
        console.log('Reconnected after', attemptNumber, 'attempts');
        if (callbacks.onReconnect) callbacks.onReconnect(attemptNumber);
    });

    return {
        socket: socket,
        isConnected: function() { return isConnected; },
        getSocket: function() { return socket; }
    };
}

/**
 * Format a time value in seconds to MM:SS.mmm format.
 *
 * @param {number} seconds - Time value in seconds
 * @returns {string} - Formatted time string
 */
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

/**
 * Format a number with thousands separator.
 *
 * @param {number} num - Number to format
 * @returns {string} - Formatted number string
 */
function formatNumber(num) {
    if (!num || isNaN(num)) return '-';
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Clamp a value between min and max bounds.
 *
 * @param {number} value - Value to clamp
 * @param {number} min - Minimum bound
 * @param {number} max - Maximum bound
 * @returns {number} - Clamped value
 */
function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

/**
 * Validate that data is a non-null object.
 *
 * @param {*} data - Data to validate
 * @returns {boolean} - True if data is valid
 */
function isValidData(data) {
    return data && typeof data === 'object';
}
