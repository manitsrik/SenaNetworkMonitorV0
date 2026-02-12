// Topology JavaScript
// Handles network topology visualization using Vis.js

// Initialize Socket.IO connection
const socket = io();

// Vis.js network instance
let network = null;
let nodes = new vis.DataSet([]);
let edges = new vis.DataSet([]);
let allDevices = []; // Store all devices for modal
let allConnections = []; // Store all connections
let isGroupedView = false; // Toggle for grouped/free view
let isWirelessView = false; // Toggle for wireless view

// Location type zones base configuration
const locationTypeZonesBase = {
    'cloud': { label: '☁️ CLOUD', color: 'rgba(59, 130, 246, 0.15)', borderColor: '#3b82f6' },
    'internet': { label: '🌐 INTERNET', color: 'rgba(16, 185, 129, 0.15)', borderColor: '#10b981' },
    'remote': { label: '🏢 REMOTE SITE', color: 'rgba(245, 158, 11, 0.15)', borderColor: '#f59e0b' },
    'on-premise': { label: '🏠 ON-PREMISE', color: 'rgba(99, 102, 241, 0.15)', borderColor: '#6366f1' }
};

// Dynamic zone dimensions (calculated based on device count)
let dynamicZones = {};

// Zone sizing constants
const MIN_ZONE_WIDTH = 400;
const MIN_ZONE_HEIGHT = 350;
const DEVICE_SPACING_X = 350; // Increased spacing for better distribution
const DEVICE_SPACING_Y = 250; // Increased spacing for better distribution
const ZONE_PADDING = 80;
const ZONE_GAP = 30;

// Initialize topology
document.addEventListener('DOMContentLoaded', () => {
    initializeNetwork();
    loadTopologyData();
    setupSocketListeners();
    setupThemeListener();
});

// Get text color based on current theme
function getTextColor() {
    const theme = document.documentElement.getAttribute('data-theme') || 'dark';
    return theme === 'dark' ? '#f1f5f9' : '#0f172a';
}

// Setup theme change listener
function setupThemeListener() {
    // Listen for theme changes
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.attributeName === 'data-theme') {
                updateNodeColors();
            }
        });
    });

    observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-theme']
    });
}

// Update all node colors when theme changes
function updateNodeColors() {
    const textColor = getTextColor();

    // Update network options
    if (network) {
        network.setOptions({
            nodes: {
                font: {
                    color: textColor
                }
            }
        });
    }

    // Update all existing nodes
    const allNodes = nodes.get();
    allNodes.forEach(node => {
        nodes.update({
            id: node.id,
            font: {
                size: isGroupedView ? 20 : 150,
                face: 'Inter, sans-serif',
                vadjust: isGroupedView ? 0 : -30,
                mod: isGroupedView ? '' : 'bold',
                color: textColor
            }
        });
    });
}

// Initialize Vis.js network
function initializeNetwork() {
    const container = document.getElementById('topology-network');

    const data = {
        nodes: nodes,
        edges: edges
    };

    const options = {
        nodes: {
            shape: 'dot',
            size: 100,
            font: {
                size: 150,
                face: 'Inter, sans-serif',
                mod: 'bold',
                vadjust: -30,
                color: getTextColor()
            },
            borderWidth: 2,
            shadow: {
                enabled: true,
                color: 'rgba(0,0,0,0.3)',
                size: 10,
                x: 0,
                y: 0
            },
            scaling: {
                label: {
                    enabled: true,
                    min: 14,
                    max: 150,
                    drawThreshold: 2
                }
            }
        },
        edges: {
            width: 3,
            color: {
                color: 'rgba(71, 85, 105, 0.8)',
                highlight: '#6366f1',
                hover: '#818cf8'
            },
            smooth: {
                type: 'dynamic',
                roundness: 0.5
            },
            shadow: false
        },
        physics: {
            enabled: true,
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
                gravitationalConstant: -3000,
                centralGravity: 0.003,
                springLength: 350,
                springConstant: 0.02,
                avoidOverlap: 1.0,
                damping: 0.4
            },
            stabilization: {
                enabled: true,
                iterations: 800,
                updateInterval: 25,
                fit: true
            }
        },
        layout: {
            randomSeed: 2,
            improvedLayout: true
        },
        interaction: {
            hover: true,
            tooltipDelay: 200,
            zoomView: true,
            dragView: true,
            dragNodes: true
        },
        manipulation: {
            enabled: false
        }
    };

    network = new vis.Network(container, data, options);

    // After stabilization, disable physics and fit to screen
    network.on('stabilizationIterationsDone', () => {
        network.setOptions({ physics: { enabled: false } });
        network.fit({
            animation: {
                duration: 500,
                easingFunction: 'easeInOutQuad'
            }
        });
    });

    // Draw zone backgrounds when in grouped view
    network.on('beforeDrawing', (ctx) => {
        if (isGroupedView) {
            drawZoneBackgrounds(ctx);
            constrainOnPremiseNodes();
        }
    });

    // Also constrain after drawing for better physics containment
    network.on('afterDrawing', () => {
        if (isGroupedView) {
            constrainOnPremiseNodes();
        }
    });

    // Event listeners
    network.on('click', (params) => {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            showNodeInfo(nodeId);
        } else if (params.edges.length > 0) {
            const edgeId = params.edges[0];
            showEdgeOptions(edgeId);
        }
    });

    // Hover to enlarge font
    network.on('hoverNode', (params) => {
        const nodeId = params.node;
        nodes.update({
            id: nodeId,
            size: isGroupedView ? 35 : 110,
            font: {
                size: isGroupedView ? 30 : 160,
                face: 'Inter, sans-serif',
                mod: isGroupedView ? '' : 'bold',
                color: getTextColor()
            }
        });
    });

    // Reset font on blur
    network.on('blurNode', (params) => {
        const nodeId = params.node;
        nodes.update({
            id: nodeId,
            size: isGroupedView ? 25 : 100,
            font: {
                size: isGroupedView ? 20 : 150,
                face: 'Inter, sans-serif',
                mod: isGroupedView ? '' : 'bold',
                color: getTextColor()
            }
        });
    });
}

// Draw zone background boxes (2x2 grid with dynamic sizing)
function drawZoneBackgrounds(ctx) {
    const zoneOrder = ['cloud', 'internet', 'remote', 'on-premise'];

    zoneOrder.forEach(zoneKey => {
        const zone = dynamicZones[zoneKey];
        if (!zone) return;

        const x = zone.x - zone.width / 2;
        const y = zone.y - zone.height / 2;
        const width = zone.width;
        const height = zone.height;

        // Draw background box with rounded corners
        ctx.fillStyle = zone.color;
        ctx.beginPath();
        const radius = 15;
        ctx.moveTo(x + radius, y);
        ctx.lineTo(x + width - radius, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
        ctx.lineTo(x + width, y + height - radius);
        ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
        ctx.lineTo(x + radius, y + height);
        ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
        ctx.lineTo(x, y + radius);
        ctx.quadraticCurveTo(x, y, x + radius, y);
        ctx.closePath();
        ctx.fill();

        // Draw border
        ctx.strokeStyle = zone.borderColor;
        ctx.lineWidth = 3;
        ctx.stroke();

        // Draw zone label at top-left corner with device count
        ctx.fillStyle = zone.borderColor;
        ctx.font = 'bold 18px Inter, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText(`${zone.label} (${zone.deviceCount})`, x + 15, y + 12);
    });
}

// Calculate dynamic zone sizes based on device count
function calculateDynamicZones(groupedDevices) {
    const zoneKeys = ['cloud', 'internet', 'remote', 'on-premise'];
    const zoneSizes = {};

    // Calculate required size for each zone
    zoneKeys.forEach(key => {
        const devices = groupedDevices[key] || [];
        const deviceCount = devices.length;
        const devicesPerRow = Math.max(1, Math.min(deviceCount, 6)); // Max 6 devices per row
        const rows = Math.ceil(deviceCount / devicesPerRow);

        const width = Math.max(MIN_ZONE_WIDTH, devicesPerRow * DEVICE_SPACING_X + ZONE_PADDING * 2);
        const height = Math.max(MIN_ZONE_HEIGHT, rows * DEVICE_SPACING_Y + ZONE_PADDING * 2 + 40); // +40 for label

        zoneSizes[key] = {
            ...locationTypeZonesBase[key],
            width: width,
            height: height,
            deviceCount: deviceCount,
            devicesPerRow: devicesPerRow
        };
    });

    // Give ON-PREMISE grid layout sizing
    if (zoneSizes['on-premise'].deviceCount > 0) {
        const onPremCount = zoneSizes['on-premise'].deviceCount;
        // Increase columns to spread out more (max 8 per row)
        const onPremPerRows = Math.max(1, Math.min(onPremCount, 8));
        const onPremRows = Math.ceil(onPremCount / onPremPerRows);

        const onPremWidth = Math.max(MIN_ZONE_WIDTH, onPremPerRows * DEVICE_SPACING_X + ZONE_PADDING * 2);
        const onPremHeight = Math.max(MIN_ZONE_HEIGHT, onPremRows * DEVICE_SPACING_Y + ZONE_PADDING * 2 + 40);

        zoneSizes['on-premise'].width = onPremWidth;
        zoneSizes['on-premise'].height = onPremHeight;
        zoneSizes['on-premise'].devicesPerRow = onPremPerRows;
    }

    // Use uniform width for all zones (max width across all zones)
    const uniformWidth = Math.max(
        zoneSizes['cloud'].width,
        zoneSizes['internet'].width,
        zoneSizes['remote'].width,
        zoneSizes['on-premise'].width
    );
    zoneKeys.forEach(key => { zoneSizes[key].width = uniformWidth; });

    // Calculate row heights (max height in each row)
    const topRowHeight = Math.max(zoneSizes['cloud'].height, zoneSizes['internet'].height);
    const bottomRowHeight = Math.max(zoneSizes['remote'].height, zoneSizes['on-premise'].height);

    const totalWidth = uniformWidth * 2 + ZONE_GAP;
    const totalHeight = topRowHeight + bottomRowHeight + ZONE_GAP;

    // Position zones in 2x2 grid with uniform width
    zoneSizes['cloud'].x = -totalWidth / 2 + uniformWidth / 2;
    zoneSizes['cloud'].y = -totalHeight / 2 + topRowHeight / 2;
    zoneSizes['cloud'].height = topRowHeight;

    zoneSizes['internet'].x = totalWidth / 2 - uniformWidth / 2;
    zoneSizes['internet'].y = -totalHeight / 2 + topRowHeight / 2;
    zoneSizes['internet'].height = topRowHeight;

    zoneSizes['remote'].x = -totalWidth / 2 + uniformWidth / 2;
    zoneSizes['remote'].y = totalHeight / 2 - bottomRowHeight / 2;
    zoneSizes['remote'].height = bottomRowHeight;

    zoneSizes['on-premise'].x = totalWidth / 2 - uniformWidth / 2;
    zoneSizes['on-premise'].y = totalHeight / 2 - bottomRowHeight / 2;
    zoneSizes['on-premise'].height = bottomRowHeight;

    return zoneSizes;
}

// Load topology data
async function loadTopologyData() {
    try {
        const response = await fetch('/api/topology');
        const data = await response.json();

        allDevices = data.devices;
        allConnections = data.connections;

        updateTopology(data.devices, data.connections);
    } catch (error) {
        console.error('Error loading topology:', error);
    }
}

// Update topology visualization
function updateTopology(devices, connections) {
    // Filter for Wireless View if active
    let displayDevices = devices;
    let displayConnections = connections;

    if (isWirelessView) {
        displayDevices = devices.filter(d => (d.device_type || '').toLowerCase() === 'wireless');
        const deviceIds = new Set(displayDevices.map(d => d.id));
        displayConnections = connections.filter(c =>
            c.view_type === 'wireless' &&
            deviceIds.has(c.device_id) &&
            deviceIds.has(c.connected_to)
        );
    } else {
        // Standard view: show standard connections (or legacy ones with no view_type)
        displayConnections = connections.filter(c => !c.view_type || c.view_type === 'standard');
    }

    // Clear existing nodes and edges
    nodes.clear();
    edges.clear();

    // Group devices by location_type for positioning
    const groupedDevices = {};
    displayDevices.forEach(device => {
        const locType = device.location_type || 'on-premise';
        if (!groupedDevices[locType]) {
            groupedDevices[locType] = [];
        }
        groupedDevices[locType].push(device);
    });

    // Calculate dynamic zone sizes based on device count
    if (isGroupedView) {
        dynamicZones = calculateDynamicZones(groupedDevices);
    }

    // Add devices as nodes
    const deviceMap = {};
    displayDevices.forEach(d => deviceMap[d.id] = d);

    displayDevices.forEach(device => {
        const color = getNodeColor(device.status);
        const icon = getDeviceIcon(device.device_type);
        const deviceType = device.device_type || 'other';
        const locType = device.location_type || 'on-premise';
        const locTypeLabel = getLocationTypeLabel(locType);

        // Calculate position if grouped view
        let nodeOptions = {
            id: device.id,
            label: `${icon}\n${device.name}`,
            title: `${icon} ${device.name}\n${device.ip_address}\nType: ${deviceType}\nLocation: ${device.location || 'N/A'}\nZone: ${locTypeLabel}\nStatus: ${device.status}\n${device.response_time !== null && device.response_time !== undefined ? `Response: ${device.response_time}ms` : ''}`,
            status: device.status, // Store status for edge coloring
            color: {
                background: color,
                border: color,
                highlight: {
                    background: color,
                    border: '#ffffff'
                }
            },
            size: isGroupedView ? 25 : 100,
            font: {
                size: isGroupedView ? 20 : 150,
                face: 'Inter, sans-serif',
                mod: isGroupedView ? '' : 'bold',
                vadjust: isGroupedView ? 0 : -30,
                color: getTextColor()
            }
        };

        // Calculate fixed position if grouped view is enabled (2x2 grid with dynamic sizing)
        if (isGroupedView) {
            const zone = dynamicZones[locType] || dynamicZones['on-premise'];
            const devicesInZone = groupedDevices[locType] || [];
            const index = devicesInZone.indexOf(device);

            // Unified grid layout logic for ALL zones including On-Premise
            const devicesPerRow = zone.devicesPerRow || Math.ceil(Math.sqrt(devicesInZone.length));
            const row = Math.floor(index / devicesPerRow);
            const col = index % devicesPerRow;
            const totalRows = Math.ceil(devicesInZone.length / devicesPerRow);

            // Explicit large spacing
            const spacingX = 400;
            const spacingY = 300;

            const gridWidth = (devicesPerRow - 1) * spacingX;
            const gridHeight = (totalRows - 1) * spacingY;

            // Center the grid within the zone
            const xOffset = zone.x + (col * spacingX) - gridWidth / 2;
            const yOffset = zone.y + (row * spacingY) - gridHeight / 2 + 30; // +30 for label offset

            nodeOptions.x = xOffset;
            nodeOptions.y = yOffset;
            nodeOptions.fixed = { x: true, y: true };
        }
        nodes.add(nodeOptions);
    });

    // Add connections as edges with varied routing to avoid overlap
    const edgePairCount = {};
    const nodeEdgeCount = {};

    displayConnections.forEach(conn => {
        const pairKey = [Math.min(conn.device_id, conn.connected_to), Math.max(conn.device_id, conn.connected_to)].join('-');
        if (!edgePairCount[pairKey]) edgePairCount[pairKey] = 0;
        edgePairCount[pairKey]++;

        nodeEdgeCount[conn.device_id] = (nodeEdgeCount[conn.device_id] || 0) + 1;
        nodeEdgeCount[conn.connected_to] = (nodeEdgeCount[conn.connected_to] || 0) + 1;

        const edgeIndex = edgePairCount[pairKey];

        let smoothOptions;
        if (isGroupedView) {
            // Zone view: use varied curve types and roundness to separate lines
            const types = ['curvedCW', 'curvedCCW', 'cubicBezier'];
            const typeIndex = (conn.id || edgeIndex) % types.length;
            const baseRoundness = 0.15 + (edgeIndex * 0.12);
            const variation = ((conn.device_id * 7 + conn.connected_to * 13) % 20) / 100;
            smoothOptions = {
                type: types[typeIndex],
                roundness: Math.min(baseRoundness + variation, 0.8)
            };
        } else {
            // Free view: dynamic routing (reverted)
            const direction = edgeIndex % 2 === 0 ? 1 : -1;
            const roundness = 0.2 + (Math.floor((edgeIndex - 1) / 2) * 0.15) * direction;
            smoothOptions = {
                type: 'curvedCW',
                roundness: roundness
            };
        }

        // Check for cross-zone edges involving On-Premise
        let edgePhysics = true;
        if (isGroupedView) {
            const fromDev = deviceMap[conn.device_id];
            const toDev = deviceMap[conn.connected_to];
            if (fromDev && toDev) {
                const loc1 = fromDev.location_type || 'on-premise';
                const loc2 = toDev.location_type || 'on-premise';
                if ((loc1 === 'on-premise' && loc2 !== 'on-premise') ||
                    (loc1 !== 'on-premise' && loc2 === 'on-premise')) {
                    edgePhysics = false;
                }
            }
        }

        edges.add({
            id: conn.id,
            from: conn.device_id,
            to: conn.connected_to,
            title: 'Click to delete connection',
            physics: edgePhysics,
            smooth: smoothOptions
        });
    });

    // Handle physics based on view mode
    if (isGroupedView) {
        // Zone View: enable physics for ON-PREMISE free view, other zones fixed
        network.setOptions({
            physics: {
                enabled: true,
                solver: 'repulsion',
                repulsion: {
                    centralGravity: 0.0, // Disable gravity to keep zones separated
                    springLength: 300,
                    springConstant: 0.0, // Disable springs
                    nodeDistance: 250,
                    damping: 1.0 // Stop movement
                },
                stabilization: {
                    enabled: true,
                    iterations: 1500,
                    updateInterval: 25,
                    fit: true
                }
            }
        });
        network.stabilize();
    } else {
        // Free View: enable physics to spread out nodes, then stabilize
        network.setOptions({
            physics: {
                enabled: true,
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {
                    gravitationalConstant: -3000,
                    centralGravity: 0.003,
                    springLength: 350,
                    springConstant: 0.02,
                    avoidOverlap: 1.0,
                    damping: 0.4
                },
                stabilization: {
                    enabled: true,
                    iterations: 800,
                    updateInterval: 25,
                    fit: true
                }
            }
        });
        network.stabilize();
    }
}

// Get location type label
function getLocationTypeLabel(locType) {
    const labels = {
        'cloud': 'Cloud',
        'internet': 'Internet',
        'remote': 'Remote Site',
        'on-premise': 'On-Premise'
    };
    return labels[locType] || 'On-Premise';
}

// Toggle grouped view
function toggleGroupedView() {
    isGroupedView = !isGroupedView;

    // Update button text
    const btn = document.getElementById('toggle-view-btn');
    if (btn) {
        btn.innerHTML = isGroupedView ? '🔓 Free View' : '📊 Zone View';
    }

    // Show/hide zone legend
    const zoneLegend = document.getElementById('zone-legend');
    if (zoneLegend) {
        zoneLegend.style.display = isGroupedView ? 'block' : 'none';
    }

    // Reload topology with new layout
    updateTopology(allDevices, allConnections);
}

// Toggle wireless view
function toggleWirelessView() {
    isWirelessView = !isWirelessView;

    // Update button text/style
    const btn = document.getElementById('toggle-wireless-btn');
    if (btn) {
        btn.innerHTML = isWirelessView ? '📶 Show All Devices' : '📶 Wireless View';

        // Toggle active class
        if (isWirelessView) {
            btn.classList.remove('btn-info');
            btn.classList.add('btn-warning');
        } else {
            btn.classList.remove('btn-warning');
            btn.classList.add('btn-info');
        }
    }

    // Reload topology with new filter
    updateTopology(allDevices, allConnections);
}

// Get node color based on status
function getNodeColor(status) {
    const colors = {
        'up': '#10b981',      // green
        'slow': '#f59e0b',    // orange/yellow
        'down': '#ef4444',    // red
        'unknown': '#94a3b8'  // gray
    };
    return colors[status] || colors['unknown'];
}

// Get device icon based on type
function getDeviceIcon(deviceType) {
    const type = (deviceType || 'other').toLowerCase();
    const icons = {
        'switch': '🔀',
        'firewall': '🛡️',
        'server': '🖥️',
        'router': '🌐',
        'wireless': '📶',
        'website': '🌐',
        'vmware': '🖴',
        'ippbx': '☎️',
        'vpnrouter': '🔒',
        'dns': '🔍',
        'other': '⚙️'
    };
    return icons[type] || icons['other'];
}

// Setup Socket.IO listeners
function setupSocketListeners() {
    socket.on('connect', () => {
        console.log('Connected to server');
    });

    socket.on('status_update', (data) => {
        console.log('Status update:', data);
        updateNodeStatus(data);
    });

    socket.on('device_deleted', (data) => {
        console.log('Device deleted:', data);
        nodes.remove(data.id);
    });

    socket.on('topology_updated', (data) => {
        console.log('Topology updated:', data);
        loadTopologyData(); // Reload topology
    });
}

// Update node status
function updateNodeStatus(device) {
    // Update device in master list if present
    const masterIndex = allDevices.findIndex(d => d.id === device.id);
    if (masterIndex !== -1) {
        allDevices[masterIndex] = { ...allDevices[masterIndex], ...device };
    } else {
        // Truly new device, reload topology
        loadTopologyData();
        return;
    }

    const node = nodes.get(device.id);
    if (node) {
        const color = getNodeColor(device.status);
        const icon = getDeviceIcon(device.device_type);
        const deviceType = device.device_type || 'other';

        nodes.update({
            id: device.id,
            label: `${icon}\n${device.name}`,
            title: `${icon} ${device.name}\n${device.ip_address}\nType: ${deviceType}\nStatus: ${device.status}\n${device.response_time !== null && device.response_time !== undefined ? `Response: ${device.response_time}ms` : ''}`,
            color: {
                background: color,
                border: color,
                highlight: {
                    background: color,
                    border: '#ffffff'
                }
            }
        });
    }
}

// Show node information
function showNodeInfo(nodeId) {
    const device = allDevices.find(d => d.id === nodeId);
    if (device) {
        alert(`Device: ${device.name}\nIP: ${device.ip_address}\nType: ${device.device_type}\nLocation: ${device.location}\nStatus: ${device.status}\nResponse Time: ${device.response_time !== null && device.response_time !== undefined ? device.response_time : 'N/A'} ms\nLast Check: ${device.last_check || 'Never'}`);
    }
}

// Show edge options (delete)
function showEdgeOptions(edgeId) {
    if (confirm('Do you want to delete this connection?')) {
        deleteConnection(edgeId);
    }
}

// Show add connection modal
function showAddConnectionModal() {
    const fromSelect = document.getElementById('from-device');
    const toSelect = document.getElementById('to-device');

    // Clear and populate device selects
    fromSelect.innerHTML = '<option value="">Select device...</option>';
    toSelect.innerHTML = '<option value="">Select device...</option>';

    allDevices.forEach(device => {
        fromSelect.innerHTML += `<option value="${device.id}">${device.name} (${device.ip_address})</option>`;
        toSelect.innerHTML += `<option value="${device.id}">${device.name} (${device.ip_address})</option>`;
    });

    document.getElementById('connection-modal').classList.add('active');
}

// Close connection modal
function closeConnectionModal() {
    document.getElementById('connection-modal').classList.remove('active');
    document.getElementById('connection-form').reset();
}

// Save connection
async function saveConnection(event) {
    event.preventDefault();

    const fromDeviceId = parseInt(document.getElementById('from-device').value);
    const toDeviceId = parseInt(document.getElementById('to-device').value);

    if (fromDeviceId === toDeviceId) {
        alert('Cannot connect a device to itself!');
        return;
    }

    try {
        const response = await fetch('/api/topology/connection', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                device_id: fromDeviceId,
                connected_to: toDeviceId,
                view_type: isWirelessView ? 'wireless' : 'standard'
            })
        });

        const result = await response.json();

        if (result.success) {
            closeConnectionModal();
            alert('Connection added successfully!');
            loadTopologyData();
        } else {
            alert('Error: ' + (result.error || 'Failed to add connection'));
        }
    } catch (error) {
        console.error('Error adding connection:', error);
        alert('Error adding connection. Please try again.');
    }
}

// Delete connection
async function deleteConnection(connectionId) {
    try {
        const response = await fetch(`/api/topology/connection/${connectionId}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            alert('Connection deleted successfully!');
            loadTopologyData();
        } else {
            alert('Error deleting connection.');
        }
    } catch (error) {
        console.error('Error deleting connection:', error);
        alert('Error deleting connection. Please try again.');
    }
}

// Fit network to screen
function fitNetwork() {
    if (network) {
        network.fit({
            animation: {
                duration: 500,
                easingFunction: 'easeInOutQuad'
            }
        });
    }
}

// Toggle Fullscreen
function toggleFullscreen() {
    const container = document.getElementById('topology-network').parentElement.parentElement; // Card element

    if (!document.fullscreenElement) {
        if (container.requestFullscreen) {
            container.requestFullscreen();
        } else if (container.mozRequestFullScreen) { // Firefox
            container.mozRequestFullScreen();
        } else if (container.webkitRequestFullscreen) { // Chrome, Safari and Opera
            container.webkitRequestFullscreen();
        } else if (container.msRequestFullscreen) { // IE/Edge
            container.msRequestFullscreen();
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.mozCancelFullScreen) {
            document.mozCancelFullScreen();
        } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
        } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
        }
    }
}

// Handle fullscreen change events to resize network
document.addEventListener('fullscreenchange', handleFullscreenChange);
document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
document.addEventListener('mozfullscreenchange', handleFullscreenChange);
document.addEventListener('MSFullscreenChange', handleFullscreenChange);

function handleFullscreenChange() {
    setTimeout(() => {
        if (network) {
            const container = document.getElementById('topology-network');
            // Force redraw with explicit pixel dimensions to ensure canvas resizes correctly
            network.setSize(`${container.clientWidth}px`, `${container.clientHeight}px`);
            network.redraw();
            network.fit();
        }
    }, 500); // Increased timeout to ensure DOM layout is complete
}

// Refresh topology
function refreshTopology() {
    loadTopologyData();
}

// Close modal when clicking outside
document.addEventListener('click', (event) => {
    const modal = document.getElementById('connection-modal');
    if (event.target === modal) {
        closeConnectionModal();
    }
});

// Constrain On-Premise nodes to their zone and add local gravity
function constrainOnPremiseNodes() {
    const zone = dynamicZones['on-premise'];
    if (!zone) return;

    const margin = 100;
    const topMargin = 110;

    const minX = zone.x - zone.width / 2 + margin;
    const maxX = zone.x + zone.width / 2 - margin;
    const minY = zone.y - zone.height / 2 + topMargin;
    const maxY = zone.y + zone.height / 2 - margin;
    const centerX = zone.x;
    const centerY = zone.y + (topMargin - margin) / 2;

    const onPremiseDevices = allDevices.filter(d => (d.location_type || 'on-premise') === 'on-premise');

    onPremiseDevices.forEach(device => {
        const bodyNode = network.body.nodes[device.id];
        if (!bodyNode) return;

        let newX = bodyNode.x;
        let newY = bodyNode.y;
        let changed = false;

        // Apply gentle position correction to keep center gravity consistent
        // Pull 0.2% towards center every frame (just enough to lift off bottom)
        const pullStrength = 0.002;
        bodyNode.x = bodyNode.x * (1 - pullStrength) + centerX * pullStrength;
        bodyNode.y = bodyNode.y * (1 - pullStrength) + centerY * pullStrength;

        // Apply velocity dampening if moving away from center too fast
        if (bodyNode.vx !== undefined) {
            const distVX = centerX - bodyNode.x;
            // Assist velocity towards center slightly
            bodyNode.vx += distVX * 0.005;
        }
        if (bodyNode.vy !== undefined) {
            const distVY = centerY - bodyNode.y;
            // Assist velocity towards center slightly
            bodyNode.vy += distVY * 0.005;
        }

        if (newX < minX) { newX = minX; changed = true; }
        if (newX > maxX) { newX = maxX; changed = true; }
        if (newY < minY) { newY = minY; changed = true; }
        if (newY > maxY) { newY = maxY; changed = true; }

        if (changed) {
            bodyNode.x = newX;
            bodyNode.y = newY;
            // Dampen velocity on boundary hit to prevent jitter
            if (bodyNode.vx !== undefined) bodyNode.vx *= 0.1;
            if (bodyNode.vy !== undefined) bodyNode.vy *= 0.1;
        }
    });
}
