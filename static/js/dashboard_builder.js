/**
 * Dashboard Builder Logic
 */

let currentLayout = [];
let isEditMode = true;
let dashboardId = document.getElementById('dashboard-id').value;
let cachedData = null; // Store fetched data
let configuringIndex = -1;

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
        } else if (type === 'trends' || type === 'performance' || type === 'topology' || type === 'device_grid' || type === 'device_list' || type === 'alerts') {
            defaultWidth = 6;
        }

        let defaultHeight = 350;
        if (type === 'stat_row') defaultHeight = 150;
        if (type === 'stat_card') defaultHeight = 150;

        const newWidget = {
            type: type,
            title: getWidgetDefaultTitleLocal(type),
            width: defaultWidth,
            height: defaultHeight,
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
    } catch (e) {
        console.error('Error rendering grid:', e);
        container.innerHTML = `<p class="text-danger">Error rendering dashboard: ${e.message}</p>`;
    }
}

function saveDashboard() {
    const name = document.getElementById('dashboard-name').value;
    const isPublic = document.getElementById('dashboard-public').value;

    if (!name.trim()) {
        alert('Please enter a dashboard name');
        return;
    }

    const payload = {
        name: name,
        is_public: parseInt(isPublic),
        layout_config: currentLayout,
        description: '' // Optional
    };

    const method = dashboardId ? 'PUT' : 'POST';
    const url = dashboardId ? `/api/dashboards/${dashboardId}` : '/api/dashboards';

    fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                alert('Dashboard saved successfully!');
                window.location.href = '/dashboards';
            } else {
                alert('Error saving dashboard: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(err => {
            console.error(err);
            alert('Error saving dashboard');
        });
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
                <label style="display:block; margin-bottom: 0.5rem;">Width (Col 1-12)</label>
                <input type="number" id="config-width" class="form-input" value="${widget.width || 4}" min="1" max="12">
            </div>
            <div class="form-group" style="flex: 1;">
                <label style="display:block; margin-bottom: 0.5rem;">Height (Pixels)</label>
                <input type="number" id="config-height" class="form-input" value="${widget.height || 350}" min="50" step="10">
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
    widget.width = newWidth || 4;
    widget.height = newHeight || (widget.type === 'stat_row' ? 150 : 350);
    widget.config = widget.config || {};
    widget.config.deviceType = newType || null;

    renderGrid();
    closeModal();
}
