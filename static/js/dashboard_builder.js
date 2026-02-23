/**
 * Dashboard Builder Logic
 */

let currentLayout = [];
let isEditMode = true;
let dashboardId = document.getElementById('dashboard-id').value;
let cachedData = null; // Store fetched data

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
        const newWidget = {
            type: type,
            title: getWidgetDefaultTitleLocal(type),
            width: 4, // Default width
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
        case 'stat_card': return 'Statistic';
        case 'topology': return 'Network Topology';
        case 'device_list': return 'Device List';
        case 'alerts': return 'Active Alerts';
        default: return 'Widget';
    }
}
