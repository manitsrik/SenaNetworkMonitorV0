// Dashboard JavaScript - Separate Charts Version
// Handles dashboard statistics, device status, and individual response time charts per device type

// Initialize Socket.IO connection
const socket = io();

// Store charts for each device type
let charts = {};
const MAX_DATA_POINTS = 20;

// Store device group states (expanded/collapsed)
let deviceGroupStates = {};

// Device type colors
const deviceTypeColors = {
    'switch': {
        border: 'rgb(16, 185, 129)',      // green
        background: 'rgba(16, 185, 129, 0.1)'
    },
    'firewall': {
        border: 'rgb(239, 68, 68)',       // red
        background: 'rgba(239, 68, 68, 0.1)'
    },
    'server': {
        border: 'rgb(99, 102, 241)',      // indigo
        background: 'rgba(99, 102, 241, 0.1)'
    },
    'router': {
        border: 'rgb(245, 158, 11)',      // amber
        background: 'rgba(245, 158, 11, 0.1)'
    },
    'website': {
        border: 'rgb(139, 92, 246)',      // purple
        background: 'rgba(139, 92, 246, 0.1)'
    },
    'wireless': {
        border: 'rgb(236, 72, 153)',      // pink
        background: 'rgba(236, 72, 153, 0.1)'
    },
    'vmware': {
        border: 'rgb(34, 197, 94)',       // emerald green (VMware green)
        background: 'rgba(34, 197, 94, 0.1)'
    },
    'ippbx': {
        border: 'rgb(59, 130, 246)',      // blue
        background: 'rgba(59, 130, 246, 0.1)'
    },
    'vpnrouter': {
        border: 'rgb(168, 85, 247)',      // purple
        background: 'rgba(168, 85, 247, 0.1)'
    },
    'dns': {
        border: 'rgb(14, 165, 233)',      // sky blue
        background: 'rgba(14, 165, 233, 0.1)'
    },
    'other': {
        border: 'rgb(148, 163, 184)',     // gray
        background: 'rgba(148, 163, 184, 0.1)'
    }
};

// Device type metadata
const typeMetadata = {
    'switch': { icon: '🔀', name: 'Switches' },
    'firewall': { icon: '🛡️', name: 'Firewalls' },
    'server': { icon: '🖥️', name: 'Servers' },
    'router': { icon: '🌐', name: 'Routers' },
    'wireless': { icon: '📶', name: 'Wireless' },
    'website': { icon: '🌐', name: 'Websites' },
    'vmware': { icon: '🖴', name: 'VMware Servers' },
    'ippbx': { icon: '☎️', name: 'IP-PBX' },
    'vpnrouter': { icon: '🔒', name: 'VPN-Router Sites' },
    'dns': { icon: '🔍', name: 'DNS Servers' },
    'other': { icon: '⚙️', name: 'Other' }
};

// Chart data storage
let chartData = {};

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    loadInitialData();
    setupSocketListeners();
});

// Load initial data
async function loadInitialData() {
    try {
        // Load devices
        const devicesResponse = await fetch('/api/devices');
        const devices = await devicesResponse.json();

        // Initialize charts based on device types
        initializeCharts(devices);
        updateDeviceList(devices);

        // Load statistics
        const statsResponse = await fetch('/api/statistics');
        const stats = await statsResponse.json();
        updateStatistics(stats);
    } catch (error) {
        console.error('Error loading initial data:', error);
    }
}

// Initialize charts for each device type
function initializeCharts(devices) {
    const container = document.getElementById('charts-container');
    container.innerHTML = '';

    // Get unique device types
    const deviceTypes = [...new Set(devices.map(d => d.device_type || 'other'))];

    deviceTypes.forEach(type => {
        const meta = typeMetadata[type] || typeMetadata['other'];
        const colors = deviceTypeColors[type] || deviceTypeColors['other'];

        // Create chart container
        const chartDiv = document.createElement('div');
        chartDiv.style.cssText = `
            background: var(--bg-secondary);
            padding: 0.75rem;
            border-radius: var(--radius-md);
            border-left: 3px solid ${colors.border};
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            transition: all 0.3s ease;
        `;

        // Add hover effect
        chartDiv.addEventListener('mouseenter', () => {
            chartDiv.style.transform = 'translateY(-2px)';
            chartDiv.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.2)';
        });
        chartDiv.addEventListener('mouseleave', () => {
            chartDiv.style.transform = 'translateY(0)';
            chartDiv.style.boxShadow = '0 2px 4px rgba(0, 0, 0, 0.1)';
        });

        chartDiv.innerHTML = `
            <div style="margin-bottom: 0.5rem; display: flex; align-items: center; justify-content: space-between;">
                <h4 style="margin: 0; color: var(--text-primary); font-size: 0.85rem; display: flex; align-items: center; gap: 0.4rem; font-weight: 600;">
                    <span style="font-size: 1rem;">${meta.icon}</span>
                    ${meta.name}
                </h4>
            </div>
            <div style="height: 60px; position: relative;">
                <canvas id="chart-${type}"></canvas>
            </div>
        `;

        container.appendChild(chartDiv);

        // Initialize chart data
        chartData[type] = {
            labels: [],
            data: []
        };

        // Create chart
        const ctx = document.getElementById(`chart-${type}`).getContext('2d');
        charts[type] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: meta.name,
                    data: [],
                    borderColor: colors.border,
                    backgroundColor: colors.background,
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
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        titleColor: '#f1f5f9',
                        bodyColor: '#cbd5e1',
                        borderColor: 'rgba(148, 163, 184, 0.2)',
                        borderWidth: 1,
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
                        grid: {
                            color: 'rgba(148, 163, 184, 0.1)'
                        },
                        ticks: {
                            color: '#94a3b8',
                            font: {
                                size: 10
                            },
                            callback: function (value) {
                                return value + ' ms';
                            }
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        },
                        ticks: {
                            color: '#94a3b8',
                            font: {
                                size: 9
                            },
                            maxRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: 5
                        }
                    }
                }
            }
        });
    });
}

// Update charts with new data
function updateCharts(devices) {
    const now = new Date();
    const timeLabel = now.toLocaleTimeString('th-TH', {
        hour: '2-digit',
        minute: '2-digit'
    });

    // Group devices by type
    const devicesByType = {};
    devices.forEach(device => {
        const type = device.device_type || 'other';
        if (!devicesByType[type]) {
            devicesByType[type] = [];
        }
        devicesByType[type].push(device);
    });

    // Update each chart
    Object.keys(charts).forEach(type => {
        const typeDevices = devicesByType[type] || [];
        const onlineDevices = typeDevices.filter(d => d.status === 'up' && d.response_time);

        let avgResponseTime = 0;
        if (onlineDevices.length > 0) {
            const totalResponseTime = onlineDevices.reduce((sum, d) => sum + parseFloat(d.response_time), 0);
            avgResponseTime = totalResponseTime / onlineDevices.length;
        }

        // Update chart data
        const chart = charts[type];
        chart.data.labels.push(timeLabel);
        chart.data.datasets[0].data.push(avgResponseTime);

        // Keep only last MAX_DATA_POINTS
        if (chart.data.labels.length > MAX_DATA_POINTS) {
            chart.data.labels.shift();
            chart.data.datasets[0].data.shift();
        }

        chart.update('none'); // Update without animation for better performance
    });
}

// Setup Socket.IO listeners
function setupSocketListeners() {
    socket.on('connect', () => {
        console.log('Connected to server');
        socket.emit('request_status');
    });

    socket.on('status_update', (device) => {
        console.log('Status update:', device);
        updateSingleDevice(device);
    });

    socket.on('statistics_update', (stats) => {
        console.log('Statistics update:', stats);
        updateStatistics(stats);

        // Reload devices to update charts
        fetch('/api/devices')
            .then(response => response.json())
            .then(devices => updateCharts(devices))
            .catch(error => console.error('Error updating charts:', error));
    });
}

// Update statistics cards
function updateStatistics(stats) {
    document.getElementById('total-devices').textContent = stats.total_devices;
    document.getElementById('devices-up').textContent = stats.devices_up;
    document.getElementById('devices-slow').textContent = stats.devices_slow || 0;
    document.getElementById('devices-down').textContent = stats.devices_down;
    document.getElementById('uptime-percentage').textContent = stats.uptime_percentage + '%';
    document.getElementById('avg-response-time').textContent = stats.average_response_time + ' ms';
}

// Update device list - grouped by type
function updateDeviceList(devices) {
    const deviceList = document.getElementById('device-list');

    if (devices.length === 0) {
        deviceList.innerHTML = `
            <p class="text-center" style="color: var(--text-muted); padding: 2rem;">
                No devices configured. <a href="/devices" style="color: var(--primary);">Add devices</a> to start monitoring.
            </p>
        `;
        return;
    }

    // Save current states before updating
    const currentStates = {};
    Object.keys(deviceGroupStates).forEach(type => {
        const element = document.getElementById(`device-group-${type}`);
        if (element) {
            currentStates[type] = element.style.display !== 'none';
        }
    });

    // Group devices by type
    const devicesByType = {};
    devices.forEach(device => {
        const type = device.device_type || 'other';
        if (!devicesByType[type]) {
            devicesByType[type] = [];
        }
        devicesByType[type].push(device);
    });

    // Device type metadata
    const typeMetadata = {
        'switch': { icon: '🔀', name: 'Switches', color: '#10b981' },
        'firewall': { icon: '🛡️', name: 'Firewalls', color: '#ef4444' },
        'server': { icon: '🖥️', name: 'Servers', color: '#6366f1' },
        'router': { icon: '🌐', name: 'Routers', color: '#f59e0b' },
        'wireless': { icon: '📶', name: 'Wireless', color: '#ec4899' },
        'website': { icon: '🌐', name: 'Websites', color: '#8b5cf6' },
        'vmware': { icon: '🖴', name: 'VMware Servers', color: '#22c55e' },
        'ippbx': { icon: '☎️', name: 'IP-PBX', color: '#3b82f6' },
        'vpnrouter': { icon: '🔒', name: 'VPN-Router Sites', color: '#a855f7' },
        'dns': { icon: '🔍', name: 'DNS Servers', color: '#0ea5e9' },
        'other': { icon: '⚙️', name: 'Other Devices', color: '#94a3b8' }
    };

    // Build grouped HTML
    let html = '';
    Object.keys(devicesByType).sort().forEach(type => {
        const meta = typeMetadata[type] || typeMetadata['other'];
        const typeDevices = devicesByType[type];
        const upCount = typeDevices.filter(d => d.status === 'up').length;
        const totalCount = typeDevices.length;

        html += `
            <div class="device-group fade-in" style="margin-bottom: 1.5rem;">
                <div class="device-group-header" onclick="toggleDeviceGroup('${type}')" style="
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    padding: 0.75rem 1rem;
                    background: var(--bg-secondary);
                    border-radius: var(--radius-md);
                    cursor: pointer;
                    border-left: 3px solid ${meta.color};
                    margin-bottom: 0.5rem;
                    transition: all 0.3s ease;
                ">
                    <div style="display: flex; align-items: center; gap: 0.75rem;">
                        <span style="font-size: 1.5rem;">${meta.icon}</span>
                        <div>
                            <h4 style="margin: 0; color: var(--text-primary); font-size: 1rem;">${meta.name}</h4>
                            <p style="margin: 0; color: var(--text-muted); font-size: 0.875rem;">${totalCount} device${totalCount > 1 ? 's' : ''}</p>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 1rem;">
                        <span style="color: var(--success); font-weight: 600;">${upCount}/${totalCount} UP</span>
                        <span id="toggle-icon-${type}" style="font-size: 1.25rem; transition: transform 0.3s ease;">▶</span>
                    </div>
                </div>
                <div id="device-group-${type}" class="device-group-content" style="
                    display: none;
                    padding-left: 1rem;
                ">
        `;

        typeDevices.forEach(device => {
            // Determine status class based on response time
            let statusClass = device.status || 'unknown';
            let statusText = device.status || 'unknown';

            // If device is up but response time > 500ms, show warning
            if (device.status === 'up' && device.response_time && parseFloat(device.response_time) > 500) {
                statusClass = 'warning';
                statusText = 'SLOW';
            }

            html += `
                <div class="device-item" style="margin-bottom: 0.5rem;">
                    <div class="device-info">
                        <h4>${meta.icon} ${device.name}</h4>
                        <p>${device.ip_address}</p>
                    </div>
                    <div style="display: flex; align-items: center; gap: 1rem;">
                        ${device.response_time ? `<span style="color: var(--text-muted); font-size: 0.875rem;">${device.response_time} ms</span>` : ''}
                        <span class="status-badge status-${statusClass}">
                            ${statusText}
                        </span>
                    </div>
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;
    });

    deviceList.innerHTML = html;

    // Restore states after updating HTML
    Object.keys(currentStates).forEach(type => {
        if (currentStates[type]) {
            const content = document.getElementById(`device-group-${type}`);
            const icon = document.getElementById(`toggle-icon-${type}`);
            if (content && icon) {
                content.style.display = 'block';
                icon.textContent = '▼';
                icon.style.transform = 'rotate(0deg)';
                deviceGroupStates[type] = true;
            }
        } else {
            deviceGroupStates[type] = false;
        }
    });
}

// Toggle device group visibility
function toggleDeviceGroup(type) {
    const content = document.getElementById(`device-group-${type}`);
    const icon = document.getElementById(`toggle-icon-${type}`);

    if (content.style.display === 'none') {
        content.style.display = 'block';
        icon.style.transform = 'rotate(0deg)';
        icon.textContent = '▼';
        deviceGroupStates[type] = true; // Save state
    } else {
        content.style.display = 'none';
        icon.style.transform = 'rotate(-90deg)';
        icon.textContent = '▶';
        deviceGroupStates[type] = false; // Save state
    }
}

// Update single device status
function updateSingleDevice(device) {
    // Reload device list
    fetch('/api/devices')
        .then(response => response.json())
        .then(devices => updateDeviceList(devices))
        .catch(error => console.error('Error updating device list:', error));
}

// Refresh status
function refreshStatus() {
    const icon = document.getElementById('refresh-icon');
    icon.style.transform = 'rotate(360deg)';
    icon.style.transition = 'transform 0.5s ease';

    socket.emit('request_status');

    setTimeout(() => {
        icon.style.transform = 'rotate(0deg)';
    }, 500);
}

// Activity log
let activityLog = [];
const MAX_ACTIVITY_ITEMS = 50;

socket.on('status_update', (device) => {
    addActivityLog(device);
});

function addActivityLog(device) {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('th-TH');

    let statusIcon, statusText;
    if (device.status === 'up') {
        statusIcon = '✅';
        statusText = 'UP';
    } else if (device.status === 'slow') {
        statusIcon = '⚠️';
        statusText = 'SLOW';
    } else {
        statusIcon = '❌';
        statusText = 'DOWN';
    }

    activityLog.unshift({
        time: timeStr,
        device: device.name,
        status: device.status,
        icon: statusIcon,
        text: statusText,
        responseTime: device.response_time
    });

    if (activityLog.length > MAX_ACTIVITY_ITEMS) {
        activityLog.pop();
    }

    updateActivityLog();
}

function updateActivityLog() {
    const logContainer = document.getElementById('activity-log');

    if (activityLog.length === 0) {
        logContainer.innerHTML = `
            <p class="text-center" style="color: var(--text-muted); padding: 1rem;">
                Waiting for activity...
            </p>
        `;
        return;
    }

    logContainer.innerHTML = activityLog.map(item => `
        <div class="activity-item fade-in" style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem;
            border-bottom: 1px solid var(--border-color);
        ">
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
