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
let isConnectMode = false; // Toggle for drag-to-connect mode

// Location type zones base configuration
const locationTypeZonesBase = {
    'cloud': { label: '☁️ CLOUD', color: 'rgba(59, 130, 246, 0.15)', borderColor: '#3b82f6' },
    'internet': { label: '🌐 INTERNET', color: 'rgba(16, 185, 129, 0.15)', borderColor: '#10b981' },
    'remote': { label: '🏢 REMOTE SITE', color: 'rgba(245, 158, 11, 0.15)', borderColor: '#f59e0b' },
    'on-premise': { label: '🏠 ON-PREMISE', color: 'rgba(99, 102, 241, 0.15)', borderColor: '#6366f1' }
};

// Dynamic zone dimensions (calculated based on device count)
let dynamicZones = {};
let onPremiseSubZones = {}; // Sub-zones within On-Premise grouped by device_type

// Sub-zone colors for device types within On-Premise
const subZoneColors = {
    'switch': { color: 'rgba(59, 130, 246, 0.12)', borderColor: '#3b82f6', label: '🔀 Switch' },
    'firewall': { color: 'rgba(239, 68, 68, 0.12)', borderColor: '#ef4444', label: '🛡️ Firewall' },
    'server': { color: 'rgba(16, 185, 129, 0.12)', borderColor: '#10b981', label: '🖥️ Server' },
    'router': { color: 'rgba(245, 158, 11, 0.12)', borderColor: '#f59e0b', label: '🌐 Router' },
    'wireless': { color: 'rgba(139, 92, 246, 0.12)', borderColor: '#8b5cf6', label: '📶 Wireless' },
    'website': { color: 'rgba(236, 72, 153, 0.12)', borderColor: '#ec4899', label: '🌐 Website' },
    'vmware': { color: 'rgba(34, 197, 94, 0.12)', borderColor: '#22c55e', label: '🖴 VMware' },
    'ippbx': { color: 'rgba(168, 85, 247, 0.12)', borderColor: '#a855f7', label: '☎️ IP PBX' },
    'vpnrouter': { color: 'rgba(20, 184, 166, 0.12)', borderColor: '#14b8a6', label: '🔒 VPN Router' },
    'dns': { color: 'rgba(249, 115, 22, 0.12)', borderColor: '#f97316', label: '🔍 DNS' },
    'other': { color: 'rgba(107, 114, 128, 0.12)', borderColor: '#6b7280', label: '⚙️ Other' }
};

// Zone sizing constants
const MIN_ZONE_WIDTH = 500;
const MIN_ZONE_HEIGHT = 400;
const DEVICE_SPACING_X = 500; // Spacing to accommodate 50px font labels
const DEVICE_SPACING_Y = 400; // Vertical spacing for 50px font labels
const ZONE_PADDING = 100;
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
        // Find device to get icon/type
        const device = allDevices.find(d => d.id === node.id);
        if (device) {
            const color = getNodeColor(device.status); // Keep current status color
            const iconEmoji = getDeviceIcon(device.device_type);
            const svgSize = isGroupedView ? 80 : 150;
            const iconSvg = getSvgIcon(iconEmoji, color, svgSize);

            nodes.update({
                id: node.id,
                shape: 'image',
                image: iconSvg,
                size: isGroupedView ? 80 : 170, // Update size
                font: {
                    size: isGroupedView ? 80 : 170, // Update font size
                    face: 'Inter, sans-serif',
                    vadjust: isGroupedView ? 0 : -5,
                    mod: isGroupedView ? '' : '',
                    color: textColor,
                    bold: {
                        size: isGroupedView ? 90 : 180,
                        vadjust: 0
                    }
                }
            });
        } else {
            // Fallback for nodes that might not match a device (shouldn't happen)
            nodes.update({
                id: node.id,
                font: {
                    color: textColor
                }
            });
        }
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
            size: 70,
            font: {
                multi: true,
                size: 100,
                face: 'Inter, sans-serif',
                mod: '',
                vadjust: -5,
                color: getTextColor(),
                bold: {
                    size: 250,
                    vadjust: 0
                }
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
                    max: 220,
                    drawThreshold: 2
                }
            }
        },
        edges: {
            width: 4,
            color: {
                color: 'rgba(71, 85, 105, 1)',
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
                gravitationalConstant: -4000,
                centralGravity: 0.01,
                springLength: 400,
                springConstant: 0.015,
                avoidOverlap: 1.0,
                damping: 0.4
            },
            stabilization: {
                enabled: true,
                iterations: 1200,
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
        }
    });

    // Draw drag connection line
    network.on('afterDrawing', (ctx) => {
        if (isConnectMode && isDraggingConnection && dragSourceNode) {
            drawConnectionLine(ctx);
        }
    });

    // Event listeners
    network.on('click', (params) => {
        if (isConnectMode) return; // Ignore clicks in connect mode

        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            showNodeInfo(nodeId);
        } else if (params.edges.length > 0) {
            const edgeId = params.edges[0];
            showEdgeOptions(edgeId);
        }
    });

    // Setup native canvas pointer events for drag-to-connect
    setupConnectModeEvents(container);

    // Hover to enlarge font
    network.on('hoverNode', (params) => {
        const nodeId = params.node;
        nodes.update({
            id: nodeId,
            size: isGroupedView ? 120 : 220, // Scale up from 80/170
            font: {
                multi: true,
                size: isGroupedView ? 120 : 220,
                face: 'Inter, sans-serif',
                mod: isGroupedView ? '' : '',
                color: getTextColor(),
                bold: {
                    size: isGroupedView ? 130 : 250
                }
            }
        });
    });

    // Reset font on blur
    network.on('blurNode', (params) => {
        const nodeId = params.node;
        nodes.update({
            id: nodeId,
            size: isGroupedView ? 80 : 170, // Reset to base size
            font: {
                multi: true,
                size: isGroupedView ? 80 : 170,
                face: 'Inter, sans-serif',
                mod: isGroupedView ? '' : '',
                color: getTextColor(),
                bold: {
                    size: isGroupedView ? 90 : 180
                }
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
        ctx.font = 'bold 80px Inter, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText(`${zone.label} (${zone.deviceCount})`, x + 15, y + 12);

        // Draw sub-zones within On-Premise
        if (zoneKey === 'on-premise' && Object.keys(onPremiseSubZones).length > 0) {
            Object.keys(onPremiseSubZones).forEach(typeKey => {
                const sub = onPremiseSubZones[typeKey];
                const subColors = subZoneColors[typeKey] || subZoneColors['other'];
                const sx = sub.x - sub.width / 2;
                const sy = sub.y - sub.height / 2;

                // Draw sub-zone background
                ctx.fillStyle = subColors.color;
                ctx.beginPath();
                const sr = 10;
                ctx.moveTo(sx + sr, sy);
                ctx.lineTo(sx + sub.width - sr, sy);
                ctx.quadraticCurveTo(sx + sub.width, sy, sx + sub.width, sy + sr);
                ctx.lineTo(sx + sub.width, sy + sub.height - sr);
                ctx.quadraticCurveTo(sx + sub.width, sy + sub.height, sx + sub.width - sr, sy + sub.height);
                ctx.lineTo(sx + sr, sy + sub.height);
                ctx.quadraticCurveTo(sx, sy + sub.height, sx, sy + sub.height - sr);
                ctx.lineTo(sx, sy + sr);
                ctx.quadraticCurveTo(sx, sy, sx + sr, sy);
                ctx.closePath();
                ctx.fill();

                // Draw sub-zone border
                ctx.strokeStyle = subColors.borderColor;
                ctx.lineWidth = 2;
                ctx.setLineDash([8, 4]);
                ctx.stroke();
                ctx.setLineDash([]);

                // Draw sub-zone label
                ctx.fillStyle = subColors.borderColor;
                ctx.font = 'bold 70px Inter, sans-serif';
                ctx.textAlign = 'left';
                ctx.textBaseline = 'top';
                ctx.fillText(`${subColors.label} (${sub.deviceCount})`, sx + 10, sy + 8);
            });
        }
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
        // set max 5 per row for Cloud, Internet, Remote
        let maxPerRow = 8;
        if (['cloud', 'internet', 'remote'].includes(key)) {
            maxPerRow = 5;
        }
        const devicesPerRow = Math.max(1, Math.min(deviceCount, maxPerRow));
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

    // Give ON-PREMISE sizing based on sub-zone layout
    if (zoneSizes['on-premise'].deviceCount > 0) {
        // Calculate sub-zone sizes first, then size on-premise to fit them
        const onPremDevices = groupedDevices['on-premise'] || [];
        const typeGroups = {};
        onPremDevices.forEach(d => {
            const t = (d.device_type || 'other').toLowerCase();
            if (!typeGroups[t]) typeGroups[t] = [];
            typeGroups[t].push(d);
        });

        const typeKeys = Object.keys(typeGroups).sort();
        const subZoneSizes = {};
        const SUB_SPACING_X = 500;
        const SUB_SPACING_Y = 450;
        const SUB_PADDING = 400;
        const SUB_LABEL_HEIGHT = 80;

        typeKeys.forEach(tk => {
            const count = typeGroups[tk].length;
            const perRow = Math.max(1, Math.min(count, 4)); // max 4 per row for all sub-zones
            const rows = Math.ceil(count / perRow);

            let w = Math.max(500, perRow * SUB_SPACING_X + SUB_PADDING * 2);
            // Force wireless frame to be wider (as if 8 cols) but keep 4 cols layout
            if (tk === 'wireless') {
                w = Math.max(500, 8 * SUB_SPACING_X + SUB_PADDING * 2);
            }

            const h = Math.max(400, rows * SUB_SPACING_Y + SUB_PADDING + SUB_LABEL_HEIGHT);
            subZoneSizes[tk] = { width: w, height: h, deviceCount: count, devicesPerRow: perRow, rows: rows };
        });

        // Arrange sub-zones in a grid (3 columns)
        const subCols = Math.min(typeKeys.length, 3);
        const subRows = Math.ceil(typeKeys.length / subCols);
        const SUB_GAP = 80;
        const ONPREM_INNER_PADDING = 150; // top padding for on-premise label

        // Find max width per column and max height per row
        const colWidths = [];
        const rowHeights = [];
        for (let c = 0; c < subCols; c++) colWidths.push(0);
        for (let r = 0; r < subRows; r++) rowHeights.push(0);

        typeKeys.forEach((tk, i) => {
            const col = i % subCols;
            const row = Math.floor(i / subCols);
            colWidths[col] = Math.max(colWidths[col], subZoneSizes[tk].width);
            rowHeights[row] = Math.max(rowHeights[row], subZoneSizes[tk].height);
        });

        const totalSubWidth = colWidths.reduce((a, b) => a + b, 0) + (subCols - 1) * SUB_GAP + SUB_PADDING * 2;
        const totalSubHeight = rowHeights.reduce((a, b) => a + b, 0) + (subRows - 1) * SUB_GAP + ONPREM_INNER_PADDING + SUB_PADDING;

        zoneSizes['on-premise'].width = Math.max(MIN_ZONE_WIDTH, totalSubWidth);
        zoneSizes['on-premise'].height = Math.max(MIN_ZONE_HEIGHT, totalSubHeight);
        zoneSizes['on-premise'].devicesPerRow = 6;
        zoneSizes['on-premise']._subZoneLayout = {
            typeKeys, subZoneSizes, colWidths, rowHeights, subCols, subRows,
            SUB_GAP, ONPREM_INNER_PADDING, SUB_PADDING, typeGroups
        };
    }

    // Use independent column widths instead of uniform width
    // Left column: cloud (top-left) + remote (bottom-left)
    // Right column: internet (top-right) + on-premise (bottom-right)
    const leftColWidth = Math.max(zoneSizes['cloud'].width, zoneSizes['remote'].width);
    const rightColWidth = Math.max(zoneSizes['internet'].width, zoneSizes['on-premise'].width);

    zoneSizes['cloud'].width = leftColWidth;
    zoneSizes['remote'].width = leftColWidth;
    zoneSizes['internet'].width = rightColWidth;
    zoneSizes['on-premise'].width = rightColWidth;

    // Calculate row heights (max height in each row)
    const topRowHeight = Math.max(zoneSizes['cloud'].height, zoneSizes['internet'].height);
    const bottomRowHeight = Math.max(zoneSizes['remote'].height, zoneSizes['on-premise'].height);

    const totalWidth = leftColWidth + rightColWidth + ZONE_GAP;
    const totalHeight = topRowHeight + bottomRowHeight + ZONE_GAP;

    // Position zones in 2x2 grid with independent column widths
    zoneSizes['cloud'].x = -totalWidth / 2 + leftColWidth / 2;
    zoneSizes['cloud'].y = -totalHeight / 2 + topRowHeight / 2;
    zoneSizes['cloud'].height = topRowHeight;

    zoneSizes['internet'].x = totalWidth / 2 - rightColWidth / 2;
    zoneSizes['internet'].y = -totalHeight / 2 + topRowHeight / 2;
    zoneSizes['internet'].height = topRowHeight;

    zoneSizes['remote'].x = -totalWidth / 2 + leftColWidth / 2;
    zoneSizes['remote'].y = totalHeight / 2 - bottomRowHeight / 2;
    zoneSizes['remote'].height = bottomRowHeight;

    zoneSizes['on-premise'].x = totalWidth / 2 - rightColWidth / 2;
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

        // Calculate sub-zone positions within On-Premise
        onPremiseSubZones = {};
        const opZone = dynamicZones['on-premise'];
        if (opZone && opZone._subZoneLayout) {
            const layout = opZone._subZoneLayout;
            const opLeft = opZone.x - opZone.width / 2;
            const opTop = opZone.y - opZone.height / 2;

            // Calculate starting position for sub-zones grid
            const totalGridWidth = layout.colWidths.reduce((a, b) => a + b, 0) + (layout.subCols - 1) * layout.SUB_GAP;
            const gridStartX = opZone.x - totalGridWidth / 2;
            const gridStartY = opTop + layout.ONPREM_INNER_PADDING;

            layout.typeKeys.forEach((tk, i) => {
                const col = i % layout.subCols;
                const row = Math.floor(i / layout.subCols);

                // Calculate x position based on column widths
                let xPos = gridStartX;
                for (let c = 0; c < col; c++) xPos += layout.colWidths[c] + layout.SUB_GAP;
                xPos += layout.colWidths[col] / 2;

                // Calculate y position based on row heights
                let yPos = gridStartY;
                for (let r = 0; r < row; r++) yPos += layout.rowHeights[r] + layout.SUB_GAP;
                yPos += layout.rowHeights[row] / 2;

                const subSize = layout.subZoneSizes[tk];
                onPremiseSubZones[tk] = {
                    x: xPos,
                    y: yPos,
                    width: layout.colWidths[col],
                    height: layout.rowHeights[row],
                    deviceCount: subSize.deviceCount,
                    devicesPerRow: subSize.devicesPerRow,
                    devices: layout.typeGroups[tk]
                };
            });
        }
    }

    // Add devices as nodes
    const deviceMap = {};
    displayDevices.forEach(d => deviceMap[d.id] = d);

    displayDevices.forEach(device => {
        const color = getNodeColor(device.status);
        const iconEmoji = getDeviceIcon(device.device_type);
        const svgSize = isGroupedView ? 80 : 150; // Increased size for Free View
        const iconSvg = getSvgIcon(iconEmoji, color, svgSize);
        const deviceType = device.device_type || 'other';
        const locType = device.location_type || 'on-premise';
        const locTypeLabel = getLocationTypeLabel(locType);

        // Calculate position if grouped view
        // Scale node size based on zone device count for zone view
        // Smaller zones get larger nodes for visibility
        let zoneNodeSize = 25;
        let zoneFontSize = 65;
        let zoneBoldSize = 70;

        let nodeOptions = {
            id: device.id,
            label: device.name,
            title: `${iconEmoji} ${device.name}\n${device.ip_address}\nType: ${deviceType}\nLocation: ${device.location || 'N/A'}\nZone: ${locTypeLabel}\nStatus: ${device.status}\n${device.response_time !== null && device.response_time !== undefined ? `Response: ${device.response_time}ms` : ''}`,
            shape: 'image',
            image: iconSvg,
            status: device.status, // Store status for edge coloring
            color: {
                background: color,
                border: color,
                highlight: {
                    background: color,
                    border: '#ffffff'
                }
            },
            size: isGroupedView ? 80 : 170, // Increased to 170 for Free View
            font: {
                multi: true,
                size: isGroupedView ? 80 : 170, // Proportional font size
                face: 'Inter, sans-serif',
                mod: isGroupedView ? '' : '',
                vadjust: isGroupedView ? 0 : -5,
                color: getTextColor(),
                bold: {
                    size: isGroupedView ? 90 : 180,
                    vadjust: 0
                }
            }
        };

        // Calculate fixed position if grouped view is enabled
        if (isGroupedView) {
            // Check if this is an on-premise device with sub-zones
            if (locType === 'on-premise' && onPremiseSubZones[deviceType]) {
                const subZone = onPremiseSubZones[deviceType];
                const devicesInSub = subZone.devices;
                const index = devicesInSub.indexOf(device);

                const subPerRow = subZone.devicesPerRow;
                const row = Math.floor(index / subPerRow);
                const col = index % subPerRow;
                const totalRows = Math.ceil(devicesInSub.length / subPerRow);

                // Position within sub-zone
                const subLabelH = 80;
                const subPad = 400;
                const availW = subZone.width - subPad * 2;
                const availH = subZone.height - subLabelH - subPad;
                const spX = subPerRow > 1 ? availW / (subPerRow - 1) : 0;
                const spY = totalRows > 1 ? Math.min(availH / (totalRows - 1), 250) : 0;

                const gW = (subPerRow - 1) * spX;
                const subTop = subZone.y - subZone.height / 2;
                const xOff = subZone.x + (col * spX) - gW / 2;
                const yOff = subTop + subLabelH + subPad / 2 + (row * spY);

                nodeOptions.x = xOff;
                nodeOptions.y = yOff;
                nodeOptions.fixed = { x: true, y: true };
            } else {
                // Standard zone positioning for non-on-premise zones
                const zone = dynamicZones[locType] || dynamicZones['on-premise'];
                const devicesInZone = groupedDevices[locType] || [];
                const index = devicesInZone.indexOf(device);

                const devicesPerRow = zone.devicesPerRow || Math.ceil(Math.sqrt(devicesInZone.length));
                const row = Math.floor(index / devicesPerRow);
                const col = index % devicesPerRow;
                const totalRows = Math.ceil(devicesInZone.length / devicesPerRow);

                const labelHeight = 50;
                const padding = 400;
                const availableWidth = zone.width - padding * 2;
                const availableHeight = zone.height - labelHeight - padding;
                const spacingX = devicesPerRow > 1 ? availableWidth / (devicesPerRow - 1) : 0;
                const maxSpacingY = 300;
                const spacingY = totalRows > 1 ? Math.min(availableHeight / (totalRows - 1), maxSpacingY) : 0;

                const gridWidth = (devicesPerRow - 1) * spacingX;

                const zoneTop = zone.y - zone.height / 2;
                const xOffset = zone.x + (col * spacingX) - gridWidth / 2;
                const yOffset = zoneTop + labelHeight + padding / 2 + (row * spacingY);

                nodeOptions.x = xOffset;
                nodeOptions.y = yOffset;
                nodeOptions.fixed = { x: true, y: true };
            }
        }
        nodes.add(nodeOptions);
    });

    // Add connections as edges (only in Free View, hidden in Zone View)
    if (!isGroupedView) {
        const edgePairCount = {};
        const nodeEdgeCount = {};

        displayConnections.forEach(conn => {
            const pairKey = [Math.min(conn.device_id, conn.connected_to), Math.max(conn.device_id, conn.connected_to)].join('-');
            if (!edgePairCount[pairKey]) edgePairCount[pairKey] = 0;
            edgePairCount[pairKey]++;

            nodeEdgeCount[conn.device_id] = (nodeEdgeCount[conn.device_id] || 0) + 1;
            nodeEdgeCount[conn.connected_to] = (nodeEdgeCount[conn.connected_to] || 0) + 1;

            const edgeIndex = edgePairCount[pairKey];

            const smoothOptions = {
                type: 'continuous',
                roundness: 0.15
            };

            edges.add({
                id: conn.id,
                from: conn.device_id,
                to: conn.connected_to,
                title: 'Click to delete connection',
                physics: true,
                smooth: smoothOptions
            });
        });
    }

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
                    gravitationalConstant: -4000,
                    centralGravity: 0.01,
                    springLength: 400,
                    springConstant: 0.015,
                    avoidOverlap: 1.0,
                    damping: 0.4
                },
                stabilization: {
                    enabled: true,
                    iterations: 1200,
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

// Generate SVG icon
function getSvgIcon(emoji, color, size = 100) {
    const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 28 28">
        <circle cx="14" cy="14" r="12" fill="${color}" stroke="#ffffff" stroke-width="2" />
        <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" font-size="12" font-family="Segoe UI Emoji, Apple Color Emoji, sans-serif">${emoji}</text>
    </svg>`;
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
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
        const iconEmoji = getDeviceIcon(device.device_type);
        const iconSvg = getSvgIcon(iconEmoji, color);
        const deviceType = device.device_type || 'other';

        nodes.update({
            id: device.id,
            label: device.name,
            title: `${iconEmoji} ${device.name}\n${device.ip_address}\nType: ${deviceType}\nStatus: ${device.status}\n${device.response_time !== null && device.response_time !== undefined ? `Response: ${device.response_time}ms` : ''}`,
            shape: 'image',
            image: iconSvg,
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

// --- Drag-to-Connect Mode (Native Canvas Pointer Events) ---

let isDraggingConnection = false;
let dragSourceNode = null;
let dragCurrentMousePos = null;

// Setup native canvas pointer events for connect mode
function setupConnectModeEvents(container) {
    const canvas = container.getElementsByTagName('canvas')[0];
    if (!canvas) {
        console.error('Canvas not found for connect mode events');
        return;
    }
    console.log('[ConnectMode] Canvas found, attaching pointer events');

    canvas.addEventListener('pointerdown', (e) => {
        if (!isConnectMode) return;

        const rect = canvas.getBoundingClientRect();
        const domPos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        const nodeId = network.getNodeAt(domPos);
        console.log('[ConnectMode] pointerdown at', domPos, 'nodeId:', nodeId);

        if (nodeId !== undefined) {
            isDraggingConnection = true;
            dragSourceNode = nodeId;
            canvas.setPointerCapture(e.pointerId); // Capture pointer for reliable tracking
            e.preventDefault();
            e.stopPropagation();
            console.log('[ConnectMode] Drag started from node:', nodeId);
        }
    }, true); // Use capture phase to intercept before vis.js

    canvas.addEventListener('pointermove', (e) => {
        if (!isConnectMode || !isDraggingConnection) return;

        // Convert DOM coordinates to canvas (world) coordinates
        const rect = canvas.getBoundingClientRect();
        const domPos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        dragCurrentMousePos = network.DOMtoCanvas(domPos);
        network.redraw(); // Trigger afterDrawing to draw the line
        e.preventDefault();
        e.stopPropagation();
    }, true);

    canvas.addEventListener('pointerup', (e) => {
        if (!isConnectMode || !isDraggingConnection) return;

        const rect = canvas.getBoundingClientRect();
        const domPos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        const targetNodeId = network.getNodeAt(domPos);
        console.log('[ConnectMode] pointerup at', domPos, 'targetNode:', targetNodeId, 'sourceNode:', dragSourceNode);

        if (targetNodeId !== undefined && targetNodeId !== dragSourceNode) {
            console.log('[ConnectMode] Creating connection:', dragSourceNode, '->', targetNodeId);
            handleDragConnect({ from: dragSourceNode, to: targetNodeId });
        }

        // Release pointer capture
        canvas.releasePointerCapture(e.pointerId);

        // Reset drag state
        isDraggingConnection = false;
        dragSourceNode = null;
        dragCurrentMousePos = null;
        network.redraw(); // Clear the line
        e.preventDefault();
        e.stopPropagation();
    }, true);
}

// Toggle connect mode on/off
function toggleConnectMode() {
    isConnectMode = !isConnectMode;

    const btn = document.querySelector('[onclick="toggleConnectMode()"]');
    const indicator = document.getElementById('connect-mode-indicator');

    if (isConnectMode) {
        // Update button style
        if (btn) {
            btn.classList.remove('btn-success');
            btn.classList.add('btn-danger');
            btn.innerHTML = '✋ Cancel Connect';
        }
        // Show indicator
        if (indicator) indicator.style.display = 'block';

        // Disable dragNodes and dragView so mouse events don't move nodes/canvas
        network.setOptions({ interaction: { dragNodes: false, dragView: false } });

    } else {
        // Reset button style
        if (btn) {
            btn.classList.remove('btn-danger');
            btn.classList.add('btn-success');
            btn.innerHTML = '➕ Add Connection';
        }
        // Hide indicator
        if (indicator) indicator.style.display = 'none';

        // Re-enable dragNodes and dragView
        network.setOptions({ interaction: { dragNodes: true, dragView: true } });

        isDraggingConnection = false;
        dragSourceNode = null;
        dragCurrentMousePos = null;
        network.redraw();
    }
}

// Draw the temporary connection line
function drawConnectionLine(ctx) {
    if (!dragSourceNode || !dragCurrentMousePos) return;

    const startPos = network.getPositions([dragSourceNode])[dragSourceNode];
    if (!startPos) return;

    ctx.beginPath();
    ctx.moveTo(startPos.x, startPos.y);
    ctx.lineTo(dragCurrentMousePos.x, dragCurrentMousePos.y);

    ctx.strokeStyle = '#ef4444'; // Red line
    ctx.lineWidth = 6;
    ctx.setLineDash([14, 8]); // Dashed line
    ctx.stroke();
    ctx.setLineDash([]); // Reset dash
}

// Handle the drag-connect edge creation
async function handleDragConnect(edgeData) {
    const fromId = edgeData.from;
    const toId = edgeData.to;

    // Validate: can't connect to self
    if (fromId === toId) {
        alert('Cannot connect a device to itself!');
        return;
    }

    // Validate: in wireless view, both devices must be wireless
    if (isWirelessView) {
        const fromDevice = allDevices.find(d => d.id === fromId);
        const toDevice = allDevices.find(d => d.id === toId);
        const fromIsWireless = fromDevice && (fromDevice.device_type || '').toLowerCase() === 'wireless';
        const toIsWireless = toDevice && (toDevice.device_type || '').toLowerCase() === 'wireless';

        if (!fromIsWireless || !toIsWireless) {
            alert('In Wireless View, only wireless devices can be connected!');
            return;
        }
    }

    // Save via API
    try {
        const response = await fetch('/api/topology/connection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                device_id: fromId,
                connected_to: toId,
                view_type: isWirelessView ? 'wireless' : 'standard'
            })
        });

        const result = await response.json();

        if (result.success) {
            loadTopologyData();
        } else {
            alert('Error: ' + (result.error || 'Failed to add connection'));
        }
    } catch (error) {
        console.error('Error adding connection:', error);
        alert('Error adding connection. Please try again.');
    }
}

// ESC key to exit connect mode
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && isConnectMode) {
        toggleConnectMode();
    }
});

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

// Listen for fullscreen change to resize network


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
    const container = document.getElementById('topology-network');
    const isFs = !!document.fullscreenElement;

    if (isFs) {
        // Remove inline height constraints so CSS fullscreen rules take effect
        container.style.height = '100%';
        container.style.minHeight = '0';
    } else {
        // Restore normal height
        container.style.height = '65vh';
        container.style.minHeight = '500px';
    }

    // Resize vis.js network at multiple intervals to ensure proper layout
    [100, 300, 600].forEach(delay => {
        setTimeout(() => {
            if (network) {
                network.setSize('100%', '100%');
                network.redraw();
                network.fit({ animation: { duration: 300, easingFunction: 'easeInOutQuad' } });
            }
        }, delay);
    });
}

// Refresh topology
function refreshTopology() {
    loadTopologyData();
}



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
