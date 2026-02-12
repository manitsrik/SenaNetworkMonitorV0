// Dashboard JavaScript - Redesigned Version
// Handles dashboard with Mini Topology, Response Time Chart, and Active Alerts

// Initialize Socket.IO connection
const socket = io();

// Chart instance
let responseChart = null;

// Vis.js network instance for mini topology
let miniNetwork = null;
let miniNodes = new vis.DataSet([]);
let miniEdges = new vis.DataSet([]);
let topologyLoaded = false; // Track if topology was initially loaded

// Chart data
const MAX_DATA_POINTS = 60;
let chartLabels = [];
let chartData = [];

// Activity log
let activityLog = [];
const MAX_ACTIVITY_ITEMS = 20;

// Device type metadata
const typeMetadata = {
    'switch': { icon: '🔀', name: 'Switches', color: '#10b981' },
    'firewall': { icon: '🛡️', name: 'Firewalls', color: '#ef4444' },
    'server': { icon: '🖥️', name: 'Servers', color: '#6366f1' },
    'router': { icon: '🌐', name: 'Routers', color: '#f59e0b' },
    'wireless': { icon: '📶', name: 'Wireless', color: '#ec4899' },
    'website': { icon: '🌐', name: 'Websites', color: '#8b5cf6' },
    'vmware': { icon: '🖴', name: 'VMware', color: '#22c55e' },
    'ippbx': { icon: '☎️', name: 'IP-PBX', color: '#3b82f6' },
    'vpnrouter': { icon: '🔒', name: 'VPN Router', color: '#a855f7' },
    'dns': { icon: '🔍', name: 'DNS', color: '#0ea5e9' },
    'other': { icon: '⚙️', name: 'Other', color: '#94a3b8' }
};

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    initMiniTopology();
    initResponseChart();
    loadInitialData();
    setupSocketListeners();
});

// ============================================
// Data Loading
// ============================================

async function loadInitialData() {
    try {
        // Load devices
        const devicesResponse = await fetch('/api/devices');
        const devices = await devicesResponse.json();

        // Load statistics
        const statsResponse = await fetch('/api/statistics');
        const stats = await statsResponse.json();

        // Load topology
        const topoResponse = await fetch('/api/topology');
        const topology = await topoResponse.json();

        // Update all components
        updateStatistics(stats);
        updateDeviceTypeStats(devices);
        updateMiniTopology(topology.devices, topology.connections);
        updateSlowDevices(devices);
        updateActiveAlerts(devices);
        updateSystemStatus(stats);

    } catch (error) {
        console.error('Error loading initial data:', error);
    }
}

// ============================================
// Statistics Cards
// ============================================

function updateStatistics(stats) {
    document.getElementById('total-devices').textContent = stats.total_devices || 0;
    document.getElementById('devices-up').textContent = stats.devices_up || 0;
    document.getElementById('devices-slow').textContent = stats.devices_slow || 0;
    document.getElementById('devices-down').textContent = stats.devices_down || 0;
    document.getElementById('uptime-percentage').textContent = (stats.uptime_percentage || 0) + '%';
    document.getElementById('avg-response-time').textContent = stats.average_response_time || 0;

    // Update chart with new data point
    addChartDataPoint(stats.average_response_time || 0);
}

function updateSystemStatus(stats) {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.getElementById('system-status-text');

    if (stats.devices_down > 0) {
        statusDot.className = 'status-dot status-dot-down';
        statusText.textContent = `${stats.devices_down} Device${stats.devices_down > 1 ? 's' : ''} Down`;
    } else if (stats.devices_slow > 0) {
        statusDot.className = 'status-dot status-dot-up';
        statusText.textContent = `${stats.devices_slow} Slow Response`;
    } else {
        statusDot.className = 'status-dot status-dot-up';
        statusText.textContent = 'All Systems Normal';
    }
}

// ============================================
// Device Type Statistics
// ============================================

function updateDeviceTypeStats(devices) {
    const container = document.getElementById('device-type-stats');

    // Group devices by type
    const devicesByType = {};
    devices.forEach(device => {
        const type = device.device_type || 'other';
        if (!devicesByType[type]) {
            devicesByType[type] = { total: 0, up: 0, down: 0, slow: 0 };
        }
        devicesByType[type].total++;
        if (device.status === 'up') {
            if (device.response_time && parseFloat(device.response_time) > 500) {
                devicesByType[type].slow++;
            } else {
                devicesByType[type].up++;
            }
        } else {
            devicesByType[type].down++;
        }
    });

    // Generate HTML
    let html = '';
    Object.keys(devicesByType).sort().forEach(type => {
        const meta = typeMetadata[type] || typeMetadata['other'];
        const stats = devicesByType[type];
        const upPercent = stats.total > 0 ? Math.round((stats.up / stats.total) * 100) : 0;

        let statusColor = '#10b981'; // green
        if (stats.down > 0) statusColor = '#ef4444'; // red
        else if (stats.slow > 0) statusColor = '#f59e0b'; // yellow

        html += `
            <div class="device-type-item" style="border-left-color: ${meta.color};">
                <div class="device-type-icon">${meta.icon}</div>
                <div class="device-type-info">
                    <div class="device-type-name">${meta.name}</div>
                    <div class="device-type-count">${stats.total} devices</div>
                </div>
                <div class="device-type-status" style="color: ${statusColor};">
                    ${stats.up}/${stats.total}
                </div>
            </div>
        `;
    });

    if (html === '') {
        html = '<p class="text-muted text-center" style="grid-column: span 2; padding: 2rem;">No devices configured</p>';
    }

    container.innerHTML = html;
}

// ============================================
// Mini Topology
// ============================================

function initMiniTopology() {
    const container = document.getElementById('mini-topology');

    const options = {
        nodes: {
            shape: 'dot',
            size: 8,
            font: {
                size: 9,
                color: getTextColor()
            },
            borderWidth: 1,
            shadow: false
        },
        edges: {
            width: 1.5,
            color: {
                color: 'rgba(148, 163, 184, 0.6)',
                highlight: '#6366f1'
            },
            smooth: {
                type: 'dynamic',
                roundness: 0.5
            }
        },
        physics: {
            enabled: true,
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
                gravitationalConstant: -25,
                centralGravity: 0.08,
                springLength: 30,
                springConstant: 0.1
            },
            stabilization: {
                enabled: true,
                iterations: 250,
                updateInterval: 25,
                fit: true
            }
        },
        layout: {
            randomSeed: 2,
            improvedLayout: true
        },
        interaction: {
            dragNodes: false,
            zoomView: false,
            dragView: false,
            hover: true
        }
    };

    miniNetwork = new vis.Network(container, { nodes: miniNodes, edges: miniEdges }, options);

    // Stop physics and fit all nodes in view after stabilization
    miniNetwork.on('stabilizationIterationsDone', function () {
        miniNetwork.setOptions({ physics: { enabled: false } });
        // Fit all nodes with maximum padding
        miniNetwork.fit({
            animation: false,
            maxZoomLevel: 0.6
        });
        // Scale down to ensure nodes don't touch edges
        const currentScale = miniNetwork.getScale();
        miniNetwork.moveTo({
            scale: currentScale * 0.50,
            animation: false
        });
    });

    // Click to go to topology page
    miniNetwork.on('click', function (params) {
        if (params.nodes.length > 0) {
            window.location.href = '/topology';
        }
    });
}

function getTextColor() {
    const theme = document.documentElement.getAttribute('data-theme');
    return theme === 'light' ? '#0f172a' : '#f1f5f9';
}

function updateMiniTopology(devices, connections) {
    // If topology already loaded, just update node colors
    if (topologyLoaded && miniNodes.length > 0) {
        updateTopologyNodeColors(devices);
        return;
    }

    // Clear existing
    miniNodes.clear();
    miniEdges.clear();

    // Add nodes
    devices.forEach(device => {
        const color = getNodeColor(device.status, device.response_time);
        const meta = typeMetadata[device.device_type] || typeMetadata['other'];

        miniNodes.add({
            id: device.id,
            label: device.name.length > 12 ? device.name.substring(0, 12) + '...' : device.name,
            color: {
                background: color,
                border: color,
                highlight: { background: color, border: '#ffffff' }
            },
            title: `${device.name}\n${device.ip_address}\nStatus: ${device.status}\n${device.response_time ? device.response_time + ' ms' : ''}`
        });
    });

    // Add edges
    connections.forEach(conn => {
        miniEdges.add({
            id: conn.id,
            from: conn.device_id,
            to: conn.connected_to
        });
    });

    topologyLoaded = true;
}

// Update only node colors without rebuilding the network
function updateTopologyNodeColors(devices) {
    devices.forEach(device => {
        const color = getNodeColor(device.status, device.response_time);
        try {
            miniNodes.update({
                id: device.id,
                color: {
                    background: color,
                    border: color,
                    highlight: { background: color, border: '#ffffff' }
                },
                title: `${device.name}\n${device.ip_address}\nStatus: ${device.status}\n${device.response_time ? device.response_time + ' ms' : ''}`
            });
        } catch (e) {
            // Node doesn't exist, will be added on next full refresh
        }
    });
}

function getNodeColor(status, responseTime) {
    if (status === 'down') return '#ef4444'; // Red
    if (status === 'up' && responseTime && parseFloat(responseTime) > 500) return '#f59e0b'; // Yellow/Orange for slow
    if (status === 'up') return '#10b981'; // Green
    if (status === 'slow') return '#f59e0b'; // Yellow/Orange
    return '#f59e0b'; // Default to yellow for unknown status
}

// ============================================
// Response Time Chart
// ============================================

function initResponseChart() {
    const ctx = document.getElementById('response-chart').getContext('2d');

    responseChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Avg Response Time',
                data: [],
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                tension: 0.4,
                fill: true,
                borderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#f1f5f9',
                    bodyColor: '#cbd5e1',
                    padding: 8,
                    displayColors: false,
                    callbacks: {
                        label: function (context) {
                            return context.parsed.y.toFixed(2) + ' ms';
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(148, 163, 184, 0.1)' },
                    ticks: {
                        color: '#94a3b8',
                        font: { size: 10 },
                        callback: value => value + ' ms'
                    }
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        color: '#94a3b8',
                        font: { size: 9 },
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 6
                    }
                }
            }
        }
    });
}

function addChartDataPoint(value) {
    const now = new Date();
    const timeLabel = now.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });

    chartLabels.push(timeLabel);
    chartData.push(value);

    if (chartLabels.length > MAX_DATA_POINTS) {
        chartLabels.shift();
        chartData.shift();
    }

    responseChart.data.labels = chartLabels;
    responseChart.data.datasets[0].data = chartData;
    responseChart.update('none');
}

// ============================================
// Slow Devices List
// ============================================

function updateSlowDevices(devices) {
    const container = document.getElementById('slow-devices-list');

    // Filter and sort by response time
    const slowDevices = devices
        .filter(d => d.status === 'up' && d.response_time && parseFloat(d.response_time) > 100)
        .sort((a, b) => parseFloat(b.response_time) - parseFloat(a.response_time))
        .slice(0, 5);

    if (slowDevices.length === 0) {
        container.innerHTML = '<p class="text-muted" style="font-size: 0.875rem;">No slow devices</p>';
        return;
    }

    container.innerHTML = slowDevices.map(device => `
        <div class="slow-device-item">
            <span class="slow-device-name">${device.name}</span>
            <span class="slow-device-time">${device.response_time} ms</span>
        </div>
    `).join('');
}

// ============================================
// Active Alerts
// ============================================

function updateActiveAlerts(devices) {
    const tbody = document.getElementById('alerts-tbody');
    const noAlertsMsg = document.getElementById('no-alerts-msg');
    const alertCountBadge = document.getElementById('alert-count-badge');
    const alertCount = document.getElementById('alert-count');

    // Get devices that are down or slow
    const alertDevices = devices.filter(d =>
        d.status === 'down' ||
        (d.status === 'up' && d.response_time && parseFloat(d.response_time) > 500)
    );

    alertCount.textContent = alertDevices.length;

    if (alertDevices.length === 0) {
        tbody.innerHTML = '';
        noAlertsMsg.style.display = 'block';
        alertCountBadge.className = 'status-badge status-up';
        return;
    }

    noAlertsMsg.style.display = 'none';
    alertCountBadge.className = 'status-badge status-down';

    tbody.innerHTML = alertDevices.map(device => {
        let severity, severityClass;
        if (device.status === 'down') {
            severity = 'Critical';
            severityClass = 'severity-critical';
        } else {
            severity = 'Warning';
            severityClass = 'severity-warning';
        }

        const timeAgo = device.last_check ? formatTimeAgo(device.last_check) : 'N/A';

        return `
            <tr>
                <td><span class="severity-badge ${severityClass}">⚠️ ${severity}</span></td>
                <td>${device.name}</td>
                <td>${timeAgo}</td>
                <td><span class="status-badge status-${device.status}">${device.status.toUpperCase()}</span></td>
            </tr>
        `;
    }).join('');
}

function formatTimeAgo(dateStr) {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;

    return date.toLocaleDateString('th-TH');
}

// ============================================
// Socket.IO Listeners
// ============================================

function setupSocketListeners() {
    socket.on('connect', () => {
        console.log('Connected to server');
        socket.emit('request_status');
    });

    socket.on('status_update', (device) => {
        console.log('Status update:', device);
        addActivityLog(device);

        // Reload data to update all components
        loadInitialData();
    });

    socket.on('statistics_update', (stats) => {
        console.log('Statistics update:', stats);
        updateStatistics(stats);
        updateSystemStatus(stats);
    });
}

// ============================================
// Activity Log
// ============================================

function addActivityLog(device) {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('th-TH');

    let statusIcon, statusText, statusClass;
    if (device.status === 'up') {
        statusIcon = '✅';
        statusText = 'UP';
        statusClass = 'activity-item-up';
    } else if (device.status === 'slow') {
        statusIcon = '⚠️';
        statusText = 'SLOW';
        statusClass = 'activity-item-slow';
    } else {
        statusIcon = '❌';
        statusText = 'DOWN';
        statusClass = 'activity-item-down';
    }

    activityLog.unshift({
        time: timeStr,
        device: device.name,
        status: device.status,
        icon: statusIcon,
        text: statusText,
        class: statusClass,
        responseTime: device.response_time
    });

    if (activityLog.length > MAX_ACTIVITY_ITEMS) {
        activityLog.pop();
    }

    updateActivityLogUI();
}

function updateActivityLogUI() {
    const logContainer = document.getElementById('activity-log');

    if (activityLog.length === 0) {
        logContainer.innerHTML = `
            <p class="text-center text-muted" style="padding: 1rem;">
                Waiting for activity...
            </p>
        `;
        return;
    }

    logContainer.innerHTML = activityLog.map(item => `
        <div class="activity-item ${item.class}">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <span style="font-size: 1.25rem;">${item.icon}</span>
                <div>
                    <strong style="color: var(--text-primary);">${item.device}</strong>
                    <span style="color: var(--text-muted); font-size: 0.875rem; margin-left: 0.5rem;">
                        ${item.text}
                    </span>
                </div>
            </div>
            <div style="text-align: right;">
                <div style="color: var(--text-muted); font-size: 0.875rem;">${item.time}</div>
                ${item.responseTime ? `<div style="color: var(--text-muted); font-size: 0.75rem;">${item.responseTime} ms</div>` : ''}
            </div>
        </div>
    `).join('');
}

// ============================================
// Theme Support
// ============================================

// Update topology colors when theme changes
const originalToggleTheme = window.toggleTheme;
if (typeof originalToggleTheme === 'function') {
    window.toggleTheme = function () {
        originalToggleTheme();
        setTimeout(() => {
            if (miniNetwork) {
                miniNodes.forEach(node => {
                    miniNodes.update({ id: node.id, font: { color: getTextColor() } });
                });
            }
        }, 100);
    };
}
