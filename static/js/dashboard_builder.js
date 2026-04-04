/**
 * Dashboard Builder Logic
 */

let currentLayout = [];
let isEditMode = true;
let dashboardId = document.getElementById('dashboard-id').value;
let cachedData = null; // Store fetched data
let cachedSubTopologies = [];
let configuringIndex = -1;
let grid = null; // GridStack instance

// Dashboard Variables state
let dashboardVariables = {
    location: true,
    deviceType: true,
    monitorType: false,
    status: false
};

function updateVariables() {
    dashboardVariables.location = document.getElementById('var-location').checked;
    dashboardVariables.deviceType = document.getElementById('var-deviceType').checked;
    dashboardVariables.monitorType = document.getElementById('var-monitorType').checked;
    dashboardVariables.status = document.getElementById('var-status').checked;
}

function loadVariablesUI(vars) {
    if (!vars) return;
    dashboardVariables = { ...dashboardVariables, ...vars };
    document.getElementById('var-location').checked = !!dashboardVariables.location;
    document.getElementById('var-deviceType').checked = !!dashboardVariables.deviceType;
    document.getElementById('var-monitorType').checked = !!dashboardVariables.monitorType;
    document.getElementById('var-status').checked = !!dashboardVariables.status;
}

document.addEventListener('DOMContentLoaded', () => {
    // Load initial data once
    fetchData().then(() => {
        if (dashboardId) {
            loadDashboard(dashboardId);
        } else {
            renderGrid();
        }
    });
});

async function fetchData() {
    try {
        // Collect specific bandwidth interface IDs from layout
        let bandwidthIds = [];
        if (currentLayout) {
            currentLayout.forEach(w => {
                if (w.type === 'bandwidth' && w.config && w.config.mode === 'specific' && w.config.deviceId && w.config.ifIndex) {
                    bandwidthIds.push(`${w.config.deviceId}:${w.config.ifIndex}`);
                }
            });
        }
        
        const bwUrl = bandwidthIds.length > 0 ? `/api/bandwidth/current?ids=${bandwidthIds.join(',')}` : '/api/bandwidth/current';

        const [devices, stats, topology, bandwidth, subTopologies] = await Promise.all([
            fetch('/api/devices').then(r => r.json()),
            fetch('/api/statistics').then(r => r.json()),
            fetch('/api/topology').then(r => r.json()),
            fetch(bwUrl).then(r => r.json()).catch(() => ({ top_interfaces: [] })),
            fetch('/api/sub-topologies').then(r => r.json()).catch(() => [])
        ]);
        cachedData = { devices, stats, connections: topology.connections, bandwidth };
        cachedSubTopologies = Array.isArray(subTopologies) ? subTopologies : [];
    } catch (error) {
        console.error('Error fetching data:', error);
        cachedData = { devices: [], stats: {}, connections: [], bandwidth: { top_interfaces: [] } }; // Fallback
        cachedSubTopologies = [];
    }
}

function loadDashboard(id) {
    fetch(`/api/dashboards/${id}`)
        .then(res => res.json())
        .then(data => {
            document.getElementById('dashboard-name').value = data.name;
            document.getElementById('dashboard-public').value = data.is_public ? "1" : "0";
            
            // Handle both old (array) and new ({widgets, variables}) format
            let config = data.layout_config || [];
            if (Array.isArray(config)) {
                currentLayout = config;
            } else {
                currentLayout = config.widgets || [];
                loadVariablesUI(config.variables);
            }
            
            renderGrid();
        })
        .catch(err => console.error(err));
}

function addWidget(type) {
    try {
        console.log('Adding widget:', type);

        // Add new widget to layout
        let defaultWidth = 4;
        if (type === 'stat_row') {
            defaultWidth = 12;
        } else if (type === 'trends' || type === 'performance' || type === 'topology' || type === 'device_grid' || type === 'device_list' || type === 'alerts' || type === 'device_pie' || type === 'bandwidth' || type === 'system_metrics' || type === 'network_traffic') {
            defaultWidth = 6;
        }

        let defaultHeight = 4; // GridStack height (rows)
        if (type === 'stat_row') defaultHeight = 2;
        if (type === 'stat_card') defaultHeight = 2;

        const newWidget = {
            id: 'w_' + Date.now(), // GridStack needs unique IDs ideally, or we track by index
            type: type,
            title: getWidgetDefaultTitleLocal(type),
            w: defaultWidth,
            h: defaultHeight,
            // x and y will be auto-assigned by GridStack if not provided
            config: {} // specific config
        };

        currentLayout.push(newWidget);
        renderGrid();
    } catch (e) {
        console.error('Error adding widget:', e);
        alert('Failed to add widget: ' + e.message);
    }
}

function removeWidget(index) {
    if (confirm('Remove this widget?')) {
        currentLayout.splice(index, 1);
        renderGrid();
    }
}

function renderGrid() {
    const container = document.getElementById('grid-canvas');

    if (!cachedData) {
        // Data not yet loaded
        fetchData().then(() => renderGrid());
        return;
    }

    // Retry mechanism for DashboardRenderer
    if (typeof window.DashboardRenderer === 'undefined' && typeof DashboardRenderer === 'undefined') {
        console.warn('DashboardRenderer not loaded yet. Attempting dynamic load...');

        // Check if we already tried to load it dynamically
        if (!window.dynamicLoadTried) {
            window.dynamicLoadTried = true;
            const script = document.createElement('script');
            script.src = '/static/js/renderer_lib.js?v=dynamic';
            script.onload = () => {
                console.log('renderer_lib.js loaded dynamically');
                renderGrid();
            };
            script.onerror = (e) => {
                console.error('Failed to load renderer_lib.js dynamically', e);
                container.innerHTML = '<p class="text-danger">Error: Could not load DashboardRenderer. Please check console.</p>';
            };
            document.body.appendChild(script);
        } else {
            // If we already tried, just wait a bit more
            setTimeout(renderGrid, 500);
        }
        return;
    }

    // Ensure we use the available one
    const Renderer = window.DashboardRenderer || DashboardRenderer;

    try {
        Renderer.renderDashboard(container, currentLayout, cachedData, true);
        initGridStack();
    } catch (e) {
        console.error('Error rendering grid:', e);
        container.innerHTML = `<p class="text-danger">Error rendering dashboard: ${e.message}</p>`;
    }
}

function initGridStack() {
    // If a grid already exists, destroy it before re-rendering
    if (grid) {
        grid.destroy(false); // false means don't remove DOM elements, just the grid behavior
    }

    grid = GridStack.init({
        cellHeight: 78, // Slightly more compact rows
        margin: 3,      // Unified margin for all sides (reduced for compactness)
        handle: '.widget-title', // drag handle
        float: true, // Allow widgets to be placed anywhere
        animate: true
    });

    // Listen for changes (drag, drop, resize)
    grid.on('change', function(event, items) {
        if (!items) return;
        
        // Update currentLayout based on new GridStack positions
        items.forEach(item => {
            const index = item.el.dataset.index;
            if (index !== undefined && currentLayout[index]) {
                currentLayout[index].x = item.x;
                currentLayout[index].y = item.y;
                currentLayout[index].w = item.w;
                currentLayout[index].h = item.h;
            }
        });
        
        // We do NOT call renderGrid() here because GridStack already updated the DOM
        // and we don't want to interrupt the user's drag/resize action.
        // We might need to tell charts to resize though.
        setTimeout(() => {
             window.dispatchEvent(new Event('resize'));
        }, 100);
    });
}

function saveDashboard() {
    try {
        const nameInput = document.getElementById('dashboard-name');
        const publicInput = document.getElementById('dashboard-public');

        if (!nameInput) {
            throw new Error('Dashboard name input element not found');
        }

        const name = nameInput.value;
        const isPublic = publicInput ? publicInput.value : "0";

        if (!name.trim()) {
            alert('Please enter a dashboard name');
            return;
        }

        console.log('Preparing to save dashboard:', name);

        // Ensure currentLayout has the latest x, y, w, h from grid before saving
        // This handles cases where widgets auto-flowed but weren't dragged
        if (grid) {
            const items = grid.getGridItems();
            items.forEach(el => {
                const node = el.gridstackNode;
                const index = el.dataset.index;
                if (node && index !== undefined && currentLayout[index]) {
                    currentLayout[index].x = node.x;
                    currentLayout[index].y = node.y;
                    currentLayout[index].w = node.w || 4;
                    currentLayout[index].h = node.h || 4;
                }
            });
        }
        
        console.log('Current layout with extracted coords:', currentLayout);

        // Deep copy layout and ensure no DOM elements or circular refs are present
        // This is a common cause of JSON.stringify failures
        let layoutToSave;
        try {
            layoutToSave = JSON.parse(JSON.stringify(currentLayout));
        } catch (e) {
            console.error('Circular reference or invalid data in layout:', e);
            throw new Error('Failed to prepare dashboard data: ' + e.message);
        }

        const payload = {
            name: name,
            is_public: parseInt(isPublic),
            layout_config: {
                widgets: layoutToSave,
                variables: { ...dashboardVariables }
            },
            description: ''
        };

        const method = dashboardId ? 'PUT' : 'POST';
        const url = dashboardId ? `/api/dashboards/${dashboardId}` : '/api/dashboards';

        console.log(`Sending ${method} request to ${url}...`);

        fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(res => {
                if (!res.ok) {
                    throw new Error(`Server responded with status ${res.status}: ${res.statusText}`);
                }
                return res.json();
            })
            .then(data => {
                console.log('Save response:', data);
                if (data.success) {
                    alert('Dashboard saved successfully!');
                    window.location.href = '/dashboards';
                } else {
                    alert('Error saving dashboard: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(err => {
                console.error('Fetch error:', err);
                alert('Connection error while saving: ' + err.message);
            });
    } catch (criticalError) {
        console.error('Critical oversight in saveDashboard:', criticalError);
        alert('Could not save dashboard: ' + criticalError.message);
    }
}

// Local fallback just in case
function getWidgetDefaultTitleLocal(type) {
    switch (type) {
        case 'gauge': return 'Response Time Gauge';
        case 'performance': return 'Performance Overview';
        case 'trends': return 'Response Trends';
        case 'stat_card': return 'Statistic';
        case 'stat_row': return 'Statistics Summary';
        case 'topology': return 'Network Topology';
        case 'device_list': return 'Device List';
        case 'device_grid': return 'Device Status Grid';
        case 'alerts': return 'Active Alerts';
        case 'activity': return 'Recent Activity';
        case 'device_pie': return 'Device Status Summary';
        case 'bandwidth': return 'Top Bandwidth';
        case 'system_metrics': return 'System Performance';
        case 'network_traffic': return 'Network Traffic';
        default: return 'Widget';
    }
}

// Configuration Modal Logic
function configureWidget(index) {
    configuringIndex = index;
    const widget = currentLayout[index];
    const modal = document.getElementById('config-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');

    modalTitle.textContent = `Configure ${widget.type.charAt(0).toUpperCase() + widget.type.slice(1)} Widget`;

    // Get unique device types from cached data
    const types = new Set();
    if (cachedData && cachedData.devices) {
        cachedData.devices.forEach(d => {
            if (d.device_type) types.add(d.device_type);
        });
    }

    // Build the form
    let html = `
        <div class="form-group" style="margin-bottom: 1rem;">
            <label style="display:block; margin-bottom: 0.5rem;">Widget Title</label>
            <input type="text" id="config-title" class="form-input" value="${widget.title || ''}" placeholder="Enter title...">
        </div>
    `;

    // 2. Filter Configuration
    const currentMode = (widget.config && widget.config.deviceId) ? 'device' : (widget.config && widget.config.deviceType) ? 'type' : 'all';
    
    html += `
        <div class="form-group" style="margin-bottom: 1rem;">
            <label style="display:block; margin-bottom: 0.5rem;">Filter Mode</label>
            <select id="config-filter-mode" class="form-input" onchange="toggleFilterMode(this.value)">
                <option value="all" ${currentMode === 'all' ? 'selected' : ''}>No Filter (All Devices)</option>
                <option value="type" ${currentMode === 'type' ? 'selected' : ''}>Filter by Device Type</option>
                <option value="device" ${currentMode === 'device' ? 'selected' : ''}>Filter by Specific Device</option>
            </select>
        </div>

        <div id="filter-type-field" style="display: ${currentMode === 'type' ? 'block' : 'none'}; margin-bottom: 1rem;">
            <label style="display:block; margin-bottom: 0.5rem;">Select Device Type</label>
            <select id="config-device-type" class="form-input">
                <option value="">-- Select Type --</option>
    `;

    const Renderer = window.DashboardRenderer || DashboardRenderer;
    Array.from(types).sort().forEach(type => {
        const meta = Renderer.typeMetadata[type] || { name: type };
        const selected = (widget.config && widget.config.deviceType === type) ? 'selected' : '';
        html += `<option value="${type}" ${selected}>${meta.name || type}</option>`;
    });

    html += `
            </select>
        </div>

        <div id="filter-device-field" style="display: ${currentMode === 'device' ? 'block' : 'none'}; margin-bottom: 1rem;">
            <label style="display:block; margin-bottom: 0.5rem;">Select Specific Device</label>
            <select id="config-device-id" class="form-input">
                <option value="">-- Select Device --</option>
    `;

    if (cachedData && cachedData.devices) {
        cachedData.devices.forEach(d => {
            const selected = (widget.config && String(widget.config.deviceId) === String(d.id)) ? 'selected' : '';
            html += `<option value="${d.id}" ${selected}>${d.name} (${d.ip_address})</option>`;
        });
    }

    html += `</select></div>`;

    // Special config for Bandwidth widget
    if (widget.type === 'bandwidth') {
        const mode = (widget.config && widget.config.mode) || 'top';
        const selectedDeviceId = (widget.config && widget.config.deviceId) || '';
        const selectedIfIndex = (widget.config && widget.config.ifIndex) || '';

        html += `
            <div class="form-group" style="margin-bottom: 1rem;">
                <label style="display:block; margin-bottom: 0.5rem;">Display Mode</label>
                <select id="config-bw-mode" class="form-input" onchange="toggleBwConfig(this.value)">
                    <option value="top" ${mode === 'top' ? 'selected' : ''}>Top Interfaces Table (Auto)</option>
                    <option value="specific" ${mode === 'specific' ? 'selected' : ''}>Specific Interface (Table)</option>
                    <option value="specific_chart" ${mode === 'specific_chart' ? 'selected' : ''}>Specific Interface (History Chart)</option>
                </select>
            </div>
            <div id="bw-specific-fields" style="display: ${mode.startsWith('specific') ? 'block' : 'none'}; border: 1px dashed var(--border-color); padding: 1rem; border-radius: 4px; margin-bottom: 1rem;">
                <div class="form-group" style="margin-bottom: 1rem;">
                    <label style="display:block; margin-bottom: 0.5rem;">Select Device (SNMP)</label>
                    <select id="config-bw-device" class="form-input" onchange="loadBwInterfaces(this.value)">
                        <option value="">-- Select Device --</option>
        `;

        if (cachedData && cachedData.devices) {
            cachedData.devices.filter(d => d.monitor_type === 'snmp').forEach(d => {
                html += `<option value="${d.id}" ${selectedDeviceId == d.id ? 'selected' : ''}>${d.name} (${d.ip_address})</option>`;
            });
        }

        html += `
                    </select>
                </div>
                <div class="form-group">
                    <label style="display:block; margin-bottom: 0.5rem;">Select Interface</label>
                    <select id="config-bw-interface" class="form-input">
                        <option value="">-- Select Interface --</option>
                    </select>
                </div>
            </div>
        `;
        
        // Inline script to handle dynamic loading and toggling (executed when modal opens)
        setTimeout(() => {
            if (selectedDeviceId) loadBwInterfaces(selectedDeviceId, selectedIfIndex);
        }, 100);
    }

    // Special config for System Metrics, Response Trends, or Network Traffic
    if (widget.type === 'system_metrics' || widget.type === 'trends' || widget.type === 'network_traffic') {
        const range = (widget.config && widget.config.minutes) || 60;
        html += `
            <div class="form-group" style="margin-bottom: 1rem;">
                <label style="display:block; margin-bottom: 0.5rem;">Default Time Range</label>
                <select id="config-minutes" class="form-input">
                    <option value="15" ${range == 15 ? 'selected' : ''}>15 Minutes</option>
                    <option value="60" ${range == 60 ? 'selected' : ''}>1 Hour</option>
                    <option value="180" ${range == 180 ? 'selected' : ''}>3 Hours</option>
                    <option value="360" ${range == 360 ? 'selected' : ''}>6 Hours</option>
                    <option value="720" ${range == 720 ? 'selected' : ''}>12 Hours</option>
                    <option value="1440" ${range == 1440 ? 'selected' : ''}>24 Hours</option>
                </select>
            </div>
        `;

        if (widget.type === 'network_traffic') {
            const selectedIfIdx = (widget.config && widget.config.ifIndex) || '';
            const selectedDevId = (widget.config && widget.config.deviceId) || '';

            html += `
                <div id="nt-interface-container" style="display: none; border: 1px dashed var(--border-color); padding: 1rem; border-radius: 4px; margin-bottom: 1rem;">
                    <div class="form-group">
                        <label style="display:block; margin-bottom: 0.5rem;">Select SNMP Interface</label>
                        <select id="config-nt-interface" class="form-input">
                            <option value="">-- Select Interface --</option>
                        </select>
                    </div>
                </div>
                <div id="nt-agent-info" style="display: none; border: 1px solid var(--primary); padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem; background: rgba(16, 185, 129, 0.05);">
                    <i class="fas fa-info-circle"></i> This device uses <strong>Agent (WinRM/SSH)</strong>. Total network traffic will be displayed.
                </div>
            `;

            // Initial load if device already selected
            setTimeout(() => {
                const devSelector = document.getElementById('config-device-id');
                if (devSelector) {
                    devSelector.onchange = (e) => handleNetworkDeviceChange(e.target.value);
                    if (selectedDevId) handleNetworkDeviceChange(selectedDevId, selectedIfIdx);
                }
            }, 100);
        }

        if (widget.type === 'system_metrics') {
            html += `
                <div class="alert alert-info" style="font-size: 0.8rem; padding: 10px; margin-bottom: 1rem; border: 1px solid var(--primary); border-radius: 4px; background: rgba(16, 185, 129, 0.1);">
                    <i class="fas fa-info-circle"></i> Requires direct device agent (WinRM/SSH) or SNMP performance monitoring.
                </div>
            `;
        }
    }

    if (widget.type === 'topology') {
        const topologyMode = (widget.config && widget.config.topologyMode) || 'main';
        const selectedSubTopologyId = (widget.config && widget.config.subTopologyId) || '';
        const renderStyle = (widget.config && widget.config.renderStyle) || 'standard';

        html += `
            <div class="form-group" style="margin-bottom: 1rem;">
                <label style="display:block; margin-bottom: 0.5rem;">Topology Source</label>
                <select id="config-topology-mode" class="form-input" onchange="toggleTopologySource(this.value)">
                    <option value="main" ${topologyMode === 'main' ? 'selected' : ''}>Main Topology</option>
                    <option value="sub_topology" ${topologyMode === 'sub_topology' ? 'selected' : ''}>Sub-Topology</option>
                </select>
            </div>
            <div id="topology-subtopology-field" style="display: ${topologyMode === 'sub_topology' ? 'block' : 'none'}; margin-bottom: 1rem;">
                <label style="display:block; margin-bottom: 0.5rem;">Select Sub-Topology</label>
                <select id="config-sub-topology-id" class="form-input">
                    <option value="">-- Select Sub-Topology --</option>
                    ${cachedSubTopologies.map(st => `<option value="${st.id}" ${String(selectedSubTopologyId) === String(st.id) ? 'selected' : ''}>${st.name}</option>`).join('')}
                </select>
            </div>
            <div class="form-group" style="margin-bottom: 1rem;">
                <label style="display:block; margin-bottom: 0.5rem;">Render Style</label>
                <select id="config-topology-render-style" class="form-input">
                    <option value="standard" ${renderStyle === 'standard' ? 'selected' : ''}>Standard</option>
                    <option value="premium3d" ${renderStyle === 'premium3d' ? 'selected' : ''}>Premium 3D</option>
                </select>
                <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.35rem;">
                    Premium 3D will use the saved layout from the selected sub-topology.
                </div>
            </div>
        `;
    }

    // Add layout controls (width and height)
    html += `
        <div style="display: flex; gap: 1rem; margin-top: 1rem;">
            <div class="form-group" style="flex: 1;">
                <label style="display:block; margin-bottom: 0.5rem;">Width (Columns, 1-12)</label>
                <input type="number" id="config-width" class="form-input" value="${widget.w || widget.width || 4}" min="1" max="12">
            </div>
            <div class="form-group" style="flex: 1;">
                <label style="display:block; margin-bottom: 0.5rem;">Height (Rows)</label>
                <input type="number" id="config-height" class="form-input" value="${widget.h || 4}" min="1" max="10">
            </div>
        </div>
    `;

    modalBody.innerHTML = html;
    modal.style.display = 'flex';
}

function closeModal() {
    document.getElementById('config-modal').style.display = 'none';
    configuringIndex = -1;
}

function saveWidgetConfig() {
    if (configuringIndex === -1) return;

    const widget = currentLayout[configuringIndex];
    const newTitle = document.getElementById('config-title').value;
    const newWidth = parseInt(document.getElementById('config-width').value);
    const newHeight = parseInt(document.getElementById('config-height').value);

    widget.title = newTitle || null;
    widget.w = newWidth || 4;
    widget.h = newHeight || (widget.type === 'stat_row' || widget.type === 'stat_card' ? 2 : 4);
    
    // Also remove old properties to keep it clean
    delete widget.width;
    delete widget.height;
    
    widget.config = widget.config || {};
    
    // Clear old filter settings first
    delete widget.config.deviceType;
    delete widget.config.deviceId;

    const filterMode = document.getElementById('config-filter-mode').value;
    if (filterMode === 'type') {
        widget.config.deviceType = document.getElementById('config-device-type').value || null;
    } else if (filterMode === 'device') {
        widget.config.deviceId = document.getElementById('config-device-id').value || null;
    }

    if (widget.type === 'bandwidth') {
        const mode = document.getElementById('config-bw-mode').value;
        widget.config.mode = mode;
        if (mode.startsWith('specific')) {
            widget.config.deviceId = document.getElementById('config-bw-device').value;
            widget.config.ifIndex = document.getElementById('config-bw-interface').value;
        } else {
            delete widget.config.deviceId;
            delete widget.config.ifIndex;
        }
    }

    if (widget.type === 'system_metrics' || widget.type === 'trends' || widget.type === 'network_traffic') {
        const mins = document.getElementById('config-minutes');
        if (mins) widget.config.minutes = parseInt(mins.value);

        if (widget.type === 'network_traffic') {
            const ifaceSelector = document.getElementById('config-nt-interface');
            if (ifaceSelector && ifaceSelector.offsetParent !== null) {
                widget.config.ifIndex = ifaceSelector.value;
            } else {
                delete widget.config.ifIndex; // Agent mode
            }
        }
    }

    if (widget.type === 'topology') {
        const topologyModeEl = document.getElementById('config-topology-mode');
        const subTopologyEl = document.getElementById('config-sub-topology-id');
        const renderStyleEl = document.getElementById('config-topology-render-style');
        widget.config.topologyMode = topologyModeEl ? topologyModeEl.value : 'main';
        widget.config.renderStyle = renderStyleEl ? renderStyleEl.value : 'standard';

        if (widget.config.topologyMode === 'sub_topology' && subTopologyEl && subTopologyEl.value) {
            widget.config.subTopologyId = subTopologyEl.value;
        } else {
            delete widget.config.subTopologyId;
        }

        if (widget.config.topologyMode !== 'sub_topology') {
            widget.config.renderStyle = 'standard';
        }
    }

    renderGrid();
    closeModal();
}

// Filter Mode Toggling
window.toggleFilterMode = function(val) {
    document.getElementById('filter-type-field').style.display = (val === 'type') ? 'block' : 'none';
    document.getElementById('filter-device-field').style.display = (val === 'device') ? 'block' : 'none';
};

window.toggleTopologySource = function(val) {
    const field = document.getElementById('topology-subtopology-field');
    if (field) field.style.display = (val === 'sub_topology') ? 'block' : 'none';
};

// Bandwidth Customization Helpers (Global scope)
window.toggleBwConfig = function(mode) {
    const fields = document.getElementById('bw-specific-fields');
    if (fields) fields.style.display = mode.startsWith('specific') ? 'block' : 'none';
};

window.loadBwInterfaces = function(deviceId, selectedIfIndex = null) {
    const selector = document.getElementById('config-bw-interface');
    if (!selector || !deviceId) return;

    selector.innerHTML = '<option value="">Loading...</option>';

    fetch(`/api/bandwidth/interfaces?device_id=${deviceId}`)
        .then(res => res.json())
        .then(data => {
            if (data.success && data.interfaces) {
                let html = '<option value="">-- Select Interface --</option>';
                data.interfaces.forEach(iface => {
                    const sel = (selectedIfIndex && selectedIfIndex == iface.if_index) ? 'selected' : '';
                    html += `<option value="${iface.if_index}" ${sel}>${iface.if_name} (${(iface.if_speed/1000000).toFixed(0)} Mbps)</option>`;
                });
                selector.innerHTML = html;
            } else {
                selector.innerHTML = '<option value="">Error loading interfaces</option>';
            }
        })
        .catch(() => {
            selector.innerHTML = '<option value="">Fetch failed</option>';
        });
};

window.handleNetworkDeviceChange = function(deviceId, selectedIfIndex = null) {
    if (!deviceId || !cachedData) return;
    const device = cachedData.devices.find(d => String(d.id) === String(deviceId));
    const ifContainer = document.getElementById('nt-interface-container');
    const agentInfo = document.getElementById('nt-agent-info');

    if (!device) return;

    if (device.monitor_type === 'snmp') {
        if (ifContainer) ifContainer.style.display = 'block';
        if (agentInfo) agentInfo.style.display = 'none';
        
        // Load interfaces
        const selector = document.getElementById('config-nt-interface');
        if (selector) {
            selector.innerHTML = '<option value="">Loading...</option>';
            fetch(`/api/bandwidth/interfaces?device_id=${deviceId}`)
                .then(res => res.json())
                .then(data => {
                    if (data.success && data.interfaces) {
                        let html = '<option value="">-- Select Interface --</option>';
                        data.interfaces.forEach(iface => {
                            const sel = (selectedIfIndex && String(selectedIfIndex) === String(iface.if_index)) ? 'selected' : '';
                            html += `<option value="${iface.if_index}" ${sel}>${iface.if_name} (${(iface.if_speed/1000000).toFixed(0)} Mbps)</option>`;
                        });
                        selector.innerHTML = html;
                    }
                });
        }
    } else {
        if (ifContainer) ifContainer.style.display = 'none';
        if (agentInfo) agentInfo.style.display = 'block';
    }
};

// Save As Template
function saveAsTemplate() {
    const name = document.getElementById('dashboard-name').value;
    if (!name.trim()) {
        alert('Please enter a dashboard name first');
        return;
    }
    
    const templateName = prompt('Template name:', name + ' Template');
    if (!templateName) return;
    
    const description = prompt('Template description (optional):', '');
    
    // Sync grid positions
    if (grid) {
        const items = grid.getGridItems();
        items.forEach(el => {
            const node = el.gridstackNode;
            const index = el.dataset.index;
            if (node && index !== undefined && currentLayout[index]) {
                currentLayout[index].x = node.x;
                currentLayout[index].y = node.y;
                currentLayout[index].w = node.w || 4;
                currentLayout[index].h = node.h || 4;
            }
        });
    }
    
    let layoutToSave;
    try {
        layoutToSave = JSON.parse(JSON.stringify(currentLayout));
    } catch (e) {
        alert('Failed to prepare template data: ' + e.message);
        return;
    }
    
    fetch('/api/dashboards/templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name: templateName,
            description: description || '',
            layout_config: JSON.stringify({
                widgets: layoutToSave,
                variables: { ...dashboardVariables }
            }),
            category: 'custom'
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            alert('Template saved successfully! \u2705');
        } else {
            alert('Error saving template: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => alert('Connection error: ' + err.message));
}
