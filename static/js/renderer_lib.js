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
    lastFullscreenWidgetIndex: null,
    fullscreenListenerBound: false,

    /**
     * Render a list of widgets into a container
     * @param {HTMLElement} container - The grid container
     * @param {Array} layoutConfig - The layout configuration
     * @param {Object} data - The data available (devices, stats, topology)
     * @param {boolean} isEditMode - If true, adds edit controls
     */

    renderDashboard: function (container, layoutConfig, data, isEditMode = false) {
        this.ensureFullscreenListeners();

        // Normalize layoutConfig: handle both array and {widgets, variables} object format
        if (layoutConfig && !Array.isArray(layoutConfig) && typeof layoutConfig === 'object') {
            layoutConfig = layoutConfig.widgets || [];
        }
        if (!layoutConfig) layoutConfig = [];

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
            widgetEl.className = 'grid-stack-item';
            
            // Set GridStack attributes - ensure we use numbers and avoid NaN/null strings
            const gw = parseInt(widget.w || widget.width || 4);
            const gh = parseInt(widget.h || (widget.type === 'stat_row' || widget.type === 'stat_card' ? 2 : 4));
            
            widgetEl.setAttribute('gs-w', isNaN(gw) ? 4 : gw);
            widgetEl.setAttribute('gs-h', isNaN(gh) ? 4 : gh);

            if (widget.x !== undefined && widget.x !== null && widget.x !== "null") {
                widgetEl.setAttribute('gs-x', widget.x);
            }
            if (widget.y !== undefined && widget.y !== null && widget.y !== "null") {
                widgetEl.setAttribute('gs-y', widget.y);
            }

            // Determine class configuration
            widgetEl.setAttribute('data-type', widget.type);
            widgetEl.dataset.index = index;
            widgetEl.id = `widget-${index}`;

            let controlsHtml = '';
            let dragHandleHtml = '';
            const fullscreenControl = widget.type === 'topology'
                ? `<button class="widget-btn fullscreen" onclick="window.DashboardRenderer.toggleWidgetFullscreen(${index})" title="Fullscreen"><i class="fas fa-expand"></i></button>`
                : '';
            if (isEditMode) {
                // Remove individual drag handle icon to use the whole title as handle
                dragHandleHtml = ``;
                controlsHtml = `
                    <div class="widget-controls">
                        ${fullscreenControl}
                        <button class="widget-btn configure" onclick="configureWidget(${index})" title="Configure"><i class="fas fa-cog"></i></button>
                        <button class="widget-btn delete" onclick="removeWidget(${index})" title="Remove"><i class="fas fa-trash"></i></button>
                    </div>
                `;
            } else if (fullscreenControl) {
                controlsHtml = `
                    <div class="widget-controls">
                        ${fullscreenControl}
                    </div>
                `;
            }

            const flexDir = widget.type === 'stat_row' ? 'row' : 'column';
            
            // GridStack requires an inner div with class 'grid-stack-item-content'
            // We use this inner div to house our custom widget structure
            const contentWrapperHtml = `
                <div class="grid-stack-item-content" data-fullscreen-widget-index="${index}">
                    <div class="widget-header">
                        <div class="widget-title" style="display: flex; align-items: center;">${dragHandleHtml}${widget.title || getWidgetDefaultTitle(widget.type)}</div>
                        ${controlsHtml}
                    </div>
                    <div class="widget-content" id="widget-content-${index}" style="height: calc(100% - 2rem); min-height: 0; position: relative; display: flex; flex-direction: ${flexDir};"></div>
                </div>
            `;
            
            widgetEl.innerHTML = contentWrapperHtml;

            container.appendChild(widgetEl);

            // Render specific content inside the .widget-content container
            const contentContainer = widgetEl.querySelector('.widget-content');
            this.renderWidgetContent(contentContainer, widget, data, index);
        });
    },



    updateWidgetContent: function (container, widget, data, index) {
        try {
            // Apply filtering if configured, same as renderWidgetContent
            let widgetData = data;
            if (widget.config && (widget.config.deviceType || widget.config.deviceId)) {
                widgetData = this.filterData(data, widget.config);
            }

            switch (widget.type) {
                case 'topology':
                    this.updateTopology(container, index, widgetData, widget);
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
                case 'device_pie':
                    this.updateDevicePie(container, widget, widgetData, index);
                    break;
                case 'bandwidth':
                    this.updateBandwidth(container, widget, widgetData, index);
                    break;
                case 'system_metrics':
                    this.renderSystemMetrics(container, widget, widgetData, index);
                    break;
                case 'network_traffic':
                    this.renderNetworkTraffic(container, widget, widgetData, index);
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
            if (widget.config && (widget.config.deviceType || widget.config.deviceId)) {
                widgetData = this.filterData(data, widget.config);
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
                case 'device_pie':
                    this.renderDevicePie(container, widget, widgetData, index);
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
                case 'bandwidth':
                    this.renderBandwidth(container, widget, widgetData, index);
                    break;
                case 'system_metrics':
                    this.renderSystemMetrics(container, widget, widgetData, index);
                    break;
                case 'network_traffic':
                    this.renderNetworkTraffic(container, widget, widgetData, index);
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
     * Filter data by device type or specific device ID and recalculate statistics
     */
    filterData: function (originalData, widgetConfig) {
        if (!widgetConfig) return originalData;

        const { deviceType, deviceId } = widgetConfig;
        if (!deviceType && !deviceId) return originalData;

        // filter devices
        const devices = (originalData.devices || []).filter(d => {
            if (deviceId) {
                return String(d.id) === String(deviceId);
            }
            if (deviceType) {
                return (d.device_type || 'other').toLowerCase() === deviceType.toLowerCase();
            }
            return true;
        });

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
            devices_slow: devices.filter(d => d.status === 'slow').length,
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

    ensureFullscreenListeners: function () {
        if (this.fullscreenListenerBound) return;
        const handler = () => {
            const active = document.fullscreenElement;
            const activeIndex = active && active.dataset ? active.dataset.fullscreenWidgetIndex : null;
            if (activeIndex !== null && activeIndex !== undefined) {
                this.lastFullscreenWidgetIndex = activeIndex;
            }
            const targetIndex = activeIndex !== null && activeIndex !== undefined ? activeIndex : this.lastFullscreenWidgetIndex;
            if (targetIndex !== null && targetIndex !== undefined) {
                [80, 220, 500].forEach(delay => {
                    setTimeout(() => this.refreshTopologyLayout(targetIndex), delay);
                });
            }
        };
        document.addEventListener('fullscreenchange', handler);
        document.addEventListener('webkitfullscreenchange', handler);
        document.addEventListener('mozfullscreenchange', handler);
        document.addEventListener('MSFullscreenChange', handler);
        this.fullscreenListenerBound = true;
    },

    toggleWidgetFullscreen: function (index) {
        const wrapper = document.querySelector(`#widget-${index} .grid-stack-item-content`);
        if (!wrapper) return;

        this.lastFullscreenWidgetIndex = index;

        if (document.fullscreenElement) {
            if (document.exitFullscreen) document.exitFullscreen();
            else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
            else if (document.msExitFullscreen) document.msExitFullscreen();
            return;
        }

        if (wrapper.requestFullscreen) wrapper.requestFullscreen();
        else if (wrapper.webkitRequestFullscreen) wrapper.webkitRequestFullscreen();
        else if (wrapper.msRequestFullscreen) wrapper.msRequestFullscreen();
    },

    refreshTopologyLayout: function (index) {
        const network = this.instances[`network_${index}`];
        if (!network) return;
        try {
            if (typeof network.redraw === 'function') network.redraw();
            if (typeof network.fit === 'function') network.fit({ animation: false });
            this.syncPremiumWidgetOverlay(index);
        } catch (e) {
            console.warn('Failed to refresh topology fullscreen layout:', e);
        }
    },

    addTopologyZoomControls: function (container, index) {
        const controls = document.createElement('div');
        controls.className = 'topology-zoom-controls';
        controls.style.position = 'absolute';
        controls.style.top = '0.5rem';
        controls.style.right = '0.5rem';
        controls.style.zIndex = '20';
        controls.style.display = 'flex';
        controls.style.gap = '0.35rem';
        controls.style.pointerEvents = 'auto';
        controls.innerHTML = `
            <button class="widget-btn" title="Zoom In" onclick="window.DashboardRenderer.zoomTopology(${index}, 1.2)"><i class="fas fa-plus"></i></button>
            <button class="widget-btn" title="Zoom Out" onclick="window.DashboardRenderer.zoomTopology(${index}, 0.85)"><i class="fas fa-minus"></i></button>
            <button class="widget-btn" title="Fit" onclick="window.DashboardRenderer.fitTopology(${index})"><i class="fas fa-expand-arrows-alt"></i></button>
        `;
        container.appendChild(controls);
    },

    zoomTopology: function (index, factor) {
        const network = this.instances[`network_${index}`];
        if (!network || typeof network.getScale !== 'function' || typeof network.moveTo !== 'function') return;
        try {
            const scale = network.getScale();
            const position = typeof network.getViewPosition === 'function' ? network.getViewPosition() : { x: 0, y: 0 };
            network.moveTo({
                position,
                scale: Math.max(0.15, Math.min(3, scale * factor)),
                animation: { duration: 180, easingFunction: 'easeInOutQuad' }
            });
            setTimeout(() => this.syncPremiumWidgetOverlay(index), 200);
        } catch (e) {
            console.warn('Failed to zoom topology widget:', e);
        }
    },

    fitTopology: function (index) {
        const network = this.instances[`network_${index}`];
        if (!network || typeof network.fit !== 'function') return;
        try {
            network.fit({ animation: { duration: 220, easingFunction: 'easeInOutQuad' } });
            setTimeout(() => this.syncPremiumWidgetOverlay(index), 240);
        } catch (e) {
            console.warn('Failed to fit topology widget:', e);
        }
    },

    resolveTopologyData: async function (widget, fallbackData, index) {
        const topologyMode = widget && widget.config ? (widget.config.topologyMode || 'main') : 'main';
        const subTopologyId = widget && widget.config ? widget.config.subTopologyId : null;

        if (topologyMode !== 'sub_topology' || !subTopologyId) {
            return fallbackData;
        }

        const response = await fetch(`/api/sub-topologies/${subTopologyId}?_t=${Date.now()}`);
        if (!response.ok) {
            throw new Error(`Failed to load sub-topology ${subTopologyId}`);
        }
        const subTopology = await response.json();
        const resolvedData = {
            devices: subTopology.devices || [],
            connections: subTopology.connections || [],
            stats: this.buildStatsFromDevices(subTopology.devices || []),
            node_positions: subTopology.node_positions || {},
            theme_mode: subTopology.theme_mode || 'standard',
            background_image: subTopology.background_image || null
        };

        if (widget.config && (widget.config.deviceType || widget.config.deviceId)) {
            return this.filterData(resolvedData, widget.config);
        }

        return resolvedData;
    },

    buildStatsFromDevices: function (devices) {
        const totalDevices = devices.length;
        const devicesUp = devices.filter(d => d.status === 'up').length;
        const devicesDown = devices.filter(d => d.status === 'down').length;
        const devicesSlow = devices.filter(d => d.status === 'slow').length;

        let uptimePercentage = 0;
        let averageResponseTime = 0;

        if (totalDevices > 0) {
            uptimePercentage = Math.round(((devicesUp + devicesSlow) / totalDevices) * 100);

            const responseTimes = devices
                .map(d => parseFloat(d.response_time))
                .filter(t => !isNaN(t) && t > 0);

            if (responseTimes.length > 0) {
                const totalRt = responseTimes.reduce((a, b) => a + b, 0);
                averageResponseTime = Math.round((totalRt / responseTimes.length) * 100) / 100;
            }
        }

        return {
            total_devices: totalDevices,
            devices_up: devicesUp,
            devices_down: devicesDown,
            devices_slow: devicesSlow,
            uptime_percentage: uptimePercentage,
            average_response_time: averageResponseTime
        };
    },

    buildTopologyDatasets: function (data) {
        const nodes = new vis.DataSet(
            (data.devices || []).map(device => {
                const rt = device.response_time !== null && device.response_time !== undefined ? `${device.response_time} ms` : 'N/A';
                return {
                    id: device.id,
                    label: device.name,
                    title: `Device: ${device.name}\nStatus: ${device.status.toUpperCase()}\nLocation: ${device.location || 'N/A'}\nResponse: ${rt}`,
                    shape: 'circularImage',
                    image: this.getNodeSvgUrl(device.device_type, device.status),
                    size: 100,
                    borderWidth: 0,
                    borderWidthSelected: 0,
                    color: { background: 'transparent', border: 'transparent' }
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
                width: 5,
                color: { color: 'rgba(148, 163, 184, 0.6)' }
            }))
        );

        return { nodes, edges };
    },

    parseNodePositions: function (nodePositions) {
        if (!nodePositions) return {};
        try {
            return typeof nodePositions === 'string' ? JSON.parse(nodePositions) : nodePositions;
        } catch (e) {
            return {};
        }
    },

    isPremiumTopologyWidget: function (widget, resolvedData) {
        return !!(
            widget &&
            widget.config &&
            widget.config.topologyMode === 'sub_topology' &&
            widget.config.renderStyle === 'premium3d' &&
            resolvedData &&
            (resolvedData.theme_mode || '').toLowerCase() === 'premium'
        );
    },

    getPremiumWidgetTemplateId: function (device) {
        const type = (device.device_type || 'server').toLowerCase();
        if (type === 'server' || type === 'vmware') return 'wide-server-template';
        if (type === 'switch') return 'rackmount-hardware-template';
        if (type === 'wireless' || type === 'wifi') return 'wireless-ap-template';
        return 'floating-node-template';
    },

    renderPremiumWidgetNode: function (overlay, device, index) {
        let el = document.getElementById(`premium-widget-node-${index}-${device.id}`);
        if (!el) {
            el = document.createElement('div');
            el.id = `premium-widget-node-${index}-${device.id}`;
            el.className = 'dom-overlay-node';
            el.setAttribute('data-node-id', device.id);
            el.style.position = 'absolute';
            el.style.pointerEvents = 'auto';
            overlay.appendChild(el);
        }

        const type = (device.device_type || 'server').toLowerCase();
        const templateId = this.getPremiumWidgetTemplateId(device);
        const templateNode = document.getElementById(templateId);
        if (!templateNode) return;

        const iconMap = {
            'firewall': 'fa-shield-halved',
            'switch': 'fa-network-wired',
            'router': 'fa-globe',
            'internet': 'fa-cloud',
            'wireless': 'fa-wifi',
            'server': 'fa-server',
            'vmware': 'fa-database'
        };

        let html = templateNode.innerHTML
            .replace(/{id}/g, `${index}-${device.id}`)
            .replace(/{name}/g, device.name || 'Unknown')
            .replace(/{ip}/g, device.ip_address || 'N/A')
            .replace(/{icon}/g, iconMap[type] || 'fa-microchip')
            .replace(/{status}/g, device.status || 'unknown')
            .replace(/{type-label}/g, device.device_type || 'N/A')
            .replace(/{response-label}/g, device.response_time != null ? `${device.response_time}ms` : '--')
            .replace(/{glow-class}/g, `glow-${type}`);

        if (type === 'switch') {
            html = html.replace(/{image_url}/g, '/static/icons/premium_switch.png?v=2');
        }
        if (type === 'wireless' || type === 'wifi') {
            html = html.replace(/{image_url}/g, '/static/icons/premium_wireless.svg?v=2');
        }
        if (type === 'server' || type === 'vmware') {
            const cpu = device.response_time != null ? Math.min(99, Math.max(5, Math.round(device.response_time % 100))) : 15;
            const cpuColor = cpu > 80 ? 'critical' : (cpu > 50 ? 'warning' : 'healthy');
            html = html.replace(/{cpu}/g, cpu).replace(/{cpu-color}/g, cpuColor);
        }

        el.innerHTML = html;
        if (type === 'switch') {
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
        }
        el.onclick = (evt) => {
            evt.stopPropagation();
            const network = this.instances[`network_${index}`];
            if (network) network.selectNodes([device.id]);
            if (typeof showPremiumDeviceDetails === 'function') {
                showPremiumDeviceDetails(device);
            }
        };
    },

    syncPremiumWidgetOverlay: function (index) {
        const network = this.instances[`network_${index}`];
        const resolvedData = this.instances[`topology_data_${index}`];
        const overlay = this.instances[`topology_overlay_${index}`];
        if (!network || !resolvedData || !overlay) return;

        const scale = network.getScale();
        (resolvedData.devices || []).forEach(device => {
            const el = document.getElementById(`premium-widget-node-${index}-${device.id}`);
            if (!el) return;

            const pos = network.getPositions([device.id])[device.id];
            if (!pos) return;

            const domPos = network.canvasToDOM(pos);
            const width = el.offsetWidth || 120;
            const height = el.offsetHeight || 120;
            const isSwitchNode = !!el.querySelector('.rackmount-node');
            const effectiveScale = isSwitchNode
                ? Math.max(0.8, Math.min(1.25, scale * 1.2))
                : Math.max(0.42, Math.min(1.2, scale));

            el.style.left = `${domPos.x - (width / 2)}px`;
            el.style.top = `${domPos.y - (height / 2)}px`;
            el.style.transform = `scale(${effectiveScale})`;
            el.style.transformOrigin = 'center center';
        });
    },

    renderPremiumTopology: function (container, widget, resolvedData, index) {
        container.innerHTML = '';
        container.style.height = '100%';
        container.style.position = 'relative';
        container.style.overflow = 'hidden';

        const canvas = document.createElement('div');
        canvas.style.position = 'absolute';
        canvas.style.inset = '0';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        container.appendChild(canvas);

        const overlay = document.createElement('div');
        overlay.className = 'premium-widget-overlay';
        overlay.style.position = 'absolute';
        overlay.style.inset = '0';
        overlay.style.pointerEvents = 'none';
        overlay.style.overflow = 'hidden';
        overlay.style.zIndex = '10';
        container.appendChild(overlay);
        this.addTopologyZoomControls(container, index);

        const nodePositions = this.parseNodePositions(resolvedData.node_positions);
        const nodes = new vis.DataSet((resolvedData.devices || []).map(device => ({
            id: device.id,
            label: null,
            x: nodePositions[device.id] ? nodePositions[device.id].x : 0,
            y: nodePositions[device.id] ? nodePositions[device.id].y : 0,
            shape: 'dot',
            size: 1,
            color: {
                background: 'rgba(0,0,0,0)',
                border: 'rgba(0,0,0,0)',
                highlight: { background: 'rgba(0,0,0,0)', border: 'rgba(0,0,0,0)' }
            },
            font: { size: 0, color: 'rgba(0,0,0,0)' },
            title: `${device.name} (${device.ip_address || 'N/A'})`
        })));

        const edges = new vis.DataSet((resolvedData.connections || []).map((conn, idx) => {
            const fromDevice = (resolvedData.devices || []).find(d => d.id === conn.device_id);
            const toDevice = (resolvedData.devices || []).find(d => d.id === conn.connected_to);
            let edgeColor = '#999';
            if (fromDevice && toDevice) {
                if (fromDevice.status === 'down' || toDevice.status === 'down') edgeColor = '#ef4444';
                else if (fromDevice.status === 'slow' || toDevice.status === 'slow') edgeColor = '#f59e0b';
                else if (fromDevice.status === 'up' && toDevice.status === 'up') edgeColor = '#10b981';
            }
            return {
                id: conn.id || `premium_edge_${index}_${idx}`,
                from: conn.device_id,
                to: conn.connected_to,
                color: { color: edgeColor, highlight: '#38bdf8' },
                width: 3,
                smooth: { type: 'curvedCW', roundness: 0.2 },
                shadow: { enabled: true, color: 'rgba(0,0,0,0.3)', size: 5, x: 2, y: 2 }
            };
        }));

        const network = new vis.Network(canvas, { nodes, edges }, {
            interaction: {
                hover: true,
                dragNodes: false,
                dragView: true,
                zoomView: true,
                navigationButtons: false,
                tooltipDelay: 200
            },
            physics: { enabled: false },
            nodes: { font: { size: 0, color: 'rgba(0,0,0,0)' } },
            edges: {
                color: { color: 'rgba(56, 189, 248, 0.5)', highlight: '#38bdf8' },
                width: 3,
                smooth: { type: 'curvedCW', roundness: 0.2 },
                shadow: { enabled: true, color: 'rgba(0,0,0,0.3)', size: 5, x: 2, y: 2 }
            }
        });

        (resolvedData.devices || []).forEach(device => this.renderPremiumWidgetNode(overlay, device, index));
        const sync = () => this.syncPremiumWidgetOverlay(index);
        network.on('afterDrawing', sync);
        network.on('selectNode', sync);
        network.on('deselectNode', sync);
        network.once('afterDrawing', () => {
            network.fit({ animation: false });
            setTimeout(sync, 0);
        });

        this.instances[`network_${index}`] = network;
        this.instances[`nodes_${index}`] = nodes;
        this.instances[`edges_${index}`] = edges;
        this.instances[`topology_overlay_${index}`] = overlay;
        this.instances[`topology_data_${index}`] = resolvedData;
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
        const GAUGE_MAX = 2000; // Increased to accommodate higher website/server thresholds
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
                const isLight = document.documentElement.getAttribute('data-theme') === 'light';
                const ticks = [0, 200, 500, 1000, 2000];
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillStyle = isLight ? '#64748b' : '#94a3b8'; // Adjusted for better contrast
                ctx.font = '600 14px Inter, sans-serif';

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
                    ctx.strokeStyle = isLight ? '#cbd5e1' : '#475569';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                });

                // Value Text (Centered below the needle axis)
                ctx.font = '800 48px Inter, sans-serif';
                ctx.fillStyle = isLight ? '#1e293b' : '#f8fafc';
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
                ctx.fillStyle = isLight ? '#1e293b' : '#f8fafc';
                ctx.strokeStyle = isLight ? '#f1f5f9' : '#1e1b4b';
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
        listHeader.innerHTML = '<span style="font-weight:700; font-size:1.1rem; color: var(--text-primary);">Top Slow Devices</span>';
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
                            <span style="font-weight:600; font-size:1.0rem; color: var(--text-primary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:70%;">${device.name}</span>
                            <span style="font-weight:700; color: #d97706; font-size:1.0rem;">${time.toFixed(2)} ms</span>
                        </div>
                        <div style="height: 6px; background: var(--bg-tertiary); border-radius: 3px; position: relative;">
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
                    <div style="margin-bottom: 0.5rem; font-size: 0.95rem;">
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
                    <div class="stat-label" style="font-size: 0.85rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px;">${label}</div>
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

    renderDevicePie: function (container, widget, data, index) {
        container.innerHTML = '';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.position = 'relative';
        container.style.padding = '1.25rem';

        // Chart Area
        const chartWrapper = document.createElement('div');
        chartWrapper.style.flex = '1';
        chartWrapper.style.position = 'relative';
        chartWrapper.style.minHeight = '140px';
        container.appendChild(chartWrapper);

        const canvas = document.createElement('canvas');
        canvas.style.position = 'absolute';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        chartWrapper.appendChild(canvas);

        const centerOverlay = document.createElement('div');
        centerOverlay.style.position = 'absolute';
        centerOverlay.style.top = '50%';
        centerOverlay.style.left = '50%';
        centerOverlay.style.transform = 'translate(-50%, -50%)';
        centerOverlay.style.textAlign = 'center';
        centerOverlay.style.pointerEvents = 'none';
        centerOverlay.innerHTML = `
            <div class="pie-total-val" style="font-size: 2.75rem; font-weight: 700; color: var(--text-primary); line-height: 1;">0</div>
            <div style="font-size: 0.75rem; font-weight: 600; color: var(--text-muted); letter-spacing: 1px; margin-top: 4px;">DEVICES</div>
        `;
        chartWrapper.appendChild(centerOverlay);

        // Legend Area
        const legendContainer = document.createElement('div');
        legendContainer.style.marginTop = '1.25rem';
        legendContainer.className = 'pie-legend-container';
        container.appendChild(legendContainer);

        const ctx = canvas.getContext('2d');
        const isLight = document.documentElement.getAttribute('data-theme') === 'light';
        const colorOnline = '#10b981';
        const colorWarning = '#f59e0b';
        const colorDown = '#ef4444';
        const colorOffline = '#64748b';

        const chart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Online', 'Warning', 'Down', 'Offline'],
                datasets: [{
                    data: [0, 0, 0, 0],
                    backgroundColor: [colorOnline, colorWarning, colorDown, colorOffline],
                    borderWidth: 0,
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '76%',
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        enabled: true,
                        callbacks: {
                            label: function(context) {
                                let label = context.label || '';
                                if (label) { label += ': '; }
                                if (context.parsed !== null) {
                                    const totalMatch = context.dataset.data.reduce((a, b) => a + b, 0);
                                    if (totalMatch > 0) {
                                        label += context.parsed + ' (' + Math.round((context.parsed / totalMatch) * 100) + '%)';
                                    } else {
                                        label += context.parsed;
                                    }
                                }
                                return label;
                            }
                        }
                    }
                },
                layout: { padding: 0 }
            }
        });

        this.instances[`chart_${index}`] = chart;
        
        // Initial Update
        this.updateDevicePie(container, widget, data, index);
    },

    updateDevicePie: function (container, widget, data, index) {
        const chart = this.instances[`chart_${index}`];
        if (!chart) return;

        const stats = data.stats || {};
        const countOnline = stats.devices_up || 0;
        const countSlow = stats.devices_slow || 0;
        const countDown = stats.devices_down || 0;
        const total = stats.total_devices || 0;
        const countOffline = Math.max(0, total - (countOnline + countSlow + countDown));

        const isLight = document.documentElement.getAttribute('data-theme') === 'light';
        const colorEmpty = isLight ? '#e2e8f0' : '#334155';
        const colorOnline = '#10b981';
        const colorWarning = '#f59e0b';
        const colorDown = '#ef4444';
        const colorOffline = '#64748b';

        // Update Chart
        if (total === 0) {
            chart.data.datasets[0].data = [1];
            chart.data.datasets[0].backgroundColor = [colorEmpty];
            chart.data.labels = ['No Devices'];
            chart.options.plugins.tooltip.enabled = false;
        } else {
            chart.data.datasets[0].data = [countOnline, countSlow, countDown, countOffline];
            chart.data.datasets[0].backgroundColor = [colorOnline, colorWarning, colorDown, colorOffline];
            chart.data.labels = ['Online', 'Warning', 'Down', 'Offline'];
            chart.options.plugins.tooltip.enabled = true;
        }
        chart.update();

        // Update Center Text
        const centerValEl = container.querySelector('.pie-total-val');
        if (centerValEl) centerValEl.textContent = total;

        // Update Legend
        const legendContainer = container.querySelector('.pie-legend-container');
        if (legendContainer) {
            const legendItems = [
                { label: 'Online', count: countOnline, color: colorOnline },
                { label: 'Warning', count: countSlow, color: colorWarning },
                { label: 'Down', count: countDown, color: colorDown },
                { label: 'Offline', count: countOffline, color: colorOffline }
            ];

            legendContainer.innerHTML = legendItems.map((item, idx) => {
                const borderBottom = idx !== legendItems.length - 1 ? 'border-bottom: 1px solid var(--border-color);' : '';
                return `
                <div style="display: flex; justify-content: space-between; padding: 0.6rem 0.25rem; ${borderBottom} font-size: 0.9rem;">
                    <div style="display: flex; align-items: center; color: var(--text-secondary);">
                        <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background-color: ${item.color}; margin-right: 0.75rem;"></span>
                        ${item.label}
                    </div>
                    <div style="font-weight: 600; color: var(--text-primary);">${item.count}</div>
                </div>
                `;
            }).join('');
        }
    },

    renderTopology: async function (container, widget, data, index) {
        // Just fill the container
        container.style.height = '100%';
        container.style.position = 'relative';
        container.innerHTML = '';

        const canvas = document.createElement('div');
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.innerHTML = `<div class="flex-center" style="height:100%; color:var(--text-muted); font-size:0.9rem;">Loading topology...</div>`;
        container.appendChild(canvas);

        const requestKey = `topology_request_${index}`;
        const token = Date.now() + Math.random();
        this.instances[requestKey] = token;

        let resolvedData;
        try {
            resolvedData = await this.resolveTopologyData(widget, data, index);
        } catch (e) {
            console.error('Error loading topology widget:', e);
            if (this.instances[requestKey] === token) {
                canvas.innerHTML = `<div class="flex-center" style="height:100%; color:var(--danger); font-size:0.9rem;">Failed to load topology</div>`;
            }
            return;
        }

        if (this.instances[requestKey] !== token) {
            return;
        }

        if (this.isPremiumTopologyWidget(widget, resolvedData)) {
            this.renderPremiumTopology(container, widget, resolvedData, index);
            return;
        }

        const { nodes, edges } = this.buildTopologyDatasets(resolvedData);
        canvas.innerHTML = '';
        this.addTopologyZoomControls(container, index);

        const options = {
            nodes: {
                shape: 'circularImage',
                font: { color: document.documentElement.getAttribute('data-theme') === 'light' ? '#0f172a' : '#f1f5f9', size: 30, face: 'Inter, sans-serif' }
            },
            physics: {
                enabled: true,
                solver: 'barnesHut',
                barnesHut: {
                    gravitationalConstant: -8000, 
                    centralGravity: 0.3, // Updated per user request
                    springLength: 250, // Updated per user request
                    springConstant: 0.05,
                    damping: 0.09,
                    avoidOverlap: 1
                },
                stabilization: { 
                    iterations: 5000,
                    updateInterval: 100
                }
            },
            layout: { 
                improvedLayout: true,
                randomSeed: 2,
                hierarchical: false
            },
            interaction: { zoomView: true, dragView: true, hover: true },
            autoResize: true
        };


        const network = new vis.Network(canvas, { nodes, edges }, options);

        // Hover events for enlargement
        network.on('hoverNode', (params) => {
            nodes.update({
                id: params.node,
                size: 150,
                font: { size: 50 }
            });
            canvas.style.cursor = 'pointer';
        });

        network.on('blurNode', (params) => {
            nodes.update({
                id: params.node,
                size: 100,
                font: { size: 30 }
            });
            canvas.style.cursor = 'default';
        });

        // Fit network and stop physics when stabilization is done
        const stopPhysics = () => {
            if (network.stabilized) return;
            console.log('Topology stabilized, locking physics.');
            network.setOptions({ physics: false });
            network.fit();
            network.stabilized = true; // Flag to prevent re-fitting in updateTopology
        };

        network.on('stabilizationFinished', stopPhysics);
        network.on('stabilizationIterationsDone', stopPhysics);

        // Fallback: Force stop physics after 5 seconds
        setTimeout(() => {
            if (!network.stabilized) {
                console.log('Physics fallback: Locking movement.');
                stopPhysics();
            }
        }, 5000);

        this.instances[`network_${index}`] = network;
        this.instances[`nodes_${index}`] = nodes;
        this.instances[`edges_${index}`] = edges;
        this.instances[`topology_overlay_${index}`] = null;
        this.instances[`topology_data_${index}`] = resolvedData;
    },




    updateTopology: async function (container, index, data, widget) {
        const nodesDS = this.instances[`nodes_${index}`];
        const edgesDS = this.instances[`edges_${index}`];
        const network = this.instances[`network_${index}`];

        let resolvedData;
        try {
            resolvedData = await this.resolveTopologyData(widget, data, index);
        } catch (e) {
            console.error('Error updating topology widget:', e);
            return;
        }

        if (this.isPremiumTopologyWidget(widget, resolvedData)) {
            this.renderPremiumTopology(container, widget, resolvedData, index);
            return;
        }

        this.instances[`topology_data_${index}`] = resolvedData;

        if (!nodesDS || !edgesDS || !network) return; // Should re-render if missing

        // 1. Update Nodes
        const currentIds = new Set(nodesDS.getIds());
        const newIds = new Set();

        const validDevices = (resolvedData.devices || []);

        const nodeUpdates = validDevices.map(device => {
            newIds.add(device.id);
            const rt = device.response_time !== null && device.response_time !== undefined ? `${device.response_time} ms` : 'N/A';
            return {
                id: device.id,
                label: device.name,
                title: `Device: ${device.name}\nStatus: ${device.status.toUpperCase()}\nLocation: ${device.location || 'N/A'}\nResponse: ${rt}`,
                shape: 'circularImage',
                image: this.getNodeSvgUrl(device.device_type, device.status),
                size: 100,
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
        (resolvedData.connections || []).forEach(conn => {
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

        // Only fit if NOT yet stabilized (initial load) or if nodes were removed/added significantly
        if (network && !network.stabilized && (toRemove.length > 0 || edgesToRemove.length > 0 || nodeUpdates.length > 0)) {
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
        const alerts = devices.filter(d => d.status === 'down' || d.status === 'slow');

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
        const currentRange = this.instances[`trend_range_${index}`] || 60;
        this.instances[`trend_range_${index}`] = currentRange;
        this.instances[`widget_${index}`] = widget;

        const filterType = widget.config ? widget.config.deviceType : null;
        const filterDeviceId = widget.config ? widget.config.deviceId : null;
        let contentArea = document.getElementById(`trend-content-${index}`);

        // Only render the structure if it's not already there
        if (!contentArea) {
            container.style.height = '100%';
            container.style.display = 'flex';
            container.style.flexDirection = 'column';
            container.style.overflow = 'hidden';

            container.innerHTML = `
                <div style="display: flex; justify-content: flex-end; gap: 5px; margin-bottom: 10px; flex-shrink: 0;">
                    ${[15, 60, 180].map(r => `
                        <button class="btn btn-sm ${currentRange === r ? 'btn-primary' : 'btn-outline-secondary'}" 
                                style="padding: 2px 8px; font-size: 0.75rem;"
                                onclick="window.DashboardRenderer.setTrendRange(${index}, ${r}, this)">
                            ${r >= 180 ? '3h' : r >= 60 ? '1h' : r + 'm'}
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
            // Add margin to requested minutes to ensure we always get data even with monitoring gaps
            let requestMinutes = currentRange;
            if (currentRange <= 15) requestMinutes = 30;
            else if (currentRange <= 60) requestMinutes = 90;
            const url = filterDeviceId 
                ? `/api/statistics/trend?minutes=${requestMinutes}&device_id=${filterDeviceId}&_t=${Date.now()}`
                : `/api/statistics/trend?minutes=${requestMinutes}&_t=${Date.now()}`;
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const trends = await response.json();

            // Re-check contentArea in case it was destroyed during fetch
            contentArea = document.getElementById(`trend-content-${index}`);
            if (!contentArea) return;

            // Optional: fallback to empty array if undefined
            const safeTrends = trends || [];

            // --- Added Padding Logic ---
            const pointsToDisplay = 50;
            const now = new Date();
            const start = new Date(now.getTime() - currentRange * 60 * 1000);
            const stepMs = (now.getTime() - start.getTime()) / pointsToDisplay;

            const timeBuckets = [];
            const isShortRange = currentRange <= 10;

            // Generate exact 50 linear buckets for X-axis labels
            for (let i = 0; i < pointsToDisplay; i++) {
                const bucketTime = new Date(start.getTime() + (i * stepMs));
                const isoString = new Date(bucketTime.getTime() - (bucketTime.getTimezoneOffset() * 60000)).toISOString();
                const timeLabel = isShortRange ? isoString.substring(11, 19) : isoString.substring(11, 16);
                timeBuckets.push({
                    time: bucketTime.getTime(),
                    label: timeLabel
                });
            }
            // ---------------------------

            const datasets = {};

            // Process data into datasets
            safeTrends.forEach(item => {
                const type = item.device_type || 'other';
                const dId = item.device_id;
                const dName = item.device_name;
                
                // Filtering
                if (filterDeviceId) {
                    if (String(dId) !== String(filterDeviceId)) return;
                } else if (filterType && type !== filterType) {
                    return;
                }

                // Determine label and key
                const datasetKey = filterDeviceId ? `dev_${dId}` : type;
                const datasetLabel = filterDeviceId ? (dName || `Device ${dId}`) : (this.typeMetadata[type]?.name || type);

                if (!datasets[datasetKey]) {
                    const meta = this.typeMetadata[type] || this.typeMetadata['other'];
                    datasets[datasetKey] = {
                        label: datasetLabel,
                        data: Array(pointsToDisplay).fill(null),
                        borderColor: meta.color,
                        backgroundColor: meta.color + '20',
                        borderWidth: 2,
                        tension: 0,
                        fill: true,
                        pointRadius: 1,
                        spanGaps: true
                    };
                }

                // Parse "YYYY-MM-DD HH:MM:SS" manually to avoid browser timezone/ISO parsing bugs
                const parts = item.timestamp.split(/[- :]/);
                const year = parseInt(parts[0], 10);
                const month = parseInt(parts[1], 10) - 1; // 0-indexed month
                const day = parseInt(parts[2], 10);
                const hours = parseInt(parts[3] || 0, 10);
                const minutes = parseInt(parts[4] || 0, 10);
                const seconds = parseInt(parts[5] || 0, 10);

                // This guarantees the timestamp is treated as explicitly local Browser time, matching our X-axis bounds
                const itemTime = new Date(year, month, day, hours, minutes, seconds).getTime();

                // Only push points within our viewing window (allowing 5 mins grace for timezone slop)
                if (itemTime >= start.getTime() - (5 * 60000)) {
                    // Find closest matching label for categorical X-axis using strict math
                    let closestIndex = Math.floor((itemTime - start.getTime()) / stepMs);

                    // Clamp to valid array bounds (0 to 49)
                    if (closestIndex < 0) closestIndex = 0;
                    if (closestIndex >= pointsToDisplay) closestIndex = pointsToDisplay - 1;

                    // Directly assign value to the mathematical array position instead of pushing categorical X strings
                    datasets[datasetKey].data[closestIndex] = Math.round(item.avg_response_time);
                }
            });

            // Extract the labels
            const sortedTimes = timeBuckets.map(b => b.label);

            const chartDatasets = Object.values(datasets);



            const existingChart = this.instances[`chart_${index}`];
            if (existingChart && document.getElementById(`trend-chart-${index}`)) {
                // Smooth literal update for live WebSocket ticks
                existingChart.data.labels = sortedTimes;

                // Deep mutation to force Chart.js to recognize array changes
                existingChart.data.datasets.forEach((dataset, i) => {
                    if (chartDatasets[i]) {
                        dataset.data = chartDatasets[i].data;
                    }
                });

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

    renderBandwidth: function (container, widget, data, index) {
        this.updateBandwidth(container, widget, data, index);
    },

    updateBandwidth: function (container, widget, data, index) {
        if (!data.bandwidth || !data.bandwidth.top_interfaces || data.bandwidth.top_interfaces.length === 0) {
            container.innerHTML = `
                <div style="padding: 2rem; color: var(--text-muted); text-align: center; height: 100%; display: flex; align-items: center; justify-content: center;">
                    <em>No bandwidth data available</em>
                </div>`;
            return;
        }

        const top = data.bandwidth.top_interfaces;
        let displayData = [];
        const mode = widget.config ? widget.config.mode : 'top';

        if (mode === 'specific_chart' && widget.config.deviceId && widget.config.ifIndex) {
            // Chart rendering for specific interface
            const chartCanvasId = 'bwchart_' + widget.id;
            
            // Check if chart already drawn and we just need to update it (optional optimization)
            // But usually container is cleared by dashboard engine. We'll draw fresh.
            container.innerHTML = `
                <div style="height: 100%; width: 100%; padding: 0.5rem; display: flex; flex-direction: column;">
                    <div id="bwchart-loading-${widget.id}" style="text-align: center; color: var(--text-muted); font-size: 0.8rem; padding: 1rem;">
                        <i class="fa-solid fa-spinner fa-spin"></i> Loading chart data...
                    </div>
                    <div style="flex-grow: 1; position: relative;">
                        <canvas id="${chartCanvasId}"></canvas>
                    </div>
                </div>
            `;

            // Asynchronously fetch history for this specific interface
            fetch(`/api/bandwidth/history?device_id=${widget.config.deviceId}&if_index=${widget.config.ifIndex}&minutes=60`)
                .then(r => r.json())
                .then(hist => {
                    const loadingEl = document.getElementById(`bwchart-loading-${widget.id}`);
                    if (loadingEl) loadingEl.style.display = 'none';

                    if (!hist.success || !hist.history || hist.history.length === 0) {
                        const canvasContainer = document.getElementById(chartCanvasId)?.parentElement;
                        if (canvasContainer) {
                            canvasContainer.innerHTML = `
                                <div style="display:flex; height:100%; align-items:center; justify-content:center; color: var(--text-muted); font-size: 0.8rem;">
                                    No historical data found.
                                </div>
                            `;
                        }
                        return;
                    }

                    // Prepare data for Chart.js
                    // Sort ascending by time
                    const sortedHistory = hist.history.sort((a, b) => new Date(a.sampled_at) - new Date(b.sampled_at));
                    
                    const labels = [];
                    const dataIn = [];
                    const dataOut = [];
                    
                    sortedHistory.forEach(row => {
                        const d = new Date(row.sampled_at);
                        labels.push(d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
                        dataIn.push(row.bps_in ? parseFloat((row.bps_in / 1000000).toFixed(2)) : 0);
                        dataOut.push(row.bps_out ? parseFloat((row.bps_out / 1000000).toFixed(2)) : 0);
                    });

                    const canvas = document.getElementById(chartCanvasId);
                    if (!canvas) return; // widget might have been removed

                    if (this.instances[widget.id]) {
                        this.instances[widget.id].destroy();
                    }

                    const ctx = canvas.getContext('2d');
                    this.instances[widget.id] = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: [
                                {
                                    label: 'In (Mbps)',
                                    data: dataIn,
                                    borderColor: '#10b981',
                                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                                    fill: true,
                                    tension: 0.4,
                                    borderWidth: 2,
                                    pointRadius: 0,
                                    pointHitRadius: 10
                                },
                                {
                                    label: 'Out (Mbps)',
                                    data: dataOut,
                                    borderColor: '#f59e0b',
                                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                                    fill: true,
                                    tension: 0.4,
                                    borderWidth: 2,
                                    pointRadius: 0,
                                    pointHitRadius: 10
                                }
                            ]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            interaction: {
                                mode: 'index',
                                intersect: false,
                            },
                            plugins: {
                                legend: {
                                    display: true,
                                    position: 'top',
                                    labels: { boxWidth: 10, font: { size: 10 }, color: '#9ca3af' }
                                },
                                tooltip: {
                                    callbacks: {
                                        label: function(context) {
                                            return context.dataset.label + ': ' + context.parsed.y + ' Mbps';
                                        }
                                    }
                                }
                            },
                            scales: {
                                x: {
                                    grid: { display: false, drawBorder: false },
                                    ticks: { maxTicksLimit: 6, color: '#9ca3af', font: { size: 9 } }
                                },
                                y: {
                                    beginAtZero: true,
                                    grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false },
                                    ticks: { color: '#9ca3af', font: { size: 9 } }
                                }
                            }
                        }
                    });
                })
                .catch(err => {
                    console.error("Error loading bandwidth history:", err);
                    const loadingEl = document.getElementById(`bwchart-loading-${widget.id}`);
                    if (loadingEl) loadingEl.innerHTML = 'Error loading history';
                });

            return; // We exit early because rendering is async
        }
        else if (mode === 'specific' || mode === 'specific_table') {
            // Find the specific interface in the pooled current data
            const found = top.find(iface => 
                iface.device_id == widget.config.deviceId && 
                iface.if_index == widget.config.ifIndex
            );
            if (found) {
                displayData = [found];
            } else {
                container.innerHTML = `
                    <div style="padding: 1rem; color: var(--text-muted); text-align: center; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;">
                        <span style="font-size: 1.5rem; margin-bottom: 0.5rem;">🔍</span>
                        <div style="font-size: 0.8rem;">Interface not found in latest samples.</div>
                        <div style="font-size: 0.7rem; opacity: 0.7;">Check if SNMP is working for this device.</div>
                    </div>`;
                return;
            }
        } else {
            // Default "Top" mode
            const limitCount = widget.h === 2 ? 5 : (widget.h >= 6 ? 20 : 10);
            displayData = top.slice(0, limitCount);
        }

        let trs = displayData.map(iface => {
            const inMbps = (iface.avg_bps_in / 1000000).toFixed(2);
            const outMbps = (iface.avg_bps_out / 1000000).toFixed(2);
            return `
                <tr>
                    <td style="padding: 0.5rem; border-bottom: 1px solid var(--border-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 150px;" title="${iface.hostname || iface.device_name}">
                        <div style="font-weight: 500; color: var(--text-primary); text-overflow: ellipsis; overflow: hidden;">${iface.hostname || iface.device_name || 'Unknown'}</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-overflow: ellipsis; overflow: hidden;">${iface.if_name || iface.if_desc}</div>
                    </td>
                    <td style="padding: 0.5rem; border-bottom: 1px solid var(--border-color); text-align: right;">
                        <span style="color: #10b981; font-weight: 500;">${inMbps}</span>
                        <div style="font-size: 0.7rem; color: var(--text-muted);">In (Mbps)</div>
                    </td>
                    <td style="padding: 0.5rem; border-bottom: 1px solid var(--border-color); text-align: right;">
                        <span style="color: #f59e0b; font-weight: 500;">${outMbps}</span>
                        <div style="font-size: 0.7rem; color: var(--text-muted);">Out (Mbps)</div>
                    </td>
                </tr>
            `;
        }).join('');

        container.innerHTML = `
            <div class="table-responsive" style="height: 100%; overflow-y: auto; padding: 0.5rem;">
                <table style="width: 100%; border-collapse: collapse; font-size: 0.85rem; table-layout: fixed;">
                    <tbody>
                        ${trs}
                    </tbody>
                </table>
            </div>
        `;
    },
    renderNetworkTraffic: async function (container, widget, data, index) {
        const deviceId = widget.config ? widget.config.deviceId : null;
        const ifIndex = widget.config ? widget.config.ifIndex : null;
        const currentRange = this.instances[`nt_range_${index}`] || (widget.config ? widget.config.minutes : 60) || 60;
        this.instances[`nt_range_${index}`] = currentRange;
        this.instances[`widget_${index}`] = widget;

        if (!deviceId) {
            container.innerHTML = `<div class="flex-center" style="height:100%; flex-direction:column; gap:10px; color:var(--text-muted); font-size:0.9rem;"><i class="fas fa-exchange-alt" style="font-size:2rem;"></i><span>Please select a device in config</span></div>`;
            return;
        }

        const device = data && data.devices ? data.devices.find(d => String(d.id) === String(deviceId)) : null;
        if (!device && data) {
            container.innerHTML = `<div class="flex-center" style="height:100%; color:var(--danger);">Device not found</div>`;
            return;
        }

        // If we don't have device info yet (e.g. initial re-render without full data object)
        // we'll try to proceed or wait for data.
        const monitorType = device ? device.monitor_type : (widget.config ? widget.config.monitorType : 'ping');

        let chartArea = document.getElementById(`nt-chart-${index}`);
        if (!chartArea) {
            container.style.height = '100%';
            container.style.display = 'flex';
            container.style.flexDirection = 'column';
            container.style.overflow = 'hidden';
            container.innerHTML = `
                <div style="display: flex; justify-content: flex-end; gap: 5px; margin-bottom: 10px; flex-shrink: 0;">
                    ${[15, 60, 180, 360, 1440].map(r => `
                        <button class="btn btn-sm ${currentRange == r ? 'btn-primary' : 'btn-outline-secondary'}" 
                                style="padding: 2px 8px; font-size: 0.75rem;"
                                onclick="window.DashboardRenderer.setNetworkTrafficRange(${index}, ${r}, this)">
                            ${r >= 1440 ? '24h' : r >= 360 ? '6h' : r >= 180 ? '3h' : r >= 60 ? '1h' : r + 'm'}
                        </button>
                    `).join('')}
                </div>
                <div id="nt-chart-${index}" style="flex: 1; position: relative; min-height: 0;">
                    <canvas></canvas>
                </div>
            `;
            chartArea = document.getElementById(`nt-chart-${index}`);
        }

        try {
            let labels = [];
            let inData = [];
            let outData = [];

            if (monitorType === 'snmp') {
                if (ifIndex) {
                    const response = await fetch(`/api/bandwidth/history?device_id=${deviceId}&if_index=${ifIndex}&minutes=${currentRange}&_t=${Date.now()}`);
                    const history = await response.json();
                    if (history.success && history.history) {
                        for (let i = 0; i < history.history.length; i++) {
                            const p = history.history[i];
                            const d = new Date((p.timestamp || p.sampled_at).replace(' ', 'T'));
                            if (i > 0) {
                                const prevD = new Date((history.history[i-1].timestamp || history.history[i-1].sampled_at).replace(' ', 'T'));
                                if (d - prevD > 180000) {
                                    labels.push(''); inData.push(null); outData.push(null);
                                    labels.push(' '); inData.push(0); outData.push(0);
                                    labels.push(' '); inData.push(0); outData.push(0);
                                    labels.push(''); inData.push(null); outData.push(null);
                                }
                            }
                            labels.push(d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
                            inData.push(p.bps_in);
                            outData.push(p.bps_out);
                        }
                    }
                } else {
                    chartArea.innerHTML = `<div class="flex-center" style="height:100%; flex-direction:column; gap:8px; color:var(--text-muted); font-size:0.85rem;"><i class="fas fa-plug" style="font-size:1.5rem; opacity:0.5;"></i><span>Please select an interface in config</span></div>`;
                    return;
                }
            } else {
                 const hours = currentRange / 60;
                 const response = await fetch(`/api/devices/${deviceId}/performance?hours=${hours}&_t=${Date.now()}`);
                 const perfData = await response.json();
                 const netIn = perfData.network_in || [];
                 const netOut = perfData.network_out || [];
                 for (let i = 0; i < netIn.length; i++) {
                     const p = netIn[i];
                     const d = new Date((p.timestamp || p.checked_at).replace(' ', 'T'));
                     if (i > 0) {
                         const prevD = new Date((netIn[i-1].timestamp || netIn[i-1].checked_at).replace(' ', 'T'));
                         if (d - prevD > 180000) {
                             labels.push(''); inData.push(null); outData.push(null);
                             labels.push(' '); inData.push(0); outData.push(0);
                             labels.push(' '); inData.push(0); outData.push(0);
                             labels.push(''); inData.push(null); outData.push(null);
                         }
                     }
                     labels.push(d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
                     inData.push(p.value);
                     outData.push(netOut[i] ? netOut[i].value : null);
                 }
            }

            this.updateNetworkTrafficChart(`nt-chart-${index}`, labels, inData, outData, index);
        } catch (e) {
            console.error('Error loading NT data:', e);
            if (chartArea) chartArea.innerHTML = `<div class="flex-center" style="height:100%; color:var(--danger); font-size:0.8rem;">Error loading data</div>`;
        }
    },

    updateNetworkTrafficChart: function (containerId, labels, inData, outData, index) {
        const container = document.getElementById(containerId);
        if (!container) return;
        const canvas = container.querySelector('canvas');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const existingChart = this.instances[`chart_nt_${index}`];
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        const color = isDark ? '#ffffff' : '#4b5563';

        if (existingChart) {
            existingChart.data.labels = labels;
            existingChart.data.datasets[0].data = inData;
            existingChart.data.datasets[1].data = outData;
            existingChart.options.scales.x.ticks.color = color;
            existingChart.options.scales.y.ticks.color = color;
            existingChart.update('none');
        } else {
            this.instances[`chart_nt_${index}`] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'IN',
                            data: inData,
                            borderColor: '#10b981',
                            backgroundColor: '#10b98120',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.1,
                            pointRadius: (ctx) => ctx.chart.data.labels[ctx.dataIndex] === ' ' ? 3 : 0,
                            pointBackgroundColor: (ctx) => ctx.chart.data.labels[ctx.dataIndex] === ' ' ? '#ef4444' : '#10b981',
                            pointBorderColor: (ctx) => ctx.chart.data.labels[ctx.dataIndex] === ' ' ? '#ef4444' : '#10b981',
                            segment: {
                                borderColor: (ctx) => ctx.chart.data.labels[ctx.p0DataIndex] === ' ' && ctx.chart.data.labels[ctx.p1DataIndex] === ' ' ? '#ef4444' : undefined,
                                borderDash: (ctx) => ctx.chart.data.labels[ctx.p0DataIndex] === ' ' && ctx.chart.data.labels[ctx.p1DataIndex] === ' ' ? [4, 4] : undefined
                            }
                        },
                        {
                            label: 'OUT',
                            data: outData,
                            borderColor: '#3b82f6',
                            backgroundColor: '#3b82f620',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.1,
                            pointRadius: (ctx) => ctx.chart.data.labels[ctx.dataIndex] === ' ' ? 3 : 0,
                            pointBackgroundColor: (ctx) => ctx.chart.data.labels[ctx.dataIndex] === ' ' ? '#ef4444' : '#3b82f6',
                            pointBorderColor: (ctx) => ctx.chart.data.labels[ctx.dataIndex] === ' ' ? '#ef4444' : '#3b82f6',
                            segment: {
                                borderColor: (ctx) => ctx.chart.data.labels[ctx.p0DataIndex] === ' ' && ctx.chart.data.labels[ctx.p1DataIndex] === ' ' ? '#ef4444' : undefined,
                                borderDash: (ctx) => ctx.chart.data.labels[ctx.p0DataIndex] === ' ' && ctx.chart.data.labels[ctx.p1DataIndex] === ' ' ? [4, 4] : undefined
                            }
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    spanGaps: false,
                    plugins: {
                        legend: { 
                            display: true, 
                            position: 'top', 
                            labels: { 
                                boxWidth: 12, 
                                font: { size: 10 },
                                color: color
                            } 
                        },
                        tooltip: { mode: 'index', intersect: false }
                    },
                    scales: {
                        x: { 
                            grid: { display: false },
                            ticks: { font: { size: 9 }, color: color, maxTicksLimit: 6 }
                        },
                        y: {
                            beginAtZero: true,
                            grid: { color: 'rgba(100,116,139,0.1)' },
                            ticks: { 
                                font: { size: 9 }, 
                                color: color,
                                callback: (val) => {
                                    if (val >= 1000000) return (val/1000000).toFixed(1) + 'M';
                                    if (val >= 1000) return (val/1000).toFixed(1) + 'K';
                                    return val;
                                }
                            }
                        }
                    }
                }
            });
        }
    },

    setNetworkTrafficRange: function (index, range, btn) {
        const parent = btn.parentElement;
        parent.querySelectorAll('button').forEach(b => {
            b.classList.remove('btn-primary');
            b.classList.add('btn-outline-secondary');
        });
        btn.classList.remove('btn-outline-secondary');
        btn.classList.add('btn-primary');

        this.instances[`nt_range_${index}`] = range;
        const widget = this.instances[`widget_${index}`];
        const container = document.getElementById(`nt-chart-${index}`).parentElement; 

        // Use a robust way to get current device data depending on if we are in builder or view
        const data = (typeof cachedData !== 'undefined' && cachedData) ? cachedData : (typeof originalData !== 'undefined' ? originalData : { devices: [] });
        this.renderNetworkTraffic(container, widget, data, index);
    },

    clearInstances: function () {
        Object.values(this.instances).forEach(inst => {
            if (inst && typeof inst.destroy === 'function') inst.destroy();
        });
        this.instances = {};
    },
    renderSystemMetrics: async function (container, widget, data, index) {
        const deviceId = widget.config ? widget.config.deviceId : null;
        const currentRange = this.instances[`sys_range_${index}`] || (widget.config ? widget.config.minutes : 60) || 60;
        this.instances[`sys_range_${index}`] = currentRange;
        this.instances[`widget_${index}`] = widget;

        if (!deviceId) {
            container.innerHTML = `
                <div class="flex-center" style="height: 100%; flex-direction: column; gap: 10px; color: var(--text-muted); font-size: 0.9rem;">
                    <i class="fas fa-server" style="font-size: 2rem;"></i>
                    <span>Please select a specific device in config</span>
                </div>
            `;
            return;
        }

        let contentArea = document.getElementById(`sys-content-${index}`);
        if (!contentArea) {
            container.style.height = '100%';
            container.style.display = 'flex';
            container.style.flexDirection = 'column';
            container.style.overflow = 'hidden';

            container.innerHTML = `
                <div style="display: flex; justify-content: flex-end; gap: 5px; margin-bottom: 10px; flex-shrink: 0;">
                    ${[15, 60, 180, 360, 1440].map(r => `
                        <button class="btn btn-sm ${currentRange == r ? 'btn-primary' : 'btn-outline-secondary'}" 
                                style="padding: 2px 8px; font-size: 0.75rem;"
                                onclick="window.DashboardRenderer.setSystemMetricsRange(${index}, ${r}, this)">
                            ${r >= 1440 ? '24h' : r >= 360 ? '6h' : r >= 180 ? '3h' : r >= 60 ? '1h' : r + 'm'}
                        </button>
                    `).join('')}
                </div>
                <div id="sys-content-${index}" style="flex: 1; display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; min-height: 0;">
                    <div class="sys-metric-box" style="position: relative; border: 1px solid var(--border-color); border-radius: 8px; padding: 5px; background: var(--bg-secondary); display: flex; flex-direction: column; box-shadow: var(--shadow-sm);">
                        <div style="font-size: 0.65rem; font-weight: 700; color: var(--text-primary); text-transform: uppercase; text-align: center;">CPU (%)</div>
                        <div id="sys-cpu-${index}" style="flex: 1; position: relative; min-height: 0;"></div>
                    </div>
                    <div class="sys-metric-box" style="position: relative; border: 1px solid var(--border-color); border-radius: 8px; padding: 5px; background: var(--bg-secondary); display: flex; flex-direction: column; box-shadow: var(--shadow-sm);">
                        <div style="font-size: 0.65rem; font-weight: 700; color: var(--text-primary); text-transform: uppercase; text-align: center;">RAM (%)</div>
                        <div id="sys-ram-${index}" style="flex: 1; position: relative; min-height: 0;"></div>
                    </div>
                    <div class="sys-metric-box" style="position: relative; border: 1px solid var(--border-color); border-radius: 8px; padding: 5px; background: var(--bg-secondary); display: flex; flex-direction: column; box-shadow: var(--shadow-sm);">
                        <div style="font-size: 0.65rem; font-weight: 700; color: var(--text-primary); text-transform: uppercase; text-align: center;">Disk (%)</div>
                        <div id="sys-disk-${index}" style="flex: 1; position: relative; min-height: 0;"></div>
                    </div>
                </div>
            `;
            contentArea = document.getElementById(`sys-content-${index}`);
        }

        try {
            const hours = currentRange / 60;
            const response = await fetch(`/api/devices/${deviceId}/performance?hours=${hours}&_t=${Date.now()}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const perfData = await response.json();

            this.renderPerfChart(`sys-cpu-${index}`, 'CPU', perfData.cpu || [], '#10b981', `${index}_cpu`);
            this.renderPerfChart(`sys-ram-${index}`, 'RAM', perfData.ram || [], '#6366f1', `${index}_ram`);
            this.renderPerfChart(`sys-disk-${index}`, 'Disk', perfData.disk || [], '#f59e0b', `${index}_disk`);

        } catch (e) {
            console.error('Error loading metrics:', e);
            if (contentArea) contentArea.innerHTML = `<div class="flex-center" style="grid-column: span 3; color: var(--danger); font-size: 0.8rem;">Error loading data</div>`;
        }
    },

    renderPerfChart: function (containerId, label, points, color, instanceKey) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const labels = points.map(p => {
            const dateStr = p.timestamp || p.checked_at || p.sampled_at;
            if (!dateStr) return '';
            const d = new Date(dateStr.replace(' ', 'T')); // Ensure ISO-ish for parsing
            return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        });
        const values = points.map(p => p.value);

        const existingChart = this.instances[`chart_${instanceKey}`];
        
        if (existingChart && container.querySelector('canvas')) {
            existingChart.data.labels = labels;
            existingChart.data.datasets[0].data = values;
            existingChart.update('none');
        } else {
            container.innerHTML = '<canvas style="width: 100%; height: 100%;"></canvas>';
            const ctx = container.querySelector('canvas').getContext('2d');
            
            if (existingChart) existingChart.destroy();

            this.instances[`chart_${instanceKey}`] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: label,
                        data: values,
                        borderColor: color,
                        backgroundColor: color + '15',
                        borderWidth: 2,
                        pointRadius: 0,
                        fill: true,
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { 
                        legend: { display: false }, 
                        tooltip: { mode: 'index', intersect: false } 
                    },
                    scales: {
                        x: { 
                            display: true,
                            grid: { display: false },
                            ticks: { 
                                maxRotation: 0, 
                                autoSkip: true, 
                                maxTicksLimit: 4,
                                font: { size: 10 },
                                color: document.documentElement.getAttribute('data-theme') === 'dark' ? '#ffffff' : '#4b5563'
                            }
                        },
                        y: { 
                            display: true,
                            beginAtZero: true, 
                            max: 100,
                            grid: { color: 'rgba(100, 116, 139, 0.1)' },
                            ticks: { 
                                font: { size: 10 },
                                color: document.documentElement.getAttribute('data-theme') === 'dark' ? '#ffffff' : '#4b5563',
                                callback: function(value) { return value + '%'; },
                                maxTicksLimit: 4
                            }
                        }
                    }
                }
            });
        }
    },

    setSystemMetricsRange: function (index, range, btn) {
        const parent = btn.parentElement;
        parent.querySelectorAll('button').forEach(b => {
            b.classList.remove('btn-primary');
            b.classList.add('btn-outline-secondary');
        });
        btn.classList.remove('btn-outline-secondary');
        btn.classList.add('btn-primary');

        this.instances[`sys_range_${index}`] = range;
        const widget = this.instances[`widget_${index}`];
        const container = document.getElementById(`sys-content-${index}`).parentElement; 
        this.renderSystemMetrics(container, widget, null, index);
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
        case 'bandwidth': return 'Top Bandwidth';
        case 'network_traffic': return 'Network Traffic';
        default: return 'Widget';
    }
}
