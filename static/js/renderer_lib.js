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
        'cctv': { icon: '📹', name: 'CCTV', color: '#14b8a6' },
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
            widgetEl.setAttribute('data-type', widget.type);

            if (widget.type === 'stat_card') {
                // Remove the default card styling for stat cards to use the specific stat-card class
                let widthClass = widget.width || 2;
                if (typeof widthClass === 'number' || !widthClass.startsWith('w-col-')) {
                    widthClass = `w-col-${widthClass}`;
                }
                widgetEl.className = `stat-card-wrapper ${widthClass}`;
                widgetEl.style.padding = '0';
                widgetEl.style.border = 'none';
                widgetEl.style.background = 'transparent';
                widgetEl.style.boxShadow = 'none';
            } else {
                let widthClass = widget.width || 4; // Default width 4 (1/3)
                if (typeof widthClass === 'number' || !widthClass.startsWith('w-col-')) {
                    widthClass = `w-col-${widthClass}`;
                }
                widgetEl.className = `grid-widget ${widthClass}`;
            }

            // Apply custom height to the whole widget card if specified
            if (widget.height) {
                widgetEl.style.height = `${widget.height}px`;
                widgetEl.style.minHeight = 'auto'; // Allow smaller than default min-height
            }

            widgetEl.dataset.index = index;
            widgetEl.id = `widget-${index}`;

            let controlsHtml = '';
            if (isEditMode) {
                controlsHtml = `
                    <div class="widget-controls">
                        <button class="widget-btn configure" onclick="configureWidget(${index})" title="Configure"><i class="fas fa-cog"></i></button>
                        <button class="widget-btn delete" onclick="removeWidget(${index})" title="Remove"><i class="fas fa-trash"></i></button>
                    </div>
                `;
            }

            const flexDir = widget.type === 'stat_row' ? 'row' : 'column';
            // Render structure (Standardized for all types)
            widgetEl.innerHTML = `
                <div class="widget-header">
                    <div class="widget-title">${widget.title || getWidgetDefaultTitle(widget.type)}</div>
                    ${controlsHtml}
                </div>
                <div class="widget-content" id="widget-content-${index}" style="height: calc(100% - 2rem); min-height: 0; position: relative; display: flex; flex-direction: ${flexDir};"></div>
            `;

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
                    this.updateGauge(index, widgetData);
                    break;
                case 'performance':
                    this.updatePerformance(container, widget, widgetData, index);
                    break;
                case 'stat_card':
                    this.updateStatCard(container, widget, widgetData);
                    break;
                case 'stat_row':
                    this.updateStatRow(container, widget, widgetData);
                    break;
                case 'trends':
                    // Silent update (already fetches internally)
                    this.renderResponseTrends(container, widget, widgetData, index);
                    break;
                case 'alerts':
                case 'activity':
                default:
                    // Fallback to re-render for list-heavy widgets until granular logic is added
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
                case 'trends':
                    this.renderResponseTrends(container, widget, widgetData, index);
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
        if (!deviceType) return originalData;

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
        container.style.flex = '1';
        container.style.minHeight = '0';
        container.style.position = 'relative';
        container.style.padding = '10px';

        const canvas = document.createElement('canvas');
        canvas.style.position = 'absolute';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        container.appendChild(canvas);

        const ctx = canvas.getContext('2d');
        const GAUGE_MAX = 500; // Aligned with SLOW_RESPONSE_THRESHOLD in config.py
        const value = data.stats ? (data.stats.average_response_time || 0) : 0;

        const gaugeNeedle = {
            id: 'gaugeNeedle',
            afterDatasetDraw(chart, args, options) {
                const { ctx, config, data, chartArea: { top, bottom, left, right, width, height } } = chart;
                ctx.save();
                const needleValue = data.datasets[0].needleValue || 0;

                // Use actual chart center from data element
                const meta = chart.getDatasetMeta(0).data[0];
                const cx = meta.x;
                const cy = meta.y;
                const innerRadius = meta.innerRadius;
                const outerRadius = meta.outerRadius;

                // Scale needle to GAUGE_MAX
                let angle = Math.PI + (Math.min(needleValue, GAUGE_MAX) / GAUGE_MAX) * Math.PI;

                // Ticks and Labels
                const ticks = [0, 100, 250, 400, 500];
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillStyle = '#94a3b8';
                ctx.font = '600 11px Inter, sans-serif';

                ticks.forEach(t => {
                    const tAngle = Math.PI + (t / GAUGE_MAX) * Math.PI;
                    // Position labels outside the inner arc
                    const tx = cx + Math.cos(tAngle) * (innerRadius - 20);
                    const ty = cy + Math.sin(tAngle) * (innerRadius - 20);
                    ctx.fillText(t, tx, ty);

                    // Small ticks on the arc
                    ctx.beginPath();
                    ctx.moveTo(cx + Math.cos(tAngle) * innerRadius, cy + Math.sin(tAngle) * innerRadius);
                    ctx.lineTo(cx + Math.cos(tAngle) * (innerRadius - 6), cy + Math.sin(tAngle) * (innerRadius - 6));
                    ctx.strokeStyle = '#cbd5e1';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                });

                // Value Text (Centered below the needle axis)
                ctx.font = '800 36px Inter, sans-serif';
                ctx.fillStyle = '#1e293b';
                ctx.textAlign = 'center';
                ctx.fillText(needleValue.toFixed(2), cx, cy + 35);

                // Needle
                ctx.save();
                ctx.translate(cx, cy);
                ctx.rotate(angle);

                // Needle Body
                ctx.beginPath();
                ctx.moveTo(0, -3);
                ctx.lineTo(outerRadius - 5, 0);
                ctx.lineTo(0, 3);
                ctx.fillStyle = '#334155';
                ctx.shadowBlur = 8;
                ctx.shadowColor = 'rgba(0,0,0,0.4)';
                ctx.fill();

                // Needle Cap
                ctx.rotate(-angle);
                ctx.beginPath();
                ctx.arc(0, 0, 8, 0, Math.PI * 2);
                ctx.fillStyle = '#1e293b';
                ctx.strokeStyle = '#f1f5f9';
                ctx.lineWidth = 2;
                ctx.fill();
                ctx.stroke();

                ctx.restore();
                ctx.restore();
            }
        };

        const chart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [50, 50, 50, 50],
                    backgroundColor: ['#10b981', '#f59e0b', '#fb923c', '#ef4444'],
                    borderWidth: 0,
                    needleValue: value
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                rotation: -90,
                circumference: 180,
                cutout: '80%',
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                },
                layout: { padding: { top: 30, bottom: 60, left: 10, right: 10 } }
            },
            plugins: [gaugeNeedle]
        });

        this.instances[`chart_${index}`] = chart;
    },

    updateGauge: function (index, data) {
        const chart = this.instances[`chart_${index}`];
        if (!chart) return;
        const value = data.stats ? (data.stats.average_response_time || 0) : 0;
        chart.data.datasets[0].needleValue = value;
        chart.update();
    },

    renderPerformance: function (container, widget, data, index) {
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.overflow = 'hidden';
        container.style.padding = '0';

        const totalHeight = container.offsetHeight || widget.height || 400;
        const gaugeHeight = Math.floor(totalHeight * 0.60);
        const listHeight = totalHeight - gaugeHeight;

        // Gauge Container
        const gaugeContainer = document.createElement('div');
        gaugeContainer.style.flex = `0 0 ${gaugeHeight}px`;
        gaugeContainer.style.position = 'relative';
        container.appendChild(gaugeContainer);

        // List Outer Container (Nested Card feel)
        const listWrapper = document.createElement('div');
        listWrapper.style.flex = '1';
        listWrapper.style.padding = '0 15px 15px 15px';
        listWrapper.style.display = 'flex';
        listWrapper.style.flexDirection = 'column';
        container.appendChild(listWrapper);

        const listContainer = document.createElement('div');
        listContainer.style.flex = '1';
        listContainer.style.overflowY = 'auto';
        listContainer.style.background = 'var(--bg-glass)';
        listContainer.style.backdropFilter = 'blur(10px)';
        listContainer.style.border = '1px solid var(--border-color)';
        listContainer.style.borderRadius = '12px';
        listContainer.style.padding = '12px';
        listWrapper.appendChild(listContainer);

        // Header
        const listHeader = document.createElement('div');
        listHeader.style.display = 'flex';
        listHeader.style.justifyContent = 'space-between';
        listHeader.style.alignItems = 'center';
        listHeader.style.marginBottom = '12px';
        listHeader.innerHTML = '<span style="font-weight:700; font-size:0.95rem; color: #1e293b;">Top Slow Devices</span>';
        listContainer.appendChild(listHeader);

        // Content
        const listContent = document.createElement('div');
        listContainer.appendChild(listContent);

        this.renderGauge(gaugeContainer, widget, data, index);

        const devices = data.devices || [];
        const slowest = devices
            .filter(d => d.status === 'up' && d.response_time)
            .sort((a, b) => parseFloat(b.response_time) - parseFloat(a.response_time))
            .slice(0, 5);

        if (slowest.length === 0) {
            listContent.innerHTML = `<p style="text-align:center; color:var(--text-muted); font-size:0.85rem">No data</p>`;
        } else {
            const maxTime = Math.max(...slowest.map(d => parseFloat(d.response_time)));
            listContent.innerHTML = slowest.map(device => {
                const time = parseFloat(device.response_time);
                const percent = Math.min((time / maxTime) * 100, 100);
                return `
                    <div style="margin-bottom: 12px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 6px; align-items: center;">
                            <span style="font-weight:600; font-size:0.9rem; color: #334155; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:70%;">${device.name}</span>
                            <span style="font-weight:700; color: #d97706; font-size:0.9rem;">${time.toFixed(2)} ms</span>
                        </div>
                        <div style="height: 6px; background: #f1f5f9; border-radius: 3px; position: relative;">
                            <div style="height: 100%; width: ${percent}%; background: linear-gradient(90deg, #f59e0b, #d97706); border-radius: 3px;"></div>
                        </div>
                    </div>
                `;
            }).join('');
        }
    },

    updatePerformance: function (container, widget, data, index) {
        // 1. Update Gauge
        this.updateGauge(index, data);

        // 2. Update Slow Devices List
        const listContainer = container.querySelector('div:last-child > div:last-child');
        if (!listContainer) return;

        const devices = data.devices || [];
        const slowest = devices
            .filter(d => d.status === 'up' && d.response_time)
            .sort((a, b) => parseFloat(b.response_time) - parseFloat(a.response_time))
            .slice(0, 5);

        if (slowest.length === 0) {
            listContainer.innerHTML = `
                <div style="display: flex; flex-direction: column; align-items: center; padding: 1.5rem; color: var(--text-muted);">
                    <p style="margin:0; font-size:0.85rem">No devices with data found</p>
                </div>
            `;
        } else {
            const maxTime = Math.max(...slowest.map(d => parseFloat(d.response_time)));
            listContainer.innerHTML = slowest.map(device => {
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
        const deviceType = (widget.config && widget.config.deviceType);
        const typeMeta = deviceType ? (this.typeMetadata[deviceType] || this.typeMetadata['other']) : null;

        switch (statType) {
            case 'up':
                value = stats.devices_up || 0;
                label = 'Devices Up';
                icon = typeMeta ? typeMeta.icon : '🖥️';
                cssClass = 'stat-card-online';
                break;
            case 'down':
                value = stats.devices_down || 0;
                label = 'Devices Down';
                icon = '❌'; // Keep indicator for critical state
                cssClass = 'stat-card-alerts';
                break;
            case 'slow':
                value = stats.devices_slow || 0;
                label = 'Slow Devices';
                icon = '⚠️'; // Keep warning icon
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
                icon = typeMeta ? typeMeta.icon : '🖥️';
                cssClass = 'stat-card-online';
        }

        if (widget.title) label = widget.title;

        // Render standard stat card HTML
        container.innerHTML = `
            <div class="stat-card ${cssClass}" style="height: 100%; display: flex; align-items: center; gap: 1.25rem; padding: 0.75rem 1.25rem;">
                <div class="stat-icon" style="width: 48px; height: 48px; display: flex; align-items: center; justify-content: center; background: var(--bg-tertiary); border-radius: 50%; font-size: 1.5rem; flex-shrink: 0;">${icon}</div>
                <div class="stat-content" style="display: flex; flex-direction: column; justify-content: center; min-width: 0;">
                    <div class="stat-value" style="font-size: 1.75rem; font-weight: 800; line-height: 1; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${value}</div>
                    <div class="stat-label" style="font-size: 0.65rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px;">${label}</div>
                </div>
            </div>
        `;
    },

    updateStatCard: function (container, widget, data) {
        const stats = data.stats || {};
        let value;
        const statType = widget.statType || 'total';
        const deviceType = (widget.config && widget.config.deviceType);
        const typeMeta = deviceType ? (this.typeMetadata[deviceType] || this.typeMetadata['other']) : null;

        switch (statType) {
            case 'up':
                value = stats.devices_up || 0;
                break;
            case 'down':
                value = stats.devices_down || 0;
                break;
            case 'slow':
                value = stats.devices_slow || 0;
                break;
            case 'uptime':
                value = (stats.uptime_percentage || 0) + '%';
                break;
            case 'latency':
                value = (stats.average_response_time || 0) + '<small>ms</small>';
                break;
            default: // total
                value = stats.total_devices || 0;
        }

        const valueEl = container.querySelector('.stat-value');
        if (valueEl && valueEl.innerHTML !== String(value)) { // Use innerHTML for potential <small> tag
            valueEl.innerHTML = value;
        }
    },

    renderStatRow: function (container, widget, data) {
        container.style.display = 'flex';
        container.style.setProperty('flex-direction', 'row', 'important');
        container.style.setProperty('flex-wrap', 'nowrap', 'important');
        container.style.gap = '1rem';
        container.style.height = '100%';

        let cards = widget.cards || [];

        // If no cards were manually defined, automatically generate the 5 standard stat cards.
        if (cards.length === 0) {
            const type = widget.config ? widget.config.deviceType : null;
            const typeMeta = type ? (this.typeMetadata[type] || this.typeMetadata['other']) : null;
            const typeName = typeMeta ? typeMeta.name.toUpperCase() : 'NETWORK';
            const deviceNoun = type === 'wireless' ? 'APS' : (type ? typeName : 'DEVICES');

            cards = [
                { type: 'stat_card', statType: 'uptime', config: { deviceType: type }, title: `${typeName} UPTIME` },
                { type: 'stat_card', statType: 'up', config: { deviceType: type }, title: `ONLINE ${deviceNoun}` },
                { type: 'stat_card', statType: 'latency', config: { deviceType: type }, title: `AVG ${type ? type.toUpperCase() : 'NET'} LATENCY` },
                { type: 'stat_card', statType: 'slow', config: { deviceType: type }, title: `SLOW ${deviceNoun}` },
                { type: 'stat_card', statType: 'down', config: { deviceType: type }, title: `ALERTS` }
            ];
        }

        if (cards.length === 0) {
            container.innerHTML = '<div style="display:flex; align-items:center; justify-content:center; height:100%; width:100%; color:var(--text-muted);">No cards in row - Please configure Device Type filter</div>';
            return;
        }

        container.innerHTML = ''; // Clear prior content

        cards.forEach(cardConfig => {
            const cardWrapper = document.createElement('div');
            cardWrapper.className = 'stat-row-item';
            cardWrapper.style.flex = '1';
            cardWrapper.style.minWidth = '0'; // Prevent flex item overflow
            cardWrapper.style.height = '100%';
            container.appendChild(cardWrapper);

            // Reuse renderStatCard logic
            this.renderStatCard(cardWrapper, cardConfig, data);
        });
    },

    updateStatRow: function (container, widget, data) {
        container.style.display = 'flex';
        container.style.setProperty('flex-direction', 'row', 'important');
        container.style.setProperty('flex-wrap', 'nowrap', 'important');
        let cards = widget.cards || [];
        const cardWrappers = container.children; // Assuming each child is a card wrapper

        // If no cards were manually defined, automatically generate the 5 standard stat cards.
        if (cards.length === 0) {
            const type = widget.config ? widget.config.deviceType : null;
            const typeMeta = type ? (this.typeMetadata[type] || this.typeMetadata['other']) : null;
            const typeName = typeMeta ? typeMeta.name.toUpperCase() : 'NETWORK';
            const deviceNoun = type === 'wireless' ? 'APS' : (type ? typeName : 'DEVICES');

            cards = [
                { type: 'stat_card', statType: 'uptime', config: { deviceType: type }, title: `${typeName} UPTIME` },
                { type: 'stat_card', statType: 'up', config: { deviceType: type }, title: `ONLINE ${deviceNoun}` },
                { type: 'stat_card', statType: 'latency', config: { deviceType: type }, title: `AVG ${type ? type.toUpperCase() : 'NET'} LATENCY` },
                { type: 'stat_card', statType: 'slow', config: { deviceType: type }, title: `SLOW ${deviceNoun}` },
                { type: 'stat_card', statType: 'down', config: { deviceType: type }, title: `ALERTS` }
            ];
        }

        if (cards.length === 0) {
            // If there are no cards, the renderStatRow would have put a message.
            // No update needed if it's just a message.
            return;
        }

        cards.forEach((cardConfig, i) => {
            const cardWrapper = cardWrappers[i];
            if (cardWrapper) {
                this.updateStatCard(cardWrapper, cardConfig, data);
            }
        });
    },


    renderTopology: function (container, widget, data, index) {
        // Just fill the container
        container.style.height = '100%';
        container.style.position = 'relative';
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
                    size: 400, // Increased 10x (from 40)
                    borderWidth: 0,
                    borderWidthSelected: 0,
                    color: { background: 'transparent', border: 'transparent' }
                };
            })
        );

        const uniqueEdges = new Map();
        (data.connections || []).forEach(conn => {
            const ids = [conn.device_id, conn.connected_to].sort((a, b) => a - b);
            const key = `${ids[0]} -${ids[1]} `;
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
                width: 5, // Increased from 1.5
                color: { color: 'rgba(148, 163, 184, 0.6)' }
            }))
        );

        const options = {
            nodes: {
                shape: 'circularImage',
                font: { color: document.documentElement.getAttribute('data-theme') === 'light' ? '#0f172a' : '#f1f5f9', size: 100, face: 'Inter, sans-serif' }
            },
            physics: {
                enabled: true,
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {
                    gravitationalConstant: -10000, // Stronger repulsion for huge nodes
                    centralGravity: 0.005,
                    springLength: 1200, // Significantly longer springs
                    springConstant: 0.08,
                    avoidOverlap: 1
                },
                stabilization: { iterations: 150 }
            },
            layout: { improvedLayout: true },
            interaction: { zoomView: true, dragView: true, hover: true },
            autoResize: true
        };


        const network = new vis.Network(canvas, { nodes, edges }, options);

        // Fit network to container when stabilization is done
        network.on('stabilizationFinished', () => {
            network.fit();
        });

        this.instances[`network_${index}`] = network;
        this.instances[`nodes_${index}`] = nodes;
        this.instances[`edges_${index}`] = edges;
    },




    updateTopology: function (index, data, widget) {
        const nodesDS = this.instances[`nodes_${index}`];
        const edgesDS = this.instances[`edges_${index}`];
        const network = this.instances[`network_${index}`];

        if (!nodesDS || !edgesDS) return; // Should re-render if missing

        // 1. Update Nodes
        const currentIds = new Set(nodesDS.getIds());
        const newIds = new Set();

        const validDevices = (data.devices || []);

        const nodeUpdates = validDevices.map(device => {
            newIds.add(device.id);
            return {
                id: device.id,
                label: device.name,
                shape: 'circularImage',
                image: this.getNodeSvgUrl(device.device_type, device.status),
                size: 400, // Consistency with 10x scale
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

        // Keep fitted if content changed
        if (network && (toRemove.length > 0 || edgesToRemove.length > 0 || nodeUpdates.length > 0)) {
            // Give it a tiny bit of time for physics to react
            setTimeout(() => network.fit(), 200);
        }
    },

    renderDeviceList: function (container, widget, data) {
        const devices = data.devices || [];
        // Fill the parent container which already has the widget height applied
        container.style.height = '100%';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';

        let html = `
    <div class="table-container" style="flex: 1; overflow-y: auto;">
        <table class="devices-table" style="width: 100%; border-collapse: collapse;">
            <thead style="position: sticky; top: 0; background: var(--bg-tertiary); z-index: 10;">
                <tr>
                    <th style="text-align: left; padding: 0.75rem; border-bottom: 2px solid var(--border-color);">Device</th>
                    <th style="text-align: left; padding: 0.75rem; border-bottom: 2px solid var(--border-color);">IP Address</th>
                    <th style="text-align: left; padding: 0.75rem; border-bottom: 2px solid var(--border-color);">Status</th>
                </tr>
            </thead>
            <tbody>
                `;

        if (devices.length === 0) {
            html += '<tr><td colspan="3" style="text-align: center; padding: 2rem; color: var(--text-muted);">No devices found</td></tr>';
        } else {
            devices.forEach(d => {
                const statusBadge = `<span class="status-badge status-${d.status}">${d.status.toUpperCase()}</span>`;
                html += `
                    <tr>
                        <td style="padding: 0.75rem; border-bottom: 1px solid var(--border-color);">${d.name}</td>
                        <td style="padding: 0.75rem; border-bottom: 1px solid var(--border-color); font-family: monospace;">${d.ip_address}</td>
                        <td style="padding: 0.75rem; border-bottom: 1px solid var(--border-color);">${statusBadge}</td>
                    </tr>
                `;
            });
        }

        html += '</tbody></table></div>';
        container.innerHTML = html;
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

        let html = '<div class="device-type-grid">';

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
        container.style.height = '100%';
    },

    renderAlerts: function (container, widget, data) {
        const galleryHeight = widget.height || 500;
        container.style.height = `${galleryHeight}px`;
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
        container.style.height = '100%';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';

        const recent = (data.devices || [])
            .filter(d => d.last_check)
            .sort((a, b) => new Date(b.last_check) - new Date(a.last_check))
            .slice(0, 8);

        let html = `
             <div style="flex: 0 0 auto; display: flex; justify-content: flex-end; margin-bottom: 0.5rem;">
                <span class="status-badge status-up">
                    <span style="display:inline-block; margin-right:5px; animation: blink 1s infinite;">●</span> Live
                </span>
            </div>
            <div style="flex: 1; overflow-y: auto;">
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

    renderResponseTrends: async function (container, widget, data, index) {
        const currentRange = this.instances[`trend_range_${index}`] || 15;
        this.instances[`trend_range_${index}`] = currentRange;
        this.instances[`widget_${index}`] = widget;

        const filterType = widget.config ? widget.config.deviceType : null;
        let contentArea = document.getElementById(`trend-content-${index}`);

        // Only render the structure if it's not already there
        if (!contentArea) {
            container.style.height = '100%';
            container.style.display = 'flex';
            container.style.flexDirection = 'column';
            container.style.overflow = 'hidden';

            container.innerHTML = `
                <div style="display: flex; justify-content: flex-end; gap: 5px; margin-bottom: 10px; flex-shrink: 0;">
                    ${[1, 15, 60].map(r => `
                        <button class="btn btn-sm ${currentRange === r ? 'btn-primary' : 'btn-outline-secondary'}" 
                                style="padding: 2px 8px; font-size: 0.75rem;"
                                onclick="window.DashboardRenderer.setTrendRange(${index}, ${r}, this)">
                            ${r >= 60 ? '1h' : r + 'm'}
                        </button>
                    `).join('')}
                </div>
                <div id="trend-content-${index}" style="flex: 1; min-height: 0; position: relative; display: flex; align-items: center; justify-content: center; overflow: hidden;">
                    <div class="text-muted" style="font-size: 0.8rem;">
                        <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true" style="margin-right: 5px;"></span>
                        Loading trends...
                    </div>
                </div>
            `;
            contentArea = document.getElementById(`trend-content-${index}`);
        }

        try {
            const requestMinutes = currentRange === 1 ? 3 : currentRange;
            const response = await fetch(`/api/statistics/trend?minutes=${requestMinutes}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const trends = await response.json();

            // Re-check contentArea in case it was destroyed during fetch
            contentArea = document.getElementById(`trend-content-${index}`);
            if (!contentArea) return;

            if (!trends || trends.length === 0) {
                contentArea.innerHTML = '<div class="text-muted" style="font-size: 0.8rem;">No trend data available for this range.</div>';
                if (this.instances[`chart_${index}`]) {
                    this.instances[`chart_${index}`].destroy();
                    delete this.instances[`chart_${index}`];
                }
                return;
            }

            const datasets = {};
            const timestamps = new Set();

            trends.forEach(item => {
                const type = item.device_type || 'other';
                if (filterType && type !== filterType) return;

                let timeLabel = currentRange <= 10 ? item.timestamp.substring(11, 19) : item.timestamp.substring(11, 16);
                timestamps.add(timeLabel);

                if (!datasets[type]) {
                    const meta = this.typeMetadata[type] || this.typeMetadata['other'];
                    datasets[type] = {
                        label: meta.name,
                        data: {},
                        borderColor: meta.color,
                        backgroundColor: meta.color + '20',
                        borderWidth: 2,
                        tension: 0.4,
                        fill: true,
                        pointRadius: 0,
                        spanGaps: true
                    };
                }
                datasets[type].data[timeLabel] = Math.round(item.avg_response_time);
            });

            const sortedTimes = Array.from(timestamps).sort();
            const chartDatasets = Object.values(datasets).map(ds => ({
                ...ds,
                data: sortedTimes.map(time => ds.data[time] || null)
            }));

            if (chartDatasets.length === 0) {
                contentArea.innerHTML = `<div class="text-muted" style="font-size: 0.8rem;">No data found for ${filterType || 'selected filters'}.</div>`;
                if (this.instances[`chart_${index}`]) {
                    this.instances[`chart_${index}`].destroy();
                    delete this.instances[`chart_${index}`];
                }
                return;
            }

            const existingChart = this.instances[`chart_${index}`];
            if (existingChart && document.getElementById(`trend-chart-${index}`)) {
                // Smooth update
                existingChart.data.labels = sortedTimes;
                existingChart.data.datasets = chartDatasets;
                existingChart.update('none'); // Update without animation for continuous feel
            } else {
                // Initial render or re-render
                contentArea.innerHTML = `<canvas id="trend-chart-${index}" style="position: absolute; top:0; left:0; width: 100%; height: 100%;"></canvas>`;
                const ctx = document.getElementById(`trend-chart-${index}`).getContext('2d');

                if (existingChart) existingChart.destroy();

                this.instances[`chart_${index}`] = new Chart(ctx, {
                    type: 'line',
                    data: { labels: sortedTimes, datasets: chartDatasets },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                display: !filterType,
                                position: 'top',
                                align: 'end',
                                labels: { usePointStyle: true, boxWidth: 6, font: { size: 10 } }
                            },
                            tooltip: {
                                mode: 'index',
                                intersect: false,
                                padding: 8,
                                bodyFont: { size: 11 },
                                titleFont: { size: 11 }
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                grid: { color: 'rgba(0,0,0,0.03)' },
                                ticks: { font: { size: 10 } },
                                title: { display: true, text: 'ms', font: { size: 9 } }
                            },
                            x: {
                                grid: { display: false },
                                ticks: { font: { size: 10 }, maxTicksLimit: 8 }
                            }
                        }
                    }
                });
            }
        } catch (e) {
            console.error('Error rendering trend chart:', e);
            contentArea = document.getElementById(`trend-content-${index}`);
            if (contentArea) {
                contentArea.innerHTML = `<div class="text-danger" style="font-size: 0.8rem;">Error loading trends: ${e.message}</div>`;
            }
        }
    },

    setTrendRange: function (index, range, btn) {
        this.instances[`trend_range_${index}`] = range;
        const container = document.getElementById(`widget-content-${index}`);
        if (container) {
            const widget = this.instances[`widget_${index}`] || { type: 'trends', config: {} };
            this.renderResponseTrends(container, widget, null, index); // Null data is fine as it fetches
            const group = btn.parentElement;
            Array.from(group.children).forEach(c => c.classList.remove('btn-primary'));
            Array.from(group.children).forEach(c => c.classList.add('btn-outline-secondary'));
            btn.classList.remove('btn-outline-secondary');
            btn.classList.add('btn-primary');
        }
    },

    // Helpers


    getNodeSvgUrl: function (type, status) {
        const meta = this.typeMetadata[type || 'other'] || this.typeMetadata['other'];
        const icon = meta.icon;

        let color = '#f59e0b'; // warning
        if (status === 'up') color = '#10b981'; // success
        else if (status === 'down') color = '#ef4444'; // danger

        // High-resolution SVG for 10x nodes
        const svgString = `
            <svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">
                <defs>
                    <filter id="shadow" x="-50%" y="-50%" width="200%" height="200%">
                         <feDropShadow dx="0" dy="10" stdDeviation="15" flood-color="rgba(0,0,0,0.3)"/>
                    </filter>
                </defs>
                <circle cx="200" cy="200" r="180" fill="white" stroke="${color}" stroke-width="20" filter="url(#shadow)"/>
                <circle cx="200" cy="200" r="130" fill="${color}" opacity="0.1"/>
                <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" font-family="Segoe UI Emoji, Apple Color Emoji, sans-serif" font-size="220">${icon}</text>
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
        case 'trends': return 'Response Trends';
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
