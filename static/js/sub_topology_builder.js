// Sub-Topology Builder JavaScript
// Handles device selection, preview, and drag-to-connect for sub-topology creation/editing

let allDevices = [];
let selectedDeviceIds = new Set();
let previewNetwork = null;
let previewNodes = new vis.DataSet([]);
let previewEdges = new vis.DataSet([]);
let customConnections = []; // {device_id, connected_to}
let isBuilderConnectMode = false;
let isDraggingConn = false;
let dragSourceNodeId = null;
let dragMousePos = null;
let backgroundImageUrl = null;
let backgroundZoom = 100; // percentage
let backgroundOpacity = 100; // percentage
let backgroundBrightness = 100; // percentage
let savedNodePositions = {}; // {deviceId: {x, y}}
let themeMode = 'standard'; // 'standard' or 'premium'
const previewBgImage = new Image();

// ========================================
// Initialize
// ========================================
document.addEventListener('DOMContentLoaded', async () => {
    await loadAllDevices();
    initPreviewNetwork();
    if (SUB_TOPO_ID) {
        await loadExistingSubTopology();
    }
    setupThemeListener();
});

async function loadAllDevices() {
    try {
        const response = await fetch('/api/devices');
        allDevices = await response.json();
        populateTypeFilter();
        renderDeviceList();
    } catch (error) {
        console.error('Error loading devices:', error);
    }
}

async function loadExistingSubTopology() {
    try {
        const response = await fetch(`/api/sub-topologies/${SUB_TOPO_ID}`);
        const data = await response.json();

        document.getElementById('sub-topo-name').value = data.name || '';
        document.getElementById('sub-topo-desc').value = data.description || '';
        themeMode = (data.theme_mode || 'standard').toLowerCase();

        const themeSelect = document.getElementById('theme-mode-select');
        if (themeSelect) {
            themeSelect.value = themeMode;
        }

        // Select devices
        data.devices.forEach(d => selectedDeviceIds.add(d.id));

        // Load connections
        customConnections = (data.connections || []).map(c => ({
            device_id: c.device_id,
            connected_to: c.connected_to
        }));

        // Load saved node positions
        if (data.node_positions) {
            try {
                savedNodePositions = typeof data.node_positions === 'string'
                    ? JSON.parse(data.node_positions)
                    : data.node_positions;
            } catch (e) {
                savedNodePositions = {};
            }
        }

        renderDeviceList();
        updatePreview();

        // Restore background image if saved
        if (data.background_image) {
            backgroundImageUrl = data.background_image;
            if (data.background_zoom) backgroundZoom = data.background_zoom;
            if (data.background_opacity != null) backgroundOpacity = data.background_opacity;
            if (data.background_brightness != null) backgroundBrightness = data.background_brightness;
            applyBackground(backgroundImageUrl);
        }
    } catch (error) {
        console.error('Error loading sub-topology:', error);
    }
}

// ========================================
// Device Type Filter
// ========================================
function populateTypeFilter() {
    const filter = document.getElementById('device-type-filter');
    const types = [...new Set(allDevices.map(d => d.device_type || 'other'))].sort();
    types.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t;
        opt.textContent = t.charAt(0).toUpperCase() + t.slice(1);
        filter.appendChild(opt);
    });
}

function filterDevices() {
    renderDeviceList();
}

// ========================================
// Device List Rendering
// ========================================
function renderDeviceList() {
    const container = document.getElementById('device-list');
    const search = (document.getElementById('device-search').value || '').toLowerCase();
    const typeFilter = document.getElementById('device-type-filter').value;

    let filtered = allDevices.filter(d => {
        const matchSearch = !search || d.name.toLowerCase().includes(search) || d.ip_address.toLowerCase().includes(search);
        const matchType = !typeFilter || (d.device_type || 'other') === typeFilter;
        return matchSearch && matchType;
    });

    // Group by device type
    const groups = {};
    filtered.forEach(d => {
        const type = d.device_type || 'other';
        if (!groups[type]) groups[type] = [];
        groups[type].push(d);
    });

    container.innerHTML = '';
    const sortedTypes = Object.keys(groups).sort();

    sortedTypes.forEach(type => {
        // Type group header
        const header = document.createElement('div');
        header.className = 'type-group-header';
        header.style.display = 'flex';
        header.style.alignItems = 'center';

        const icon = getDeviceIcon(type);
        const label = document.createElement('span');
        label.textContent = `${icon} ${type.toUpperCase()} (${groups[type].length})`;
        header.appendChild(label);

        // Select/Deselect all buttons
        const btns = document.createElement('div');
        btns.className = 'select-type-btns';

        const selAllBtn = document.createElement('button');
        selAllBtn.textContent = 'All';
        selAllBtn.onclick = (e) => { e.stopPropagation(); selectAllOfType(type); };
        btns.appendChild(selAllBtn);

        const deselBtn = document.createElement('button');
        deselBtn.textContent = 'None';
        deselBtn.onclick = (e) => { e.stopPropagation(); deselectAllOfType(type); };
        btns.appendChild(deselBtn);

        header.appendChild(btns);
        container.appendChild(header);

        // Devices in this group
        groups[type].forEach(device => {
            const item = document.createElement('div');
            item.className = 'device-item' + (selectedDeviceIds.has(device.id) ? ' selected' : '');
            item.onclick = () => toggleDeviceSelection(device.id);

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = selectedDeviceIds.has(device.id);
            checkbox.onclick = (e) => { e.stopPropagation(); toggleDeviceSelection(device.id); };

            const statusDot = document.createElement('div');
            statusDot.className = 'device-status-dot';
            statusDot.style.background = getStatusColor(device.status);

            const nameSpan = document.createElement('span');
            nameSpan.textContent = device.name;
            nameSpan.style.flex = '1';
            nameSpan.style.overflow = 'hidden';
            nameSpan.style.textOverflow = 'ellipsis';
            nameSpan.style.whiteSpace = 'nowrap';

            const ipSpan = document.createElement('span');
            ipSpan.textContent = device.ip_address;
            ipSpan.style.color = 'var(--text-muted)';
            ipSpan.style.fontSize = '0.75rem';

            item.appendChild(checkbox);
            item.appendChild(statusDot);
            item.appendChild(nameSpan);
            item.appendChild(ipSpan);
            container.appendChild(item);
        });
    });

    updateSelectedCount();
}

function toggleDeviceSelection(deviceId) {
    if (selectedDeviceIds.has(deviceId)) {
        selectedDeviceIds.delete(deviceId);
        // Remove connections involving this device
        customConnections = customConnections.filter(
            c => c.device_id !== deviceId && c.connected_to !== deviceId
        );
    } else {
        selectedDeviceIds.add(deviceId);
    }
    renderDeviceList();
    updatePreview();
}

function selectAllOfType(type) {
    allDevices.filter(d => (d.device_type || 'other') === type).forEach(d => selectedDeviceIds.add(d.id));
    renderDeviceList();
    updatePreview();
}

function deselectAllOfType(type) {
    const idsToRemove = allDevices.filter(d => (d.device_type || 'other') === type).map(d => d.id);
    idsToRemove.forEach(id => selectedDeviceIds.delete(id));
    customConnections = customConnections.filter(
        c => !idsToRemove.includes(c.device_id) && !idsToRemove.includes(c.connected_to)
    );
    renderDeviceList();
    updatePreview();
}

function updateSelectedCount() {
    document.getElementById('selected-count').textContent = selectedDeviceIds.size;
}

// ========================================
// Vis.js Preview Network
// ========================================
function initPreviewNetwork() {
    const container = document.getElementById('preview-network');

    // Add background to confirm visibility
    container.style.background = '#eef2ff';

    const options = {
        interaction: {
            hover: true,
            multiselect: false,
            navigationButtons: true,
            keyboard: false
        },
        physics: {
            enabled: false,
        },
        nodes: {
            shape: 'image',
            size: 40,
            font: { size: 12, color: getTextColor() }
        },
        edges: {
            width: 2,
            color: { color: '#999', highlight: '#3b82f6' },
            smooth: { type: 'continuous' }
        }
    };

    // Physics is disabled in options

    previewNetwork = new vis.Network(container, { nodes: previewNodes, edges: previewEdges }, options);

    // Render background on canvas
    previewNetwork.on('beforeDrawing', (ctx) => {
        // Draw background color (Theme-aware)
        const theme = document.documentElement.getAttribute('data-theme') || 'dark';
        ctx.fillStyle = theme === 'dark' ? '#1a1a2e' : '#f8fafc';
        ctx.fillRect(-10000, -10000, 20000, 20000);

        if (previewBgImage.complete && previewBgImage.src) {
            ctx.save();
            const scale = backgroundZoom / 100;
            const w = previewBgImage.width * scale;
            const h = previewBgImage.height * scale;

            // Apply brightness and opacity
            ctx.globalAlpha = backgroundOpacity / 100;
            ctx.filter = `brightness(${backgroundBrightness}%)`;

            ctx.drawImage(previewBgImage, -w / 2, -h / 2, w, h);
            ctx.restore();
        }
    });

    // Setup drag-to-connect
    setupBuilderConnectEvents(container);

    // After drawing, draw drag line
    previewNetwork.on('afterDrawing', (ctx) => {
        if (isDraggingConn && dragSourceNodeId !== null && dragMousePos) {
            drawDragLine(ctx);
        }
    });

    // Handle drag start to allow movement
    previewNetwork.on('dragStart', () => {
        // We can leave physics disabled to let user drag manually freely
    });

    // Sync DOM overlay on every render cycle
    previewNetwork.on('render', syncOverlayNodes);
    previewNetwork.on('afterDrawing', syncOverlayNodes);
}

function onThemeModeChange(mode) {
    themeMode = mode;
    updatePreview();
}

function syncOverlayNodes() {
    if (!previewNetwork) return;
    const container = document.getElementById('dom-overlay-container');
    if (!container) return;

    if (themeMode !== 'premium') {
        container.style.display = 'none';
        return;
    }

    container.style.display = 'block';

    const nodes = previewNodes.get();
    const networkEl = document.getElementById('preview-network');
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
        const pos = previewNetwork.getPositions([node.id])[node.id];
        if (!pos) return;

        // Convert canvas pos to DOM pos
        const domPos = previewNetwork.canvasToDOM(pos);

        // Center the element on the glass frame
        const width = el.offsetWidth;
        const height = el.offsetHeight;

        // Apply offset correction
        el.style.left = `${domPos.x + offsetX - (width / 2)}px`;
        el.style.top = `${domPos.y + offsetY - (height / 2)}px`;

        // Keep switch cards readable when the preview zooms out.
        const scale = previewNetwork.getScale();
        const isSwitchNode = !!el.querySelector('.rackmount-node');
        const effectiveScale = isSwitchNode
            ? Math.max(1.08, Math.min(1.55, scale * 1.55))
            : Math.max(0.45, Math.min(1.5, scale));
        el.style.transform = `scale(${effectiveScale})`;
    });
}

function snapshotCurrentPreviewPositions() {
    if (!previewNetwork || previewNodes.length === 0) return;

    const positions = previewNetwork.getPositions();
    Object.entries(positions || {}).forEach(([nodeId, pos]) => {
        if (pos && Number.isFinite(pos.x) && Number.isFinite(pos.y)) {
            savedNodePositions[nodeId] = { x: pos.x, y: pos.y };
        }
    });
}

function getNewNodePlacement(existingPositions, newNodeIndex, totalNewNodes) {
    if (!existingPositions.length) {
        return null;
    }

    const xs = existingPositions.map(p => p.x);
    const ys = existingPositions.map(p => p.y);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const centerY = (minY + maxY) / 2;

    const columnX = maxX + 220;
    const spacingY = 110;
    const startY = centerY - ((totalNewNodes - 1) * spacingY) / 2;

    return {
        x: columnX,
        y: startY + (newNodeIndex * spacingY)
    };
}

function cleanupStalePremiumNodes(selectedDevices) {
    const container = document.getElementById('dom-overlay-container');
    if (!container) return;

    const selectedIds = new Set((selectedDevices || []).map(d => String(d.id)));
    container.querySelectorAll('[id^="premium-node-"]').forEach(el => {
        const nodeId = String(el.getAttribute('data-node-id') || '').trim();
        if (!selectedIds.has(nodeId)) {
            el.remove();
        }
    });
}

function updatePreview() {
    snapshotCurrentPreviewPositions();

    const selectedDevices = allDevices.filter(d => selectedDeviceIds.has(d.id));
    cleanupStalePremiumNodes(selectedDevices);

    previewNodes.clear();
    previewEdges.clear();

    if (selectedDevices.length === 0) {
        const container = document.getElementById('dom-overlay-container');
        if (container) container.innerHTML = '';
        return;
    }

    const count = selectedDevices.length;
    const radius = Math.max(150, count * 30);
    const angleStep = (2 * Math.PI) / count;
    const devicesWithSavedPositions = selectedDevices.filter(d => savedNodePositions[d.id]);
    const existingPositions = devicesWithSavedPositions.map(d => savedNodePositions[d.id]);
    const devicesWithoutSavedPositions = selectedDevices.filter(d => !savedNodePositions[d.id]);
    const hasExistingLayout = existingPositions.length > 0;
    let newNodeCounter = 0;

    selectedDevices.forEach((device, index) => {
        const color = getStatusColor(device.status);
        const icon = getDeviceIcon(device.device_type);

        // Use saved position if available, otherwise circle layout
        let savedPos = savedNodePositions[device.id];
        if (!savedPos && hasExistingLayout) {
            savedPos = getNewNodePlacement(existingPositions, newNodeCounter, devicesWithoutSavedPositions.length);
            if (savedPos) {
                savedNodePositions[device.id] = savedPos;
                newNodeCounter += 1;
            }
        }

        const angle = index * angleStep;
        const nodeX = savedPos ? savedPos.x : radius * Math.cos(angle);
        const nodeY = savedPos ? savedPos.y : radius * Math.sin(angle);

        const isPremiumMode = (themeMode || '').toLowerCase() === 'premium';
        if (isPremiumMode) {
            // In premium mode, the actual vis.js node is just a transparent hit area
            previewNodes.add({
                id: device.id,
                label: null, // Forcefully hide canvas label
                x: nodeX,
                y: nodeY,
                fixed: savedPos ? { x: false, y: false } : undefined,
                shape: 'dot',
                size: 40,
                color: {
                    background: 'rgba(0,0,0,0)',
                    border: 'rgba(0,0,0,0)',
                    highlight: { background: 'rgba(0,0,0,0)', border: 'rgba(0,0,0,0)' }
                },
                font: { size: 0, color: 'rgba(0,0,0,0)' }, // Ensure canvas label is invisible
                title: `${device.name} (${device.ip_address})`
            });

            // Create/Update Premium DOM Node
            renderPremiumDOMNode(device);
        } else {
            // Standard Mode
            const svgIcon = getSvgIcon(icon, color, 40, device.device_type);
            previewNodes.add({
                id: device.id,
                label: `${icon} ${device.name}`,
                x: nodeX,
                y: nodeY,
                fixed: savedPos ? { x: false, y: false } : undefined,
                shape: 'image',
                image: svgIcon,
                size: 40,
                color: {
                    background: color,
                    border: color,
                    highlight: { background: color, border: '#fff' }
                },
                font: { color: getTextColor(), size: 12 },
                title: `${device.name}\n${device.ip_address}\nType: ${device.device_type || 'N/A'}\nStatus: ${device.status}`
            });

            // Remove premium node if exists
            const el = document.getElementById(`premium-node-${device.id}`);
            if (el) el.remove();
        }
    });

    // If premium, we might want to hide edges or style them differently
    if (themeMode === 'premium') {
        previewNetwork.setOptions({
            edges: {
                color: { color: 'rgba(56, 189, 248, 0.4)', highlight: '#38bdf8' },
                width: 2,
                smooth: false
            }
        });
    } else {
        previewNetwork.setOptions({
            edges: {
                color: { color: '#64748b', highlight: '#3b82f6' },
                width: 1,
                smooth: { enabled: true }
            }
        });
    }

    customConnections.forEach((conn, idx) => {
        if (selectedDeviceIds.has(conn.device_id) && selectedDeviceIds.has(conn.connected_to)) {
            previewEdges.add({
                id: `conn_${idx}`,
                from: conn.device_id,
                to: conn.connected_to
            });
        }
    });

    // Preserve the existing layout when editing; only brand-new topologies should use circle/physics layout.
    const allHavePositions = selectedDevices.every(d => savedNodePositions[d.id]);
    if (previewNetwork) {
        if ((allHavePositions || hasExistingLayout) && selectedDevices.length > 0) {
            // Existing layouts should stay fixed even when new devices are added.
            previewNetwork.setOptions({ physics: { enabled: false } });
            setTimeout(() => {
                fitPreviewCentered();
            }, 100);
        } else {
            // New nodes without positions — run physics briefly then freeze
            previewNetwork.setOptions({ physics: { enabled: true } });
            previewNetwork.stabilize();
            previewNetwork.once('stabilized', () => {
                fitPreviewCentered();
                previewNetwork.setOptions({ physics: { enabled: false } });
            });
        }
    }
}

function fitPreview() {
    fitPreviewCentered();
}

/**
 * Custom fit function for builder that keeps origin (0,0) at center.
 */
function fitPreviewCentered() {
    if (!previewNetwork) return;

    const nodes = previewNodes.get();
    if (nodes.length === 0) {
        previewNetwork.moveTo({ position: { x: 0, y: 0 }, zoom: 1.0 });
        return;
    }

    let maxAbsX = 0;
    let maxAbsY = 0;

    nodes.forEach(node => {
        const pos = previewNetwork.getPositions([node.id])[node.id];
        if (pos) {
            maxAbsX = Math.max(maxAbsX, Math.abs(pos.x) + 50);
            maxAbsY = Math.max(maxAbsY, Math.abs(pos.y) + 50);
        }
    });

    const container = document.getElementById('preview-network');
    const cw = container.clientWidth;
    const ch = container.clientHeight;

    if (cw === 0 || ch === 0) return;

    const zoomX = (cw * 0.9) / (2 * maxAbsX);
    const zoomY = (ch * 0.9) / (2 * maxAbsY);
    const zoom = Math.min(zoomX, zoomY, 2.0);

    previewNetwork.moveTo({
        position: { x: 0, y: 0 },
        scale: zoom,
        animation: { duration: 500, easingFunction: 'easeInOutQuad' }
    });
}

// ========================================
// Drag-to-Connect in Preview
// ========================================
function setupBuilderConnectEvents(container) {
    const canvas = container.querySelector('canvas');
    if (!canvas) return;

    canvas.addEventListener('pointerdown', (e) => {
        if (!isBuilderConnectMode) return;
        const pos = previewNetwork.DOMtoCanvas({ x: e.offsetX, y: e.offsetY });
        const nodeId = previewNetwork.getNodeAt({ x: e.offsetX, y: e.offsetY });
        if (nodeId !== undefined) {
            isDraggingConn = true;
            dragSourceNodeId = nodeId;
            dragMousePos = pos;
            previewNetwork.setOptions({ interaction: { dragNodes: false, dragView: false } });
            e.preventDefault();
        }
    });

    canvas.addEventListener('pointermove', (e) => {
        if (!isDraggingConn) return;
        dragMousePos = previewNetwork.DOMtoCanvas({ x: e.offsetX, y: e.offsetY });
        previewNetwork.redraw();
    });

    canvas.addEventListener('pointerup', (e) => {
        if (!isDraggingConn) return;
        const targetNodeId = previewNetwork.getNodeAt({ x: e.offsetX, y: e.offsetY });

        if (targetNodeId !== undefined && targetNodeId !== dragSourceNodeId) {
            // Check if connection already exists
            const exists = customConnections.some(
                c => (c.device_id === dragSourceNodeId && c.connected_to === targetNodeId) ||
                    (c.device_id === targetNodeId && c.connected_to === dragSourceNodeId)
            );
            if (!exists) {
                customConnections.push({ device_id: dragSourceNodeId, connected_to: targetNodeId });
                updatePreview();
            }
        }

        isDraggingConn = false;
        dragSourceNodeId = null;
        dragMousePos = null;
        previewNetwork.setOptions({ interaction: { dragNodes: true, dragView: true } });
        previewNetwork.redraw();
    });
}

function drawDragLine(ctx) {
    const fromPos = previewNetwork.getPositions([dragSourceNodeId])[dragSourceNodeId];
    if (!fromPos || !dragMousePos) return;

    ctx.save();
    ctx.beginPath();
    ctx.setLineDash([8, 4]);
    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth = 2;
    ctx.moveTo(fromPos.x, fromPos.y);
    ctx.lineTo(dragMousePos.x, dragMousePos.y);
    ctx.stroke();
    ctx.restore();
}

function toggleBuilderConnectMode() {
    isBuilderConnectMode = !isBuilderConnectMode;
    const banner = document.getElementById('connect-banner');
    banner.style.display = isBuilderConnectMode ? 'block' : 'none';

    if (!isBuilderConnectMode) {
        isDraggingConn = false;
        dragSourceNodeId = null;
        dragMousePos = null;
    }
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isBuilderConnectMode) {
        toggleBuilderConnectMode();
    }
});

// ========================================
// Save Sub-Topology
// ========================================
async function saveSubTopology() {
    const name = document.getElementById('sub-topo-name').value.trim();
    const description = document.getElementById('sub-topo-desc').value.trim();

    if (!name) {
        alert('กรุณาตั้งชื่อ Sub-Topology');
        return;
    }

    if (selectedDeviceIds.size === 0) {
        alert('กรุณาเลือกอย่างน้อย 1 อุปกรณ์');
        return;
    }

    // Capture current node positions from vis.js
    const positions = previewNetwork ? previewNetwork.getPositions() : {};
    const nodePositionsJson = JSON.stringify(positions);

    const payload = {
        name,
        description: description || null,
        device_ids: Array.from(selectedDeviceIds),
        connections: customConnections,
        background_image: backgroundImageUrl || '',
        background_zoom: backgroundZoom,
        background_opacity: backgroundOpacity,
        background_brightness: backgroundBrightness,
        node_positions: nodePositionsJson,
        theme_mode: themeMode
    };

    try {
        let response;
        if (SUB_TOPO_ID) {
            response = await fetch(`/api/sub-topologies/${SUB_TOPO_ID}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } else {
            response = await fetch('/api/sub-topologies', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        }

        const result = await response.json();

        if (result.success || response.ok) {
            const id = SUB_TOPO_ID || result.id;
            window.location.href = `/sub-topology/${id}`;
        } else {
            alert('Error: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Save error:', error);
        alert('Failed to save sub-topology');
    }
}

// ========================================
// Background Image Upload
// ========================================
async function uploadBackground(input) {
    const file = input.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/sub-topologies/upload-bg', {
            method: 'POST',
            body: formData
        });
        const result = await response.json();

        if (result.success) {
            backgroundImageUrl = result.url;
            applyBackground(backgroundImageUrl);
        } else {
            alert('Upload failed: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Upload error:', error);
        alert('Failed to upload background image');
    }

    // Reset input so the same file can be re-selected
    input.value = '';
}

function removeBackground() {
    backgroundImageUrl = '';
    backgroundZoom = 100;
    backgroundOpacity = 100;
    backgroundBrightness = 100;
    previewBgImage.src = '';

    const container = document.getElementById('preview-network');
    container.style.backgroundImage = 'none';
    container.style.backgroundColor = '';

    document.getElementById('remove-bg-btn').style.display = 'none';
    document.getElementById('bg-zoom-controls').style.display = 'none';
    document.getElementById('bg-opacity-controls').style.display = 'none';
    document.getElementById('bg-zoom-slider').value = 100;
    document.getElementById('bg-zoom-value').textContent = '100%';
    document.getElementById('bg-opacity-slider').value = 100;
    document.getElementById('bg-opacity-value').textContent = '100%';

    if (previewNetwork) previewNetwork.redraw();
}

function applyBackground(url) {
    backgroundImageUrl = url;
    previewBgImage.src = url;
    previewBgImage.onload = () => {
        if (previewNetwork) previewNetwork.redraw();
    };

    const container = document.getElementById('preview-network');
    container.style.backgroundImage = 'none';
    container.style.backgroundColor = 'transparent';

    document.getElementById('remove-bg-btn').style.display = 'inline-block';
    document.getElementById('bg-zoom-controls').style.display = 'inline-flex';
    document.getElementById('bg-opacity-controls').style.display = 'inline-flex';
    document.getElementById('bg-zoom-slider').value = backgroundZoom;
    document.getElementById('bg-zoom-value').textContent = backgroundZoom + '%';
    document.getElementById('bg-opacity-slider').value = backgroundOpacity;
    document.getElementById('bg-opacity-value').textContent = backgroundOpacity + '%';
    document.getElementById('bg-brightness-slider').value = backgroundBrightness;
    document.getElementById('bg-brightness-value').textContent = backgroundBrightness + '%';
}

function onBgBrightnessChange(val) {
    backgroundBrightness = parseInt(val);
    document.getElementById('bg-brightness-value').textContent = backgroundBrightness + '%';
    if (previewNetwork) previewNetwork.redraw();
}

function onBgZoomChange(val) {
    backgroundZoom = parseInt(val);
    document.getElementById('bg-zoom-value').textContent = backgroundZoom + '%';
    if (previewNetwork) previewNetwork.redraw();
}

function bgZoomIn() {
    backgroundZoom = Math.min(500, backgroundZoom + 10);
    document.getElementById('bg-zoom-slider').value = backgroundZoom;
    onBgZoomChange(backgroundZoom);
}

function bgZoomOut() {
    backgroundZoom = Math.max(10, backgroundZoom - 10);
    document.getElementById('bg-zoom-slider').value = backgroundZoom;
    onBgZoomChange(backgroundZoom);
}

function bgZoomReset() {
    backgroundZoom = 100;
    document.getElementById('bg-zoom-slider').value = 100;
    onBgZoomChange(100);
}

function onBgOpacityChange(val) {
    backgroundOpacity = parseInt(val);
    document.getElementById('bg-opacity-value').textContent = backgroundOpacity + '%';
    if (previewNetwork) previewNetwork.redraw();
}

// ========================================
// Utility Functions
// ========================================
function getTextColor() {
    return document.documentElement.getAttribute('data-theme') === 'dark' ? '#e2e8f0' : '#1e293b';
}

function applyThemeToBuilderPreview() {
    renderDeviceList();

    const container = document.getElementById('preview-network');
    if (container) {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        container.style.backgroundColor = isDark ? '#1a1a2e' : '#f8fafc';
    }

    updatePreview();

    if (previewNetwork) {
        setTimeout(() => {
            if (previewNetwork) {
                previewNetwork.redraw();
                syncOverlayNodes();
            }
        }, 0);
    }
}

function setupThemeListener() {
    const observer = new MutationObserver(() => {
        applyThemeToBuilderPreview();
    });

    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    window.addEventListener('themechange', applyThemeToBuilderPreview);
}

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
        return '/static/icons/internet_globe.svg?v=1';
    }
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
        el.style.pointerEvents = 'none'; // Let vis.js handle drag in builder
        container.appendChild(el);
    }

    const type = (device.device_type || 'server').toLowerCase();
    const isServer = type === 'server' || type === 'vmware';
    const isInternet = type === 'internet';
    const isSwitch = type === 'switch';
    const isFirewall = type === 'firewall';
    const isWireless = type === 'wireless' || type === 'wifi';

    // Choose Template
    let templateId = 'floating-node-template';
    if (isInternet) templateId = 'internet-node-template';
    if (isServer) templateId = 'wide-server-template';
    if (isSwitch || isFirewall) templateId = 'rackmount-hardware-template';
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
    if (isInternet) imageUrl = '/static/icons/internet_globe.svg?v=1';
    else if (isSwitch) imageUrl = '/static/icons/premium_switch.png?v=2';
    else if (isFirewall) imageUrl = '/static/icons/premium_firewall.svg?v=1';
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
        const cpu = Math.floor(Math.random() * 60) + 10;
        const color = cpu > 80 ? 'critical' : (cpu > 50 ? 'warning' : 'healthy');
        html = html.replace(/{cpu}/g, cpu).replace(/{cpu-color}/g, color);
    }

    el.innerHTML = html;

    // FORCE POSITION VIA JS - Bypasses all CSS Caching
    setTimeout(() => {
        if (isSwitch) {
            const title = el.querySelector('.hardware-title');
            const ip = el.querySelector('.hardware-ip');
            if (title) {
                title.style.setProperty('position', 'absolute', 'important');
                title.style.setProperty('display', 'block', 'important');
            }
            if (ip) {
                ip.style.setProperty('position', 'absolute', 'important');
                ip.style.setProperty('display', 'block', 'important');
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
            label.style.setProperty('bottom', '6px', 'important');
            label.style.setProperty('position', 'absolute', 'important');
            label.style.setProperty('display', 'block', 'important');
        }
    }, 0);
}
