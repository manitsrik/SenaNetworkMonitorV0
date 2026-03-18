/**
 * Dashboard Builder Logic
 */

let currentLayout = [];
let isEditMode = true;
let dashboardId = document.getElementById('dashboard-id').value;
let cachedData = null; // Store fetched data
let configuringIndex = -1;
let grid = null; // GridStack instance

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
        const [devices, stats, topology] = await Promise.all([
            fetch('/api/devices').then(r => r.json()),
            fetch('/api/statistics').then(r => r.json()),
            fetch('/api/topology').then(r => r.json())
        ]);
        cachedData = { devices, stats, connections: topology.connections };
    } catch (error) {
        console.error('Error fetching data:', error);
        cachedData = { devices: [], stats: {}, connections: [] }; // Fallback
    }
}

function loadDashboard(id) {
    fetch(`/api/dashboards/${id}`)
        .then(res => res.json())
        .then(data => {
            document.getElementById('dashboard-name').value = data.name;
            document.getElementById('dashboard-public').value = data.is_public ? "1" : "0";
            currentLayout = data.layout_config || [];
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
        } else if (type === 'trends' || type === 'performance' || type === 'topology' || type === 'device_grid' || type === 'device_list' || type === 'alerts' || type === 'device_pie') {
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
        margin: 6,      // Unified margin for all sides (reduced from verticalMargin: 10)
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
            layout_config: layoutToSave,
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
        <div class="form-group" style="margin-bottom: 1rem;">
            <label style="display:block; margin-bottom: 0.5rem;">Filter by Device Type</label>
            <select id="config-device-type" class="form-input">
                <option value="">All Devices (No Filter)</option>
    `;

    const Renderer = window.DashboardRenderer || DashboardRenderer;
    Array.from(types).sort().forEach(type => {
        const meta = Renderer.typeMetadata[type] || { name: type };
        const selected = (widget.config && widget.config.deviceType === type) ? 'selected' : '';
        html += `<option value="${type}" ${selected}>${meta.name || type}</option>`;
    });

    html += `</select></div>`;

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
    const newType = document.getElementById('config-device-type').value;
    const newWidth = parseInt(document.getElementById('config-width').value);
    const newHeight = parseInt(document.getElementById('config-height').value);

    widget.title = newTitle || null;
    widget.w = newWidth || 4;
    widget.h = newHeight || (widget.type === 'stat_row' || widget.type === 'stat_card' ? 2 : 4);
    
    // Also remove old properties to keep it clean
    delete widget.width;
    delete widget.height;
    
    widget.config = widget.config || {};
    widget.config.deviceType = newType || null;

    renderGrid();
    closeModal();
}
