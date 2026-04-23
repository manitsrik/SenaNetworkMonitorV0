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
    'internet': 'fa-cloud', 'cloud': 'fa-cloud',
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

function getPremiumInternetImageUrl() {
    const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="6 8 108 92">
        <defs>
            <linearGradient id="cloudStroke" x1="16" y1="18" x2="108" y2="82" gradientUnits="userSpaceOnUse">
                <stop offset="0" stop-color="#c8f6ff"/>
                <stop offset="0.25" stop-color="#67d3ff"/>
                <stop offset="0.62" stop-color="#38bdf8"/>
                <stop offset="1" stop-color="#2563eb"/>
            </linearGradient>
            <linearGradient id="globeStroke" x1="42" y1="34" x2="78" y2="68" gradientUnits="userSpaceOnUse">
                <stop offset="0" stop-color="#e0fbff"/>
                <stop offset="0.24" stop-color="#67e8f9"/>
                <stop offset="0.68" stop-color="#38bdf8"/>
                <stop offset="1" stop-color="#2563eb"/>
            </linearGradient>
            <filter id="glow" x="-30%" y="-30%" width="160%" height="170%">
                <feDropShadow dx="0" dy="0" stdDeviation="2.4" flood-color="#38bdf8" flood-opacity="0.12"/>
                <feDropShadow dx="0" dy="4" stdDeviation="3.4" flood-color="#0f172a" flood-opacity="0.12"/>
            </filter>
        </defs>
        <g filter="url(#glow)" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path d="M30 76h55c8 0 14-5 14-12 0-6-4-11-11-13-2-9-10-15-20-15-7 0-13 3-17 8-2-1-4-1-6-1-8 0-14 5-14 12v2c-5 2-9 7-9 12 0 8 6 14 14 14z" stroke="url(#cloudStroke)" stroke-width="5.8"/>
            <path d="M33 71h50c6 0 11-4 11-9s-4-9-10-9h-2c-2-8-9-13-17-13-6 0-11 2-15 7-2 0-3-1-5-1-6 0-11 4-11 10v2c-4 2-7 5-7 9 0 5 4 9 9 9z" stroke="#e0f2fe" stroke-opacity="0.42" stroke-width="1.7"/>
            <circle cx="58" cy="47" r="15.5" stroke="url(#globeStroke)" stroke-width="3.5"/>
            <ellipse cx="58" cy="47" rx="6.1" ry="15.5" stroke="url(#globeStroke)" stroke-width="2.2"/>
            <ellipse cx="58" cy="47" rx="12.4" ry="5.3" stroke="url(#globeStroke)" stroke-width="2.2"/>
            <path d="M43 47h30M58 32v30M48 38c3 2.7 6.4 4.1 10 4.1 3.6 0 7-1.4 10-4.1M48 56c3-2.7 6.4-4.1 10-4.1 3.6 0 7 1.4 10 4.1" stroke="url(#globeStroke)" stroke-width="1.95"/>
        </g>
    </svg>`;
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg.trim());
}

function createDeviceCardDom(dv) {
    const tier = getTier(dv.device_type);
    const isServer = (tier === 'servers');
    const type = (dv.device_type || '').toLowerCase();
    const isInternet = type === 'internet' || type === 'cloud';
    const isFirewall = type === 'firewall';
    const isRouter = type === 'router';
    const isWireless = type === 'wireless' || type === 'wifi';
    
    // Choose Template
    const tmplId = isInternet
        ? 'internet-node-template'
        : isWireless
        ? 'wireless-ap-template'
        : (isServer || isFirewall || isRouter ? 'rackmount-hardware-template' : 'floating-node-template');
    const tmpl = document.getElementById(tmplId).innerHTML;
    
    let cpu = dv.cpu_usage || 0;
    if (dv.status !== 'up' && dv.status !== 'slow') {
        cpu = 0; 
    }

    let imageUrl = '';
    if (isInternet) imageUrl = getPremiumInternetImageUrl();
    else if (isFirewall) imageUrl = '/static/icons/premium_firewall.svg?v=1';
    else if (isRouter) imageUrl = '/static/icons/premium_router.svg?v=1';
    else if (isWireless) imageUrl = '/static/icons/premium_wireless.svg?v=2';

    let html = tmpl
        .replace(/{id}/g, dv.id)
        .replace(/{status}/g, dv.status || 'unknown')
        .replace(/{icon}/g, getIcon(dv.device_type))
        .replace(/{glow-class}/g, GLOW_MAPPING[tier])
        .replace(/{image_url}/g, imageUrl)
        .replace(/{name}/g, dv.name)
        .replace(/{ip}/g, dv.ip_address || '0.0.0.0')
        .replace(/{cpu}/g, cpu)
        .replace(/{cpu-color}/g, getBarColor(cpu));
        
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
