/**
 * Dashboard Renderer
 * Responsible for rendering widgets on the dashboard.
 */

console.log('Loading DashboardRenderer...');
window.DashboardRenderer = {
    // metadata for device types
    typeMetadata: {
        'switch': { icon: '🔀', name: 'Switches', color: '#10b981' },
        'firewall': { icon: '🛡️', name: 'Firewalls', color: '#ef4444' },
        'server': { icon: '🖥️', name: 'Servers', color: '#6366f1' },
        'router': { icon: '🌐', name: 'Routers', color: '#f59e0b' },
        'wireless': { icon: '📶', name: 'Wireless', color: '#ec4899' },
        'website': { icon: '🌐', name: 'Websites', color: '#8b5cf6' },
        'vmware': { icon: '🖴', name: 'VMware', color: '#22c55e' },
        'ippbx': { icon: '☎️', name: 'IP-PBX', color: '#3b82f6' },
        'vpnrouter': { icon: '🔒', name: 'VPN Router', color: '#a855f7' },
        'dns': { icon: '🔍', name: 'DNS', color: '#0ea5e9' },
        'other': { icon: '⚙️', name: 'Other', color: '#94a3b8' }
    },

    // Store references to charts/networks to destroy them when re-rendering
    instances: {},

    /**
     * Render a list of widgets into a container
     * @param {HTMLElement} container - The grid container
     * @param {Array} layoutConfig - The layout configuration
     * @param {Object} data - The data available (devices, stats, topology)
     * @param {boolean} isEditMode - If true, adds edit controls
     */

    renderDashboard: function (container, layoutConfig, data, isEditMode = false) {
        // Check if we can do an incremental update
        if (!isEditMode && container.children.length === layoutConfig.length) {
            let structureMatch = true;
            // Simple check: ensure all widget containers exist
            for (let i = 0; i < layoutConfig.length; i++) {
                if (!document.getElementById(`widget-content-${i}`)) {
                    structureMatch = false;
                    break;
                }
            }

            if (structureMatch) {
                layoutConfig.forEach((widget, index) => {
                    const contentContainer = document.getElementById(`widget-content-${index}`);
                    this.updateWidgetContent(contentContainer, widget, data, index);
                });
                return;
            }
        }

        container.innerHTML = '';
        this.clearInstances();

        if (!layoutConfig || layoutConfig.length === 0) {

            container.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; padding: 4rem; color: var(--text-muted); border: 2px dashed var(--border-color); border-radius: 1rem;">
                    ${isEditMode ? 'Dashboard is empty. Add widgets from the sidebar.' : 'This dashboard is empty.'}
                </div>
            `;
            return;
        }

        layoutConfig.forEach((widget, index) => {
            const widgetEl = document.createElement('div');

            // Determine class configuration
            // Check if widget is a 'stat_card' row item or a regular grid item
            // The stat cards in the main dashboard are NOT in the main 12-col grid, they are in a separate flex/grid row.
            // But here we are rendering everything into one grid container.
            // We can emulate the row by making stat cards take small width.

            if (widget.type === 'stat_card') {
                // Remove the default card styling for stat cards to use the specific stat-card class
                widgetEl.className = `stat-card-wrapper w-col-${widget.width || 2}`;
                widgetEl.style.padding = '0';
                widgetEl.style.border = 'none';
                widgetEl.style.background = 'transparent';
                widgetEl.style.boxShadow = 'none';
            } else {
                widgetEl.className = `grid-widget w-col-${widget.width || 4}`; // Default width 4 (1/3)
            }

            widgetEl.dataset.index = index;
            widgetEl.id = `widget-${index}`;

            let controlsHtml = '';
            if (isEditMode) {
                controlsHtml = `
                    <div class="widget-controls" style="position: absolute; top: 5px; right: 5px; z-index: 10;">
                        <button class="widget-btn delete" onclick="removeWidget(${index})" title="Remove"><i class="fas fa-trash"></i></button>
                    </div>
                `;
            }

            // Render structure based on type
            if (widget.type === 'stat_card') {
                widgetEl.innerHTML = `${controlsHtml}<div class="widget-content" id="widget-content-${index}" style="height:100%"></div>`;
            } else {
                widgetEl.innerHTML = `
                    <div class="widget-header">
                        <div class="widget-title">${widget.title || getWidgetDefaultTitle(widget.type)}</div>
                        ${controlsHtml}
                    </div>
                    <div class="widget-content" id="widget-content-${index}"></div>
                `;
            }

            container.appendChild(widgetEl);

            // Render specific content
            const contentContainer = widgetEl.querySelector('.widget-content');
            this.renderWidgetContent(contentContainer, widget, data, index);
        });
    },



    updateWidgetContent: function (container, widget, data, index) {
        try {
            // Apply filtering if configured, same as renderWidgetContent
            let widgetData = data;
            if (widget.config && widget.config.deviceType) {
                widgetData = this.filterData(data, widget.config.deviceType);
            }

            switch (widget.type) {
                case 'topology':
                    this.updateTopology(index, widgetData, widget);
                    break;
                case 'gauge':
                case 'performance':
                    // For now, re-render these is fine, or improve later.
                    // performance re-render might flicker the list, but gauge is canvas.
                    // Let's re-render for simplicity unless user complains, 
                    // BUT for performance widget with list, re-rendering clears scroll position.
                    // Ideally we should have granular updates for all.
                    // For this task, user complained about TOPOLOGY flickering.
                    // So we can fallback to re-render for others for now.
                    container.innerHTML = '';
                    this.renderWidgetContent(container, widget, data, index);
                    break;

                case 'stat_card':
                case 'stat_row':
                case 'alerts':
                case 'activity':
                default:
                    // Text based widgets - re-rendering is usually fast and unnoticeable 
                    // unless they have scroll/input state.

                    // Alert/Activity have scroll. Re-rendering resets scroll.
                    // TODO: Implement graceful updates for lists.
                    // For now, full re-render of content.
                    container.innerHTML = '';
                    this.renderWidgetContent(container, widget, data, index);
            }
        } catch (e) {

            console.error('Error updating widget:', e);
        }
    },

    renderWidgetContent: function (container, widget, data, index) {

        try {
            // Apply filtering if configured
            let widgetData = data;
            if (widget.config && widget.config.deviceType) {
                widgetData = this.filterData(data, widget.config.deviceType);
            }

            switch (widget.type) {

                case 'gauge':
                    this.renderGauge(container, widget, widgetData, index);
                    break;
                case 'performance':
                    this.renderPerformance(container, widget, widgetData, index);
                    break;
                case 'stat_card':
                    this.renderStatCard(container, widget, widgetData);
                    break;
                case 'stat_row':
                    this.renderStatRow(container, widget, widgetData);
                    break;
                case 'topology':
                    this.renderTopology(container, widget, widgetData, index);
                    break;
                case 'device_list':
                    this.renderDeviceList(container, widget, widgetData); // Fallback
                    break;
                case 'device_grid':
                    this.renderDeviceGrid(container, widget, widgetData);
                    break;
                case 'alerts':
                    this.renderAlerts(container, widget, widgetData);
                    break;
                case 'activity':
                    this.renderActivityLog(container, widget, widgetData);
                    break;
                default:
                    container.innerHTML = `<p class="text-muted">Unknown widget type: ${widget.type}</p>`;
            }
        } catch (e) {
            console.error(`Error rendering widget ${widget.type}:`, e);
            container.innerHTML = `<p class="text-danger">Error rendering widget</p>`;
        }
    },

    /**
     * Filter data by device type and recalculate statistics
     */
    filterData: function (originalData, deviceType) {
        // filter devices
        const devices = (originalData.devices || []).filter(d =>
            (d.device_type || 'other').toLowerCase() === deviceType.toLowerCase()
        );
        const deviceIds = new Set(devices.map(d => d.id));

        // Filter connections
        const connections = (originalData.connections || []).filter(c =>
            deviceIds.has(c.device_id) && deviceIds.has(c.connected_to)
        );

        // Recalculate stats
        const stats = {
            total_devices: devices.length,
            devices_up: devices.filter(d => d.status === 'up').length,
            devices_down: devices.filter(d => d.status === 'down').length,
            devices_slow: devices.filter(d => d.status === 'slow' || (d.status === 'up' && parseFloat(d.response_time) > 500)).length,
            uptime_percentage: 0,
            average_response_time: 0
        };

        if (stats.total_devices > 0) {
            stats.uptime_percentage = Math.round(((stats.devices_up + stats.devices_slow) / stats.total_devices) * 100);

            const responseTimes = devices
                .map(d => parseFloat(d.response_time))
                .filter(t => !isNaN(t) && t > 0);

            if (responseTimes.length > 0) {
                const totalRt = responseTimes.reduce((a, b) => a + b, 0);
                stats.average_response_time = Math.round(totalRt / responseTimes.length * 100) / 100;
            }
        }

        return {
            devices: devices,
            connections: connections,
            stats: stats
        };
    },

    // ===================================
    // Specific Renderers
    // ===================================

    renderGauge: function (container, widget, data, index) {
        const canvas = document.createElement('canvas');
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        container.appendChild(canvas);

        const ctx = canvas.getContext('2d');
        const GAUGE_MAX = 500;
        const value = data.stats ? (data.stats.average_response_time || 0) : 0;

        // Reuse gauge logic
        const gaugeNeedle = {
            id: 'gaugeNeedle',
            afterDatasetDraw(chart, args, options) {
                const { ctx, config, data, chartArea: { top, bottom, left, right, width, height } } = chart;
                ctx.save();
                const needleValue = data.datasets[0].needleValue || 0;
                let angle = Math.PI + (needleValue / GAUGE_MAX) * Math.PI;
                if (needleValue > GAUGE_MAX) angle = 2 * Math.PI;

                const cx = width / 2;
                const cy = chart.chartArea.bottom - 10;

                ctx.translate(cx, cy);
                ctx.rotate(angle);
                ctx.beginPath();
                ctx.moveTo(0, -2);
                ctx.lineTo(height - (ctx.canvas.offsetHeight * 0.2), 0);
                ctx.lineTo(0, 2);
                ctx.fillStyle = '#475569';
                ctx.fill();

                ctx.rotate(-angle);
                ctx.translate(-cx, -cy);
                ctx.beginPath();
                ctx.arc(cx, cy, 5, 0, 10);
                ctx.fillStyle = '#475569';
                ctx.fill();
                ctx.restore();

                // Value Text
                ctx.save();
                ctx.font = 'bold 24px Inter, sans-serif';
                ctx.fillStyle = DashboardRenderer.getGaugeColor(needleValue);
                ctx.textAlign = 'center';
                ctx.textBaseline = 'bottom';
                ctx.fillText(needleValue.toFixed(2), cx, cy - 20);

                ctx.font = '12px Inter, sans-serif';
                ctx.fillStyle = '#94a3b8';
                ctx.fillText('ms', cx, cy + 5);
                ctx.restore();
            }
        };


        const renderValue = value > GAUGE_MAX ? GAUGE_MAX : value;


        const chart = new Chart(ctx, {
            type: 'doughnut',

            data: {
                labels: ['Fast', 'Moderate', 'Slow'],
                datasets: [{
                    data: [100, 200, 200], // 0-100, 100-300, 300-500
                    backgroundColor: ['#10b981', '#f59e0b', '#ef4444'], // Green, Yellow, Red
                    borderWidth: 0,
                    needleValue: value
                }]
            },

            options: {
                responsive: true,
                maintainAspectRatio: false,
                rotation: -90,
                circumference: 180,
                cutout: '75%',
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                },
                layout: { padding: { bottom: 20 } }
            },
            plugins: [gaugeNeedle]
        });


        this.instances[`chart_${index}`] = chart;
    },

    renderPerformance: function (container, widget, data, index) {
        // Layout: Top 50% Gauge, Bottom 50% List
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.height = '500px';
        container.style.overflow = 'hidden';

        // Gauge Container
        const gaugeContainer = document.createElement('div');
        gaugeContainer.style.flex = '1';
        gaugeContainer.style.minHeight = '180px';
        gaugeContainer.style.position = 'relative';
        container.appendChild(gaugeContainer);

        // List Container
        const listContainer = document.createElement('div');
        listContainer.style.flex = '1';
        listContainer.style.overflowY = 'auto';
        listContainer.style.borderTop = '1px solid var(--border-color)';
        listContainer.style.paddingTop = '10px';
        container.appendChild(listContainer);

        // Header for List
        const listHeader = document.createElement('h4');
        listHeader.textContent = 'Top Slow Devices';
        listHeader.style.fontSize = '0.9rem';
        listHeader.style.marginBottom = '0.5rem';
        listHeader.style.padding = '0 1rem';
        listContainer.appendChild(listHeader);

        // Content for List
        const listContent = document.createElement('div');
        listContent.style.padding = '0 1rem';
        listContainer.appendChild(listContent);

        // 1. Render Gauge
        this.renderGauge(gaugeContainer, widget, data, index);

        // 2. Render Slow Devices List
        const devices = data.devices || [];
        const slowDevices = devices
            .filter(d => d.status === 'up' && d.response_time && parseFloat(d.response_time) > 100)
            .sort((a, b) => parseFloat(b.response_time) - parseFloat(a.response_time))
            .slice(0, 5); // Top 5

        if (slowDevices.length === 0) {
            listContent.innerHTML = `
                <div style="display: flex; flex-direction: column; align-items: center; padding: 1rem; color: var(--text-muted);">
                    <p style="margin:0; font-size:0.85rem">No slow devices detected</p>
                </div>
            `;
        } else {
            const maxTime = Math.max(...slowDevices.map(d => parseFloat(d.response_time)));

            listContent.innerHTML = slowDevices.map(device => {
                const time = parseFloat(device.response_time);
                const percent = (time / maxTime) * 100;
                return `
                    <div style="margin-bottom: 0.5rem; font-size: 0.85rem;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                            <span style="font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:180px;" title="${device.name}">${device.name}</span>
                            <span style="color: var(--warning); font-weight:600;">${device.response_time} ms</span>
                        </div>
                        <div style="height: 4px; background: var(--bg-tertiary); border-radius: 2px; overflow: hidden;">
                             <div style="height: 100%; width: ${percent}%; background: var(--warning); border-radius: 2px;"></div>
                        </div>
                    </div>
                 `;
            }).join('');
        }
    },

    renderStatCard: function (container, widget, data) {
        const stats = data.stats || {};
        let value, label, icon, cssClass;

        const statType = widget.statType || 'total';

        switch (statType) {
            case 'up':
                value = stats.devices_up || 0;
                label = 'Devices Up';
                icon = '🖥️';
                cssClass = 'stat-card-online';
                break;
            case 'down':
                value = stats.devices_down || 0;
                label = 'Devices Down'; // Or 'Active Alerts'
                icon = '❌';
                cssClass = 'stat-card-alerts';
                break;
            case 'slow':
                value = stats.devices_slow || 0;
                label = 'Slow Devices';
                icon = '⚠️';
                cssClass = 'stat-card-slow';
                break;
            case 'uptime':
                value = (stats.uptime_percentage || 0) + '%';
                label = 'Network Uptime';
                icon = '✅';
                cssClass = 'stat-card-uptime';
                break;
            case 'latency':
                value = (stats.average_response_time || 0) + '<small>ms</small>';
                label = 'Avg Latency';
                icon = '⚡';
                cssClass = 'stat-card-latency';
                break;
            default: // total
                value = stats.total_devices || 0;
                label = 'Total Devices';
                icon = '🖥️';
                cssClass = 'stat-card-online';
        }

        if (widget.title) label = widget.title;

        // Render standard stat card HTML
        container.innerHTML = `
            <div class="stat-card ${cssClass}" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <div class="stat-icon">${icon}</div>
                <div class="stat-content">
                    <div class="stat-value">${value}</div>
                    <div class="stat-label">${label}</div>
                </div>
            </div>

        `;
    },

    renderStatRow: function (container, widget, data) {
        container.style.display = 'flex';
        container.style.gap = '1rem';
        container.style.height = '100%';

        const cards = widget.cards || [];
        if (cards.length === 0) {
            container.innerHTML = '<div class="text-muted">No cards in row</div>';
            return;
        }

        cards.forEach(cardConfig => {
            const cardWrapper = document.createElement('div');
            cardWrapper.style.flex = '1';
            cardWrapper.style.minWidth = '0'; // Prevent flex item overflow
            container.appendChild(cardWrapper);

            // Reuse renderStatCard logic
            // stat_card renderer expects the wrapper to have the card logic. 
            // But renderStatCard appends distinct HTML to container.
            // Let's call renderStatCard with the wrapper.
            this.renderStatCard(cardWrapper, cardConfig, data);
        });
    },


    renderTopology: function (container, widget, data, index) {

        container.style.height = '500px';
        const canvas = document.createElement('div');
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        container.appendChild(canvas);

        const nodes = new vis.DataSet(
            (data.devices || []).map(device => {
                // Remove color logic here as it is handled in SVG
                return {
                    id: device.id,
                    label: device.name,
                    shape: 'circularImage',
                    image: this.getNodeSvgUrl(device.device_type, device.status),
                    size: 20,
                    borderWidth: 0, // Border is in SVG
                    borderWidthSelected: 0,
                    color: { background: 'transparent', border: 'transparent' } // Let SVG handle colors
                };
            })
        );

        const uniqueEdges = new Map();
        (data.connections || []).forEach(conn => {
            const ids = [conn.device_id, conn.connected_to].sort((a, b) => a - b);
            const key = `${ids[0]}-${ids[1]}`;
            if (!uniqueEdges.has(key)) {
                uniqueEdges.set(key, conn);
            } else {
                const existing = uniqueEdges.get(key);
                if (conn.view_type === 'standard' && existing.view_type !== 'standard') {
                    uniqueEdges.set(key, conn);
                }
            }
        });

        const edges = new vis.DataSet(
            Array.from(uniqueEdges.values()).map(conn => ({
                id: conn.id,
                from: conn.device_id,
                to: conn.connected_to,
                width: 1.5,
                color: { color: 'rgba(148, 163, 184, 0.6)' }
            }))
        );

        const options = {
            nodes: {
                shape: 'circularImage',
                font: { color: document.documentElement.getAttribute('data-theme') === 'light' ? '#0f172a' : '#f1f5f9', size: 10, face: 'Inter, sans-serif' }
            },
            physics: { enabled: true, stabilization: { iterations: 100 } },
            layout: { improvedLayout: true },
            interaction: { zoomView: true, dragView: true, hover: true }
        };


        const network = new vis.Network(canvas, { nodes, edges }, options);
        this.instances[`network_${index}`] = network;
        this.instances[`nodes_${index}`] = nodes;
        this.instances[`edges_${index}`] = edges;
    },




    updateTopology: function (index, data, widget) {
        const nodesDS = this.instances[`nodes_${index}`];
        const edgesDS = this.instances[`edges_${index}`];

        if (!nodesDS || !edgesDS) return; // Should re-render if missing

        // 1. Update Nodes
        const currentIds = new Set(nodesDS.getIds());
        const newIds = new Set();

        const validDevices = (data.devices || []); // Add filtering if widget.config has filters

        const nodeUpdates = validDevices.map(device => {
            newIds.add(device.id);
            return {
                id: device.id,
                label: device.name,
                shape: 'circularImage',
                image: this.getNodeSvgUrl(device.device_type, device.status),
                size: 20,
                color: { background: 'transparent', border: 'transparent' }
            };
        });

        nodesDS.update(nodeUpdates);

        // Remove nodes that are no longer present
        const toRemove = [...currentIds].filter(id => !newIds.has(id));
        if (toRemove.length > 0) nodesDS.remove(toRemove);


        // 2. Update Edges
        const currentEdgeIds = new Set(edgesDS.getIds());
        const newEdgeIds = new Set();

        const uniqueEdges = new Map();
        (data.connections || []).forEach(conn => {
            const ids = [conn.device_id, conn.connected_to].sort((a, b) => a - b);
            const key = `${ids[0]}-${ids[1]}`;
            if (!uniqueEdges.has(key)) {
                uniqueEdges.set(key, conn);
            } else {
                const existing = uniqueEdges.get(key);
                if (conn.view_type === 'standard' && existing.view_type !== 'standard') {
                    uniqueEdges.set(key, conn);
                }
            }
        });

        const edgeUpdates = Array.from(uniqueEdges.values()).map(conn => {
            newEdgeIds.add(conn.id);
            return {
                id: conn.id,
                from: conn.device_id,
                to: conn.connected_to,
                width: 1.5,
                color: { color: 'rgba(148, 163, 184, 0.6)' }
            };
        });

        edgesDS.update(edgeUpdates);

        const edgesToRemove = [...currentEdgeIds].filter(id => !newEdgeIds.has(id));
        if (edgesToRemove.length > 0) edgesDS.remove(edgesToRemove);
    },

    renderDeviceGrid: function (container, widget, data) {

        const devices = data.devices || [];
        const devicesByType = {};

        // Group everything by type (even if filtered) because that's the view structure
        devices.forEach(device => {
            const type = device.device_type || 'other';
            if (!devicesByType[type]) {
                devicesByType[type] = {
                    total: 0, up: 0, down: 0, slow: 0,
                    totalResponseTime: 0, responseTimeCount: 0
                };
            }
            devicesByType[type].total++;
            if (device.status === 'up') {
                if (device.response_time && parseFloat(device.response_time) > 0) {
                    devicesByType[type].totalResponseTime += parseFloat(device.response_time);
                    devicesByType[type].responseTimeCount++;
                }
                if (device.response_time && parseFloat(device.response_time) > 500) {
                    devicesByType[type].slow++;
                } else {
                    devicesByType[type].up++;
                }
            } else if (device.status === 'slow') {
                devicesByType[type].slow++;
            } else {
                devicesByType[type].down++;
            }
        });

        let html = '<div class="device-type-grid" style="grid-template-columns: 1fr;">';

        if (Object.keys(devicesByType).length === 0) {
            html += '<p class="text-muted text-center" style="padding:1rem">No devices</p>';
        } else {
            Object.keys(devicesByType).sort().forEach(type => {
                const meta = this.typeMetadata[type] || this.typeMetadata['other'];
                const stats = devicesByType[type];
                const avgResponseTime = stats.responseTimeCount > 0 ? Math.round(stats.totalResponseTime / stats.responseTimeCount) : 0;
                const total = stats.total;
                const upPercent = total > 0 ? (stats.up / total) * 100 : 0;
                const slowPercent = total > 0 ? (stats.slow / total) * 100 : 0;
                const downPercent = total > 0 ? (stats.down / total) * 100 : 0;

                let statusClass = 'status-normal';
                let statusColor = 'var(--success)';

                if (stats.down > 0) {
                    statusClass = 'status-critical';
                    statusColor = 'var(--danger)';
                } else if (stats.slow > 0) {
                    statusClass = 'status-warning';
                    statusColor = 'var(--warning)';
                }

                html += `
                    <div class="device-type-card ${statusClass}">
                        <div class="device-card-header">
                            <div class="device-icon-wrapper" style="background-color: ${meta.color}20; color: ${meta.color};">
                                ${meta.icon}
                            </div>
                            <div class="device-info">
                                <div class="device-name">${meta.name}</div>
                                <div class="device-count">${stats.total} Devices</div>
                                <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">
                                    Avg: <span style="font-weight: 600; color: var(--text-primary);">${avgResponseTime} ms</span>
                                </div>
                            </div>
                            <div class="device-status-badge" style="color: ${statusColor};">
                                ${stats.up}/${stats.total}
                            </div>
                        </div>
                        
                        <div class="device-progress-bar">
                            <div class="progress-segment success" style="width: ${upPercent}%"></div>
                            <div class="progress-segment warning" style="width: ${slowPercent}%"></div>
                            <div class="progress-segment danger" style="width: ${downPercent}%"></div>
                        </div>
                    </div>
                `;
            });
        }
        html += '</div>';
        container.innerHTML = html;
        container.style.overflowY = 'auto';
        // container.style.maxHeight = '300px'; // Removed max-height
        container.style.height = '500px';
    },

    renderAlerts: function (container, widget, data) {
        container.style.height = '500px';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';

        const devices = data.devices || [];
        const alerts = devices.filter(d => d.status === 'down' || (d.status === 'up' && parseFloat(d.response_time) > 500));

        let html = `
            <div style="flex: 0 0 auto; display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                <span class="status-badge ${alerts.length > 0 ? 'status-down' : 'status-up'}">
                    ${alerts.length} alerts
                </span>
            </div>
            <div class="table-container" style="flex: 1; overflow-y: auto;">
        `;

        if (alerts.length === 0) {
            html += `
                <p class="text-center text-muted" style="padding: 2rem;">
                    ✅ No active alerts - All systems operational
                </p>
            `;
        } else {
            html += `
                <table class="alerts-table">
                    <thead>
                        <tr>
                            <th>Severity</th>
                            <th>Device</th>
                            <th>Time</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            alerts.forEach(d => {
                const isDown = d.status === 'down';
                const severity = isDown ? 'Critical' : 'Warning';
                const badgeStyle = isDown ? 'background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid #ef4444;' : 'background: rgba(245, 158, 11, 0.1); color: #f59e0b; border: 1px solid #f59e0b;';

                html += `
                    <tr>
                        <td><span class="status-badge" style="${badgeStyle}">⚠️ ${severity}</span></td>
                        <td>${d.name}</td>
                        <td>${d.last_check ? new Date(d.last_check).toLocaleTimeString() : 'N/A'}</td>
                        <td><span class="status-badge status-${d.status}">${d.status.toUpperCase()}</span></td>
                    </tr>
                `;
            });
            html += '</tbody></table>';
        }

        html += '</div>';
        container.innerHTML = html;
    },

    renderActivityLog: function (container, widget, data) {
        // Since we don't have historical log in default API response, we show current state snapshot or live indicator
        // Ideally checking 'last_check' times

        const recent = (data.devices || [])
            .filter(d => d.last_check)
            .sort((a, b) => new Date(b.last_check) - new Date(a.last_check))
            .slice(0, 8);

        let html = `
             <div style="display: flex; justify-content: flex-end; margin-bottom: 0.5rem;">
                <span class="status-badge status-up">
                    <span style="display:inline-block; margin-right:5px; animation: blink 1s infinite;">●</span> Live
                </span>
            </div>
            <div style="max-height: 250px; overflow-y: auto;">
        `;

        if (recent.length === 0) {
            html += '<p class="text-center text-muted">Waiting for activity...</p>';
        } else {
            recent.forEach(d => {
                let icon = '✅';
                if (d.status === 'down') { icon = '❌'; }
                else if (d.status === 'slow') { icon = '⚠️'; }

                html += `
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0; border-bottom: 1px solid var(--border-color);">
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <span>${icon}</span>
                            <div>
                                <div style="font-weight: 500; font-size: 0.9rem;">${d.name}</div>
                                <div style="font-size: 0.75rem; color: var(--text-muted);">${d.status.toUpperCase()}</div>
                            </div>
                        </div>
                        <div style="text-align: right;">
                             <div style="font-size: 0.75rem; color: var(--text-muted);">${new Date(d.last_check).toLocaleTimeString()}</div>
                             ${d.response_time ? `<div style="font-size: 0.7rem; color: var(--text-muted);">${d.response_time} ms</div>` : ''}
                        </div>
                    </div>
                `;
            });
        }
        html += '</div>';
        container.innerHTML = html;
    },

    // Helpers


    getNodeSvgUrl: function (type, status) {
        const meta = this.typeMetadata[type || 'other'] || this.typeMetadata['other'];
        const icon = meta.icon;

        let color = '#f59e0b'; // warning
        if (status === 'up') color = '#10b981'; // success
        else if (status === 'down') color = '#ef4444'; // danger

        // Generate SVG
        const svgString = `
            <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">
                <defs>
                    <filter id="shadow" x="-50%" y="-50%" width="200%" height="200%">
                         <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="rgba(0,0,0,0.2)"/>
                    </filter>
                </defs>
                <circle cx="20" cy="20" r="18" fill="white" stroke="${color}" stroke-width="3" filter="url(#shadow)"/>
                <circle cx="20" cy="20" r="13" fill="${color}" opacity="0.1"/>
                <text x="50%" y="50%" dominant-baseline="central" text-anchor="middle" font-family="Segoe UI Emoji, Apple Color Emoji, sans-serif" font-size="20">${icon}</text>
            </svg>
        `.trim();

        return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgString);
    },

    getNodeColor: function (status, responseTime) {

        if (status === 'down') return '#ef4444';
        if (status === 'up' && responseTime && parseFloat(responseTime) > 500) return '#f59e0b';
        if (status === 'up') return '#10b981';
        return '#f59e0b';
    },

    getGaugeColor: function (value) {
        if (value < 100) return '#10b981';
        if (value < 300) return '#f59e0b';
        return '#ef4444';
    },

    clearInstances: function () {
        Object.values(this.instances).forEach(inst => {
            if (inst.destroy) inst.destroy();
        });
        this.instances = {};
    }
};

function getWidgetDefaultTitle(type) {
    switch (type) {

        case 'gauge': return 'Response Time Gauge';

        case 'performance': return 'Performance Overview';
        case 'stat_row': return 'Statistics Row';
        case 'stat_card': return 'Statistic';
        case 'topology': return 'Network Topology';
        case 'device_list': return 'Device List';
        case 'device_grid': return 'Device Status';
        case 'alerts': return 'Active Alerts';
        case 'activity': return 'Recent Activity';
        default: return 'Widget';
    }
}
