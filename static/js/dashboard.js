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

// Gauge Chart Configuration
const GAUGE_MAX = 500; // Max value for gauge (ms)

// Activity log
let activityLog = [];
const MAX_ACTIVITY_ITEMS = 20;

// Device type metadata
const typeMetadata = {
    'switch': { icon: '🔄', name: 'Switches', color: '#10b981' },
    'firewall': { icon: '🛡️', name: 'Firewalls', color: '#ef4444' },
    'server': { icon: '🖥️', name: 'Servers', color: '#6366f1' },
    'router': { icon: '🌐', name: 'Routers', color: '#f59e0b' },
    'wireless': { icon: '📶', name: 'Wireless', color: '#ec4899' },
    'website': { icon: '🌍', name: 'Websites', color: '#8b5cf6' },
    'vmware': { icon: '🖥️', name: 'VMware', color: '#22c55e' },
    'ippbx': { icon: '☎️', name: 'IP-PBX', color: '#3b82f6' },
    'vpnrouter': { icon: '🔒', name: 'VPN Router', color: '#a855f7' },
    'dns': { icon: '🔍', name: 'DNS', color: '#0ea5e9' },
    'other': { icon: '⚙️', name: 'Other', color: '#94a3b8' }
};

// Gauge Chart Configuration

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    initMiniTopology();
    initResponseChart();
    initDeviceTypeResponseChart();
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
        updateDeviceTypeResponseChart(devices);
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
    const avgResponse = stats.average_response_time || 0;
    document.getElementById('avg-response-time').textContent = avgResponse;
    // Also update the hero value in the new Response Time card
    const heroResponse = document.getElementById('avg-response-time-hero');
    if (heroResponse) heroResponse.textContent = avgResponse;

    // Update Gauge
    if (responseChart) {
        responseChart.data.datasets[0].needleValue = avgResponse;
        responseChart.update();
    }
}

function updateSlowDevicesList(devices) {
    const listContainer = document.getElementById('slow-devices-list');
    if (!listContainer) return;

    const slowDevices = devices.filter(d =>
        (d.status === 'up' && d.response_time && parseFloat(d.response_time) > 200)
    ).sort((a, b) => (parseFloat(b.response_time) || 0) - (parseFloat(a.response_time) || 0))
        .slice(0, 5);

    if (slowDevices.length === 0) {
        listContainer.innerHTML = '<p class="text-muted" style="font-size: 0.8rem; text-align: center;">No slow devices detected</p>';
        return;
    }

    listContainer.innerHTML = slowDevices.map(d => `
        <div class="slow-device-item" style="margin-bottom: 0.5rem; padding: 0.5rem; background: var(--bg-primary); border-radius: var(--radius-md); border-left: 3px solid var(--warning);">
            <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                <span style="font-size: 0.85rem; font-weight: 500;">${d.name}</span>
                <span style="font-size: 0.85rem; color: var(--warning); font-weight: 600;">${d.response_time}ms</span>
            </div>
        </div>
    `).join('');
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
            devicesByType[type] = {
                total: 0,
                up: 0,
                down: 0,
                slow: 0,
                totalResponseTime: 0,
                responseTimeCount: 0
            };
        }
        devicesByType[type].total++;
        if (device.status === 'up') {
            if (device.response_time && parseFloat(device.response_time) > 0) {
                devicesByType[type].totalResponseTime += parseFloat(device.response_time);
                devicesByType[type].responseTimeCount++;
            }

            if (device.response_time && parseFloat(device.response_time) > 500) {
                devicesByType[type].slow++;
            } else {
                devicesByType[type].up++;
            }
        } else if (device.status === 'slow') {
            // Handle explicit slow status if it exists in data
            if (device.response_time && parseFloat(device.response_time) > 0) {
                devicesByType[type].totalResponseTime += parseFloat(device.response_time);
                devicesByType[type].responseTimeCount++;
            }
            devicesByType[type].slow++;
        } else {
            devicesByType[type].down++;
        }
    });

    // Generate HTML
    let html = '<div class="device-type-grid">';

    Object.keys(devicesByType).sort().forEach(type => {
        const meta = typeMetadata[type] || typeMetadata['other'];
        const stats = devicesByType[type];

        // Calculate average response time
        const avgResponseTime = stats.responseTimeCount > 0
            ? Math.round(stats.totalResponseTime / stats.responseTimeCount)
            : 0;

        // Calculate percentages for progress bar
        const total = stats.total;
        const upPercent = total > 0 ? (stats.up / total) * 100 : 0;
        const slowPercent = total > 0 ? (stats.slow / total) * 100 : 0;
        const downPercent = total > 0 ? (stats.down / total) * 100 : 0;

        let statusClass = 'status-normal';
        let statusIcon = 'check-circle';
        let statusColor = 'var(--success)';

        if (stats.down > 0) {
            statusClass = 'status-critical';
            statusIcon = 'alert-circle';
            statusColor = 'var(--danger)';
        } else if (stats.slow > 0) {
            statusClass = 'status-warning';
            statusIcon = 'alert-triangle';
            statusColor = 'var(--warning)';
        }

        html += `
            <div class="device-type-card ${statusClass}">
                <div class="device-card-header">
                    <div class="device-icon-wrapper" style="background-color: ${meta.color}20; color: ${meta.color};">
                        ${meta.icon}
                    </div>
                    <div class="device-info">
                        <div class="device-name">${meta.name}</div>
                        <div class="device-count">${stats.total} Devices</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">
                            Avg: <span style="font-weight: 600; color: var(--text-primary);">${avgResponseTime} ms</span>
                        </div>
                    </div>
                    <div class="device-status-badge" style="color: ${statusColor};">
                        ${stats.up}/${stats.total}
                    </div>
                </div>
                
                <div class="device-progress-bar">
                    <div class="progress-segment success" style="width: ${upPercent}%"></div>
                    <div class="progress-segment warning" style="width: ${slowPercent}%"></div>
                    <div class="progress-segment danger" style="width: ${downPercent}%"></div>
                </div>
            </div>
        `;
    });

    html += '</div>';

    if (Object.keys(devicesByType).length === 0) {
        html = '<p class="text-muted text-center" style="padding: 2rem;">No devices configured</p>';
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
            size: 30, // 5x scaling starting point
            font: {
                size: 12,
                color: getTextColor(),
                face: 'Inter, system-ui, sans-serif'
            },
            borderWidth: 2.5,
            shadow: false,
            scaling: { label: { enabled: false } }
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
            solver: 'repulsion',
            repulsion: {
                centralGravity: 0.3,
                springLength: 100,
                springConstant: 0.05,
                nodeDistance: 150,
                damping: 0.09
            },
            stabilization: {
                enabled: true,
                iterations: 1500,
                updateInterval: 100,
                fit: true
            }
        },
        layout: {
            randomSeed: 2,
            improvedLayout: true
        },
        interaction: {
            dragNodes: true, // Allow repositioning
            zoomView: true, // Allow zooming like the full map
            dragView: true, // Allow panning
            hover: true
        }
    };

    miniNetwork = new vis.Network(container, { nodes: miniNodes, edges: miniEdges }, options);

    // Fit all nodes and FREEZE physics after stabilization to stop shaking
    miniNetwork.on('stabilizationIterationsDone', function () {
        miniNetwork.setOptions({ physics: { enabled: false } }); // Stop all movement
        // Ensure perfect fit with safety margin
        miniNetwork.fit();
    });

    // Also fit when zoom is changed to prevent getting lost
    miniNetwork.on('zoom', function () {
        if (miniNetwork.getScale() < 0.05) {
            miniNetwork.fit();
        }
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
    if (!devices || devices.length === 0) return;

    // Force rebuild if nodes are missing despite topologyLoaded being true
    if (topologyLoaded && miniNodes.length === devices.length) {
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
        const iconSvg = getSvgIcon(meta.icon, color);

        const isCore = device.device_type === 'core_switch' || device.device_type === 'l3_switch';
        miniNodes.add({
            id: device.id,
            label: device.name.length > 20 ? device.name.substring(0, 20) + '...' : device.name,
            shape: 'image',
            image: iconSvg,
            size: 40, // Reasonable size for standard layout
            color: {
                background: color,
                border: color,
                highlight: { background: color, border: '#ffffff' }
            },
            title: `${device.name}\n${device.ip_address}\nStatus: ${device.status}`
        });
    });

    // Create Map for unique edges (key: minId-maxId)
    const uniqueEdges = new Map();

    connections.forEach(conn => {
        const ids = [conn.device_id, conn.connected_to].sort((a, b) => a - b);
        const key = `${ids[0]}-${ids[1]}`;

        if (!uniqueEdges.has(key)) {
            uniqueEdges.set(key, conn);
        } else {
            const existing = uniqueEdges.get(key);
            if (conn.view_type === 'standard' && existing.view_type !== 'standard') {
                uniqueEdges.set(key, conn);
            }
        }
    });

    // Add edges from unique map
    uniqueEdges.forEach(conn => {
        miniEdges.add({
            id: conn.id,
            from: conn.device_id,
            to: conn.connected_to
        });
    });

    topologyLoaded = true;

    // Definitively fit after rebuild
    setTimeout(() => {
        if (miniNetwork) {
            miniNetwork.fit();
            setTimeout(() => miniNetwork.fit(), 200);
        }
    }, 300);
}

// Update only node colors without rebuilding the network
function updateTopologyNodeColors(devices) {
    devices.forEach(device => {
        const color = getNodeColor(device.status, device.response_time);
        const meta = typeMetadata[device.device_type] || typeMetadata['other'];
        const iconSvg = getSvgIcon(meta.icon, color);

        try {
            const isCore = device.device_type === 'core_switch' || device.device_type === 'l3_switch';
            miniNodes.update({
                id: device.id,
                image: iconSvg,
                size: isCore ? 70 : 40, // Consistent 5x scaling
                color: {
                    background: color,
                    border: color,
                    highlight: { background: color, border: '#ffffff' }
                },
                title: `${device.name}\n${device.ip_address}\nStatus: ${device.status}`
            });
        } catch (e) {
            // Node doesn't exist, will be added on next full refresh
        }
    });
}

function getSvgIcon(emoji, color) {
    const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
        <circle cx="16" cy="16" r="14" fill="${color}" stroke="#ffffff" stroke-width="2.5" />
        <text x="50%" y="56%" dominant-baseline="middle" text-anchor="middle" font-size="16" font-family="Segoe UI Emoji, Apple Color Emoji, sans-serif">${emoji}</text>
    </svg>`;
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}

function getNodeColor(status, responseTime) {
    if (status === 'down') return '#ef4444'; // Red
    if (status === 'up' && responseTime && parseFloat(responseTime) > 500) return '#f59e0b'; // Yellow/Orange for slow
    if (status === 'up') return '#10b981'; // Green
    if (status === 'slow') return '#f59e0b'; // Yellow/Orange
    return '#f59e0b'; // Default to yellow for unknown status
}

// ============================================
// Response Time Gauge Chart
// ============================================

function initResponseChart() {
    const ctx = document.getElementById('response-chart');
    if (!ctx) return;

    responseChart = new Chart(ctx.getContext('2d'), {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [40, 40, 20], // 0-200 (40%), 200-400 (40%), 400-500 (20%)
                backgroundColor: ['#10b981', '#f59e0b', '#ef4444'], // Green, Orange, Red
                borderWidth: 0,
                circumference: 180,
                rotation: 270,
                cutout: '80%',
                needleValue: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: {
                    bottom: 0,
                    top: 50,
                    left: 20,
                    right: 20
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false }
            }
        },
        plugins: [{
            id: 'cleanGaugeWithScales',
            afterDraw: (chart) => {
                const { ctx } = chart;
                ctx.save();
                const dataset = chart.config.data.datasets[0];
                const needleValue = dataset.needleValue || 0;
                const meta = chart.getDatasetMeta(0);
                const segments = meta.data;

                if (!segments || segments.length < 3) {
                    ctx.restore();
                    return;
                }

                // --- Sync to Metadata for Perfect Alignment ---
                const cx = segments[0].x;
                const cy = segments[0].y;
                const outerRadius = segments[0].outerRadius;
                const startAngle = segments[0].startAngle;
                const endAngle = segments[2].endAngle;
                const totalSweep = endAngle - startAngle;

                // --- Drawing Scale & Ticks ---
                const tickLabelRadius = outerRadius + 22;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.font = '600 0.8rem "Inter", sans-serif';
                ctx.fillStyle = '#94a3b8';

                const labels = [
                    { text: '0', val: 0 },
                    { text: '100', val: 100 },
                    { text: '200', val: 200 },
                    { text: '300', val: 300 },
                    { text: '400', val: 400 },
                    { text: '500+', val: 500 }
                ];

                labels.forEach(p => {
                    const angle = startAngle + (p.val / 500 * totalSweep);

                    // Major Tick
                    ctx.beginPath();
                    ctx.moveTo(cx + Math.cos(angle) * (outerRadius + 2), cy + Math.sin(angle) * (outerRadius + 2));
                    ctx.lineTo(cx + Math.cos(angle) * (outerRadius + 8), cy + Math.sin(angle) * (outerRadius + 8));
                    ctx.strokeStyle = '#cbd5e1';
                    ctx.lineWidth = 1.5;
                    ctx.stroke();

                    // Label
                    ctx.fillText(p.text, cx + Math.cos(angle) * tickLabelRadius, cy + Math.sin(angle) * tickLabelRadius);
                });

                // Minor Ticks
                for (let i = 0; i <= 25; i++) {
                    if (i % 5 === 0) continue;
                    const angle = startAngle + (i / 25 * totalSweep);
                    ctx.beginPath();
                    ctx.moveTo(cx + Math.cos(angle) * (outerRadius + 2), cy + Math.sin(angle) * (outerRadius + 2));
                    ctx.lineTo(cx + Math.cos(angle) * (outerRadius + 5), cy + Math.sin(angle) * (outerRadius + 5));
                    ctx.strokeStyle = '#e2e8f0';
                    ctx.lineWidth = 1;
                    ctx.stroke();
                }

                // --- Center Value Drawing ---
                ctx.restore();
                ctx.save();
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.font = 'bold 2rem "Inter", sans-serif';

                if (needleValue > 400) ctx.fillStyle = '#ef4444';
                else if (needleValue > 200) ctx.fillStyle = '#f59e0b';
                else ctx.fillStyle = '#10b981';

                ctx.fillText(needleValue.toFixed(2), cx, cy - 10);
                ctx.restore();

                // --- Needle Drawing ---
                ctx.save();
                const needleAngle = startAngle + (Math.min(needleValue / 500, 1) * totalSweep);

                ctx.translate(cx, cy);
                ctx.rotate(needleAngle);

                ctx.beginPath();
                ctx.lineWidth = 4;
                ctx.lineCap = 'round';
                ctx.strokeStyle = '#334155';
                ctx.moveTo(0, 0);
                ctx.lineTo(outerRadius * 0.85, 0);
                ctx.stroke();

                ctx.beginPath();
                ctx.arc(0, 0, 8, 0, Math.PI * 2);
                ctx.fillStyle = '#334155';
                ctx.fill();

                ctx.beginPath();
                ctx.arc(0, 0, 3, 0, Math.PI * 2);
                ctx.fillStyle = '#94a3b8';
                ctx.fill();

                ctx.restore();
            }
        }]
    });
}

function updateSlowDevices(devices) {
    const container = document.getElementById('slow-devices-list');

    // Filter and sort by response time
    const slowDevices = devices
        .filter(d => d.status === 'up' && d.response_time && parseFloat(d.response_time) > 100)
        .sort((a, b) => parseFloat(b.response_time) - parseFloat(a.response_time))
        .slice(0, 5);

    if (slowDevices.length === 0) {
        container.innerHTML = `
            <div style="display: flex; flex-direction: column; align-items: center; padding: 2rem; color: var(--text-muted);">
                <span style="font-size: 2rem; margin-bottom: 0.5rem;">⚡</span>
                <p>No slow devices detected</p>
                <small>All systems responding efficiently</small>
            </div>
        `;
        return;
    }

    const maxTime = Math.max(...slowDevices.map(d => parseFloat(d.response_time)));

    const html = slowDevices.map(device => {
        const time = parseFloat(device.response_time);
        const percent = (time / maxTime) * 100;

        return `
        <div class="slow-device-item">
            <div class="slow-device-info">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span class="slow-device-name" title="${device.name}">${device.name}</span>
                    <span class="slow-device-time-badge">${device.response_time} ms</span>
                </div>
                <div class="slow-device-bar-bg">
                    <div class="slow-device-bar-fill" style="width: ${percent}%"></div>
                </div>
            </div>
        </div>
    `}).join('');

    container.innerHTML = `<div class="slow-devices-container">${html}</div>`;
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

    const alertsContainer = document.getElementById('alerts-list-modern');
    if (!alertsContainer) return;

    alertCount.textContent = alertDevices.length;

    if (alertDevices.length === 0) {
        tbody.innerHTML = '';
        noAlertsMsg.style.display = 'block';
        alertCountBadge.className = 'status-badge status-up';
        alertsContainer.innerHTML = '';
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

    alertsContainer.innerHTML = alertDevices.map(alert => `
        <div class="activity-item" style="border-left: 3px solid var(--${alert.status === 'down' ? 'danger' : 'warning'})">
            <div class="activity-icon status-${alert.status}">
                ${alert.status === 'down' ? '❌' : '⚠️'}
            </div>
            <div class="activity-details">
                <div class="activity-text"><strong>${alert.name}</strong> is ${alert.status}</div>
                <div class="activity-time">${formatTimeAgo(alert.last_check)}</div>
            </div>
        </div>
    `).join('');
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

    let debounceTimer;
    socket.on('status_update', (device) => {
        console.log('Status update:', device);
        addActivityLog(device);

        // Debounce reload to update all components once per batch
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            loadInitialData();
        }, 1000);
    });

    socket.on('statistics_update', (stats) => {
        console.log('Statistics update:', stats);
        // The original instruction had updateResponseTime(stats); updateSlowDevicesList(devices); updateStatisticsDisplay(stats);
        // but updateResponseTime and updateStatisticsDisplay are not defined.
        // Assuming the intent was to add updateSlowDevicesList and keep existing updates.
        // To get 'devices' for updateSlowDevicesList, we need to fetch them or pass them from a broader scope.
        // For now, calling loadInitialData() will ensure all components, including slow devices, are updated.
        // If 'devices' were available directly, we could call updateSlowDevicesList(devices) here.
        // For simplicity and to avoid undefined functions, we'll rely on loadInitialData for now.
        loadInitialData();
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
        <div class="activity-item ${item.class}" style="display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 1rem; margin-bottom: 0.75rem; background: var(--bg-secondary); border-radius: var(--radius-md); border-left: 4px solid var(--${item.status === 'up' ? 'success' : (item.status === 'slow' ? 'warning' : 'danger')});">
            <div style="display: flex; align-items: center; gap: 1rem;">
                <div style="font-size: 1.25rem; width: 24px; text-align: center;">${item.icon}</div>
                <div>
                    <div style="font-weight: 600; color: var(--text-primary); font-size: 0.9rem;">${item.device}</div>
                    <div style="display: flex; align-items: center; gap: 0.5rem; margin-top: 2px;">
                        <span style="font-size: 0.75rem; font-weight: 700; color: var(--${item.status === 'up' ? 'success' : (item.status === 'slow' ? 'warning' : 'danger')}); opacity: 0.8;">${item.text}</span>
                        ${item.responseTime ? `<span style="color: var(--text-muted); font-size: 0.75rem;">• ${item.responseTime} ms</span>` : ''}
                    </div>
                </div>
            </div>
            <div style="text-align: right;">
                <div style="color: var(--text-muted); font-size: 0.75rem; font-weight: 500;">${item.time}</div>
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


// ============================================
// Device Type Response Time Chart
// ============================================

// ============================================
// Device Type Response Time Trend Chart
// ============================================

// ============================================
// Device Type Response Time Trend Chart
// ============================================

let deviceTypeChart = null;
let currentTrendRange = 15; // Default to 15 minutes

function updateTrendRange(minutes, btn) {
    currentTrendRange = minutes;

    // Update active button state
    if (btn) {
        const group = btn.parentElement;
        Array.from(group.children).forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
    }

    updateDeviceTypeResponseChart();
}

// Expose to global scope for HTML onclick
window.updateTrendRange = updateTrendRange;

function initDeviceTypeResponseChart() {
    const ctx = document.getElementById('device-type-response-chart');
    if (!ctx) return;

    deviceTypeChart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: {
            labels: [], // Time labels
            datasets: [] // Will be populated dynamically
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    align: 'end',
                    labels: {
                        usePointStyle: true,
                        boxWidth: 8,
                        color: '#94a3b8',
                        font: {
                            size: 11
                        }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#f8fafc',
                    bodyColor: '#f8fafc',
                    padding: 10,
                    cornerRadius: 8,
                    displayColors: true,
                    itemSort: function (a, b) {
                        return b.raw - a.raw;
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Response Time (ms)',
                        color: '#94a3b8'
                    },
                    grid: {
                        color: 'rgba(148, 163, 184, 0.1)'
                    },
                    ticks: {
                        color: '#94a3b8'
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#94a3b8',
                        maxTicksLimit: 8
                    },
                    title: {
                        display: true,
                        text: 'Time',
                        color: '#94a3b8'
                    }
                }
            },
            animation: {
                duration: 750 // Enable animation for smoother updates
            }
        }
    });
}

async function updateDeviceTypeResponseChart() {
    if (!deviceTypeChart) return;

    try {
        // Fetch at least 3 minutes of data to ensure we have enough points for a line
        // 1 minute is too short for 30s ping intervals (might result in 0-1 points)
        const requestMinutes = currentTrendRange === 1 ? 3 : currentTrendRange;
        const response = await fetch(`/api/statistics/trend?minutes=${requestMinutes}`);

        if (!response.ok) {
            console.error('Failed to fetch trend stats:', response.status);
            return;
        }

        const trends = await response.json();

        if (!trends || trends.length === 0) {
            // No data available
            return;
        }

        // Process data
        // Group by device type
        const datasets = {};
        const timestamps = new Set();

        trends.forEach(item => {
            const type = item.device_type || 'other';

            // Format time label based on range
            let timeLabel;
            if (currentTrendRange <= 10) {
                // Show seconds for short ranges (HH:MM:SS)
                timeLabel = item.timestamp.substring(11, 19);
            } else {
                // Show HH:MM for longer ranges
                timeLabel = item.timestamp.substring(11, 16);
            }

            timestamps.add(timeLabel);

            if (!datasets[type]) {
                const meta = typeMetadata[type] || typeMetadata['other'];
                datasets[type] = {
                    label: meta.name,
                    data: {}, // Map time to value for easy lookup
                    borderColor: meta.color,
                    backgroundColor: meta.color + '20', // Low opacity fill
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    pointRadius: 0,
                    pointHoverRadius: 6,
                    pointBackgroundColor: meta.color,
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 1,
                    spanGaps: true // Connect lines over missing data
                };
            }

            datasets[type].data[timeLabel] = Math.round(item.avg_response_time);
        });

        // Sort timestamps
        const sortedTimes = Array.from(timestamps).sort();

        // Convert datasets to Chart.js format
        const chartDatasets = Object.values(datasets).map(ds => {
            const dataArray = sortedTimes.map(time => ds.data[time] || null); // Use null for missing data points
            return {
                ...ds,
                data: dataArray
            };
        });

        // Sort datasets by latest value (optional, for legend order)
        chartDatasets.sort((a, b) => {
            const lastA = a.data[a.data.length - 1] || 0;
            const lastB = b.data[b.data.length - 1] || 0;
            return lastB - lastA;
        });

        deviceTypeChart.data.labels = sortedTimes;
        deviceTypeChart.data.datasets = chartDatasets;
        deviceTypeChart.update();

    } catch (error) {
        console.error('Error fetching trend stats:', error);
    }
}

