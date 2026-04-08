function getDeviceIcon(status, deviceType) {
    let statusClass = 'status-unknown';
    if (status === 'up') statusClass = 'status-up';
    else if (status === 'down') statusClass = 'status-down';
    else if (status === 'slow') statusClass = 'status-slow';

    let faIcon = 'fa-server';
    switch (deviceType?.toLowerCase()) {
        case 'router': faIcon = 'fa-route'; break;
        case 'internet': faIcon = 'fa-cloud'; break;
        case 'switch': faIcon = 'fa-ethernet'; break;
        case 'firewall': faIcon = 'fa-shield-halved'; break;
        case 'wireless': faIcon = 'fa-wifi'; break;
        case 'website': faIcon = 'fa-globe'; break;
        case 'dns': faIcon = 'fa-book-atlas'; break;
        case 'vmware': faIcon = 'fa-server'; break;
        case 'ippbx': faIcon = 'fa-phone'; break;
        case 'cctv': faIcon = 'fa-video'; break;
        case 'vpnrouter': faIcon = 'fa-network-wired'; break;
        case 'server': faIcon = 'fa-server'; break;
        default: faIcon = 'fa-laptop'; break;
    }

    const html = `
        <div class="modern-marker ${statusClass}">
            <div class="marker-pulse"></div>
            <div class="marker-core">
                <i class="fa-solid ${faIcon}"></i>
            </div>
        </div>
    `;

    return L.divIcon({
        className: 'custom-modern-div-icon',
        html: html,
        iconSize: [40, 40],
        iconAnchor: [20, 20],
        popupAnchor: [0, -20]
    });
}

// Add styles dynamically for the custom modern map markers
const style = document.createElement('style');
style.innerHTML = `
.custom-modern-div-icon {
    background: transparent;
    border: none;
}
.modern-marker {
    position: relative;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.marker-core {
    width: 32px;
    height: 32px;
    background: var(--status-color);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 2;
    box-shadow: 0 3px 8px rgba(0,0,0,0.5);
    border: 2px solid white;
}
.marker-core i {
    font-size: 14px;
    color: white;
}
.marker-pulse {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    border-radius: 50%;
    background: var(--status-color);
    z-index: 1;
    opacity: 0.4;
}

/* Status Colors via CSS Variables */
.status-up { --status-color: #10b981; }
.status-down { --status-color: #f43f5e; }
.status-slow { --status-color: #f59e0b; }
.status-unknown { --status-color: #64748b; }

/* Pulse Animations */
@keyframes pulse-up {
    0% { transform: scale(0.9); opacity: 0.6; }
    50% { transform: scale(1.4); opacity: 0.1; }
    100% { transform: scale(0.9); opacity: 0.6; }
}
@keyframes pulse-down {
    0% { transform: scale(0.9); opacity: 0.8; }
    50% { transform: scale(1.6); opacity: 0; }
    100% { transform: scale(0.9); opacity: 0.8; }
}
@keyframes pulse-slow {
    0% { transform: scale(0.9); opacity: 0.7; }
    50% { transform: scale(1.3); opacity: 0.2; }
    100% { transform: scale(0.9); opacity: 0.7; }
}

.status-up .marker-pulse { animation: pulse-up 2s infinite ease-in-out; }
.status-down .marker-pulse { animation: pulse-down 1s infinite ease-in-out; }
.status-slow .marker-pulse { animation: pulse-slow 1.5s infinite ease-in-out; }
.status-unknown .marker-pulse { display: none; }

/* Adjust leaflet popup for modern look */
.leaflet-popup-content-wrapper {
    border-radius: 8px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.15);
}
`;
document.head.appendChild(style);

let map;
let allDevices = [];
let markerLayer = L.layerGroup();

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    fetchDevices();
});

function initMap() {
    // Default to Thailand center
    map = L.map('gis-map').setView([13.7563, 100.5018], 6);

    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    }).addTo(map);

    markerLayer.addTo(map);
}

function fetchDevices() {
    fetch('/api/devices')
        .then(res => res.json())
        .then(devices => {
            allDevices = devices;
            plotDevices();
        })
        .catch(err => console.error("Error fetching devices:", err));
}

function plotDevices() {
    markerLayer.clearLayers();
    const filter = document.getElementById('map-status-filter').value;
    
    let plottedCount = 0;
    let bounds = L.latLngBounds();

    allDevices.forEach(device => {
        if (!device.latitude || !device.longitude) return;
        if (filter !== 'all' && device.status !== filter) return;

        let icon = getDeviceIcon(device.status, device.device_type);

        const marker = L.marker([device.latitude, device.longitude], { icon: icon });
        const popupContent = `
            <div style="min-width: 200px;">
                <div style="font-weight: bold; font-size: 1.1em; border-bottom: 1px solid #ddd; margin-bottom: 5px; padding-bottom: 5px;">
                    ${device.name}
                </div>
                <div><strong>IP:</strong> ${device.ip_address}</div>
                <div><strong>Type:</strong> ${device.device_type}</div>
                <div><strong>Location:</strong> ${device.location || 'Unknown'}</div>
                <div><strong>Status:</strong> <span style="text-transform: uppercase; font-weight: bold; color: ${getStatusColor(device.status)}">${device.status}</span></div>
                <div><strong>Response:</strong> ${device.response_time !== null ? device.response_time + ' ms' : 'N/A'}</div>
                <div style="margin-top: 10px;">
                    <a href="/devices" class="btn btn-sm btn-primary" style="text-decoration: none; display: inline-block; padding: 2px 8px; color: white; background: #007bff; border-radius: 3px;">Manage Device</a>
                </div>
            </div>
        `;
        
        marker.bindPopup(popupContent);
        markerLayer.addLayer(marker);
        
        bounds.extend([device.latitude, device.longitude]);
        plottedCount++;
    });

    // Auto fit bounds if any points exist
    if (plottedCount > 0) {
        map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
    }
}

function getStatusColor(status) {
    switch (status) {
        case 'up': return '#28a745';
        case 'down': return '#dc3545';
        case 'slow': return '#ffc107';
        default: return '#6c757d';
    }
}

function filterMap() {
    plotDevices();
}

function refreshMap() {
    fetchDevices();
}

function toggleMapFullscreen() {
    const container = document.getElementById('map-container');
    if (!document.fullscreenElement) {
        if (container.requestFullscreen) {
            container.requestFullscreen();
        } else if (container.webkitRequestFullscreen) {
            container.webkitRequestFullscreen();
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
        }
    }
}

// Ensure map rectifies size when exiting fullscreen
document.addEventListener('fullscreenchange', () => {
    setTimeout(() => {
        if (map) map.invalidateSize();
    }, 100);
});
