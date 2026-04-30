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

        if (subTopoData.decorations) {
            try {
                subTopoData._parsedDecorations = typeof subTopoData.decorations === 'string'
                    ? JSON.parse(subTopoData.decorations)
                    : subTopoData.decorations;
            } catch (e) {
                subTopoData._parsedDecorations = [];
            }
        } else {
            subTopoData._parsedDecorations = [];
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

function getRackImageSize(rackU) {
    return Math.max(90, Math.min(540, 52 + ((parseInt(rackU, 10) || 1) * 12)));
}

function getRackImageUrl(rackU) {
    const unitCount = Math.max(1, parseInt(rackU, 10) || 1);
    const width = 220;
    const innerWidth = 132;
    const height = 36 + (unitCount * 14);
    const railTop = 18;
    const railBottom = height - 18;
    const slotHeight = (railBottom - railTop) / unitCount;
    const lineSegments = [];
    const labelSegments = [];

    for (let i = 0; i <= unitCount; i += 1) {
        const y = railTop + (slotHeight * i);
        lineSegments.push(`<line x1="54" y1="${y.toFixed(1)}" x2="${width - 54}" y2="${y.toFixed(1)}" stroke="rgba(56, 189, 248, 0.18)" stroke-width="1"/>`);
    }

    for (let i = 0; i < unitCount; i += 1) {
        const y = railTop + (slotHeight * i) + (slotHeight / 2) + 3;
        const label = unitCount - i;
        labelSegments.push(`<text x="30" y="${y.toFixed(1)}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="8" fill="#64748b">${label}</text>`);
        labelSegments.push(`<text x="${width - 30}" y="${y.toFixed(1)}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="8" fill="#64748b">${label}</text>`);
    }

    const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}">
        <defs>
            <linearGradient id="rackFrame" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stop-color="#1f2937"/>
                <stop offset="1" stop-color="#0f172a"/>
            </linearGradient>
            <linearGradient id="rackGlow" x1="0" x2="1" y1="0" y2="1">
                <stop offset="0" stop-color="rgba(56, 189, 248, 0.2)"/>
                <stop offset="1" stop-color="rgba(14, 165, 233, 0.04)"/>
            </linearGradient>
        </defs>
        <rect x="18" y="8" width="${width - 36}" height="${height - 16}" rx="14" fill="url(#rackGlow)" stroke="rgba(56, 189, 248, 0.18)" stroke-width="1.5"/>
        <rect x="40" y="10" width="18" height="${height - 20}" rx="8" fill="url(#rackFrame)" stroke="#475569" stroke-width="1"/>
        <rect x="${width - 58}" y="10" width="18" height="${height - 20}" rx="8" fill="url(#rackFrame)" stroke="#475569" stroke-width="1"/>
        <rect x="58" y="${railTop}" width="${innerWidth}" height="${(railBottom - railTop).toFixed(1)}" rx="8" fill="rgba(15, 23, 42, 0.24)" stroke="rgba(71, 85, 105, 0.5)" stroke-width="1"/>
        ${lineSegments.join('')}
        ${labelSegments.join('')}
        <text x="${width / 2}" y="18" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="11" font-weight="700" fill="#38bdf8">${unitCount}U RACK</text>
    </svg>`;

    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg.trim());
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
    const decorations = subTopoData._parsedDecorations || [];

    decorations.forEach(item => {
        if (item.type !== 'rack') return;

        const savedPos = subTopoData._parsedPositions ? subTopoData._parsedPositions[item.id] : null;
        const rackNode = {
            id: item.id,
            label: subTopoData.theme_mode === 'premium' ? null : `${item.rack_u || 1}U Rack`,
            x: savedPos ? savedPos.x : (Number.isFinite(item.x) ? item.x : 0),
            y: savedPos ? savedPos.y : (Number.isFinite(item.y) ? item.y : 0),
            shape: 'image',
            image: getRackImageUrl(item.rack_u || 1),
            size: getRackImageSize(item.rack_u || 1),
            font: {
                size: 11,
                color: getTextColor()
            },
            title: `Rack ${item.rack_u || 1}U`
        };

        subTopoNodes.add(rackNode);
    });

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
    const layoutNodeIds = devices.map(d => d.id).concat(decorations.map(item => item.id));
    const allHavePositions = layoutNodeIds.length > 0 && layoutNodeIds.every(id => {
        const pos = subTopoData._parsedPositions ? subTopoData._parsedPositions[id] : null;
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
        const isRackStyleNode = !!el.querySelector('.rackmount-node') || !!el.querySelector('.internet-node');
        const effectiveScale = isRackStyleNode
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
            <path d="M22 75H84c7 0 12-6 12-13 0-6-4-12-10-14-2-9-11-16-21-16-8 0-16 4-20 11-2-1-4-2-7-2-9 0-16 6-17 14-5 2-9 7-9 13 0 8 6 14 14 14h4z"
                fill="#ffffff"
                stroke="#1f5fbf"
                stroke-width="3.2"
                stroke-linecap="round"
                stroke-linejoin="round" />
            <text x="52" y="56"
                fill="#1f5fbf"
                font-family="Arial, Helvetica, sans-serif"
                font-size="8.5"
                font-weight="700"
                letter-spacing="0.55"
                text-anchor="middle">INTERNET</text>
            <circle cx="82" cy="20" r="4" fill="${color}" stroke="#ffffff" stroke-width="1.5" />
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
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 120">
        <path
            d="M30 94H146c16 0 30-13 30-29 0-13-9-25-22-28-3-19-20-35-41-35-17 0-31 8-40 23-4-2-7-3-11-3-15 0-28 11-31 26C14 50 8 58 8 68c0 14 10 26 22 26z"
            fill="#ffffff"
            stroke="#1f5fbf"
            stroke-width="4"
            stroke-linecap="round"
            stroke-linejoin="round"
        />
        <text
            x="90"
            y="67"
            fill="#1f5fbf"
            font-family="Arial, Helvetica, sans-serif"
            font-size="16.5"
            font-weight="700"
            letter-spacing="0.7"
            text-anchor="middle"
        >INTERNET</text>
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
    const isVmware = type === 'vmware';
    const isServer = type === 'server';
    const isInternet = type === 'internet';
    const isSwitch = type === 'switch';
    const isFirewall = type === 'firewall';
    const isRouter = type === 'router';
    const isVpnRouter = type === 'vpnrouter';
    const isWebsite = type === 'website' || type === 'web';
    const isWireless = type === 'wireless' || type === 'wifi';
    
    // Choose Template
    let templateId = 'floating-node-template';
    if (isInternet) templateId = 'internet-node-template';
    if (isServer || isVmware || isSwitch || isFirewall || isRouter || isVpnRouter || isWebsite) templateId = 'rackmount-hardware-template';
    if (isWireless) templateId = 'wireless-ap-template';

    const templateNode = document.getElementById(templateId);
    if (!templateNode) return;
    const template = templateNode.innerHTML;

    // Mapping Icons
    const iconMap = {
        'firewall': 'fa-shield-halved',
        'switch': 'fa-network-wired',
        'router': 'fa-globe',
        'vpnrouter': 'fa-lock',
        'website': 'fa-globe',
        'web': 'fa-globe',
        'internet': 'fa-cloud',
        'wireless': 'fa-wifi',
        'server': 'fa-server',
        'vmware': 'fa-database'
    };
    const icon = iconMap[type] || 'fa-microchip';
    const glowClass = isWebsite ? 'glow-website' : `glow-${type}`;

    let imageUrl = '';
    if (isInternet) imageUrl = getPremiumInternetImageUrl();
    else if (isServer) imageUrl = '/static/icons/premium_server.png?v=1';
    else if (isVmware) imageUrl = '/static/icons/premium_vmware.png?v=1';
    else if (isSwitch) imageUrl = '/static/icons/premium_switch.png?v=2';
    else if (isFirewall) imageUrl = '/static/icons/premium_firewall.svg?v=1';
    else if (isRouter) imageUrl = '/static/icons/premium_router.svg?v=1';
    else if (isVpnRouter) imageUrl = '/static/icons/premium_vpnrouter.svg?v=2';
    else if (isWebsite) imageUrl = '/static/icons/premium_website.svg?v=2';
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
        if (isSwitch || isRouter || isVpnRouter || isWebsite) {
            const title = el.querySelector('.hardware-title');
            const ip = el.querySelector('.hardware-ip');
            if (title) {
                title.style.setProperty('position', 'absolute', 'important');
                title.style.setProperty('display', 'block', 'important');
                title.style.setProperty('bottom', isVpnRouter ? '18px' : '8px', 'important');
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

