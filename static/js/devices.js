// Devices JavaScript
// Handles device management (CRUD operations)

// Initialize Socket.IO connection
const socket = io();

// Current editing device ID
let editingDeviceId = null;

// Store all devices for filtering
let allDevices = [];

// Location type icon mapping
const locationTypeIcons = {
    'cloud': '☁️',
    'internet': '🌐',
    'remote': '🏢',
    'on-premise': '🏠'
};

const locationTypeLabels = {
    'cloud': 'Cloud',
    'internet': 'Internet',
    'remote': 'Remote Site',
    'on-premise': 'On-Premise'
};

// Initialize devices page
document.addEventListener('DOMContentLoaded', () => {
    loadDevices();
    setupSocketListeners();
});

// Load all devices
async function loadDevices() {
    try {
        const response = await fetch('/api/devices');
        const devices = await response.json();
        allDevices = devices; // Store globally for filtering
        populateFilterOptions(devices); // Populate filter dropdowns
        filterDevices(); // Apply current filters
        updateDeviceCount(devices.length);
    } catch (error) {
        console.error('Error loading devices:', error);
        alert('Error loading devices. Please refresh the page.');
    }
}

// Update devices table
function updateDevicesTable(devices) {
    const tbody = document.getElementById('devices-table-body');

    if (devices.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center" style="padding: 2rem; color: var(--text-muted);">
                    No devices found. Click "Add Device" to get started.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = devices.map(device => {
        const locTypeIcon = locationTypeIcons[device.location_type] || '🏠';
        const locTypeLabel = locationTypeLabels[device.location_type] || 'On-Premise';
        return `
        <tr class="fade-in">
            <td><strong>${device.name}</strong></td>
            <td><code>${device.ip_address}</code></td>
            <td>${device.device_type || 'N/A'}</td>
            <td>${device.location || 'N/A'}</td>
            <td style="text-align: center;"><span title="${locTypeLabel}">${locTypeIcon}</span></td>
            <td>
                <span class="status-badge status-${device.status || 'unknown'}">
                    ${device.status || 'unknown'}
                </span>
            </td>
            <td>${device.response_time !== null && device.response_time !== undefined ? device.response_time + ' ms' : 'N/A'}</td>
            <td>${device.last_check ? formatDateTime(device.last_check) : 'Never'}</td>
            <td>
                <div style="display: flex; gap: 0.25rem;">
                    <button class="btn btn-sm" style="background: var(--success); color: white; padding: 0.25rem 0.5rem;" onclick="showDeviceGraph(${device.id})" title="Response Time Graph">
                        📈
                    </button>
                    ${device.monitor_type === 'snmp' ? `
                    <button class="btn btn-sm" style="background: var(--primary); color: white; padding: 0.25rem 0.5rem;" onclick="showSnmpDetails(${device.id})" title="SNMP Details">
                        📊
                    </button>
                    ` : ''}
                    ${device.monitor_type === 'http' && device.ip_address.startsWith('https') ? `
                    <button class="btn btn-sm" style="background: var(--warning); color: white; padding: 0.25rem 0.5rem;" onclick="showSslDetails(${device.id})" title="SSL Certificate">
                        🔒
                    </button>
                    ` : ''}
                    <button class="btn btn-sm btn-secondary" style="padding: 0.25rem 0.5rem;" onclick="editDevice(${device.id})" title="Edit">
                        ✏️
                    </button>
                    <button class="btn btn-sm btn-primary" style="padding: 0.25rem 0.5rem;" onclick="checkDeviceNow(${device.id})" title="Check Now">
                        🔄
                    </button>
                    <button class="btn btn-sm btn-danger" style="padding: 0.25rem 0.5rem;" onclick="deleteDevice(${device.id})" title="Delete">
                        🗑️
                    </button>
                </div>
            </td>
        </tr>
    `}).join('');
}

// Update device count
function updateDeviceCount(count) {
    const badge = document.getElementById('device-count');
    badge.textContent = `${count} device${count !== 1 ? 's' : ''}`;
}

// Format date time
function formatDateTime(dateStr) {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    return date.toLocaleString('th-TH', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Populate filter options dynamically
function populateFilterOptions(devices) {
    // Get unique values
    const types = getUniqueValues(devices, 'device_type');
    const locations = getUniqueValues(devices, 'location');

    // Populate Type filter
    const typeFilter = document.getElementById('filter-type');
    const currentType = typeFilter.value;
    typeFilter.innerHTML = '<option value="">All Types</option>';
    types.forEach(type => {
        if (type) {
            const option = document.createElement('option');
            option.value = type;
            option.textContent = type.charAt(0).toUpperCase() + type.slice(1);
            typeFilter.appendChild(option);
        }
    });
    typeFilter.value = currentType; // Restore selection

    // Populate Location filter
    const locationFilter = document.getElementById('filter-location');
    const currentLocation = locationFilter.value;
    locationFilter.innerHTML = '<option value="">All Locations</option>';
    locations.forEach(location => {
        if (location) {
            const option = document.createElement('option');
            option.value = location;
            option.textContent = location;
            locationFilter.appendChild(option);
        }
    });
    locationFilter.value = currentLocation; // Restore selection
}

// Get unique values from devices array
function getUniqueValues(devices, field) {
    const values = devices.map(device => device[field]).filter(val => val);
    return [...new Set(values)].sort();
}

// Filter devices based on search and filters
function filterDevices() {
    const searchTerm = document.getElementById('search-input').value.toLowerCase();
    const typeFilter = document.getElementById('filter-type').value.toLowerCase();
    const locationFilter = document.getElementById('filter-location').value.toLowerCase();
    const statusFilter = document.getElementById('filter-status').value.toLowerCase();
    const locationTypeFilter = document.getElementById('filter-location-type')?.value.toLowerCase() || '';

    const filteredDevices = allDevices.filter(device => {
        // Search filter (name or IP)
        const matchesSearch = !searchTerm ||
            device.name.toLowerCase().includes(searchTerm) ||
            device.ip_address.toLowerCase().includes(searchTerm);

        // Type filter
        const matchesType = !typeFilter ||
            (device.device_type && device.device_type.toLowerCase() === typeFilter);

        // Location filter
        const matchesLocation = !locationFilter ||
            (device.location && device.location.toLowerCase() === locationFilter);

        // Status filter
        const matchesStatus = !statusFilter ||
            (device.status && device.status.toLowerCase() === statusFilter);

        // Location Type filter
        const matchesLocationType = !locationTypeFilter ||
            (device.location_type && device.location_type.toLowerCase() === locationTypeFilter);

        return matchesSearch && matchesType && matchesLocation && matchesStatus && matchesLocationType;
    });

    updateDevicesTable(filteredDevices);
    updateFilteredCount(filteredDevices.length, allDevices.length);
}

// Update device count with filter info
function updateFilteredCount(filteredCount, totalCount) {
    const badge = document.getElementById('device-count');
    if (filteredCount === totalCount) {
        badge.textContent = `${totalCount} device${totalCount !== 1 ? 's' : ''}`;
    } else {
        badge.textContent = `${filteredCount} of ${totalCount} device${totalCount !== 1 ? 's' : ''}`;
    }
}

// Clear all filters
function clearFilters() {
    document.getElementById('search-input').value = '';
    document.getElementById('filter-type').value = '';
    document.getElementById('filter-location').value = '';
    document.getElementById('filter-status').value = '';
    const locationTypeFilter = document.getElementById('filter-location-type');
    if (locationTypeFilter) locationTypeFilter.value = '';
    filterDevices();
}

// Show add device modal
function showAddDeviceModal() {
    editingDeviceId = null;
    document.getElementById('modal-title').textContent = 'Add Device';
    document.getElementById('device-form').reset();
    document.getElementById('device-id').value = '';
    document.getElementById('monitor-type').value = 'ping';
    // Reset SNMP fields to defaults
    document.getElementById('snmp-community').value = 'public';
    document.getElementById('snmp-port').value = '161';
    document.getElementById('snmp-version').value = '2c';
    // Reset TCP port to default
    document.getElementById('tcp-port').value = '80';
    // Reset DNS query domain to default
    document.getElementById('dns-query-domain').value = 'google.com';
    // Reset expected status code to default
    document.getElementById('expected-status-code').value = '200';
    // Reset location type to default
    document.getElementById('device-location-type').value = 'on-premise';
    updateIPFieldLabel();
    document.getElementById('device-modal').classList.add('active');
}

// Update IP field label based on monitor type
function updateIPFieldLabel() {
    const monitorType = document.getElementById('monitor-type').value;
    const ipLabel = document.getElementById('ip-label');
    const ipInput = document.getElementById('device-ip');
    const ipHint = document.getElementById('ip-hint');
    const snmpSettings = document.getElementById('snmp-settings');
    const tcpSettings = document.getElementById('tcp-settings');
    const dnsSettings = document.getElementById('dns-settings');
    const httpSettings = document.getElementById('http-settings');

    // Hide all optional settings first
    snmpSettings.style.display = 'none';
    tcpSettings.style.display = 'none';
    dnsSettings.style.display = 'none';
    httpSettings.style.display = 'none';

    if (monitorType === 'http') {
        ipLabel.textContent = 'URL *';
        ipInput.placeholder = 'e.g., https://www.google.com';
        ipInput.removeAttribute('pattern');
        ipHint.textContent = 'Enter website URL (with http:// or https://)';
        httpSettings.style.display = 'block';
    } else if (monitorType === 'snmp') {
        ipLabel.textContent = 'IP Address *';
        ipInput.placeholder = 'e.g., 192.168.1.1';
        ipInput.removeAttribute('pattern');
        ipHint.textContent = 'Enter IP address for SNMP monitoring';
        snmpSettings.style.display = 'block';
    } else if (monitorType === 'tcp') {
        ipLabel.textContent = 'IP Address *';
        ipInput.placeholder = 'e.g., 192.168.1.1';
        ipInput.removeAttribute('pattern');
        ipHint.textContent = 'Enter IP address for TCP port check';
        tcpSettings.style.display = 'block';
    } else if (monitorType === 'dns') {
        ipLabel.textContent = 'DNS Server IP *';
        ipInput.placeholder = 'e.g., 8.8.8.8';
        ipInput.removeAttribute('pattern');
        ipHint.textContent = 'Enter DNS server IP address to test';
        dnsSettings.style.display = 'block';
    } else {
        ipLabel.textContent = 'IP Address *';
        ipInput.placeholder = 'e.g., 192.168.1.1';
        ipInput.removeAttribute('pattern');
        ipHint.textContent = 'Enter IP address for ping monitoring';
    }
}

// Close device modal
function closeDeviceModal() {
    document.getElementById('device-modal').classList.remove('active');
    editingDeviceId = null;
}

// Edit device
async function editDevice(deviceId) {
    try {
        const response = await fetch('/api/devices');
        const devices = await response.json();
        const device = devices.find(d => d.id === deviceId);

        if (device) {
            editingDeviceId = deviceId;
            document.getElementById('modal-title').textContent = 'Edit Device';
            document.getElementById('device-id').value = device.id;
            document.getElementById('device-name').value = device.name;
            document.getElementById('device-ip').value = device.ip_address;
            document.getElementById('device-type').value = device.device_type || 'server';
            document.getElementById('device-location').value = device.location || '';
            document.getElementById('monitor-type').value = device.monitor_type || 'ping';

            // Load SNMP settings
            document.getElementById('snmp-community').value = device.snmp_community || 'public';
            document.getElementById('snmp-port').value = device.snmp_port || 161;
            document.getElementById('snmp-version').value = device.snmp_version || '2c';

            // Load TCP port
            document.getElementById('tcp-port').value = device.tcp_port || 80;

            // Load DNS query domain
            document.getElementById('dns-query-domain').value = device.dns_query_domain || 'google.com';

            // Load expected status code
            document.getElementById('expected-status-code').value = device.expected_status_code || 200;

            // Load location type
            document.getElementById('device-location-type').value = device.location_type || 'on-premise';

            updateIPFieldLabel();
            document.getElementById('device-modal').classList.add('active');
        }
    } catch (error) {
        console.error('Error loading device:', error);
        alert('Error loading device details.');
    }
}

// Save device (add or update)
async function saveDevice(event) {
    event.preventDefault();

    const monitorType = document.getElementById('monitor-type').value;

    const deviceData = {
        name: document.getElementById('device-name').value,
        ip_address: document.getElementById('device-ip').value,
        device_type: document.getElementById('device-type').value,
        location: document.getElementById('device-location').value,
        location_type: document.getElementById('device-location-type').value,
        monitor_type: monitorType,
        expected_status_code: 200
    };

    // Add SNMP settings if SNMP monitor type is selected
    if (monitorType === 'snmp') {
        deviceData.snmp_community = document.getElementById('snmp-community').value || 'public';
        deviceData.snmp_port = parseInt(document.getElementById('snmp-port').value) || 161;
        deviceData.snmp_version = document.getElementById('snmp-version').value || '2c';
    }

    // Add TCP port if TCP monitor type is selected
    if (monitorType === 'tcp') {
        deviceData.tcp_port = parseInt(document.getElementById('tcp-port').value) || 80;
    }

    // Add DNS query domain if DNS monitor type is selected
    if (monitorType === 'dns') {
        deviceData.dns_query_domain = document.getElementById('dns-query-domain').value || 'google.com';
    }

    // Add expected status code if HTTP monitor type is selected
    if (monitorType === 'http') {
        deviceData.expected_status_code = parseInt(document.getElementById('expected-status-code').value) || 200;
    }

    try {
        let response;
        if (editingDeviceId) {
            // Update existing device
            response = await fetch(`/api/devices/${editingDeviceId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(deviceData)
            });
        } else {
            // Add new device
            response = await fetch('/api/devices', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(deviceData)
            });
        }

        const result = await response.json();

        if (result.success || response.ok) {
            closeDeviceModal();
            loadDevices();
            alert(editingDeviceId ? 'Device updated successfully!' : 'Device added successfully!');
        } else {
            alert('Error: ' + (result.error || 'Failed to save device'));
        }
    } catch (error) {
        console.error('Error saving device:', error);
        alert('Error saving device. Please try again.');
    }
}

// Delete device
async function deleteDevice(deviceId) {
    if (!confirm('Are you sure you want to delete this device? This action cannot be undone.')) {
        return;
    }

    try {
        const response = await fetch(`/api/devices/${deviceId}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            loadDevices();
            alert('Device deleted successfully!');
        } else {
            alert('Error deleting device.');
        }
    } catch (error) {
        console.error('Error deleting device:', error);
        alert('Error deleting device. Please try again.');
    }
}

// Check device now
async function checkDeviceNow(deviceId) {
    try {
        const response = await fetch(`/api/check/${deviceId}`, {
            method: 'POST'
        });

        const result = await response.json();

        if (result) {
            alert(`Device checked!\nStatus: ${result.status}\nResponse Time: ${result.response_time !== null && result.response_time !== undefined ? result.response_time : 'N/A'} ms`);
            loadDevices();
        }
    } catch (error) {
        console.error('Error checking device:', error);
        alert('Error checking device. Please try again.');
    }
}

// Setup Socket.IO listeners
function setupSocketListeners() {
    socket.on('connect', () => {
        console.log('Connected to server');
    });

    socket.on('status_update', (data) => {
        console.log('Status update:', data);

        // Update graph in real-time if modal is open
        if (currentGraphDeviceId === data.id) {
            addGraphDataPoint(data.id, data.response_time, data.last_check);
        }

        // Update the device in allDevices array
        const deviceIndex = allDevices.findIndex(d => d.id === data.id);
        if (deviceIndex !== -1) {
            allDevices[deviceIndex].status = data.status;
            allDevices[deviceIndex].response_time = data.response_time;
            allDevices[deviceIndex].last_check = data.last_check;
        }

        filterDevices(); // Re-render table with updated status
    });

    socket.on('device_deleted', (data) => {
        console.log('Device deleted:', data);
        loadDevices();
    });
}

// Close modal when clicking outside
document.addEventListener('click', (event) => {
    const modal = document.getElementById('device-modal');
    if (event.target === modal) {
        closeDeviceModal();
    }
    const snmpModal = document.getElementById('snmp-modal');
    if (event.target === snmpModal) {
        closeSnmpModal();
    }
});

// Current device ID for SNMP modal
let currentSnmpDeviceId = null;

// Show SNMP Details
async function showSnmpDetails(deviceId) {
    try {
        currentSnmpDeviceId = deviceId;
        const response = await fetch('/api/devices');
        const devices = await response.json();
        const device = devices.find(d => d.id === deviceId);

        if (device) {
            const modal = document.getElementById('snmp-modal');
            document.getElementById('snmp-device-name').textContent = device.name;
            document.getElementById('snmp-sysname').textContent = device.snmp_sysname || 'N/A';
            document.getElementById('snmp-sysdescr').textContent = device.snmp_sysdescr || 'N/A';
            document.getElementById('snmp-uptime').textContent = device.snmp_uptime || 'N/A';
            document.getElementById('snmp-syslocation').textContent = device.snmp_syslocation || 'Not configured';
            document.getElementById('snmp-response-time').textContent = device.response_time !== null && device.response_time !== undefined ? device.response_time + ' ms' : 'N/A';

            // Reset interfaces container
            document.getElementById('interfaces-container').innerHTML = `
                <p style="color: var(--text-muted); text-align: center; padding: 1rem;">
                    Click "Load Interfaces" to fetch interface data
                </p>
            `;

            modal.classList.add('active');
        }
    } catch (error) {
        console.error('Error loading SNMP details:', error);
        alert('Error loading SNMP details.');
    }
}

// Close SNMP modal
function closeSnmpModal() {
    document.getElementById('snmp-modal').classList.remove('active');
    currentSnmpDeviceId = null;
}

// ============================================================================
// SSL Certificate Modal Functions
// ============================================================================

// Show SSL Certificate Details
async function showSslDetails(deviceId) {
    try {
        const response = await fetch('/api/devices');
        const devices = await response.json();
        const device = devices.find(d => d.id === deviceId);

        if (device) {
            const modal = document.getElementById('ssl-modal');
            document.getElementById('ssl-device-name').textContent = device.name;

            // Format expiry date
            if (device.ssl_expiry_date) {
                const expiryDate = new Date(device.ssl_expiry_date);
                document.getElementById('ssl-expiry-date').textContent = expiryDate.toLocaleDateString('th-TH', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                });
            } else {
                document.getElementById('ssl-expiry-date').textContent = 'N/A';
            }

            // Days left with color
            const daysLeftEl = document.getElementById('ssl-days-left');
            if (device.ssl_days_left !== null && device.ssl_days_left !== undefined) {
                daysLeftEl.textContent = device.ssl_days_left + ' days';
                if (device.ssl_days_left <= 0) {
                    daysLeftEl.style.color = 'var(--danger)';
                } else if (device.ssl_days_left <= 30) {
                    daysLeftEl.style.color = 'var(--warning)';
                } else {
                    daysLeftEl.style.color = 'var(--success)';
                }
            } else {
                daysLeftEl.textContent = 'N/A';
                daysLeftEl.style.color = 'var(--text-muted)';
            }

            document.getElementById('ssl-issuer').textContent = device.ssl_issuer || 'N/A';

            // Status badge
            const statusBadge = document.getElementById('ssl-status-badge');
            const sslStatus = device.ssl_status || 'unknown';
            statusBadge.textContent = sslStatus;
            statusBadge.className = 'status-badge';
            if (sslStatus === 'ok') {
                statusBadge.classList.add('status-up');
            } else if (sslStatus === 'warning') {
                statusBadge.classList.add('status-slow');
            } else if (sslStatus === 'expired' || sslStatus === 'error') {
                statusBadge.classList.add('status-down');
            } else {
                statusBadge.classList.add('status-unknown');
            }

            modal.classList.add('active');
        }
    } catch (error) {
        console.error('Error loading SSL details:', error);
        alert('Error loading SSL certificate details.');
    }
}

// Close SSL modal
function closeSslModal() {
    document.getElementById('ssl-modal').classList.remove('active');
}

// Handle SSL modal click outside
document.addEventListener('click', (event) => {
    const sslModal = document.getElementById('ssl-modal');
    if (event.target === sslModal) {
        closeSslModal();
    }
});

// Load interface data
async function loadInterfaces() {
    if (!currentSnmpDeviceId) return;

    const container = document.getElementById('interfaces-container');
    const btn = document.getElementById('load-interfaces-btn');

    container.innerHTML = '<p style="text-align: center; padding: 1rem;">⏳ Loading interfaces...</p>';
    btn.disabled = true;
    btn.textContent = '⏳ Loading...';

    try {
        const response = await fetch(`/api/snmp/${currentSnmpDeviceId}/interfaces`);
        const data = await response.json();

        if (data.error) {
            container.innerHTML = `<p style="color: var(--danger); text-align: center; padding: 1rem;">❌ ${data.error}</p>`;
            return;
        }

        if (!data.interfaces || data.interfaces.length === 0) {
            container.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 1rem;">No interfaces found</p>';
            return;
        }

        // Build interfaces table
        let html = `
            <table style="width: 100%; font-size: 0.85rem;">
                <thead>
                    <tr style="background: var(--glass-bg);">
                        <th style="padding: 0.5rem; text-align: left;">#</th>
                        <th style="padding: 0.5rem; text-align: left;">Interface</th>
                        <th style="padding: 0.5rem; text-align: center;">Speed</th>
                        <th style="padding: 0.5rem; text-align: center;">Status</th>
                        <th style="padding: 0.5rem; text-align: right;">Bytes In</th>
                        <th style="padding: 0.5rem; text-align: right;">Bytes Out</th>
                    </tr>
                </thead>
                <tbody>
        `;

        data.interfaces.forEach(iface => {
            const statusColor = iface.oper_status === 'up' ? 'var(--success)' : 'var(--danger)';
            const statusIcon = iface.oper_status === 'up' ? '🟢' : '🔴';

            html += `
                <tr style="border-bottom: 1px solid var(--glass-border);">
                    <td style="padding: 0.5rem;">${iface.index}</td>
                    <td style="padding: 0.5rem;"><code>${iface.name}</code></td>
                    <td style="padding: 0.5rem; text-align: center;">${iface.speed}</td>
                    <td style="padding: 0.5rem; text-align: center;">
                        ${statusIcon} ${iface.oper_status.toUpperCase()}
                    </td>
                    <td style="padding: 0.5rem; text-align: right;">${formatBytes(iface.bytes_in)}</td>
                    <td style="padding: 0.5rem; text-align: right;">${formatBytes(iface.bytes_out)}</td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;

    } catch (error) {
        console.error('Error loading interfaces:', error);
        container.innerHTML = '<p style="color: var(--danger); text-align: center; padding: 1rem;">❌ Error loading interfaces</p>';
    } finally {
        btn.disabled = false;
        btn.textContent = '🔄 Refresh';
    }
}

// Format bytes to human readable
function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// ============================================================================
// Real-time Graph Functions
// ============================================================================

// Current graph device ID and chart instance
let currentGraphDeviceId = null;
let responseTimeChart = null;
let graphHistoryData = [];
const MAX_GRAPH_POINTS = 50;
const SLOW_THRESHOLD = 500; // ms

// Show device graph modal
async function showDeviceGraph(deviceId) {
    currentGraphDeviceId = deviceId;

    // Find device info
    const device = allDevices.find(d => d.id === deviceId);
    if (!device) {
        alert('Device not found');
        return;
    }

    // Update modal info
    document.getElementById('graph-device-name').textContent = device.name;
    document.getElementById('graph-device-ip').textContent = device.ip_address;
    document.getElementById('graph-device-type').textContent = device.device_type || 'N/A';
    updateGraphCurrentStatus(device);

    // Show modal
    document.getElementById('graph-modal').classList.add('active');

    // Load history and create chart
    await loadGraphHistory(deviceId);
    createResponseTimeChart();
}

// Update current status display
function updateGraphCurrentStatus(device) {
    const responseEl = document.getElementById('graph-current-response');
    const badgeEl = document.getElementById('graph-status-badge');

    responseEl.textContent = device.response_time !== null && device.response_time !== undefined ? device.response_time + ' ms' : 'N/A';

    // Set color based on response time
    if (device.response_time !== null && device.response_time !== undefined) {
        if (device.response_time > SLOW_THRESHOLD) {
            responseEl.style.color = 'var(--warning)';
        } else {
            responseEl.style.color = 'var(--success)';
        }
    } else {
        responseEl.style.color = 'var(--danger)';
    }

    badgeEl.className = `status-badge status-${device.status || 'unknown'}`;
    badgeEl.textContent = device.status || 'unknown';
}

// Load graph history data
async function loadGraphHistory(deviceId) {
    try {
        const response = await fetch(`/api/devices/${deviceId}/history?limit=${MAX_GRAPH_POINTS}`);
        const history = await response.json();

        // Reverse to get chronological order (oldest first)
        graphHistoryData = history.reverse().map(h => ({
            time: new Date(h.checked_at),
            value: h.response_time
        }));

        updateGraphStatistics();
    } catch (error) {
        console.error('Error loading graph history:', error);
        graphHistoryData = [];
    }
}

// Create or update the response time chart
function createResponseTimeChart() {
    const ctx = document.getElementById('response-time-chart').getContext('2d');

    // Destroy existing chart if exists
    if (responseTimeChart) {
        responseTimeChart.destroy();
    }

    // Prepare data
    const labels = graphHistoryData.map(d => formatGraphTime(d.time));
    const values = graphHistoryData.map(d => d.value);

    // Create chart
    responseTimeChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Response Time (ms)',
                data: values,
                borderColor: 'rgba(96, 165, 250, 1)',
                backgroundColor: 'rgba(96, 165, 250, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointHoverRadius: 6,
                pointBackgroundColor: function (context) {
                    const value = context.raw;
                    if (value === null) return 'rgba(239, 68, 68, 1)';
                    if (value > SLOW_THRESHOLD) return 'rgba(251, 191, 36, 1)';
                    return 'rgba(34, 197, 94, 1)';
                },
                pointBorderColor: 'white',
                pointBorderWidth: 1
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
                    callbacks: {
                        label: function (context) {
                            const value = context.raw;
                            if (value === null) return 'DOWN';
                            return `${value} ms`;
                        }
                    }
                },
                annotation: {
                    annotations: {
                        slowLine: {
                            type: 'line',
                            yMin: SLOW_THRESHOLD,
                            yMax: SLOW_THRESHOLD,
                            borderColor: 'rgba(251, 191, 36, 0.7)',
                            borderWidth: 2,
                            borderDash: [5, 5],
                            label: {
                                display: true,
                                content: 'Slow Threshold',
                                position: 'end'
                            }
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Time',
                        color: 'rgba(255, 255, 255, 0.7)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)',
                        maxRotation: 45,
                        minRotation: 45,
                        maxTicksLimit: 10
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                },
                y: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Response Time (ms)',
                        color: 'rgba(255, 255, 255, 0.7)'
                    },
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    min: 0
                }
            },
            animation: {
                duration: 300
            }
        }
    });
}

// Format time for graph labels
function formatGraphTime(date) {
    return date.toLocaleTimeString('th-TH', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Update graph statistics
function updateGraphStatistics() {
    const validValues = graphHistoryData
        .filter(d => d.value !== null)
        .map(d => d.value);

    if (validValues.length > 0) {
        const avg = validValues.reduce((a, b) => a + b, 0) / validValues.length;
        const min = Math.min(...validValues);
        const max = Math.max(...validValues);

        document.getElementById('graph-avg').textContent = avg.toFixed(2) + ' ms';
        document.getElementById('graph-min').textContent = min.toFixed(2) + ' ms';
        document.getElementById('graph-max').textContent = max.toFixed(2) + ' ms';
    } else {
        document.getElementById('graph-avg').textContent = 'N/A';
        document.getElementById('graph-min').textContent = 'N/A';
        document.getElementById('graph-max').textContent = 'N/A';
    }

    document.getElementById('graph-count').textContent = graphHistoryData.length;
}

// Add new data point to graph (called from WebSocket)
function addGraphDataPoint(deviceId, responseTime, timestamp) {
    if (currentGraphDeviceId !== deviceId || !responseTimeChart) return;

    // Add new data point
    graphHistoryData.push({
        time: new Date(timestamp),
        value: responseTime
    });

    // Keep only last MAX_GRAPH_POINTS
    if (graphHistoryData.length > MAX_GRAPH_POINTS) {
        graphHistoryData.shift();
    }

    // Update chart
    responseTimeChart.data.labels = graphHistoryData.map(d => formatGraphTime(d.time));
    responseTimeChart.data.datasets[0].data = graphHistoryData.map(d => d.value);
    responseTimeChart.update('none');

    // Update statistics
    updateGraphStatistics();

    // Update current status
    const device = allDevices.find(d => d.id === deviceId);
    if (device) {
        device.response_time = responseTime;
        updateGraphCurrentStatus(device);
    }
}

// Refresh graph data
async function refreshGraphData() {
    if (!currentGraphDeviceId) return;

    await loadGraphHistory(currentGraphDeviceId);
    createResponseTimeChart();

    // Also update current status
    const device = allDevices.find(d => d.id === currentGraphDeviceId);
    if (device) {
        updateGraphCurrentStatus(device);
    }
}

// Close graph modal
function closeGraphModal() {
    document.getElementById('graph-modal').classList.remove('active');
    currentGraphDeviceId = null;

    // Destroy chart to free memory
    if (responseTimeChart) {
        responseTimeChart.destroy();
        responseTimeChart = null;
    }
}

// Handle graph modal click outside
document.addEventListener('click', (event) => {
    const graphModal = document.getElementById('graph-modal');
    if (event.target === graphModal) {
        closeGraphModal();
    }
});

// ============================================================================
// CSV Import/Export Functions
// ============================================================================

// Store parsed CSV data for import
let csvDataToImport = [];

// Export devices to CSV
function exportDevices() {
    window.location.href = '/api/devices/export/csv';
}

// Show import modal
function showImportModal() {
    document.getElementById('import-modal').classList.add('active');
    // Reset modal state
    document.getElementById('csv-file').value = '';
    document.getElementById('csv-preview-section').style.display = 'none';
    document.getElementById('import-result').style.display = 'none';
    document.getElementById('import-btn').disabled = true;
    csvDataToImport = [];
}

// Close import modal
function closeImportModal() {
    document.getElementById('import-modal').classList.remove('active');
    csvDataToImport = [];
}

// Preview CSV file
function previewCSV() {
    const fileInput = document.getElementById('csv-file');
    const file = fileInput.files[0];

    if (!file) {
        document.getElementById('csv-preview-section').style.display = 'none';
        document.getElementById('import-btn').disabled = true;
        return;
    }

    const reader = new FileReader();
    reader.onload = function (e) {
        const content = e.target.result;
        const lines = content.split('\n').map(line => line.trim()).filter(line => line);

        if (lines.length < 2) {
            alert('CSV file must have a header row and at least one data row.');
            return;
        }

        // Parse header
        const headers = parseCSVLine(lines[0]);

        // Check required columns
        if (!headers.includes('name') || !headers.includes('ip_address')) {
            alert('CSV must contain "name" and "ip_address" columns.');
            return;
        }

        // Parse data rows
        csvDataToImport = [];
        for (let i = 1; i < lines.length; i++) {
            const values = parseCSVLine(lines[i]);
            const row = {};
            headers.forEach((header, idx) => {
                row[header] = values[idx] || '';
            });
            csvDataToImport.push(row);
        }

        // Build preview table
        const previewSection = document.getElementById('csv-preview-section');
        const previewTable = document.getElementById('csv-preview-table');
        const thead = previewTable.querySelector('thead tr');
        const tbody = previewTable.querySelector('tbody');

        // Clear previous content
        thead.innerHTML = '';
        tbody.innerHTML = '';

        // Add header cells (only important columns)
        const displayCols = ['name', 'ip_address', 'device_type', 'monitor_type', 'location'];
        displayCols.forEach(col => {
            if (headers.includes(col)) {
                const th = document.createElement('th');
                th.textContent = col;
                th.style.padding = '0.5rem';
                thead.appendChild(th);
            }
        });

        // Add data rows (max 5 for preview)
        const previewData = csvDataToImport.slice(0, 5);
        previewData.forEach(row => {
            const tr = document.createElement('tr');
            displayCols.forEach(col => {
                if (headers.includes(col)) {
                    const td = document.createElement('td');
                    td.textContent = row[col] || '-';
                    td.style.padding = '0.5rem';
                    tr.appendChild(td);
                }
            });
            tbody.appendChild(tr);
        });

        // Show preview and update count
        document.getElementById('csv-row-count').textContent = csvDataToImport.length;
        previewSection.style.display = 'block';
        document.getElementById('import-btn').disabled = false;
    };

    reader.readAsText(file);
}

// Parse a single CSV line (handles quoted values)
function parseCSVLine(line) {
    const result = [];
    let current = '';
    let inQuotes = false;

    for (let i = 0; i < line.length; i++) {
        const char = line[i];

        if (char === '"') {
            inQuotes = !inQuotes;
        } else if (char === ',' && !inQuotes) {
            result.push(current.trim());
            current = '';
        } else {
            current += char;
        }
    }
    result.push(current.trim());

    return result;
}

// Import devices from CSV
async function importCSV() {
    const fileInput = document.getElementById('csv-file');
    const file = fileInput.files[0];

    if (!file) {
        alert('Please select a CSV file.');
        return;
    }

    const importBtn = document.getElementById('import-btn');
    const resultDiv = document.getElementById('import-result');

    importBtn.disabled = true;
    importBtn.textContent = '⏳ Importing...';
    resultDiv.style.display = 'none';

    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/api/devices/import/csv', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        // Show result
        resultDiv.style.display = 'block';
        if (result.success && result.imported > 0) {
            resultDiv.className = 'alert alert-success';
            resultDiv.innerHTML = `
                ✅ Import completed!<br>
                <strong>${result.imported}</strong> devices imported successfully.
                ${result.failed > 0 ? `<br>⚠️ ${result.failed} failed.` : ''}
            `;

            // Reload devices list
            loadDevices();

            // Close modal after 2 seconds
            setTimeout(() => {
                closeImportModal();
            }, 2000);
        } else if (result.failed > 0) {
            resultDiv.className = 'alert alert-warning';
            let html = `⚠️ Import completed with errors.<br>
                <strong>${result.imported}</strong> imported, <strong>${result.failed}</strong> failed.`;
            if (result.errors && result.errors.length > 0) {
                html += '<br><small>' + result.errors.slice(0, 5).join('<br>') + '</small>';
            }
            resultDiv.innerHTML = html;
            loadDevices();
        } else {
            resultDiv.className = 'alert alert-danger';
            resultDiv.innerHTML = `❌ Import failed: ${result.error || 'Unknown error'}`;
        }
    } catch (error) {
        console.error('Error importing CSV:', error);
        resultDiv.style.display = 'block';
        resultDiv.className = 'alert alert-danger';
        resultDiv.innerHTML = `❌ Error: ${error.message}`;
    } finally {
        importBtn.disabled = false;
        importBtn.textContent = '📤 Import Devices';
    }
}

// Download CSV template
function downloadTemplate() {
    const headers = [
        'name', 'ip_address', 'device_type', 'location', 'location_type',
        'monitor_type', 'snmp_community', 'snmp_port', 'snmp_version',
        'tcp_port', 'dns_query_domain', 'expected_status_code'
    ];

    const exampleRows = [
        ['Main Router', '192.168.1.1', 'router', 'Server Room', 'on-premise', 'ping', '', '', '', '', '', ''],
        ['Web Server', '192.168.1.10', 'server', 'Data Center', 'on-premise', 'tcp', '', '', '', '443', '', ''],
        ['DNS Server', '8.8.8.8', 'dns', 'Google', 'internet', 'dns', '', '', '', '', 'example.com', ''],
        ['Company Website', 'https://example.com', 'website', 'Cloud', 'cloud', 'http', '', '', '', '', '', '200']
    ];

    let csv = headers.join(',') + '\n';
    exampleRows.forEach(row => {
        csv += row.join(',') + '\n';
    });

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'devices_template.csv';
    a.click();
    window.URL.revokeObjectURL(url);
}

// Handle import modal click outside
document.addEventListener('click', (event) => {
    const importModal = document.getElementById('import-modal');
    if (event.target === importModal) {
        closeImportModal();
    }
});
