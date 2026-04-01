// Devices JavaScript
// Handles device management (CRUD operations)

// Initialize Socket.IO connection
const socket = io();

// Current editing device ID
let editingDeviceId = null;

// Store all devices for filtering
let allDevices = [];

// Current sorting state
let currentSortColumn = 'name';
let currentSortDirection = 'asc';

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

// Device type metadata for better naming and icons
const deviceTypeMetadata = {
    'router': { name: 'Router', icon: '🌐' },
    'switch': { name: 'Switch', icon: '🔀' },
    'server': { name: 'Server', icon: '🖥️' },
    'firewall': { name: 'Firewall', icon: '🛡️' },
    'wireless': { name: 'Wireless', icon: '📶' },
    'website': { name: 'Website', icon: '🌐' },
    'dns': { name: 'DNS', icon: '🔍' },
    'vmware': { name: 'VMware Server', icon: '🖴' },
    'ippbx': { name: 'IP-PBX', icon: '☎️' },
    'cctv': { name: 'CCTV', icon: '📹' },
    'vpnrouter': { name: 'VPN Router Site', icon: '🔒' },
    'other': { name: 'Other', icon: '⚙️' }
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
        updateSortIcons(); // Show default sort icon
        filterDevices(); // Apply current filters and sorting
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
                <td colspan="10" class="text-center" style="padding: 2rem; color: var(--text-muted);">
                    No devices found. Click "Add Device" to get started.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = devices.map(device => {
        const locTypeIcon = locationTypeIcons[device.location_type] || '🏠';
        const locTypeLabel = locationTypeLabels[device.location_type] || 'On-Premise';
        const isAgentMonitored = ['ssh', 'winrm', 'wmi'].includes(device.monitor_type);
        
        return `
        <tr class="fade-in">
            <td>
                <strong>${device.name}</strong>
                ${device.parent_device_id ? `<br><small style="color: var(--text-muted);">🔗 ${getParentName(device.parent_device_id)}</small>` : ''}
            </td>
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
            <td style="text-align: center;">
                <label class="switch">
                    <input type="checkbox" ${device.is_enabled ? 'checked' : ''} onchange="toggleDevice(${device.id}, this)">
                    <span class="slider"></span>
                </label>
            </td>
            <td>
                <div style="display: flex; gap: 0.25rem;">
                    <button class="btn btn-sm" style="background: var(--success); color: white; padding: 0.25rem 0.5rem;" onclick="showDeviceGraph(${device.id})" title="Response Time Graph">
                        📈
                    </button>
                    ${isAgentMonitored ? `
                    <button class="btn btn-sm" style="background: var(--primary); color: white; padding: 0.25rem 0.5rem;" onclick="showPerformanceMetrics(${device.id})" title="Performance Metrics">
                        📊
                    </button>
                    ${['ssh', 'winrm'].includes(device.monitor_type) ? `
                    <button class="btn btn-sm" style="background: var(--info, #0ea5e9); color: white; padding: 0.25rem 0.5rem;" onclick="showActivePorts(${device.id})" title="Active Ports">
                        🔌
                    </button>
                    ` : ''}
                    ` : ''}
                    ${device.monitor_type === 'snmp' ? `
                    <button class="btn btn-sm" style="background: var(--primary); color: white; padding: 0.25rem 0.5rem;" onclick="showSnmpDetails(${device.id})" title="SNMP Details">
                        🖥️
                    </button>
                    ` : ''}
                    ${device.monitor_type === 'http' && device.ip_address.startsWith('https') ? `
                    <button class="btn btn-sm" style="background: var(--warning); color: white; padding: 0.25rem 0.5rem;" onclick="showSslDetails(${device.id})" title="SSL Certificate">
                        🔒
                    </button>
                    ` : ''}
                    <button class="btn btn-sm" style="background: var(--primary); color: white; padding: 0.25rem 0.5rem;" onclick="openAssignmentModal(${device.id}, '${device.name}')" title="Notification Recipients">
                        🔔
                    </button>
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
    // Get unique types from data AND include all predefined types
    const dataTypes = getUniqueValues(devices, 'device_type');
    const predefinedTypes = Object.keys(deviceTypeMetadata);
    const allPossibleTypes = [...new Set([...predefinedTypes, ...dataTypes])].sort();

    const locations = getUniqueValues(devices, 'location');

    // Populate Type filter
    const typeFilter = document.getElementById('filter-type');
    const currentType = typeFilter.value;
    typeFilter.innerHTML = '<option value="">All Types</option>';

    allPossibleTypes.forEach(type => {
        if (type) {
            const meta = deviceTypeMetadata[type];
            const option = document.createElement('option');
            option.value = type;
            if (meta) {
                option.textContent = `${meta.name}`;
            } else {
                option.textContent = type.charAt(0).toUpperCase() + type.slice(1);
            }
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

// Handle header click for sorting
function handleSort(column) {
    if (currentSortColumn === column) {
        // Cycle: asc -> desc -> none -> asc
        if (currentSortDirection === 'asc') {
            currentSortDirection = 'desc';
        } else if (currentSortDirection === 'desc') {
            currentSortDirection = 'none';
        } else {
            currentSortDirection = 'asc';
        }
    } else {
        currentSortColumn = column;
        currentSortDirection = 'asc';
    }

    updateSortIcons();
    filterDevices();
}

// Update sort icons in the header
function updateSortIcons() {
    const columns = ['name', 'ip_address', 'device_type', 'location', 'location_type', 'status', 'response_time', 'last_check'];
    columns.forEach(col => {
        const icon = document.getElementById(`sort-icon-${col}`);
        if (!icon) return;

        if (col === currentSortColumn && currentSortDirection !== 'none') {
            icon.innerHTML = currentSortDirection === 'asc' ? ' ↑' : ' ↓';
            icon.classList.add('active');
        } else {
            icon.innerHTML = '';
            icon.classList.remove('active');
        }
    });
}

// Sort devices array
function sortDevices(devices) {
    if (currentSortDirection === 'none' || !currentSortColumn) {
        return devices;
    }

    const direction = currentSortDirection === 'asc' ? 1 : -1;

    return [...devices].sort((a, b) => {
        let valA = a[currentSortColumn];
        let valB = b[currentSortColumn];

        // Handle null/undefined
        if (valA === null || valA === undefined) valA = '';
        if (valB === null || valB === undefined) valB = '';

        // Special handling for specific columns
        if (currentSortColumn === 'response_time') {
            const numA = parseFloat(valA) || 0;
            const numB = parseFloat(valB) || 0;
            return (numA - numB) * direction;
        }

        if (currentSortColumn === 'last_check') {
            const dateA = valA ? new Date(valA) : new Date(0);
            const dateB = valB ? new Date(valB) : new Date(0);
            return (dateA - dateB) * direction;
        }

        // Default string comparison (case-insensitive)
        valA = String(valA).toLowerCase();
        valB = String(valB).toLowerCase();

        if (valA < valB) return -1 * direction;
        if (valA > valB) return 1 * direction;
        return 0;
    });
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

    const sortedDevices = sortDevices(filteredDevices);
    updateDevicesTable(sortedDevices);
    updateFilteredCount(sortedDevices.length, allDevices.length);
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
    // Reset SNMP v3 fields
    document.getElementById('snmp-v3-username').value = '';
    document.getElementById('snmp-v3-auth-protocol').value = 'SHA';
    document.getElementById('snmp-v3-auth-password').value = '';
    document.getElementById('snmp-v3-priv-protocol').value = 'AES128';
    document.getElementById('snmp-v3-priv-password').value = '';
    document.getElementById('snmp-v3-settings').style.display = 'none';
    // Reset TCP port to default
    document.getElementById('tcp-port').value = '80';
    // Reset DNS query domain to default
    document.getElementById('dns-query-domain').value = 'google.com';
    // Reset expected status code to default
    document.getElementById('expected-status-code').value = '200';
    // Reset expected ports
    document.getElementById('expected-ports').value = '';
    // Reset location type to default
    document.getElementById('device-location-type').value = 'on-premise';
    // Reset coordinate fields
    document.getElementById('device-latitude').value = '';
    document.getElementById('device-longitude').value = '';
    document.getElementById('device-enabled').checked = true;
    if (miniMapMarker && miniMap) {
        miniMap.removeLayer(miniMapMarker);
        miniMapMarker = null;
    }
    
    // Populate parent device dropdown
    populateParentDeviceDropdown(null);
    
    updateIPFieldLabel();
    document.getElementById('device-modal').classList.add('active');
    initMinimap();
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
    const sshSettings = document.getElementById('ssh-settings');
    const winrmSettings = document.getElementById('winrm-settings');
    const expectedPortsSettings = document.getElementById('expected-ports-settings');

    // Hide all optional settings first
    snmpSettings.style.display = 'none';
    tcpSettings.style.display = 'none';
    dnsSettings.style.display = 'none';
    httpSettings.style.display = 'none';
    sshSettings.style.display = 'none';
    winrmSettings.style.display = 'none';
    if (expectedPortsSettings) expectedPortsSettings.style.display = 'none';

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
        updateSnmpVersionFields();
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
    } else if (monitorType === 'ssh') {
        ipLabel.textContent = 'IP Address *';
        ipInput.placeholder = 'e.g., 192.168.1.1';
        ipInput.removeAttribute('pattern');
        ipHint.textContent = 'Enter IP address for SSH monitoring';
        sshSettings.style.display = 'block';
        if (expectedPortsSettings) expectedPortsSettings.style.display = 'block';
    } else if (monitorType === 'winrm') {
        ipLabel.textContent = 'IP Address *';
        ipInput.placeholder = 'e.g., 192.168.1.1';
        ipInput.removeAttribute('pattern');
        ipHint.textContent = 'Enter IP address for WinRM monitoring';
        winrmSettings.style.display = 'block';
        if (expectedPortsSettings) expectedPortsSettings.style.display = 'block';
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

// Toggle SNMP v3 fields based on selected version
function updateSnmpVersionFields() {
    const snmpVersion = document.getElementById('snmp-version').value;
    const v3Settings = document.getElementById('snmp-v3-settings');
    const communityField = document.getElementById('snmp-community').closest('.form-group');

    if (snmpVersion === '3') {
        v3Settings.style.display = 'block';
        if (communityField) communityField.style.display = 'none';
    } else {
        v3Settings.style.display = 'none';
        if (communityField) communityField.style.display = 'block';
    }
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

            // Load SNMP v3 settings
            document.getElementById('snmp-v3-username').value = device.snmp_v3_username || '';
            document.getElementById('snmp-v3-auth-protocol').value = device.snmp_v3_auth_protocol || 'SHA';
            document.getElementById('snmp-v3-auth-password').value = device.snmp_v3_auth_password || '';
            document.getElementById('snmp-v3-priv-protocol').value = device.snmp_v3_priv_protocol || 'AES128';
            document.getElementById('snmp-v3-priv-password').value = device.snmp_v3_priv_password || '';

            // Load TCP port
            document.getElementById('tcp-port').value = device.tcp_port || 80;

            // Load DNS query domain
            document.getElementById('dns-query-domain').value = device.dns_query_domain || 'google.com';

            // Load expected status code
            document.getElementById('expected-status-code').value = device.expected_status_code || 200;

            // Load location type
            document.getElementById('device-location-type').value = device.location_type || 'on-premise';

            // Load coordinates
            document.getElementById('device-latitude').value = device.latitude || '';
            document.getElementById('device-longitude').value = device.longitude || '';
            document.getElementById('device-enabled').checked = !!device.is_enabled;

            // Load SSH settings
            document.getElementById('ssh-username').value = device.ssh_username || '';
            document.getElementById('ssh-password').value = device.ssh_password || '';
            document.getElementById('ssh-port').value = device.ssh_port || 22;

            // Load WinRM (WMI) settings
            document.getElementById('winrm-username').value = device.wmi_username || '';
            document.getElementById('winrm-password').value = device.wmi_password || '';

            // Load Expected Ports
            if (document.getElementById('expected-ports')) {
                document.getElementById('expected-ports').value = device.expected_ports || '';
            }

            // Load parent device
            populateParentDeviceDropdown(deviceId);
            document.getElementById('parent-device').value = device.parent_device_id || '';

            updateIPFieldLabel();
            document.getElementById('device-modal').classList.add('active');
            
            initMinimap();
            if (device.latitude && device.longitude) {
                setMarker(device.latitude, device.longitude);
                setTimeout(() => miniMap.setView([device.latitude, device.longitude], 12), 250);
            } else {
                if (miniMapMarker && miniMap) {
                    miniMap.removeLayer(miniMapMarker);
                    miniMapMarker = null;
                }
                setTimeout(() => miniMap.setView([13.7563, 100.5018], 5), 250);
            }
        }
    } catch (error) {
        console.error('Error loading device:', error);
        alert('Error loading device details.');
    }
}

// Helper to safely get element value
function getElementValue(id, defaultValue = '') {
    const element = document.getElementById(id);
    if (!element) {
        console.warn(`Element with ID '${id}' not found. Using default value: '${defaultValue}'`);
        return defaultValue;
    }
    return element.value;
}

// Save device (add or update)
async function saveDevice(event) {
    event.preventDefault();
    console.log('saveDevice called');

    const saveBtn = event.target.querySelector('button[type="submit"]');
    const originalBtnText = saveBtn.textContent;

    // Disable button and show loading state
    saveBtn.disabled = true;
    saveBtn.textContent = '⏳ Saving...';

    try {
        const monitorType = getElementValue('monitor-type', 'ping');
        console.log('Monitor Type:', monitorType);

        const deviceData = {
            name: getElementValue('device-name'),
            ip_address: getElementValue('device-ip'),
            device_type: getElementValue('device-type', 'other'),
            location: getElementValue('device-location'),
            location_type: getElementValue('device-location-type', 'on-premise'),
            monitor_type: monitorType,
            expected_status_code: 200,
            is_enabled: document.getElementById('device-enabled').checked,
            parent_device_id: getElementValue('parent-device') ? parseInt(getElementValue('parent-device')) : null
        };

        const latVal = getElementValue('device-latitude');
        const lngVal = getElementValue('device-longitude');
        if (latVal && !isNaN(parseFloat(latVal))) deviceData.latitude = parseFloat(latVal);
        else deviceData.latitude = null;
        if (lngVal && !isNaN(parseFloat(lngVal))) deviceData.longitude = parseFloat(lngVal);
        else deviceData.longitude = null;

        // Add SNMP settings if SNMP monitor type is selected
        if (monitorType === 'snmp') {
            deviceData.snmp_community = getElementValue('snmp-community', 'public');
            deviceData.snmp_port = parseInt(getElementValue('snmp-port', '161')) || 161;
            deviceData.snmp_version = getElementValue('snmp-version', '2c');

            // Add SNMP v3 settings if v3 is selected
            if (deviceData.snmp_version === '3') {
                deviceData.snmp_v3_username = getElementValue('snmp-v3-username', '');
                deviceData.snmp_v3_auth_protocol = getElementValue('snmp-v3-auth-protocol', 'SHA');
                deviceData.snmp_v3_auth_password = getElementValue('snmp-v3-auth-password', '');
                deviceData.snmp_v3_priv_protocol = getElementValue('snmp-v3-priv-protocol', 'AES128');
                deviceData.snmp_v3_priv_password = getElementValue('snmp-v3-priv-password', '');
            }
        }

        // Add TCP port if TCP monitor type is selected
        if (monitorType === 'tcp') {
            deviceData.tcp_port = parseInt(getElementValue('tcp-port', '80')) || 80;
        }

        // Add DNS query domain if DNS monitor type is selected
        if (monitorType === 'dns') {
            deviceData.dns_query_domain = getElementValue('dns-query-domain', 'google.com');
        }

        // Add expected status code if HTTP monitor type is selected
        if (monitorType === 'http') {
            deviceData.expected_status_code = parseInt(getElementValue('expected-status-code', '200')) || 200;
        }

        // Add SSH credentials if SSH monitor type is selected
        if (monitorType === 'ssh') {
            deviceData.ssh_username = getElementValue('ssh-username', '');
            deviceData.ssh_password = getElementValue('ssh-password', '');
            deviceData.ssh_port = parseInt(getElementValue('ssh-port', '22')) || 22;
            deviceData.expected_ports = getElementValue('expected-ports', '');
        }

        // Add WinRM (WMI) credentials if WinRM monitor type is selected
        if (monitorType === 'winrm') {
            deviceData.wmi_username = getElementValue('winrm-username', '');
            deviceData.wmi_password = getElementValue('winrm-password', '');
            deviceData.expected_ports = getElementValue('expected-ports', '');
        }

        console.log('Device Data to send:', deviceData);

        let response;
        if (editingDeviceId) {
            // Update existing device
            console.log('Updating device:', editingDeviceId);
            response = await fetch(`/api/devices/${editingDeviceId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(deviceData)
            });
        } else {
            // Add new device
            console.log('Adding new device');
            response = await fetch('/api/devices', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(deviceData)
            });
        }

        console.log('Response status:', response.status);
        const result = await response.json();
        console.log('Response result:', result);

        if (result.success || response.ok) {
            closeDeviceModal();
            loadDevices();
            alert(editingDeviceId ? 'Device updated successfully!' : 'Device added successfully!');
        } else {
            console.error('Server returned error:', result);
            alert('Error: ' + (result.error || 'Failed to save device'));
        }
    } catch (error) {
        console.error('Error saving device:', error);
        alert('Error saving device: ' + error.message);
    } finally {
        // Restore button state
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = originalBtnText;
        }
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

// Toggle device monitoring status
async function toggleDevice(deviceId, checkbox) {
    const originalChecked = !checkbox.checked;
    
    try {
        const response = await fetch(`/api/devices/${deviceId}/toggle`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Success - update local array to keep filters working
            const deviceIndex = allDevices.findIndex(d => d.id === deviceId);
            if (deviceIndex !== -1) {
                allDevices[deviceIndex].is_enabled = result.is_enabled;
                allDevices[deviceIndex].status = result.status;
                if (!result.is_enabled) {
                    allDevices[deviceIndex].response_time = null;
                }
            }
            // Re-render table to reflect status change (badges, etc.)
            filterDevices();
        } else {
            // Revert checkbox on failure
            checkbox.checked = originalChecked;
            alert('Error toggling device monitoring: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        // Revert checkbox on error
        checkbox.checked = originalChecked;
        console.error('Error toggling device:', error);
        alert('Error toggling device monitoring. Please try again.');
    }
}

// Setup Socket.IO listeners
function setupSocketListeners() {
    socket.on('connect', () => {
        console.log('Connected to server');
    });

    let debounceTimer;
    socket.on('status_update', (data) => {
        // Prevent console spam
        // console.log('Status update:', data);

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

        // Debounce table re-rendering
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            filterDevices(); // Re-render table with updated status
        }, 500);
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
    const portsModal = document.getElementById('ports-modal');
    if (event.target === portsModal) {
        closePortsModal();
    }
});

// Current device ID for Ports modal
let currentPortsDeviceId = null;
let currentPortsData = [];

// Show Active Ports
async function showActivePorts(deviceId) {
    const device = allDevices.find(d => d.id === deviceId);
    if (!device) return;

    currentPortsDeviceId = deviceId;
    document.getElementById('ports-device-name').textContent = device.name;
    document.getElementById('ports-search').value = '';
    
    // Show loading
    const tbody = document.getElementById('ports-table-body');
    tbody.innerHTML = `
        <tr>
            <td colspan="5" class="text-center" style="padding: 2rem; color: var(--text-muted);">
                ⏳ Fetching live ports... This may take a few seconds.
            </td>
        </tr>
    `;
    
    document.getElementById('ports-modal').classList.add('active');
    await loadPortsData();
}

// Close Ports modal
function closePortsModal() {
    document.getElementById('ports-modal').classList.remove('active');
    currentPortsDeviceId = null;
    currentPortsData = [];
}

// Fetch and load Ports Data
async function loadPortsData() {
    if (!currentPortsDeviceId) return;
    try {
        const response = await fetch(`/api/devices/${currentPortsDeviceId}/ports`);
        const data = await response.json();
        const tbody = document.getElementById('ports-table-body');
        
        if (data.success && data.ports) {
            currentPortsData = data.ports || [];
            if (currentPortsData.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="text-center" style="padding: 2rem; color: var(--text-muted);">
                            No active listening ports found.
                        </td>
                    </tr>
                `;
            } else {
                renderPortsTable(currentPortsData);
            }
        } else {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center" style="padding: 2rem; color: var(--danger);">
                        Error: ${data.error || 'Failed to fetch ports'}
                    </td>
                </tr>
            `;
        }
    } catch (error) {
        console.error('Error fetching active ports:', error);
        document.getElementById('ports-table-body').innerHTML = `
            <tr>
                <td colspan="5" class="text-center" style="padding: 2rem; color: var(--danger);">
                    Network error occurred while fetching ports.
                </td>
            </tr>
        `;
    }
}

function refreshPortsData() {
    if (currentPortsDeviceId) {
        document.getElementById('ports-table-body').innerHTML = `
            <tr>
                <td colspan="5" class="text-center" style="padding: 2rem; color: var(--text-muted);">
                    ⏳ Refreshing ports...
                </td>
            </tr>
        `;
        loadPortsData();
    }
}

// Render Ports Table
function renderPortsTable(ports) {
    const tbody = document.getElementById('ports-table-body');
    tbody.innerHTML = ports.map(p => `
        <tr style="border-bottom: 1px solid var(--border-color);">
            <td style="padding: 0.5rem;"><code style="color: ${p.protocol.toLowerCase() === 'tcp' ? 'var(--primary)' : 'var(--warning)'}; font-weight: bold;">${p.protocol}</code></td>
            <td style="padding: 0.5rem; word-break: break-all;">${p.address}</td>
            <td style="padding: 0.5rem; font-weight: 600;">${p.port}</td>
            <td style="padding: 0.5rem; color: ${p.process && p.process !== 'Unknown' ? 'var(--text)' : 'var(--text-muted)'};">${p.process}</td>
            <td style="padding: 0.5rem;"><span class="status-badge" style="background: rgba(16, 185, 129, 0.1); color: rgb(16, 185, 129);">${p.state || 'LISTEN'}</span></td>
        </tr>
    `).join('');
}

// Filter Ports Table
function filterPortsTable() {
    const searchTerm = document.getElementById('ports-search').value.toLowerCase();
    const tbody = document.getElementById('ports-table-body');
    
    if (currentPortsData.length === 0) return;
    
    const filtered = currentPortsData.filter(p => {
        return (p.port || '').toString().includes(searchTerm) ||
               (p.process || '').toLowerCase().includes(searchTerm) ||
               (p.protocol || '').toLowerCase().includes(searchTerm) ||
               (p.address || '').toLowerCase().includes(searchTerm);
    });
    
    if (filtered.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center" style="padding: 2rem; color: var(--text-muted);">
                    No ports matching your search.
                </td>
            </tr>
        `;
    } else {
        renderPortsTable(filtered);
    }
}

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

            // Load custom OIDs
            loadCustomOids(deviceId);

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
// Custom SNMP OID Functions
// ============================================================================

// Load custom OIDs for a device
async function loadCustomOids(deviceId) {
    const container = document.getElementById('custom-oids-container');
    try {
        const response = await fetch(`/api/snmp/${deviceId}/custom-oids`);
        const data = await response.json();

        if (!data.oids || data.oids.length === 0) {
            container.innerHTML = `
                <p style="color: var(--text-muted); text-align: center; padding: 0.75rem; font-size: 0.85rem;">
                    No custom OIDs configured. Click "Add OID" to get started.
                </p>`;
            return;
        }

        let html = `
            <table style="width: 100%; font-size: 0.85rem;">
                <thead>
                    <tr style="background: var(--glass-bg);">
                        <th style="padding: 0.5rem; text-align: left;">Name</th>
                        <th style="padding: 0.5rem; text-align: left;">OID</th>
                        <th style="padding: 0.5rem; text-align: right;">Value</th>
                        <th style="padding: 0.5rem; text-align: center;">Updated</th>
                        <th style="padding: 0.5rem; text-align: center; width: 40px;"></th>
                    </tr>
                </thead>
                <tbody>`;

        data.oids.forEach(oid => {
            const lastChecked = oid.last_checked ? formatDateTime(oid.last_checked) : 'Never';
            const valueDisplay = oid.last_value !== null && oid.last_value !== undefined
                ? `${oid.last_value}${oid.unit ? ' ' + oid.unit : ''}`
                : '<span style="color: var(--text-muted);">—</span>';

            html += `
                <tr style="border-bottom: 1px solid var(--glass-border);">
                    <td style="padding: 0.5rem;"><strong>${oid.name}</strong></td>
                    <td style="padding: 0.5rem;"><code style="font-size: 0.8rem;">${oid.oid}</code></td>
                    <td style="padding: 0.5rem; text-align: right; font-weight: 600;">${valueDisplay}</td>
                    <td style="padding: 0.5rem; text-align: center; color: var(--text-muted); font-size: 0.8rem;">${lastChecked}</td>
                    <td style="padding: 0.5rem; text-align: center;">
                        <button class="btn btn-sm btn-danger" style="padding: 0.15rem 0.35rem; font-size: 0.75rem;" onclick="deleteCustomOid(${oid.id})" title="Delete">
                            🗑️
                        </button>
                    </td>
                </tr>`;
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (error) {
        console.error('Error loading custom OIDs:', error);
        container.innerHTML = '<p style="color: var(--danger); text-align: center; padding: 0.5rem;">Error loading custom OIDs</p>';
    }
}

// Toggle add OID form
function toggleAddOidForm() {
    const form = document.getElementById('add-oid-form');
    form.style.display = form.style.display === 'none' ? 'block' : 'none';
    if (form.style.display === 'block') {
        document.getElementById('new-oid-value').focus();
    }
}

// Add a custom OID
async function addCustomOid() {
    if (!currentSnmpDeviceId) return;

    const oid = document.getElementById('new-oid-value').value.trim();
    const name = document.getElementById('new-oid-name').value.trim();
    const unit = document.getElementById('new-oid-unit').value.trim();

    if (!oid || !name) {
        alert('OID and Name are required.');
        return;
    }

    try {
        const response = await fetch(`/api/snmp/${currentSnmpDeviceId}/custom-oids`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ oid, name, unit })
        });
        const result = await response.json();

        if (result.success) {
            document.getElementById('new-oid-value').value = '';
            document.getElementById('new-oid-name').value = '';
            document.getElementById('new-oid-unit').value = '';
            document.getElementById('add-oid-form').style.display = 'none';
            loadCustomOids(currentSnmpDeviceId);
        } else {
            alert('Error: ' + (result.error || 'Failed to add OID'));
        }
    } catch (error) {
        console.error('Error adding custom OID:', error);
        alert('Error adding OID.');
    }
}

// Delete a custom OID
async function deleteCustomOid(oidId) {
    if (!confirm('Delete this custom OID?')) return;

    try {
        const response = await fetch(`/api/snmp/custom-oids/${oidId}`, { method: 'DELETE' });
        const result = await response.json();
        if (result.success) {
            loadCustomOids(currentSnmpDeviceId);
        } else {
            alert('Error deleting OID.');
        }
    } catch (error) {
        console.error('Error deleting custom OID:', error);
        alert('Error deleting OID.');
    }
}

// Query all custom OIDs (live SNMP query)
async function queryCustomOids() {
    if (!currentSnmpDeviceId) return;

    const btn = document.getElementById('query-oids-btn');
    btn.disabled = true;
    btn.textContent = '⏳ Querying...';

    try {
        const response = await fetch(`/api/snmp/${currentSnmpDeviceId}/custom-oids/query`, {
            method: 'POST'
        });
        const data = await response.json();

        if (data.results && data.results.length > 0) {
            // Reload to show updated values
            loadCustomOids(currentSnmpDeviceId);
        } else {
            alert(data.message || 'No custom OIDs to query.');
        }
    } catch (error) {
        console.error('Error querying custom OIDs:', error);
        alert('Error querying OIDs.');
    } finally {
        btn.disabled = false;
        btn.textContent = '🔄 Query All';
    }
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
let currentGraphMinutes = 60;
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

    // Highlight the correct period button based on currentGraphMinutes
    const modal = document.getElementById('graph-modal');
    modal.querySelectorAll('.period-btn').forEach(btn => {
        const onclickAttr = btn.getAttribute('onclick');
        if (onclickAttr && onclickAttr.includes(`setGraphPeriod(${currentGraphMinutes},`)) {
            btn.classList.remove('btn-outline-secondary');
            btn.classList.add('btn-primary');
        } else {
            btn.classList.remove('btn-primary');
            btn.classList.add('btn-outline-secondary');
        }
    });

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
        // Fetch sampled data (50 points) for the selected minutes
        const response = await fetch(`/api/devices/${deviceId}/history?minutes=${currentGraphMinutes}&sample=50&limit=3000`);
        const history = await response.json();

        // Sort chronologically by time, stripping Flask's naive GMT assignment
        graphHistoryData = history.map(h => {
            let timeStr = h.checked_at;
            if (typeof timeStr === 'string' && timeStr.endsWith(' GMT')) {
                timeStr = timeStr.replace(' GMT', '');
            }
            return {
                time: new Date(timeStr),
                value: h.response_time
            };
        }).sort((a, b) => a.time - b.time);

        updateGraphStatistics();
    } catch (error) {
        console.error('Error loading graph history:', error);
        graphHistoryData = [];
    }
}

/**
 * Set the graph period by updating the minutes and refreshing data
 * @param {number} minutes - Number of minutes to fetch
 * @param {HTMLElement} btn - The button that was clicked
 */
async function setGraphPeriod(minutes, btn) {
    currentGraphMinutes = minutes;

    // Update button styles
    const modal = document.getElementById('graph-modal');
    modal.querySelectorAll('.period-btn').forEach(b => {
        b.classList.remove('btn-primary');
        b.classList.add('btn-outline-secondary');
    });
    btn.classList.remove('btn-outline-secondary');
    btn.classList.add('btn-primary');

    // Update button styles as before...
    if (currentGraphDeviceId) {
        await loadGraphHistory(currentGraphDeviceId);
        if (responseTimeChart) {
            const chartData = graphHistoryData.map(d => ({
                x: d.time,
                y: d.value === null ? 0 : d.value,
                originalValue: d.value
            }));
            responseTimeChart.data.datasets[0].data = chartData;

            // Sync X-axis range
            const now = new Date();
            const start = new Date(now.getTime() - currentGraphMinutes * 60 * 1000);
            responseTimeChart.options.scales.x.min = start;
            responseTimeChart.options.scales.x.max = now;

            responseTimeChart.update();
        }
    }
}

// Reset the graph zoom to default
function resetGraphZoom() {
    if (responseTimeChart) {
        responseTimeChart.resetZoom();
    }
}

// Create or update the response time chart
function createResponseTimeChart() {
    const ctx = document.getElementById('response-time-chart').getContext('2d');
    const theme = document.documentElement.getAttribute('data-theme') || 'light';
    const textColor = theme === 'light' ? '#64748b' : 'rgba(255, 255, 255, 0.7)';
    const gridColor = theme === 'light' ? 'rgba(0, 0, 0, 0.1)' : 'rgba(255, 255, 255, 0.1)';

    // Destroy existing chart if exists
    if (responseTimeChart) {
        responseTimeChart.destroy();
    }

    // Prepare data
    const chartData = graphHistoryData.map(d => ({
        x: d.time,
        y: d.value === null ? 0 : d.value,
        originalValue: d.value
    }));

    // Create chart
    responseTimeChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'Response Time (ms)',
                data: chartData,
                borderColor: 'rgba(16, 185, 129, 1)', // Emerald Green
                backgroundColor: 'rgba(16, 185, 129, 0.2)', // Semi-transparent emerald green (uniform)
                borderWidth: 2,
                fill: true,
                tension: 0, // sharp edges (jagged style)
                spanGaps: true, // Connect lines across
                
                pointRadius: (ctx) => ctx.raw && ctx.raw.originalValue === null ? 3 : 0,
                pointBackgroundColor: (ctx) => ctx.raw && ctx.raw.originalValue === null ? '#ef4444' : 'rgba(16, 185, 129, 1)',
                pointBorderColor: (ctx) => ctx.raw && ctx.raw.originalValue === null ? '#ef4444' : 'white',
                pointBorderWidth: 2,
                pointHoverRadius: 7,
                segment: {
                    borderColor: (ctx) => ctx.p0.raw && ctx.p0.raw.originalValue === null && ctx.p1.raw && ctx.p1.raw.originalValue === null ? '#ef4444' : undefined,
                    borderDash: (ctx) => ctx.p0.raw && ctx.p0.raw.originalValue === null && ctx.p1.raw && ctx.p1.raw.originalValue === null ? [4, 4] : undefined
                }
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                zoom: {
                    zoom: {
                        wheel: { enabled: true },
                        pinch: { enabled: true },
                        mode: 'x',
                    },
                    pan: {
                        enabled: true,
                        mode: 'x',
                    }
                },
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            const original = context.raw?.originalValue;
                            if (original === null || original === undefined) return 'DOWN';
                            return `${original} ms`;
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
                                position: 'end',
                                color: textColor
                            }
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'time',
                    min: new Date(new Date().getTime() - currentGraphMinutes * 60 * 1000),
                    max: new Date(),
                    time: {
                        unit: 'minute',
                        tooltipFormat: 'PPp', // date-fns format for tooltips
                        displayFormats: {
                            minute: 'HH:mm'
                        }
                    },
                    display: true,
                    title: {
                        display: true,
                        text: 'Time',
                        color: textColor
                    },
                    ticks: {
                        color: textColor,
                        maxRotation: 45,
                        minRotation: 45,
                        maxTicksLimit: 10
                    },
                    grid: {
                        color: gridColor
                    }
                },
                y: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Response Time (ms)',
                        color: textColor
                    },
                    ticks: {
                        color: textColor
                    },
                    grid: {
                        color: gridColor
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

    // Ensure array is strictly monotonically sorted by time for Chart.js
    graphHistoryData.sort((a, b) => a.time - b.time);

    // Keep only data within the requested time range
    const cutoff = new Date(new Date().getTime() - currentGraphMinutes * 60 * 1000);
    graphHistoryData = graphHistoryData.filter(d => d.time >= cutoff);

    // Update chart data and bounds
    const now = new Date();
    responseTimeChart.options.scales.x.min = cutoff;
    responseTimeChart.options.scales.x.max = now;

    // Update chart
    responseTimeChart.data.datasets[0].data = graphHistoryData.map(d => ({
        x: d.time,
        y: d.value === null ? 0 : d.value,
        originalValue: d.value
    }));
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

// ==========================================
// MiniMap Logic
// ==========================================
let miniMap = null;
let miniMapMarker = null;

function initMinimap() {
    if (!miniMap) {
        // Find the device-minimap element
        const mapElement = document.getElementById('device-minimap');
        if (!mapElement) return;

        miniMap = L.map('device-minimap').setView([13.7563, 100.5018], 5);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap'
        }).addTo(miniMap);

        miniMap.on('click', function(e) {
            setMarker(e.latlng.lat, e.latlng.lng);
        });
    }
    
    // Invalidate size after modal shows so it renders correctly
    setTimeout(() => {
        if (miniMap) miniMap.invalidateSize();
    }, 200);
}

function setMarker(lat, lng) {
    if (miniMapMarker && miniMap) {
        miniMap.removeLayer(miniMapMarker);
    }
    
    const numericLat = parseFloat(lat);
    const numericLng = parseFloat(lng);

    if (isNaN(numericLat) || isNaN(numericLng)) return;

    miniMapMarker = L.marker([numericLat, numericLng], { draggable: true }).addTo(miniMap);
    
    document.getElementById('device-latitude').value = numericLat.toFixed(6);
    document.getElementById('device-longitude').value = numericLng.toFixed(6);

    miniMapMarker.on('dragend', function(e) {
        const position = miniMapMarker.getLatLng();
        document.getElementById('device-latitude').value = position.lat.toFixed(6);
        document.getElementById('device-longitude').value = position.lng.toFixed(6);
    });
}

function resetMinimap() {
    if (miniMapMarker && miniMap) {
        miniMap.removeLayer(miniMapMarker);
        miniMapMarker = null;
    }
    document.getElementById('device-latitude').value = '';
    document.getElementById('device-longitude').value = '';
    if (miniMap) {
        miniMap.setView([13.7563, 100.5018], 5);
    }
}

// ============================================================================
// Alert Dependencies — Parent Device Helpers
// ============================================================================

/**
 * Populate the parent device dropdown in the add/edit modal.
 * Excludes the device being edited (to prevent circular reference).
 */
function populateParentDeviceDropdown(excludeDeviceId) {
    const select = document.getElementById('parent-device');
    if (!select) return;
    
    select.innerHTML = '<option value="">— None (Independent) —</option>';
    
    allDevices.forEach(device => {
        // Don't allow a device to be its own parent
        if (excludeDeviceId && device.id === excludeDeviceId) return;
        
        const meta = deviceTypeMetadata[device.device_type];
        const icon = meta ? meta.icon : '⚙️';
        const option = document.createElement('option');
        option.value = device.id;
        option.textContent = `${icon} ${device.name} (${device.ip_address})`;
        select.appendChild(option);
    });
}

// ============================================================================
// Notification Assignments
// ============================================================================

let currentAssignmentDeviceId = null;

async function openAssignmentModal(deviceId, deviceName) {
    currentAssignmentDeviceId = deviceId;
    document.getElementById('assignment-device-name').textContent = deviceName;
    document.getElementById('assignment-modal').classList.add('active');
    
    // Load data
    await loadUsersForAssignment();
    await loadAssignments(deviceId);
}

function closeAssignmentModal() {
    document.getElementById('assignment-modal').classList.remove('active');
    currentAssignmentDeviceId = null;
}

async function loadUsersForAssignment() {
    const select = document.getElementById('assign-user-select');
    try {
        const response = await fetch('/api/users');
        const users = await response.json();
        
        select.innerHTML = '<option value="">-- Choose User --</option>';
        users.forEach(user => {
            const option = document.createElement('option');
            option.value = user.id;
            option.textContent = `${user.display_name || user.username} (${user.role})`;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading users:', error);
    }
}

async function loadAssignments(deviceId) {
    const tbody = document.getElementById('assignments-table-body');
    try {
        const response = await fetch(`/api/assignments/device/${deviceId}`);
        const assignments = await response.json();
        
        if (assignments.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="3" class="text-center" style="padding: 1rem; color: var(--text-muted);">
                        No specific users assigned.
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = assignments.map(a => `
            <tr>
                <td><strong>${a.display_name || a.username}</strong></td>
                <td>${a.email || '—'}</td>
                <td style="text-align: right;">
                    <button class="btn btn-sm btn-danger" onclick="unassignUserFromDevice(${a.id})">
                        Remove
                    </button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Error loading assignments:', error);
    }
}

async function assignUserToDevice() {
    const userId = document.getElementById('assign-user-select').value;
    if (!userId || !currentAssignmentDeviceId) {
        alert('Please select a user.');
        return;
    }
    
    try {
        const response = await fetch('/api/assignments/assign', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: parseInt(userId),
                device_id: currentAssignmentDeviceId
            })
        });
        
        const result = await response.json();
        if (result.success) {
            loadAssignments(currentAssignmentDeviceId);
        } else {
            alert('Error: ' + (result.error || 'Failed to assign user'));
        }
    } catch (error) {
        console.error('Error assigning user:', error);
        alert('Error assigning user.');
    }
}

async function unassignUserFromDevice(userId) {
    if (!confirm('Remove this user from device notifications?')) return;
    
    try {
        const response = await fetch('/api/assignments/unassign', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: userId,
                device_id: currentAssignmentDeviceId
            })
        });
        
        const result = await response.json();
        if (result.success) {
            loadAssignments(currentAssignmentDeviceId);
        } else {
            alert('Error: ' + (result.error || 'Failed to remove user'));
        }
    } catch (error) {
        console.error('Error removing user:', error);
        alert('Error removing user.');
    }
}

// Add to global click listener for outside-modal closing
document.addEventListener('click', (event) => {
    const assignmentModal = document.getElementById('assignment-modal');
    if (event.target === assignmentModal) {
        closeAssignmentModal();
    }
});

/**
 * Get parent device name by ID from the allDevices array.
 */
function getParentName(parentId) {
    if (!parentId) return '';
    const parent = allDevices.find(d => d.id === parentId);
    if (!parent) return `ID:${parentId}`;
    return parent.name;
}

// ============================================================================
// Performance Metrics Modal and Charts
// ============================================================================

let currentPerfDeviceId = null;
let currentPerfHours = 6;
let cpuChart = null;
let ramChart = null;
let diskChart = null;
let networkChart = null;

/**
 * Show performance metrics for a device (CPU, RAM, Disk)
 */
async function showPerformanceMetrics(deviceId) {
    const device = allDevices.find(d => d.id === deviceId);
    if (!device) return;

    currentPerfDeviceId = deviceId;
    document.getElementById('perf-device-name').textContent = device.name;
    document.getElementById('performance-modal').classList.add('active');

    // Reset charts
    if (cpuChart) { cpuChart.destroy(); cpuChart = null; }
    if (ramChart) { ramChart.destroy(); ramChart = null; }
    if (diskChart) { diskChart.destroy(); diskChart = null; }
    if (networkChart) { networkChart.destroy(); networkChart = null; }

    await loadPerformanceData();
}

function closePerformanceModal() {
    document.getElementById('performance-modal').classList.remove('active');
    currentPerfDeviceId = null;
}

async function setPerfPeriod(hours, btn) {
    currentPerfHours = hours;
    
    // Update button styles
    const modal = document.getElementById('performance-modal');
    modal.querySelectorAll('.perf-period-btn').forEach(b => {
        b.classList.remove('btn-primary');
        b.classList.add('btn-outline-secondary');
    });
    btn.classList.remove('btn-outline-secondary');
    btn.classList.add('btn-primary');
    
    await loadPerformanceData();
}

async function loadPerformanceData() {
    if (!currentPerfDeviceId) return;

    try {
        const response = await fetch(`/api/devices/${currentPerfDeviceId}/performance?hours=${currentPerfHours}`);
        const data = await response.json();
        
        if (data.error) {
            console.error('Performance data error:', data.error);
            return;
        }

        initPerformanceCharts(data);
    } catch (error) {
        console.error('Error loading performance data:', error);
    }
}

// Initialize or update Chart.js instances with a premium gradient style
function initPerformanceCharts(data) {
    const theme = document.documentElement.getAttribute('data-theme') || 'light';
    const textColor = theme === 'light' ? '#64748b' : 'rgba(255, 255, 255, 0.6)';
    const gridColor = theme === 'light' ? 'rgba(0, 0, 0, 0.05)' : 'rgba(255, 255, 255, 0.03)';
    
    // Premium Teal/Emerald Theme
    const BRAND_COLOR = '#10b981'; 
    
    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        layout: {
            padding: { top: 10, bottom: 0, left: 0, right: 10 }
        },
        scales: {
            x: {
                type: 'time',
                time: { 
                    unit: currentPerfHours <= 1 ? 'minute' : (currentPerfHours <= 24 ? 'hour' : 'day'),
                    tooltipFormat: 'PPpp'
                },
                grid: {
                    color: gridColor,
                    drawBorder: false
                },
                ticks: {
                    color: textColor,
                    font: { size: 10 }
                }
            },
            y: {
                min: 0,
                max: 100,
                grid: {
                    color: gridColor,
                    drawBorder: false
                },
                ticks: {
                    stepSize: 25,
                    color: textColor,
                    font: { size: 10 },
                    callback: function(value) { return value + '%'; }
                }
            }
        },
        plugins: {
            legend: { display: false },
            tooltip: { 
                backgroundColor: 'rgba(15, 23, 42, 0.9)',
                titleColor: '#f8fafc',
                bodyColor: '#f8fafc',
                borderColor: 'rgba(255, 255, 255, 0.1)',
                borderWidth: 1,
                padding: 10, cornerRadius: 8,
                mode: 'index', 
                intersect: false,
                callbacks: {
                    label: function(context) {
                        return `${context.dataset.label}: ${context.parsed.y.toFixed(1)}%`;
                    }
                }
            }
        },
        interaction: {
            mode: 'nearest',
            axis: 'x',
            intersect: false
        },
        spanGaps: false
    };

    // Helper to insert null points for gaps > 3 minutes (180000ms) to break lines
    const insertGaps = (arr) => {
        const res = [];
        for (let i = 0; i < arr.length; i++) {
            const ts = arr[i].timestamp || arr[i].sampled_at;
            const d = new Date(ts.includes(' ') ? ts.replace(' ', 'T') : ts);
            if (i > 0) {
                const prevTs = arr[i-1].timestamp || arr[i-1].sampled_at;
                const prevD = new Date(prevTs.includes(' ') ? prevTs.replace(' ', 'T') : prevTs);
                if (d - prevD > 180000) {
                    res.push({ x: new Date(prevD.getTime() + 1000), y: null });
                    // Insert points at y=0 to display red downtime indicators
                    res.push({ x: new Date(prevD.getTime() + 60000), y: 0, isDown: true });
                    res.push({ x: new Date(d.getTime() - 60000), y: 0, isDown: true });
                    res.push({ x: new Date(d.getTime() - 1000), y: null });
                }
            }
            res.push({ x: d, y: arr[i].value });
        }
        return res;
    };

    const config = [
        { id: 'cpu', label: 'CPU Usage', data: data.cpu, chartVar: 'cpu' },
        { id: 'ram', label: 'RAM Usage', data: data.ram, chartVar: 'ram' },
        { id: 'disk', label: 'Disk Usage', data: data.disk, chartVar: 'disk' }
    ];

    config.forEach(set => {
        const canvas = document.getElementById(`${set.id}-chart`);
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const chartData = insertGaps(set.data);
        
        // Uniform solid fill color
        const fillColor = 'rgba(16, 185, 129, 0.2)'; 

        let existingChart = null;
        if (set.id === 'cpu') existingChart = cpuChart;
        else if (set.id === 'ram') existingChart = ramChart;
        else if (set.id === 'disk') existingChart = diskChart;

        if (existingChart) {
            existingChart.data.datasets[0].data = chartData;
            existingChart.data.datasets[0].backgroundColor = fillColor;
            existingChart.options.scales.x.time.unit = currentPerfHours <= 1 ? 'minute' : (currentPerfHours <= 24 ? 'hour' : 'day');
            existingChart.update();
        } else {
            const chart = new Chart(ctx, {
                type: 'line',
                data: {
                    datasets: [{
                        label: set.label,
                        data: chartData,
                        borderColor: BRAND_COLOR,
                        backgroundColor: fillColor,
                        borderWidth: 3,
                        fill: true,
                        tension: 0, 
                        pointRadius: (ctx) => ctx.raw && ctx.raw.isDown ? 3 : 0, 
                        pointBackgroundColor: (ctx) => ctx.raw && ctx.raw.isDown ? '#ef4444' : '#ffffff',
                        pointBorderColor: (ctx) => ctx.raw && ctx.raw.isDown ? '#ef4444' : BRAND_COLOR,
                        pointHoverRadius: 6,
                        pointHoverBackgroundColor: '#ffffff',
                        pointHoverBorderColor: BRAND_COLOR,
                        pointHoverBorderWidth: 3,
                        segment: {
                            borderColor: (ctx) => ctx.p0.raw && ctx.p0.raw.isDown && ctx.p1.raw && ctx.p1.raw.isDown ? '#ef4444' : undefined,
                            borderDash: (ctx) => ctx.p0.raw && ctx.p0.raw.isDown && ctx.p1.raw && ctx.p1.raw.isDown ? [4, 4] : undefined
                        }
                    }]
                },
                options: commonOptions
            });
            
            if (set.id === 'cpu') cpuChart = chart;
            else if (set.id === 'ram') ramChart = chart;
            else if (set.id === 'disk') diskChart = chart;
        }
    });

    // Special handling for Network Chart (Two datasets)
    const netCanvas = document.getElementById('network-chart');
    if (netCanvas) {
        const ctx = netCanvas.getContext('2d');
        const inData = insertGaps(data.network_in);
        const outData = insertGaps(data.network_out);
        
        const formatBps = (val) => {
            if (val >= 1000000000) return (val / 1000000000).toFixed(2) + ' Gbps';
            if (val >= 1000000) return (val / 1000000).toFixed(2) + ' Mbps';
            if (val >= 1000) return (val / 1000).toFixed(1) + ' Kbps';
            return val.toFixed(0) + ' bps';
        };

        const netOptions = JSON.parse(JSON.stringify(commonOptions));
        delete netOptions.scales.y.max;
        delete netOptions.scales.y.stepSize;
        netOptions.scales.y.ticks.callback = formatBps;
        netOptions.plugins.tooltip.callbacks.label = function(context) {
            return `${context.dataset.label}: ${formatBps(context.parsed.y)}`;
        };

        if (networkChart) {
            networkChart.data.datasets[0].data = inData;
            networkChart.data.datasets[1].data = outData;
            networkChart.options.scales.x.time.unit = currentPerfHours <= 1 ? 'minute' : (currentPerfHours <= 24 ? 'hour' : 'day');
            networkChart.update();
        } else {
            networkChart = new Chart(ctx, {
                type: 'line',
                data: {
                    datasets: [
                        {
                            label: 'Incoming',
                            data: inData,
                            borderColor: '#3b82f6', // Blue
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.1,
                            pointRadius: (ctx) => ctx.raw && ctx.raw.isDown ? 3 : 0,
                            pointBackgroundColor: (ctx) => ctx.raw && ctx.raw.isDown ? '#ef4444' : '#3b82f6',
                            pointBorderColor: (ctx) => ctx.raw && ctx.raw.isDown ? '#ef4444' : '#3b82f6',
                            segment: {
                                borderColor: (ctx) => ctx.p0.raw && ctx.p0.raw.isDown && ctx.p1.raw && ctx.p1.raw.isDown ? '#ef4444' : undefined,
                                borderDash: (ctx) => ctx.p0.raw && ctx.p0.raw.isDown && ctx.p1.raw && ctx.p1.raw.isDown ? [4, 4] : undefined
                            }
                        },
                        {
                            label: 'Outgoing',
                            data: outData,
                            borderColor: '#ec4899', // Pink
                            backgroundColor: 'rgba(236, 72, 153, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.1,
                            pointRadius: (ctx) => ctx.raw && ctx.raw.isDown ? 3 : 0,
                            pointBackgroundColor: (ctx) => ctx.raw && ctx.raw.isDown ? '#ef4444' : '#ec4899',
                            pointBorderColor: (ctx) => ctx.raw && ctx.raw.isDown ? '#ef4444' : '#ec4899',
                            segment: {
                                borderColor: (ctx) => ctx.p0.raw && ctx.p0.raw.isDown && ctx.p1.raw && ctx.p1.raw.isDown ? '#ef4444' : undefined,
                                borderDash: (ctx) => ctx.p0.raw && ctx.p0.raw.isDown && ctx.p1.raw && ctx.p1.raw.isDown ? [4, 4] : undefined
                            }
                        }
                    ]
                },
                options: netOptions
            });
        }
    }
}

// Ensure modals close when clicking outside
document.addEventListener('click', (event) => {
    const perfModal = document.getElementById('performance-modal');
    if (event.target === perfModal) closePerformanceModal();
});
