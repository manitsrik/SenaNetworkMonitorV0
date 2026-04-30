// Sub-Topology Builder JavaScript
// Handles device selection, preview, and drag-to-connect for sub-topology creation/editing

let allDevices = [];
let selectedDeviceIds = new Set();
let previewNetwork = null;
let previewNodes = new vis.DataSet([]);
let previewEdges = new vis.DataSet([]);
let customConnections = []; // {device_id, connected_to}
let customDecorations = []; // {id, type, rack_u, x, y}
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
const DECORATION_PREFIX = 'deco:';
const DECORATION_RACK_PREFIX = `${DECORATION_PREFIX}rack:`;

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
    updateDecorationButtons();
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

        if (data.decorations) {
            try {
                customDecorations = typeof data.decorations === 'string'
                    ? JSON.parse(data.decorations)
                    : data.decorations;
            } catch (e) {
                customDecorations = [];
            }
        } else {
            customDecorations = [];
        }

        renderDeviceList();
        updatePreview();
        updateDecorationButtons();

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

function isDecorationNodeId(nodeId) {
    return typeof nodeId === 'string' && nodeId.startsWith(DECORATION_PREFIX);
}

function isRackDecorationId(nodeId) {
    return typeof nodeId === 'string' && nodeId.startsWith(DECORATION_RACK_PREFIX);
}

function getRackImageSize(rackU) {
    return Math.max(90, Math.min(540, 52 + (rackU * 12)));
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

function getDecorationNodeIds() {
    return customDecorations.map(item => item.id);
}

function updateDecorationButtons() {
    const removeBtn = document.getElementById('remove-rack-btn');
    if (!removeBtn || !previewNetwork) return;

    const selectedRackIds = previewNetwork.getSelectedNodes().filter(isRackDecorationId);
    removeBtn.disabled = selectedRackIds.length === 0;
}

function addRackDecoration() {
    const rackSelect = document.getElementById('rack-u-select');
    const rackU = Math.max(1, parseInt(rackSelect ? rackSelect.value : '4', 10) || 4);
    const rackId = `${DECORATION_RACK_PREFIX}${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const center = previewNetwork && typeof previewNetwork.getViewPosition === 'function'
        ? previewNetwork.getViewPosition()
        : { x: 0, y: 0 };
    const offset = customDecorations.length * 36;
    const x = Math.round((center && Number.isFinite(center.x) ? center.x : 0) + offset);
    const y = Math.round((center && Number.isFinite(center.y) ? center.y : 0) + offset);

    customDecorations.push({
        id: rackId,
        type: 'rack',
        rack_u: rackU,
        x,
        y
    });
    savedNodePositions[rackId] = { x, y };

    updatePreview();
    if (previewNetwork) {
        previewNetwork.selectNodes([rackId]);
    }
    updateDecorationButtons();
}

function removeSelectedDecoration() {
    if (!previewNetwork) return;

    const selectedIds = previewNetwork.getSelectedNodes().filter(isDecorationNodeId);
    if (!selectedIds.length) return;

    const idSet = new Set(selectedIds);
    customDecorations = customDecorations.filter(item => !idSet.has(item.id));
    selectedIds.forEach(id => {
        delete savedNodePositions[id];
    });

    updatePreview();
    updateDecorationButtons();
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

    previewNetwork.on('selectNode', updateDecorationButtons);
    previewNetwork.on('deselectNode', updateDecorationButtons);
    previewNetwork.on('click', updateDecorationButtons);

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

        drawPreviewGrid(ctx);
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
        const isRackStyleNode = !!el.querySelector('.rackmount-node') || !!el.querySelector('.internet-node');
        const effectiveScale = isRackStyleNode
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

    if (selectedDevices.length === 0 && customDecorations.length === 0) {
        const container = document.getElementById('dom-overlay-container');
        if (container) container.innerHTML = '';
        updateDecorationButtons();
        return;
    }

    const isPremiumMode = (themeMode || '').toLowerCase() === 'premium';
    const count = selectedDevices.length;
    const radius = Math.max(150, count * 30);
    const angleStep = (2 * Math.PI) / count;
    const positionedDecorations = customDecorations
        .map(item => savedNodePositions[item.id] || (Number.isFinite(item.x) && Number.isFinite(item.y) ? { x: item.x, y: item.y } : null))
        .filter(Boolean);
    const devicesWithSavedPositions = selectedDevices.filter(d => savedNodePositions[d.id]);
    const existingPositions = devicesWithSavedPositions.map(d => savedNodePositions[d.id]).concat(positionedDecorations);
    const devicesWithoutSavedPositions = selectedDevices.filter(d => !savedNodePositions[d.id]);
    const hasExistingLayout = existingPositions.length > 0;
    let newNodeCounter = 0;

    customDecorations.forEach((item, index) => {
        const savedPos = savedNodePositions[item.id] || {
            x: Number.isFinite(item.x) ? item.x : index * 40,
            y: Number.isFinite(item.y) ? item.y : index * 40
        };

        savedNodePositions[item.id] = savedPos;
        previewNodes.add({
            id: item.id,
            label: isPremiumMode ? null : `${item.rack_u || 1}U Rack`,
            x: savedPos.x,
            y: savedPos.y,
            fixed: { x: false, y: false },
            shape: 'image',
            image: getRackImageUrl(item.rack_u || 1),
            size: getRackImageSize(item.rack_u || 1),
            font: { color: getTextColor(), size: 11 },
            title: `Rack ${item.rack_u || 1}U`
        });

        const el = document.getElementById(`premium-node-${item.id}`);
        if (el) el.remove();
    });

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
    const allLayoutNodeIds = selectedDevices.map(d => d.id).concat(getDecorationNodeIds());
    const allHavePositions = allLayoutNodeIds.length > 0 && allLayoutNodeIds.every(id => savedNodePositions[id]);
    if (previewNetwork) {
        if ((allHavePositions || hasExistingLayout) && allLayoutNodeIds.length > 0) {
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

    updateDecorationButtons();
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
        if (nodeId !== undefined && !isDecorationNodeId(nodeId)) {
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

        if (targetNodeId !== undefined && targetNodeId !== dragSourceNodeId && !isDecorationNodeId(targetNodeId)) {
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

    if ((e.key === 'Delete' || e.key === 'Backspace') && previewNetwork) {
        const selectedRackIds = previewNetwork.getSelectedNodes().filter(isRackDecorationId);
        if (selectedRackIds.length) {
            removeSelectedDecoration();
        }
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

    if (selectedDeviceIds.size === 0 && customDecorations.length === 0) {
        alert('Please add at least one device or rack decoration');
        return;
    }

    // Capture current node positions from vis.js
    const positions = previewNetwork ? previewNetwork.getPositions() : {};
    const nodePositionsJson = JSON.stringify(positions);
    const decorationsPayload = customDecorations.map(item => {
        const pos = positions[item.id] || savedNodePositions[item.id] || {};
        return {
            ...item,
            x: Number.isFinite(pos.x) ? pos.x : (Number.isFinite(item.x) ? item.x : 0),
            y: Number.isFinite(pos.y) ? pos.y : (Number.isFinite(item.y) ? item.y : 0)
        };
    });

    const payload = {
        name,
        description: description || null,
        device_ids: Array.from(selectedDeviceIds),
        connections: customConnections,
        decorations: decorationsPayload,
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

function drawPreviewGrid(ctx) {
    if (!previewNetwork) return;

    const container = document.getElementById('preview-network');
    if (!container) return;

    const topLeft = previewNetwork.DOMtoCanvas({ x: 0, y: 0 });
    const bottomRight = previewNetwork.DOMtoCanvas({
        x: container.clientWidth,
        y: container.clientHeight
    });

    const minX = Math.min(topLeft.x, bottomRight.x);
    const maxX = Math.max(topLeft.x, bottomRight.x);
    const minY = Math.min(topLeft.y, bottomRight.y);
    const maxY = Math.max(topLeft.y, bottomRight.y);
    const minorSpacing = 40;
    const majorSpacing = minorSpacing * 5;
    const hasBackgroundImage = Boolean(previewBgImage.complete && previewBgImage.src);
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const minorColor = isDark
        ? `rgba(148, 163, 184, ${hasBackgroundImage ? 0.08 : 0.14})`
        : `rgba(148, 163, 184, ${hasBackgroundImage ? 0.12 : 0.22})`;
    const majorColor = isDark
        ? `rgba(96, 165, 250, ${hasBackgroundImage ? 0.14 : 0.22})`
        : `rgba(59, 130, 246, ${hasBackgroundImage ? 0.16 : 0.28})`;
    const originColor = isDark
        ? 'rgba(56, 189, 248, 0.28)'
        : 'rgba(37, 99, 235, 0.32)';
    const scale = previewNetwork.getScale() || 1;
    const lineWidth = 1 / scale;

    ctx.save();
    ctx.lineWidth = lineWidth;

    for (let x = Math.floor(minX / minorSpacing) * minorSpacing; x <= maxX; x += minorSpacing) {
        if (x % majorSpacing === 0) continue;
        ctx.beginPath();
        ctx.strokeStyle = minorColor;
        ctx.moveTo(x, minY);
        ctx.lineTo(x, maxY);
        ctx.stroke();
    }

    for (let y = Math.floor(minY / minorSpacing) * minorSpacing; y <= maxY; y += minorSpacing) {
        if (y % majorSpacing === 0) continue;
        ctx.beginPath();
        ctx.strokeStyle = minorColor;
        ctx.moveTo(minX, y);
        ctx.lineTo(maxX, y);
        ctx.stroke();
    }

    for (let x = Math.floor(minX / majorSpacing) * majorSpacing; x <= maxX; x += majorSpacing) {
        ctx.beginPath();
        ctx.strokeStyle = x === 0 ? originColor : majorColor;
        ctx.moveTo(x, minY);
        ctx.lineTo(x, maxY);
        ctx.stroke();
    }

    for (let y = Math.floor(minY / majorSpacing) * majorSpacing; y <= maxY; y += majorSpacing) {
        ctx.beginPath();
        ctx.strokeStyle = y === 0 ? originColor : majorColor;
        ctx.moveTo(minX, y);
        ctx.lineTo(maxX, y);
        ctx.stroke();
    }

    ctx.restore();
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
        el.style.pointerEvents = 'none'; // Let vis.js handle drag in builder
        container.appendChild(el);
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
        const cpu = Math.floor(Math.random() * 60) + 10;
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
            label.style.setProperty('bottom', '6px', 'important');
            label.style.setProperty('position', 'absolute', 'important');
            label.style.setProperty('display', 'block', 'important');
        }
    }, 0);
}
