// Sub-Topology Viewer JavaScript
// Displays a saved sub-topology with live status updates via Socket.IO

const socket = io();

let subTopoNetwork = null;
let subTopoNodes = new vis.DataSet([]);
let subTopoEdges = new vis.DataSet([]);
let subTopoData = null;

// Background state for canvas rendering
const bgImage = new Image();
let backgroundZoom = 100;
let backgroundOpacity = 100;
let backgroundBrightness = 100;

// ========================================
// Initialize
// ========================================
document.addEventListener('DOMContentLoaded', async () => {
    initSubTopoNetwork();
    await loadSubTopology();
    setupSocketListeners();
    setupThemeListener();
});

// ========================================
// Load Data
// ========================================
async function loadSubTopology() {
    try {
        const response = await fetch(`/api/sub-topologies/${SUB_TOPO_ID}`);
        if (!response.ok) {
            document.getElementById('sub-topo-title').textContent = 'Sub-Topology Not Found';
            return;
        }
        subTopoData = await response.json();

        document.getElementById('sub-topo-title').textContent = subTopoData.name;
        document.getElementById('sub-topo-desc').textContent = subTopoData.description || '';

        // Parse saved node positions
        if (subTopoData.node_positions) {
            try {
                subTopoData._parsedPositions = typeof subTopoData.node_positions === 'string'
                    ? JSON.parse(subTopoData.node_positions)
                    : subTopoData.node_positions;
            } catch (e) {
                subTopoData._parsedPositions = {};
            }
        } else {
            subTopoData._parsedPositions = {};
        }

        renderSubTopology();
        updateStats();

        // Prepare background image for canvas rendering
        if (subTopoData.background_image) {
            bgImage.src = subTopoData.background_image;
            backgroundZoom = subTopoData.background_zoom || 100;
            backgroundOpacity = subTopoData.background_opacity != null ? subTopoData.background_opacity : 100;
            backgroundBrightness = subTopoData.background_brightness != null ? subTopoData.background_brightness : 100;

            bgImage.onload = () => {
                if (subTopoNetwork) subTopoNetwork.redraw();
            };

            // Clear any CSS background from container
            const container = document.getElementById('sub-topo-network');
            container.style.backgroundImage = 'none';
            container.style.backgroundColor = 'transparent';
        }
    } catch (error) {
        console.error('Error loading sub-topology:', error);
    }
}

function refreshSubTopo() {
    loadSubTopology();
}

// ========================================
// Render Topology
// ========================================
function renderSubTopology() {
    if (!subTopoData) return;

    subTopoNodes.clear();
    subTopoEdges.clear();

    const devices = subTopoData.devices || [];
    const connections = subTopoData.connections || [];

    devices.forEach(device => {
        const color = getStatusColor(device.status);
        const icon = getDeviceIcon(device.device_type);
        
        // Use saved position if available
        const savedPos = subTopoData._parsedPositions ? subTopoData._parsedPositions[device.id] : null;

        if (subTopoData.theme_mode === 'premium') {
            const nodeData = {
                id: device.id,
                label: '', // Hide canvas label
                x: savedPos ? savedPos.x : 0,
                y: savedPos ? savedPos.y : 0,
                shape: 'dot',
                size: 1,
                color: {
                    background: 'rgba(0,0,0,0)',
                    border: 'rgba(0,0,0,0)',
                    highlight: { background: 'rgba(0,0,0,0)', border: 'rgba(0,0,0,0)' }
                },
                title: `${device.name} (${device.ip_address})`
            };
            subTopoNodes.add(nodeData);
            renderPremiumDOMNode(device);
        } else {
            const svgIcon = getSvgIcon(icon, color, 100);
            const nodeData = {
                id: device.id,
                label: device.name,
                title: `${icon} ${device.name}\n${device.ip_address}\nType: ${device.device_type || 'N/A'}\nLocation: ${device.location || 'N/A'}\nStatus: ${device.status}\n${device.response_time != null ? `Response: ${device.response_time}ms` : ''}`,
                shape: 'image',
                image: svgIcon,
                size: 40,
                status: device.status,
                color: {
                    background: color,
                    border: color,
                    highlight: { background: color, border: '#ffffff' }
                },
                font: {
                    multi: true,
                    size: 14,
                    color: getTextColor(),
                    bold: { size: 15 }
                }
            };
            if (savedPos) {
                nodeData.x = savedPos.x;
                nodeData.y = savedPos.y;
            }
            subTopoNodes.add(nodeData);
            
            // Remove premium node if exists
            const el = document.getElementById(`premium-node-${device.id}`);
            if (el) el.remove();
        }
    });

    // Style edges for premium
    if (subTopoData.theme_mode === 'premium') {
        subTopoNetwork.setOptions({
            edges: {
                color: { color: 'rgba(56, 189, 248, 0.5)', highlight: '#38bdf8' },
                width: 3,
                smooth: { type: 'curvedCW', roundness: 0.2 },
                shadow: { enabled: true, color: 'rgba(0,0,0,0.3)', size: 5, x: 2, y: 2 }
            }
        });
    } else {
        subTopoNetwork.setOptions({
            edges: {
                color: { color: '#999' },
                width: 2,
                smooth: { type: 'continuous' }
            }
        });
    }

    connections.forEach((conn, idx) => {
        // Determine edge color based on node statuses
        const fromDevice = devices.find(d => d.id === conn.device_id);
        const toDevice = devices.find(d => d.id === conn.connected_to);
        let edgeColor = '#999';
        if (fromDevice && toDevice) {
            if (fromDevice.status === 'down' || toDevice.status === 'down') {
                edgeColor = '#ef4444';
            } else if (fromDevice.status === 'slow' || toDevice.status === 'slow') {
                edgeColor = '#f59e0b';
            } else if (fromDevice.status === 'up' && toDevice.status === 'up') {
                edgeColor = '#10b981';
            }
        }

        subTopoEdges.add({
            id: `edge_${idx}`,
            from: conn.device_id,
            to: conn.connected_to,
            color: { color: edgeColor, highlight: '#3b82f6' },
            width: 2,
            smooth: { type: 'continuous' }
        });
    });

    // If all nodes have saved positions, lock the view completely
    const allHavePositions = devices.length > 0 && devices.every(d => {
        const pos = subTopoData._parsedPositions ? subTopoData._parsedPositions[d.id] : null;
        return pos != null;
    });

    if (allHavePositions && subTopoNetwork) {
        subTopoNetwork.setOptions({
            physics: { enabled: false },
            interaction: {
                dragNodes: false,
                dragView: false,
                zoomView: false,
                navigationButtons: false
            }
        });
    }

    setTimeout(() => {
        if (subTopoNetwork) fitSubTopoCentered();
    }, 500);
}

function updateStats() {
    if (!subTopoData) return;
    const devices = subTopoData.devices || [];
    const online = devices.filter(d => d.status === 'up').length;
    const slow = devices.filter(d => d.status === 'slow').length;
    const offline = devices.filter(d => d.status === 'down').length;

    const statsEl = document.getElementById('device-stats');
    statsEl.innerHTML = `
        <span class="device-stat-badge badge-total">📊 ${devices.length} devices</span>
        <span class="device-stat-badge badge-online">✅ ${online} online</span>
        <span class="device-stat-badge badge-slow">⚠️ ${slow} slow</span>
        <span class="device-stat-badge badge-offline">❌ ${offline} offline</span>
    `;
}

// ========================================
// Vis.js Network
// ========================================
function initSubTopoNetwork() {
    const container = document.getElementById('sub-topo-network');
    const options = {
        interaction: {
            hover: true,
            multiselect: false,
            navigationButtons: true,
            tooltipDelay: 200
        },
        physics: {
            enabled: true,
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
                gravitationalConstant: -100,
                centralGravity: 0.05,
                springLength: 150,
                springConstant: 0.1
            },
            stabilization: {
                enabled: true,
                iterations: 200,
                updateInterval: 25,
                fit: true
            },
            maxVelocity: 50,
            minVelocity: 0.1,
            timestep: 0.5
        },
        nodes: {
            shape: 'image',
            size: 40,
            font: {
                multi: true,
                size: 14,
                color: getTextColor()
            }
        },
        edges: {
            width: 2,
            color: { color: '#999' },
            smooth: { type: 'continuous' }
        }
    };

    subTopoNetwork = new vis.Network(container, { nodes: subTopoNodes, edges: subTopoEdges }, options);

    // Sync DOM overlay on every render cycle
    subTopoNetwork.on('render', syncOverlayNodes);
    subTopoNetwork.on('afterDrawing', syncOverlayNodes);

    // Selection Sync for Premium Mode
    subTopoNetwork.on('selectNode', (params) => {
        if (subTopoData && subTopoData.theme_mode === 'premium') {
            syncPremiumSelection();
        }
    });
    subTopoNetwork.on('deselectNode', () => {
        if (subTopoData && subTopoData.theme_mode === 'premium') {
            syncPremiumSelection();
        }
    });

    // Also sync on click to catch edge cases
    subTopoNetwork.on('click', () => {
        if (subTopoData && subTopoData.theme_mode === 'premium') {
            syncPremiumSelection();
        }
    });

    // Render background on canvas before drawing nodes/edges
    subTopoNetwork.on('beforeDrawing', (ctx) => {
        // Draw background color (matching the theme)
        const theme = document.documentElement.getAttribute('data-theme') || 'dark';
        ctx.fillStyle = theme === 'dark' ? '#111827' : '#f8fafc';
        const canvas = ctx.canvas;
        // Use a large enough area to cover the view even when panned
        ctx.fillRect(-10000, -10000, 20000, 20000);

        if (bgImage.complete && bgImage.src) {
            ctx.save();
            const scale = backgroundZoom / 100;
            const w = bgImage.width * scale;
            const h = bgImage.height * scale;

            // Center the image at (0,0) with opacity and brightness
            ctx.globalAlpha = backgroundOpacity / 100;
            ctx.filter = `brightness(${backgroundBrightness}%)`;

            ctx.drawImage(bgImage, -w / 2, -h / 2, w, h);
            ctx.restore();
        }
    });
}

function fitSubTopoNetwork() {
    fitSubTopoCentered();
}

/**
 * Custom fit function that keeps origin (0,0) at the center of the canvas.
 * This ensures alignment with CSS background-position: center.
 */
function fitSubTopoCentered() {
    if (!subTopoNetwork) return;

    const nodes = subTopoNodes.get();
    if (nodes.length === 0) {
        subTopoNetwork.moveTo({ position: { x: 0, y: 0 }, zoom: 1.0 });
        return;
    }

    // Calculate bounding box relative to origin (0,0)
    let maxAbsX = 0;
    let maxAbsY = 0;

    nodes.forEach(node => {
        const pos = subTopoNetwork.getPositions([node.id])[node.id];
        if (pos) {
            maxAbsX = Math.max(maxAbsX, Math.abs(pos.x) + 50); // +50 for padding/node size
            maxAbsY = Math.max(maxAbsY, Math.abs(pos.y) + 50);
        }
    });

    const container = document.getElementById('sub-topo-network');
    const cw = container.clientWidth;
    const ch = container.clientHeight;

    if (cw === 0 || ch === 0) return;

    // Zoom to fit a box of size (2*maxAbsX) x (2*maxAbsY) centered at (0,0)
    const zoomX = (cw * 0.9) / (2 * maxAbsX);
    const zoomY = (ch * 0.9) / (2 * maxAbsY);
    const zoom = Math.min(zoomX, zoomY, 2.0); // Cap zoom at 2.0x

    subTopoNetwork.moveTo({
        position: { x: 0, y: 0 },
        scale: zoom,
        animation: { duration: 500, easingFunction: 'easeInOutQuad' }
    });
}

function syncOverlayNodes() {
    if (!subTopoNetwork || !subTopoData) return;
    const container = document.getElementById('dom-overlay-container');
    if (!container) return;

    if (subTopoData.theme_mode !== 'premium') {
        container.style.display = 'none';
        return;
    }

    container.style.display = 'block';

    const nodes = subTopoNodes.get();
    const networkEl = document.getElementById('sub-topo-network');
    const overlayEl = container;
    
    // Calculate offset between network container and overlay parent
    const netRect = networkEl.getBoundingClientRect();
    const overlayRect = overlayEl.getBoundingClientRect();
    const offsetX = netRect.left - overlayRect.left;
    const offsetY = netRect.top - overlayRect.top;
    
    nodes.forEach(node => {
        const el = document.getElementById(`premium-node-${node.id}`);
        if (!el) return;

        // Get canvas position
        const pos = subTopoNetwork.getPositions([node.id])[node.id];
        if (!pos) return;

        // Convert canvas pos to DOM pos (relative to network container)
        const domPos = subTopoNetwork.canvasToDOM(pos);

        // Center the element on the glass frame
        const width = el.offsetWidth;
        const height = el.offsetHeight;
        
        // Apply offset correction so overlay aligns with canvas
        el.style.left = `${domPos.x + offsetX - (width / 2)}px`;
        el.style.top = `${domPos.y + offsetY - (height / 2)}px`;

        // Scale with zoom
        const scale = subTopoNetwork.getScale();
        el.style.transform = `scale(${Math.max(0.3, Math.min(1.5, scale))})`;
    });

    // Also ensure selection is synced during generic sync
    syncPremiumSelection();
}

/**
 * Syncs the vis.js selection state to our DOM overlay elements
 */
function syncPremiumSelection() {
    if (!subTopoNetwork || !subTopoData || subTopoData.theme_mode !== 'premium') return;
    
    const selectedIds = subTopoNetwork.getSelectedNodes();
    
    document.querySelectorAll('.dom-overlay-node').forEach(el => {
        const nodeId = el.getAttribute('data-node-id');
        if (selectedIds.includes(parseInt(nodeId))) {
            el.classList.add('selected');
        } else {
            el.classList.remove('selected');
        }
    });
}

// ========================================
// Fullscreen
// ========================================
function toggleSubTopoFullscreen() {
    const card = document.getElementById('topo-card');
    if (!document.fullscreenElement) {
        if (card.requestFullscreen) card.requestFullscreen();
        else if (card.webkitRequestFullscreen) card.webkitRequestFullscreen();
        else if (card.mozRequestFullScreen) card.mozRequestFullScreen();
    } else {
        if (document.exitFullscreen) document.exitFullscreen();
        else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
        else if (document.mozCancelFullScreen) document.mozCancelFullScreen();
    }
}

document.addEventListener('fullscreenchange', handleSubTopoFullscreenChange);
document.addEventListener('webkitfullscreenchange', handleSubTopoFullscreenChange);
document.addEventListener('mozfullscreenchange', handleSubTopoFullscreenChange);
document.addEventListener('MSFullscreenChange', handleSubTopoFullscreenChange);

function handleSubTopoFullscreenChange() {
    const container = document.getElementById('sub-topo-network');
    const isFs = !!document.fullscreenElement;

    if (isFs) {
        // Remove inline height constraints so CSS fullscreen rules take effect
        container.style.height = '100%';
        container.style.minHeight = '0';
    } else {
        // Restore normal height (unset inline so CSS calc() takes over)
        container.style.height = '';
        container.style.minHeight = '';
    }

    // Resize vis.js network at multiple intervals to ensure proper layout
    [100, 300, 600].forEach(delay => {
        setTimeout(() => {
            if (subTopoNetwork) {
                subTopoNetwork.setSize('100%', '100%');
                subTopoNetwork.redraw();
                fitSubTopoCentered();
            }
        }, delay);
    });
}

// ========================================
// Socket.IO for Live Updates
// ========================================
function setupSocketListeners() {
    let debounceTimer;

    socket.on('status_update', (data) => {
        if (!subTopoData) return;
        const device = subTopoData.devices.find(d => d.id === data.id);
        if (!device) return;

        device.status = data.status;
        device.response_time = data.response_time;

        // Update node
        const color = getStatusColor(data.status);
        const icon = getDeviceIcon(device.device_type);
        const svgIcon = getSvgIcon(icon, color, 100);

        try {
            const updateObj = {
                id: data.id,
                status: data.status,
                title: `${icon} ${device.name}\n${device.ip_address}\nType: ${device.device_type || 'N/A'}\nStatus: ${data.status}\n${data.response_time != null ? `Response: ${data.response_time}ms` : ''}`
            };

            if (subTopoData.theme_mode === 'premium') {
                // In premium mode, keep canvas node transparent and label empty
                updateObj.image = null;
                updateObj.color = { background: 'rgba(0,0,0,0)', border: 'rgba(0,0,0,0)' };
                updateObj.label = '';
            } else {
                updateObj.image = svgIcon;
                updateObj.color = { background: color, border: color, highlight: { background: color, border: '#fff' } };
                updateObj.label = device.name;
            }

            subTopoNodes.update(updateObj);

            // Update Premium DOM Node if exists
            if (subTopoData.theme_mode === 'premium') {
                renderPremiumDOMNode(device);
            }
        } catch (e) { }

        // Update edge colors
        const connections = subTopoData.connections || [];
        connections.forEach((conn, idx) => {
            if (conn.device_id === data.id || conn.connected_to === data.id) {
                const fromDevice = subTopoData.devices.find(d => d.id === conn.device_id);
                const toDevice = subTopoData.devices.find(d => d.id === conn.connected_to);
                let edgeColor = '#999';
                if (fromDevice && toDevice) {
                    if (fromDevice.status === 'down' || toDevice.status === 'down') edgeColor = '#ef4444';
                    else if (fromDevice.status === 'slow' || toDevice.status === 'slow') edgeColor = '#f59e0b';
                    else if (fromDevice.status === 'up' && toDevice.status === 'up') edgeColor = '#10b981';
                }
                try {
                    subTopoEdges.update({ id: `edge_${idx}`, color: { color: edgeColor } });
                } catch (e) { }
            }
        });

        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            updateStats();
        }, 300);
    });
}

// ========================================
// Theme
// ========================================
function getTextColor() {
    return document.documentElement.getAttribute('data-theme') === 'dark' ? '#e2e8f0' : '#1e293b';
}

function setupThemeListener() {
    const observer = new MutationObserver(() => {
        const newColor = getTextColor();
        subTopoNodes.forEach(node => {
            subTopoNodes.update({ id: node.id, font: { color: newColor } });
        });
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
}

// ========================================
// Actions
// ========================================
function editSubTopo() {
    window.location.href = `/sub-topology/${SUB_TOPO_ID}/edit`;
}

async function deleteSubTopo() {
    if (!confirm('ต้องการลบ Sub-Topology นี้หรือไม่?')) return;

    try {
        const response = await fetch(`/api/sub-topologies/${SUB_TOPO_ID}`, { method: 'DELETE' });
        const result = await response.json();
        if (result.success) {
            window.location.href = '/topology';
        } else {
            alert('Error: ' + (result.error || 'Failed to delete'));
        }
    } catch (error) {
        console.error('Delete error:', error);
        alert('Failed to delete sub-topology');
    }
}

// ========================================
// Utility
// ========================================
function getStatusColor(status) {
    switch (status) {
        case 'up': return '#10b981';
        case 'slow': return '#f59e0b';
        case 'down': return '#ef4444';
        default: return '#6b7280';
    }
}

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
        'cctv': '📹',
        'vpnrouter': '🔒',
        'dns': '🔍',
        'printer': '🖨️',
        'wlc': '📶',
        'other': '⚙️'
    };
    return icons[type] || icons['other'];
}

function getSvgIcon(emoji, color, size = 100) {
    const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 28 28">
        <circle cx="14" cy="14" r="12" fill="${color}" stroke="#ffffff" stroke-width="2" />
        <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" font-size="12" font-family="Segoe UI Emoji, Apple Color Emoji, sans-serif">${emoji}</text>
    </svg>`;
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}

// ========================================
// Premium Rendering Engine
// ========================================
function renderPremiumDOMNode(device) {
    const container = document.getElementById('dom-overlay-container');
    let el = document.getElementById(`premium-node-${device.id}`);
    
    if (!el) {
        el = document.createElement('div');
        el.id = `premium-node-${device.id}`;
        el.className = 'dom-overlay-node';
        container.appendChild(el);
        
        // Add click event to mimic vis.js behavior
        el.onclick = (e) => {
             e.stopPropagation();
             subTopoNetwork.selectNodes([device.id]);
             syncPremiumSelection();
        };
        el.setAttribute('data-node-id', device.id);
    }

    const type = (device.device_type || 'server').toLowerCase();
    const isServer = type === 'server' || type === 'vmware';
    const isSwitch = type === 'switch';
    
    // Choose Template
    let templateId = 'floating-node-template';
    if (isServer) templateId = 'wide-server-template';
    if (isSwitch) templateId = 'rackmount-hardware-template';

    const templateNode = document.getElementById(templateId);
    if (!templateNode) return;
    const template = templateNode.innerHTML;

    // Mapping Icons
    const iconMap = {
        'firewall': 'fa-shield-halved',
        'switch': 'fa-network-wired',
        'router': 'fa-globe',
        'internet': 'fa-cloud',
        'wireless': 'fa-wifi',
        'server': 'fa-server',
        'vmware': 'fa-database'
    };
    const icon = iconMap[type] || 'fa-microchip';
    const glowClass = `glow-${type}`;

    // Fill Template
    let html = template
        .replace(/{id}/g, device.id)
        .replace(/{name}/g, device.name)
        .replace(/{ip}/g, device.ip_address || 'N/A')
        .replace(/{icon}/g, icon)
        .replace(/{status}/g, device.status || 'unknown')
        .replace(/{glow-class}/g, glowClass);

    // Switch/Hardware Image path
    if (isSwitch) {
        // Use the generated switch icon
        html = html.replace(/{image_url}/g, '/static/icons/premium_switch.png');
    }

    // Dynamic metrics for visual flair
    if (isServer) {
        // Use real response time or mock for CPU visual
        const cpu = device.response_time != null ? Math.min(99, Math.max(5, device.response_time % 100)) : Math.floor(Math.random() * 20) + 5;
        const color = cpu > 80 ? 'critical' : (cpu > 50 ? 'warning' : 'healthy');
        html = html.replace(/{cpu}/g, cpu).replace(/{cpu-color}/g, color);
    }

    el.innerHTML = html;
}

