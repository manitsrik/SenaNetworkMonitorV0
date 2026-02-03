// History Page JavaScript
// Handles historical data visualization and analysis

let charts = {};
const deviceTypeColors = {
    'switch': { border: 'rgb(16, 185, 129)', background: 'rgba(16, 185, 129, 0.1)' },
    'firewall': { border: 'rgb(239, 68, 68)', background: 'rgba(239, 68, 68, 0.1)' },
    'server': { border: 'rgb(99, 102, 241)', background: 'rgba(99, 102, 241, 0.1)' },
    'router': { border: 'rgb(245, 158, 11)', background: 'rgba(245, 158, 11, 0.1)' },
    'website': { border: 'rgb(139, 92, 246)', background: 'rgba(139, 92, 246, 0.1)' },
    'wireless': { border: 'rgb(236, 72, 153)', background: 'rgba(236, 72, 153, 0.1)' },
    'vmware': { border: 'rgb(34, 197, 94)', background: 'rgba(34, 197, 94, 0.1)' },
    'ippbx': { border: 'rgb(59, 130, 246)', background: 'rgba(59, 130, 246, 0.1)' },
    'vpnrouter': { border: 'rgb(168, 85, 247)', background: 'rgba(168, 85, 247, 0.1)' },
    'dns': { border: 'rgb(14, 165, 233)', background: 'rgba(14, 165, 233, 0.1)' },
    'other': { border: 'rgb(148, 163, 184)', background: 'rgba(148, 163, 184, 0.1)' }
};

const typeMetadata = {
    'switch': { icon: '🔀', name: 'Switches' },
    'firewall': { icon: '🛡️', name: 'Firewalls' },
    'server': { icon: '🖥️', name: 'Servers' },
    'router': { icon: '🌐', name: 'Routers' },
    'website': { icon: '🌐', name: 'Websites' },
    'wireless': { icon: '📶', name: 'Wireless' },
    'vmware': { icon: '🖴', name: 'VMware Servers' },
    'ippbx': { icon: '☎️', name: 'IP-PBX' },
    'vpnrouter': { icon: '🔒', name: 'VPN-Router Sites' },
    'dns': { icon: '🔍', name: 'DNS Servers' },
    'other': { icon: '⚙️', name: 'Other' }
};

// Initialize page
let allDevices = [];
let comparisonChart = null;

document.addEventListener('DOMContentLoaded', () => {
    // Set default date range to last 24 hours
    setQuickRange('24h');
    // Load device list for comparison
    loadDeviceList();
});

// Load device list for selection
async function loadDeviceList() {
    try {
        const response = await fetch('/api/devices');
        allDevices = await response.json();

        const container = document.getElementById('device-checkbox-list');
        container.innerHTML = '';

        allDevices.forEach(device => {
            const typeInfo = typeMetadata[device.device_type] || typeMetadata['other'];
            const checkbox = document.createElement('label');
            checkbox.className = 'device-checkbox-item';
            checkbox.style.cssText = `
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 0.75rem;
                background: var(--bg-tertiary);
                border-radius: var(--radius-sm);
                cursor: pointer;
                transition: all 0.2s ease;
                border: 2px solid transparent;
            `;
            checkbox.innerHTML = `
                <input type="checkbox" 
                       id="device-${device.id}" 
                       value="${device.id}" 
                       onchange="updateSelectedCount()"
                       style="width: 18px; height: 18px; cursor: pointer;">
                <span style="font-size: 1.25rem;">${typeInfo.icon}</span>
                <div style="flex: 1; min-width: 0;">
                    <div style="font-weight: 600; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                        ${device.name}
                    </div>
                    <div style="font-size: 0.75rem; color: var(--text-muted);">
                        ${device.ip_address}
                    </div>
                </div>
            `;

            // Add hover effect
            checkbox.addEventListener('mouseenter', () => {
                checkbox.style.background = 'var(--bg-secondary)';
                checkbox.style.borderColor = 'var(--primary)';
            });
            checkbox.addEventListener('mouseleave', () => {
                const input = checkbox.querySelector('input');
                if (!input.checked) {
                    checkbox.style.background = 'var(--bg-tertiary)';
                    checkbox.style.borderColor = 'transparent';
                }
            });

            container.appendChild(checkbox);
        });

        // Show device selector, hide loading
        document.getElementById('device-selector-loading').style.display = 'none';
        document.getElementById('device-selector').style.display = 'block';

    } catch (error) {
        console.error('Error loading device list:', error);
        document.getElementById('device-selector-loading').innerHTML = `
            <p style="color: var(--danger);">❌ Failed to load devices</p>
        `;
    }
}

// Update selected count
function updateSelectedCount() {
    const checkboxes = document.querySelectorAll('#device-checkbox-list input[type="checkbox"]:checked');
    document.getElementById('count-value').textContent = checkboxes.length;

    // Update visual state of checked items
    document.querySelectorAll('#device-checkbox-list label').forEach(label => {
        const input = label.querySelector('input');
        if (input.checked) {
            label.style.background = 'var(--bg-secondary)';
            label.style.borderColor = 'var(--primary)';
        } else {
            label.style.background = 'var(--bg-tertiary)';
            label.style.borderColor = 'transparent';
        }
    });
}

// Toggle select all
function toggleSelectAll() {
    const checkboxes = document.querySelectorAll('#device-checkbox-list input[type="checkbox"]');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);

    checkboxes.forEach(cb => {
        cb.checked = !allChecked;
    });

    document.getElementById('select-all-icon').textContent = allChecked ? '☑️' : '☐';
    updateSelectedCount();
}

// Clear selection
function clearSelection() {
    const checkboxes = document.querySelectorAll('#device-checkbox-list input[type="checkbox"]');
    checkboxes.forEach(cb => {
        cb.checked = false;
    });
    document.getElementById('select-all-icon').textContent = '☑️';
    updateSelectedCount();

    // Hide comparison chart
    document.getElementById('comparison-chart-container').style.display = 'none';
}

// Load multi-device history and display comparison chart
async function loadMultiDeviceHistory() {
    const checkboxes = document.querySelectorAll('#device-checkbox-list input[type="checkbox"]:checked');
    const selectedIds = Array.from(checkboxes).map(cb => cb.value);

    if (selectedIds.length === 0) {
        alert('Please select at least one device to compare');
        return;
    }

    if (selectedIds.length > 10) {
        alert('Please select at most 10 devices for comparison');
        return;
    }

    const startDate = document.getElementById('start-date').value;
    const endDate = document.getElementById('end-date').value;

    if (!startDate || !endDate) {
        alert('Please select both start and end dates');
        return;
    }

    try {
        // Show loading state
        document.getElementById('comparison-chart-container').style.display = 'block';

        // Build query parameters
        const params = new URLSearchParams({
            start_date: startDate,
            end_date: endDate,
            device_ids: selectedIds.join(',')
        });

        const response = await fetch(`/api/history?${params}`);
        const data = await response.json();

        displayComparisonChart(data, selectedIds);

    } catch (error) {
        console.error('Error loading comparison data:', error);
        alert('Failed to load comparison data');
    }
}

// Display combined comparison chart
function displayComparisonChart(data, selectedIds) {
    const container = document.getElementById('comparison-chart-container');
    container.style.display = 'block';

    // Update badge
    document.getElementById('comparison-devices-count').textContent = selectedIds.length;

    // Destroy existing chart
    if (comparisonChart) {
        comparisonChart.destroy();
    }

    if (data.length === 0) {
        document.getElementById('comparison-chart').parentElement.innerHTML = `
            <p style="text-align: center; color: var(--text-muted); padding: 3rem;">
                No data available for the selected devices and date range
            </p>
        `;
        return;
    }

    // Group data by device
    const deviceData = {};
    data.forEach(record => {
        const deviceId = record.device_id;
        if (!deviceData[deviceId]) {
            deviceData[deviceId] = {
                name: record.name,
                ip_address: record.ip_address,
                device_type: record.device_type,
                labels: [],
                data: []
            };
        }
        deviceData[deviceId].labels.push(new Date(record.checked_at).toLocaleString('th-TH'));
        deviceData[deviceId].data.push(record.response_time || 0);
    });

    // Generate distinct colors for each device
    const colors = generateDistinctColors(Object.keys(deviceData).length);

    // Create datasets
    const datasets = Object.keys(deviceData).map((deviceId, index) => {
        const device = deviceData[deviceId];
        const color = colors[index];
        return {
            label: `${device.name} (${device.ip_address})`,
            data: device.data,
            borderColor: color,
            backgroundColor: color.replace(')', ', 0.1)').replace('rgb', 'rgba'),
            tension: 0.4,
            fill: false,
            borderWidth: 2.5,
            pointRadius: 3,
            pointHoverRadius: 6,
            pointBackgroundColor: color,
            pointBorderColor: '#fff',
            pointBorderWidth: 1
        };
    });

    // Find the longest labels array for x-axis
    const allLabels = Object.values(deviceData).reduce((longest, device) =>
        device.labels.length > longest.length ? device.labels : longest, []);

    // Create chart
    const ctx = document.getElementById('comparison-chart').getContext('2d');
    comparisonChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: allLabels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: 'var(--text-secondary)',
                        usePointStyle: true,
                        padding: 20,
                        font: {
                            size: 12
                        }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    titleColor: '#f1f5f9',
                    bodyColor: '#cbd5e1',
                    borderColor: 'rgba(148, 163, 184, 0.3)',
                    borderWidth: 1,
                    padding: 14,
                    displayColors: true,
                    callbacks: {
                        label: function (context) {
                            return `${context.dataset.label}: ${context.parsed.y.toFixed(2)} ms`;
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
                        callback: function (value) {
                            return value + ' ms';
                        }
                    },
                    title: {
                        display: true,
                        text: 'Response Time (ms)',
                        color: '#94a3b8',
                        font: {
                            size: 12,
                            weight: 'bold'
                        }
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#94a3b8',
                        maxRotation: 45,
                        minRotation: 45,
                        autoSkip: true,
                        maxTicksLimit: 12
                    },
                    title: {
                        display: true,
                        text: 'Time',
                        color: '#94a3b8',
                        font: {
                            size: 12,
                            weight: 'bold'
                        }
                    }
                }
            }
        }
    });
}

// Generate distinct colors for chart lines
function generateDistinctColors(count) {
    const baseColors = [
        'rgb(59, 130, 246)',   // Blue
        'rgb(16, 185, 129)',   // Green
        'rgb(239, 68, 68)',    // Red
        'rgb(245, 158, 11)',   // Amber
        'rgb(139, 92, 246)',   // Purple
        'rgb(236, 72, 153)',   // Pink
        'rgb(20, 184, 166)',   // Teal
        'rgb(249, 115, 22)',   // Orange
        'rgb(99, 102, 241)',   // Indigo
        'rgb(168, 85, 247)'    // Violet
    ];

    if (count <= baseColors.length) {
        return baseColors.slice(0, count);
    }

    // Generate additional colors using golden angle
    const colors = [...baseColors];
    for (let i = baseColors.length; i < count; i++) {
        const hue = (i * 137.5) % 360;
        colors.push(`hsl(${hue}, 70%, 50%)`);
    }
    return colors;
}

// Set quick date range
function setQuickRange(range) {
    const endDate = new Date();
    const startDate = new Date();

    switch (range) {
        case '24h':
            startDate.setHours(startDate.getHours() - 24);
            break;
        case '7d':
            startDate.setDate(startDate.getDate() - 7);
            break;
        case '30d':
            startDate.setDate(startDate.getDate() - 30);
            break;
    }

    // Format dates for datetime-local input
    document.getElementById('start-date').value = formatDateTimeLocal(startDate);
    document.getElementById('end-date').value = formatDateTimeLocal(endDate);
}

// Format date for datetime-local input
function formatDateTimeLocal(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
}

// Load historical data
async function loadHistoricalData() {
    const startDate = document.getElementById('start-date').value;
    const endDate = document.getElementById('end-date').value;
    const deviceType = document.getElementById('device-type').value;

    if (!startDate || !endDate) {
        alert('Please select both start and end dates');
        return;
    }

    // Show loading indicator
    document.getElementById('loading-indicator').style.display = 'block';
    document.getElementById('charts-container').style.display = 'none';
    document.getElementById('stats-container').style.display = 'none';

    try {
        // Build query parameters
        const params = new URLSearchParams({
            start_date: startDate,
            end_date: endDate
        });

        if (deviceType) {
            params.append('device_type', deviceType);
        }

        // Fetch historical data and stats
        const [historyResponse, statsResponse] = await Promise.all([
            fetch(`/api/history?${params}`),
            fetch(`/api/history/stats?${params}`)
        ]);

        const historyData = await historyResponse.json();
        const statsData = await statsResponse.json();

        // Update UI
        displayHistoricalCharts(historyData);
        displayStatistics(statsData);
        displayDeviceDetails(historyData, deviceType);

        // Hide loading, show content
        document.getElementById('loading-indicator').style.display = 'none';
        document.getElementById('charts-container').style.display = 'block';
        document.getElementById('stats-container').style.display = 'block';

        // Update data points badge
        document.getElementById('data-points-badge').style.display = 'inline-flex';
        document.getElementById('data-points-count').textContent = historyData.length;

    } catch (error) {
        console.error('Error loading historical data:', error);
        document.getElementById('loading-indicator').innerHTML = `
            <p style="color: var(--danger);">❌ Error loading data. Please try again.</p>
        `;
    }
}

// Display historical charts
function displayHistoricalCharts(data) {
    const container = document.getElementById('charts-container');
    container.innerHTML = '';

    // Destroy existing charts
    Object.values(charts).forEach(chart => chart.destroy());
    charts = {};

    if (data.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-muted); padding: 2rem;">No data available for the selected period</p>';
        return;
    }

    // Group data by device type
    const dataByType = {};
    data.forEach(record => {
        const type = record.device_type || 'other';
        if (!dataByType[type]) {
            dataByType[type] = [];
        }
        dataByType[type].push(record);
    });

    // Create chart for each device type
    Object.keys(dataByType).sort().forEach(type => {
        const typeData = dataByType[type];
        const meta = typeMetadata[type] || typeMetadata['other'];
        const colors = deviceTypeColors[type] || deviceTypeColors['other'];

        // Group by device and prepare chart data
        const deviceData = {};
        typeData.forEach(record => {
            const deviceName = record.name;
            if (!deviceData[deviceName]) {
                deviceData[deviceName] = {
                    labels: [],
                    data: []
                };
            }
            deviceData[deviceName].labels.push(new Date(record.checked_at).toLocaleString('th-TH'));
            deviceData[deviceName].data.push(record.response_time || 0);
        });

        // Create chart container
        const chartDiv = document.createElement('div');
        chartDiv.style.cssText = `
            background: var(--bg-secondary);
            padding: 1rem;
            border-radius: var(--radius-md);
            border-left: 3px solid ${colors.border};
            margin-bottom: 1rem;
        `;

        chartDiv.innerHTML = `
            <div style="margin-bottom: 1rem;">
                <h4 style="margin: 0; color: var(--text-primary); display: flex; align-items: center; gap: 0.5rem;">
                    <span style="font-size: 1.25rem;">${meta.icon}</span>
                    ${meta.name}
                </h4>
            </div>
            <div style="height: 300px; position: relative;">
                <canvas id="chart-${type}"></canvas>
            </div>
        `;

        container.appendChild(chartDiv);

        // Prepare datasets for all devices of this type
        const datasets = Object.keys(deviceData).map((deviceName, index) => {
            const hue = (index * 137.5) % 360; // Golden angle for color distribution
            return {
                label: deviceName,
                data: deviceData[deviceName].data,
                borderColor: `hsl(${hue}, 70%, 50%)`,
                backgroundColor: `hsla(${hue}, 70%, 50%, 0.1)`,
                tension: 0.4,
                fill: false,
                borderWidth: 2,
                pointRadius: 2,
                pointHoverRadius: 5
            };
        });

        // Use labels from first device (all should have same timestamps)
        const labels = Object.values(deviceData)[0].labels;

        // Create chart
        const ctx = document.getElementById(`chart-${type}`).getContext('2d');
        charts[type] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            color: 'var(--text-secondary)',
                            usePointStyle: true,
                            padding: 15
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        titleColor: '#f1f5f9',
                        bodyColor: '#cbd5e1',
                        borderColor: 'rgba(148, 163, 184, 0.2)',
                        borderWidth: 1,
                        padding: 12,
                        callbacks: {
                            label: function (context) {
                                return `${context.dataset.label}: ${context.parsed.y.toFixed(2)} ms`;
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
                            callback: function (value) {
                                return value + ' ms';
                            }
                        },
                        title: {
                            display: true,
                            text: 'Response Time (ms)',
                            color: '#94a3b8'
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        },
                        ticks: {
                            color: '#94a3b8',
                            maxRotation: 45,
                            minRotation: 45,
                            autoSkip: true,
                            maxTicksLimit: 10
                        },
                        title: {
                            display: true,
                            text: 'Time',
                            color: '#94a3b8'
                        }
                    }
                }
            }
        });
    });
}

// Display statistics summary
function displayStatistics(stats) {
    if (stats.length === 0) {
        return;
    }

    // Calculate overall statistics
    let totalChecks = 0;
    let totalDevices = 0;
    let totalUpCount = 0;
    let totalSlowCount = 0;
    let totalDownCount = 0;
    let avgResponseTimes = [];

    stats.forEach(stat => {
        totalChecks += stat.total_checks || 0;
        totalDevices += stat.device_count || 0;
        totalUpCount += stat.up_count || 0;
        totalSlowCount += stat.slow_count || 0;
        totalDownCount += stat.down_count || 0;
        if (stat.avg_response_time) {
            avgResponseTimes.push(stat.avg_response_time);
        }
    });

    const avgResponse = avgResponseTimes.length > 0
        ? (avgResponseTimes.reduce((a, b) => a + b, 0) / avgResponseTimes.length).toFixed(2)
        : 0;

    const uptime = totalChecks > 0
        ? ((totalUpCount + totalSlowCount) / totalChecks * 100).toFixed(2)
        : 0;

    // Update stat cards
    document.getElementById('stat-avg-response').textContent = avgResponse + ' ms';
    document.getElementById('stat-uptime').textContent = uptime + '%';
    document.getElementById('stat-total-checks').textContent = totalChecks.toLocaleString();
    document.getElementById('stat-devices').textContent = totalDevices;
}

// Display device details
function displayDeviceDetails(data, deviceType) {
    const container = document.getElementById('device-details');

    if (data.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-muted); padding: 2rem;">No device data available</p>';
        return;
    }

    // Group by device
    const deviceStats = {};
    data.forEach(record => {
        const deviceId = record.device_id;
        if (!deviceStats[deviceId]) {
            deviceStats[deviceId] = {
                name: record.name,
                ip_address: record.ip_address,
                device_type: record.device_type,
                checks: 0,
                upCount: 0,
                slowCount: 0,
                downCount: 0,
                responseTimes: []
            };
        }

        deviceStats[deviceId].checks++;
        if (record.status === 'up') deviceStats[deviceId].upCount++;
        if (record.status === 'slow') deviceStats[deviceId].slowCount++;
        if (record.status === 'down') deviceStats[deviceId].downCount++;
        if (record.response_time) deviceStats[deviceId].responseTimes.push(record.response_time);
    });

    // Create table
    let html = `
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="border-bottom: 2px solid var(--border-color);">
                        <th style="padding: 0.75rem; text-align: left; color: var(--text-secondary);">Device</th>
                        <th style="padding: 0.75rem; text-align: left; color: var(--text-secondary);">Type</th>
                        <th style="padding: 0.75rem; text-align: center; color: var(--text-secondary);">Checks</th>
                        <th style="padding: 0.75rem; text-align: center; color: var(--text-secondary);">Uptime</th>
                        <th style="padding: 0.75rem; text-align: center; color: var(--text-secondary);">Avg Response</th>
                        <th style="padding: 0.75rem; text-align: center; color: var(--text-secondary);">Status</th>
                    </tr>
                </thead>
                <tbody>
    `;

    Object.values(deviceStats).forEach(device => {
        const avgResponse = device.responseTimes.length > 0
            ? (device.responseTimes.reduce((a, b) => a + b, 0) / device.responseTimes.length).toFixed(2)
            : 'N/A';

        const uptime = device.checks > 0
            ? ((device.upCount + device.slowCount) / device.checks * 100).toFixed(1)
            : 0;

        const meta = typeMetadata[device.device_type] || typeMetadata['other'];

        html += `
            <tr style="border-bottom: 1px solid var(--border-color);">
                <td style="padding: 0.75rem;">
                    <div style="font-weight: 600; color: var(--text-primary);">${meta.icon} ${device.name}</div>
                    <div style="font-size: 0.875rem; color: var(--text-muted);">${device.ip_address}</div>
                </td>
                <td style="padding: 0.75rem; color: var(--text-secondary);">${meta.name}</td>
                <td style="padding: 0.75rem; text-align: center; color: var(--text-secondary);">${device.checks}</td>
                <td style="padding: 0.75rem; text-align: center;">
                    <span style="color: ${uptime >= 95 ? 'var(--success)' : uptime >= 80 ? 'var(--warning)' : 'var(--danger)'}; font-weight: 600;">
                        ${uptime}%
                    </span>
                </td>
                <td style="padding: 0.75rem; text-align: center; color: var(--text-secondary);">${avgResponse} ms</td>
                <td style="padding: 0.75rem; text-align: center;">
                    <div style="display: flex; gap: 0.5rem; justify-content: center; font-size: 0.875rem;">
                        <span style="color: var(--success);">✅ ${device.upCount}</span>
                        <span style="color: var(--warning);">⚠️ ${device.slowCount}</span>
                        <span style="color: var(--danger);">❌ ${device.downCount}</span>
                    </div>
                </td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
        </div>
    `;

    container.innerHTML = html;
}
