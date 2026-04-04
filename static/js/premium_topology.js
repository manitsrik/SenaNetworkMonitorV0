// premium_topology.js
// Logic for Dual Template Map (Floating 3D Nodes vs Wide Server Cards)

let devices = [];
let lines = [];
let socket;

// Tier mappings
const TIER_MAPPING = {
    'internet': 'internet', 'cloud': 'internet',
    'firewall': 'firewall', 'router': 'firewall', 'vpnrouter': 'firewall',
    'switch': 'core', 'wifi': 'core', 'wireless': 'core',
    'server': 'servers', 'database': 'servers', 'web': 'servers', 
    'storage': 'servers', 'linux': 'servers', 'windows': 'servers', 'vmware': 'servers',
    'wmi': 'servers', 'ssh': 'servers'
};

const ICON_MAPPING = {
    'internet': 'fa-globe', 'cloud': 'fa-cloud',
    'firewall': 'fa-shield-halved', 'router': 'fa-route',
    'switch': 'fa-network-wired', 'wifi': 'fa-wifi', 'wireless': 'fa-wifi',
    'database': 'fa-database', 'web': 'fa-server',
    'storage': 'fa-hard-drive', 'vmware': 'fa-layer-group',
    'server': 'fa-server', 'linux': 'fa-linux', 'windows': 'fa-windows'
};

const GLOW_MAPPING = {
    'internet': 'glow-internet',
    'firewall': 'glow-firewall',
    'core': 'glow-switch',
    'servers': 'glow-server' // Not used for wide cards anyway
};

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    setupSockets();
});

async function initMap() {
    try {
        const res = await fetch('/api/devices');
        if (!res.ok) throw new Error('Failed to fetch devices');
        devices = await res.json();
        
        renderTopology();
        document.getElementById('topology-loading').style.display = 'none';

        // Wait for DOM to paint completely
        setTimeout(() => {
            drawLines();
        }, 400);

        window.addEventListener('resize', () => {
            lines.forEach(l => {
                try { l.position(); } catch (e) {}
            });
        });

    } catch (e) {
        console.error(e);
        document.getElementById('topology-loading').innerHTML = `<h3 class="text-danger">Failed to load map: ${e.message}</h3>`;
    }
}

function getTier(type) {
    if (!type) return 'servers';
    return TIER_MAPPING[type.toLowerCase()] || 'servers';
}

function getIcon(type) {
    if (!type) return 'fa-server';
    const t = type.toLowerCase();
    return ICON_MAPPING[t] || 'fa-server';
}

function getBarColor(val) {
    if (val == null) return 'healthy';
    if (val >= 90) return 'critical';
    if (val >= 70) return 'warning';
    return 'healthy';
}

function createDeviceCardDom(dv) {
    const tier = getTier(dv.device_type);
    const isServer = (tier === 'servers');
    const type = (dv.device_type || '').toLowerCase();
    const isWireless = type === 'wireless' || type === 'wifi';
    
    // Choose Template
    const tmplId = isWireless ? 'wireless-ap-template' : (isServer ? 'wide-server-template' : 'floating-node-template');
    const tmpl = document.getElementById(tmplId).innerHTML;
    
    let cpu = dv.cpu_usage || 0;
    if (dv.status !== 'up' && dv.status !== 'slow') {
        cpu = 0; 
    }

    let html = tmpl
        .replace(/{id}/g, dv.id)
        .replace(/{status}/g, dv.status || 'unknown')
        .replace(/{icon}/g, getIcon(dv.device_type))
        .replace(/{glow-class}/g, GLOW_MAPPING[tier])
        .replace(/{name}/g, dv.name)
        .replace(/{ip}/g, dv.ip_address || '0.0.0.0')
        .replace(/{cpu}/g, cpu)
        .replace(/{cpu-color}/g, getBarColor(cpu));

    if (isWireless) {
        html = html.replace(/{image_url}/g, '/static/icons/premium_wireless.svg?v=2');
    }
        
    const div = document.createElement('div');
    div.innerHTML = html.trim();
    const card = div.firstChild;

    // Interaction
    card.onclick = (e) => {
        if (!dv.isVirtual && typeof showPremiumDeviceDetails === 'function') {
            showPremiumDeviceDetails(dv);
        }
    };

    card.addEventListener('dblclick', () => {
        if (!dv.isVirtual) window.location.href = `/dashboard/${dv.id}`;
    });

    return card;
}

function renderTopology() {
    const tierContainers = {
        'internet': document.getElementById('tier-internet'),
        'firewall': document.getElementById('tier-firewall'),
        'core': document.getElementById('tier-core'),
        'servers': document.getElementById('tier-servers')
    };

    Object.values(tierContainers).forEach(c => c.innerHTML = '');

    // Inject "Internet" node if missing
    const hasNet = devices.some(d => getTier(d.device_type) === 'internet');
    if (!hasNet && devices.length > 0) {
        devices.push({
            id: 'virtual-internet',
            name: 'Global Internet',
            ip_address: 'WAN',
            device_type: 'internet',
            status: 'up',
            isVirtual: true
        });
    }

    devices.forEach(dv => {
        if(!dv.is_enabled && !dv.isVirtual) return; 
        const t = getTier(dv.device_type);
        const card = createDeviceCardDom(dv);
        tierContainers[t].appendChild(card);
    });
}

function drawLines() {
    // Clear and Redraw
    lines.forEach(l => { try { l.remove(); } catch(e){} });
    lines = [];
    
    // Links disabled per user preference to make Premium Map visually independent
    /*
    const getEl = (id) => document.getElementById(`device-${id}`);

    // Magic Fallback Routing
    const getFallbackParent = (childTier) => {
        let parentTier = 'internet';
        if (childTier === 'servers') parentTier = 'core';
        if (childTier === 'core') parentTier = 'firewall';
        
        const possibleParents = devices.filter(d => getTier(d.device_type) === parentTier && (d.is_enabled !== false || d.isVirtual));
        if (possibleParents.length > 0) return possibleParents[0].id;
        
        if (parentTier === 'core') return getFallbackParent('core');
        if (parentTier === 'firewall') return getFallbackParent('firewall');
        return null; // fallback to top tier
    };

    devices.forEach(dv => {
        if(!dv.is_enabled && !dv.isVirtual) return;
        const currentTier = getTier(dv.device_type);
        if (currentTier === 'internet' || currentTier === 'cloud') return; 

        let parentId = dv.parent_device_id;
        if (!parentId) parentId = getFallbackParent(currentTier);

        const childEl = getEl(dv.id);
        const parentEl = getEl(parentId);

        if (parentEl && childEl) {
            // Determine line status color
            const parentStatusDown = !dv.isVirtual && devices.find(d => d.id === parentId)?.status === 'down';
            const isDown = dv.status === 'down' || parentStatusDown;
            
            // Adjust attach points based on card shape
            // Servers are wide, usually attach to strictly TOP center
            // Floating blocks are squares, attach to BOTTOM center -> TOP center
            const lineOptions = {
                color: isDown ? 'rgba(239, 68, 68, 0.9)' : 'rgba(16, 185, 129, 0.7)',
                size: isDown ? 2 : 3,
                path: 'fluid',
                startSocket: 'bottom',
                endSocket: 'top',
                endPlug: 'arrow3',
                endPlugSize: 1.5,
                // LeaderLine native dash animation
                dash: isDown ? false : { animation: true }
            };

            const link = new LeaderLine(parentEl, childEl, lineOptions);
            lines.push(link);
        }
    });
    */
}

function setupSockets() {
    socket = io();
    socket.on('device_status_update', (data) => updateDeviceCard(data));
}

function updateDeviceCard(data) {
    const card = document.getElementById(`device-${data.id}`);
    if (!card) return; 

    // Sync Memory Model
    const dv = devices.find(d => d.id === data.id);
    if(dv) {
        dv.status = data.status;
        dv.cpu_usage = data.cpu !== undefined ? data.cpu : dv.cpu_usage;
    }

    // Floating Node Status Update
    const floatingStatus = card.querySelector('.floating-status');
    if (floatingStatus) floatingStatus.className = `floating-status status-${data.status}`;

    // Wide Node Metric Update
    const wideMetricVal = card.querySelector('.wide-metric-value');
    if (wideMetricVal) {
        const cpu = data.status === 'down' ? 0 : (data.cpu || dv.cpu_usage || 0);
        wideMetricVal.innerText = `${cpu}% CPU`;
        
        const barFill = card.querySelector('.wide-bar-fill');
        if (barFill) {
            barFill.style.width = `${cpu}%`;
            barFill.className = `wide-bar-fill bar-${getBarColor(cpu)}`;
        }
    }

    // Refresh lines instantly
    drawLines();
}
