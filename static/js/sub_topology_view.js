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
                label: null, // Forcefully hide canvas label
                x: savedPos ? savedPos.x : 0,
                y: savedPos ? savedPos.y : 0,
                shape: 'dot',
                size: 1,
                color: {
                    background: 'rgba(0,0,0,0)',
                    border: 'rgba(0,0,0,0)',
                    highlight: { background: 'rgba(0,0,0,0)', border: 'rgba(0,0,0,0)' }
                },
                font: { size: 0, color: 'rgba(0,0,0,0)' }, // Fail-safe hide
                title: `${device.name} (${device.ip_address})`
            };
            subTopoNodes.add(nodeData);
            renderPremiumDOMNode(device);
        } else {
            const svgIcon = getSvgIcon(icon, color, 100, device.device_type);
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

    // Style nodes and edges for premium
    if (subTopoData.theme_mode === 'premium') {
        subTopoNetwork.setOptions({
            nodes: {
                font: { size: 0, color: 'rgba(0,0,0,0)' } // Globally hide canvas labels in premium mode
            },
            edges: {
                color: { color: 'rgba(56, 189, 248, 0.5)', highlight: '#38bdf8' },
                width: 3,
                smooth: false,
                shadow: { enabled: true, color: 'rgba(0,0,0,0.3)', size: 5, x: 2, y: 2 }
            }
        });
    } else {
        subTopoNetwork.setOptions({
            nodes: {
                font: { size: 14, color: getTextColor() } // Restore labels in standard mode
            },
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
            smooth: false
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
                dragView: true,
                zoomView: true,
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

function zoomSubTopoIn() {
    zoomSubTopo(1.2);
}

function zoomSubTopoOut() {
    zoomSubTopo(0.85);
}

function zoomSubTopo(factor) {
    if (!subTopoNetwork) return;

    try {
        const currentScale = subTopoNetwork.getScale();
        const currentPosition = typeof subTopoNetwork.getViewPosition === 'function'
            ? subTopoNetwork.getViewPosition()
            : { x: 0, y: 0 };

        subTopoNetwork.moveTo({
            position: currentPosition,
            scale: Math.max(0.15, Math.min(3, currentScale * factor)),
            animation: { duration: 180, easingFunction: 'easeInOutQuad' }
        });

        setTimeout(() => syncOverlayNodes(), 200);
    } catch (e) {
        console.warn('Failed to zoom sub-topology:', e);
    }
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

        // Keep switch cards readable when the overall topology is zoomed out.
        const scale = subTopoNetwork.getScale();
        const isSwitchNode = !!el.querySelector('.rackmount-node');
        const effectiveScale = isSwitchNode
            ? Math.max(1.08, Math.min(1.55, scale * 1.55))
            : Math.max(0.45, Math.min(1.5, scale));
        el.style.transform = `scale(${effectiveScale})`;
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
        const svgIcon = getSvgIcon(icon, color, 100, device.device_type);

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
                updateObj.label = null;
                updateObj.font = { size: 0, color: 'rgba(0,0,0,0)' };
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

function applyThemeToSubTopology() {
    const container = document.getElementById('sub-topo-network');
    if (container) {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        container.style.backgroundColor = isDark ? '#111827' : '#f8fafc';
    }

    if (subTopoData) {
        renderSubTopology();
        setTimeout(() => {
            if (subTopoNetwork) {
                subTopoNetwork.redraw();
                syncOverlayNodes();
            }
        }, 0);
    } else if (subTopoNetwork) {
        subTopoNetwork.redraw();
        syncOverlayNodes();
    }
}

function setupThemeListener() {
    const observer = new MutationObserver(() => {
        applyThemeToSubTopology();
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    window.addEventListener('themechange', applyThemeToSubTopology);
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
        'internet': '☁️',
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

function getSvgIcon(emoji, color, size = 100, deviceType = 'other') {
    if ((deviceType || '').toLowerCase() === 'internet') {
        const svg = `
        <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 100 100">
            <defs>
                <linearGradient id="cloudStroke" x1="12" y1="10" x2="88" y2="68" gradientUnits="userSpaceOnUse">
                    <stop offset="0" stop-color="#9be7ff"/>
                    <stop offset="0.28" stop-color="#67d3ff"/>
                    <stop offset="0.62" stop-color="#2ea8ff"/>
                    <stop offset="1" stop-color="#2563eb"/>
                </linearGradient>
                <linearGradient id="cloudFill" x1="26" y1="24" x2="76" y2="64" gradientUnits="userSpaceOnUse">
                    <stop offset="0" stop-color="#ffffff" stop-opacity="0.28"/>
                    <stop offset="0.55" stop-color="#dbeafe" stop-opacity="0.14"/>
                    <stop offset="1" stop-color="#60a5fa" stop-opacity="0.04"/>
                </linearGradient>
                <linearGradient id="globeStroke" x1="34" y1="28" x2="66" y2="62" gradientUnits="userSpaceOnUse">
                    <stop offset="0" stop-color="#d8fbff"/>
                    <stop offset="0.22" stop-color="#67e8f9"/>
                    <stop offset="0.65" stop-color="#38bdf8"/>
                    <stop offset="1" stop-color="#2563eb"/>
                </linearGradient>
                <filter id="iconGlow" x="-30%" y="-30%" width="160%" height="170%">
                    <feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="#38bdf8" flood-opacity="0.16"/>
                    <feDropShadow dx="0" dy="5" stdDeviation="4" flood-color="#0f172a" flood-opacity="0.18"/>
                </filter>
            </defs>
            <g filter="url(#iconGlow)" fill="none" stroke-linecap="round" stroke-linejoin="round">
                <path d="M27 76H20C10 76 3 68 3 59c0-7 4-13 11-16 1-12 11-21 25-21 3 0 5 0 7 1 4-14 17-23 32-23 14 0 26 7 31 17 2 0 3 0 5 0 12 0 22 9 22 20 9 2 16 10 16 18 0 12-9 21-21 21H64" fill="url(#cloudFill)" stroke="url(#cloudStroke)" stroke-width="5.5"/>
                <path d="M28 72H21c-8 0-14-6-14-13 0-6 3-11 9-13 1-11 10-18 22-18 3 0 5 0 7 1 4-12 16-20 29-20 11 0 21 5 27 14" stroke="#e0f2fe" stroke-opacity="0.56" stroke-width="1.8"/>
                <circle cx="50" cy="48" r="18" fill="rgba(255,255,255,0.08)" stroke="url(#globeStroke)" stroke-width="3.8"/>
                <ellipse cx="50" cy="48" rx="7.5" ry="18" stroke="url(#globeStroke)" stroke-width="2.5"/>
                <ellipse cx="50" cy="48" rx="14" ry="6.5" stroke="url(#globeStroke)" stroke-width="2.5"/>
                <path d="M32 48h36M50 30v36M36 38c4 3 9 5 14 5s10-2 14-5M36 58c4-3 9-5 14-5s10 2 14 5" stroke="url(#globeStroke)" stroke-width="2.4"/>
                <circle cx="76" cy="17" r="4.8" fill="${color}" stroke="rgba(255,255,255,0.96)" stroke-width="1.8" />
            </g>
        </svg>`;
        return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    }
    const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 28 28">
        <circle cx="14" cy="14" r="12" fill="${color}" stroke="#ffffff" stroke-width="2" />
        <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" font-size="12" font-family="Segoe UI Emoji, Apple Color Emoji, sans-serif">${emoji}</text>
    </svg>`;
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}

function getPremiumInternetImageUrl() {
    const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="6 8 108 92">
        <defs>
            <linearGradient id="cloudStroke" x1="16" y1="18" x2="108" y2="82" gradientUnits="userSpaceOnUse">
                <stop offset="0" stop-color="#c8f6ff"/>
                <stop offset="0.25" stop-color="#67d3ff"/>
                <stop offset="0.62" stop-color="#38bdf8"/>
                <stop offset="1" stop-color="#2563eb"/>
            </linearGradient>
            <linearGradient id="globeStroke" x1="42" y1="34" x2="78" y2="68" gradientUnits="userSpaceOnUse">
                <stop offset="0" stop-color="#e0fbff"/>
                <stop offset="0.24" stop-color="#67e8f9"/>
                <stop offset="0.68" stop-color="#38bdf8"/>
                <stop offset="1" stop-color="#2563eb"/>
            </linearGradient>
            <filter id="glow" x="-30%" y="-30%" width="160%" height="170%">
                <feDropShadow dx="0" dy="0" stdDeviation="2.4" flood-color="#38bdf8" flood-opacity="0.12"/>
                <feDropShadow dx="0" dy="4" stdDeviation="3.4" flood-color="#0f172a" flood-opacity="0.12"/>
            </filter>
        </defs>
        <g filter="url(#glow)" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path d="M30 76h55c8 0 14-5 14-12 0-6-4-11-11-13-2-9-10-15-20-15-7 0-13 3-17 8-2-1-4-1-6-1-8 0-14 5-14 12v2c-5 2-9 7-9 12 0 8 6 14 14 14z" stroke="url(#cloudStroke)" stroke-width="5.8"/>
            <path d="M33 71h50c6 0 11-4 11-9s-4-9-10-9h-2c-2-8-9-13-17-13-6 0-11 2-15 7-2 0-3-1-5-1-6 0-11 4-11 10v2c-4 2-7 5-7 9 0 5 4 9 9 9z" stroke="#e0f2fe" stroke-opacity="0.42" stroke-width="1.7"/>
            <circle cx="58" cy="47" r="15.5" stroke="url(#globeStroke)" stroke-width="3.5"/>
            <ellipse cx="58" cy="47" rx="6.1" ry="15.5" stroke="url(#globeStroke)" stroke-width="2.2"/>
            <ellipse cx="58" cy="47" rx="12.4" ry="5.3" stroke="url(#globeStroke)" stroke-width="2.2"/>
            <path d="M43 47h30M58 32v30M48 38c3 2.7 6.4 4.1 10 4.1 3.6 0 7-1.4 10-4.1M48 56c3-2.7 6.4-4.1 10-4.1 3.6 0 7 1.4 10 4.1" stroke="url(#globeStroke)" stroke-width="1.95"/>
        </g>
    </svg>`;
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg.trim());
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
        
        // Add click event for premium details
        el.onclick = (e) => {
             e.stopPropagation();
             subTopoNetwork.selectNodes([device.id]);
             syncPremiumSelection();
             if (typeof showPremiumDeviceDetails === 'function') showPremiumDeviceDetails(device);
        };
        el.setAttribute('data-node-id', device.id);
    }

    const type = (device.device_type || 'server').toLowerCase();
    const isServer = type === 'server' || type === 'vmware';
    const isInternet = type === 'internet';
    const isSwitch = type === 'switch';
    const isFirewall = type === 'firewall';
    const isRouter = type === 'router';
    const isWireless = type === 'wireless' || type === 'wifi';
    
    // Choose Template
    let templateId = 'floating-node-template';
    if (isInternet) templateId = 'internet-node-template';
    if (isServer) templateId = 'wide-server-template';
    if (isSwitch || isFirewall || isRouter) templateId = 'rackmount-hardware-template';
    if (isWireless) templateId = 'wireless-ap-template';

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

    let imageUrl = '';
    if (isInternet) imageUrl = getPremiumInternetImageUrl();
    else if (isSwitch) imageUrl = '/static/icons/premium_switch.png?v=2';
    else if (isFirewall) imageUrl = '/static/icons/premium_firewall.svg?v=1';
    else if (isRouter) imageUrl = '/static/icons/premium_router.svg?v=1';
    else if (isWireless) imageUrl = '/static/icons/premium_wireless.svg?v=2';

    // Fill Template
    let html = template
        .replace(/{id}/g, device.id)
        .replace(/{name}/g, device.name)
        .replace(/{ip}/g, device.ip_address || 'N/A')
        .replace(/{icon}/g, icon)
        .replace(/{status}/g, device.status || 'unknown')
        .replace(/{type-label}/g, device.device_type || 'N/A')
        .replace(/{response-label}/g, device.response_time != null ? `${device.response_time}ms` : '--')
        .replace(/{glow-class}/g, glowClass)
        .replace(/{image_url}/g, imageUrl);

    // Dynamic metrics for visual flair
    if (isServer) {
        // Use real response time or mock for CPU visual
        const cpu = device.response_time != null ? Math.min(99, Math.max(5, device.response_time % 100)) : Math.floor(Math.random() * 20) + 5;
        const color = cpu > 80 ? 'critical' : (cpu > 50 ? 'warning' : 'healthy');
        html = html.replace(/{cpu}/g, cpu).replace(/{cpu-color}/g, color);
    }

    el.innerHTML = html;

    // FORCE POSITION VIA JS - Bypasses all CSS Caching
    setTimeout(() => {
        if (isSwitch || isRouter) {
            const title = el.querySelector('.hardware-title');
            const ip = el.querySelector('.hardware-ip');
            if (title) {
                title.style.setProperty('position', 'absolute', 'important');
                title.style.setProperty('display', 'block', 'important');
                title.style.setProperty('bottom', '8px', 'important');
                title.style.setProperty('top', 'auto', 'important');
            }
            if (ip) {
                ip.style.setProperty('display', 'none', 'important');
            }
            return;
        }

        if (isWireless) {
            const label = el.querySelector('.floating-label');
            if (label) {
                label.style.setProperty('position', 'absolute', 'important');
                label.style.setProperty('display', 'block', 'important');
            }
            return;
        }

        const label = el.querySelector('.floating-label');
        if (label) {
            label.style.setProperty('bottom', '8px', 'important');
            label.style.setProperty('position', 'absolute', 'important');
            label.style.setProperty('display', 'block', 'important');
        }
    }, 0);
}

