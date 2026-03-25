/**
 * Settings Page JavaScript
 * Handles alert settings configuration
 */

// Load settings on page load
document.addEventListener('DOMContentLoaded', function () {
    loadSettings();
    loadLDAPSettings();
    loadAlertHistory();
});

/**
 * Load current settings from API
 */
async function loadSettings() {
    try {
        const response = await fetch('/api/alert-settings');
        const settings = await response.json();

        // General settings
        document.getElementById('alert_on_down').checked = settings.alert_on_down !== 'false';
        document.getElementById('alert_on_recovery').checked = settings.alert_on_recovery !== 'false';
        document.getElementById('alert_on_ssl_expiry').checked = settings.alert_on_ssl_expiry !== 'false';
        document.getElementById('alert_cooldown').value = settings.alert_cooldown || '300';

        // Email settings
        document.getElementById('email_enabled').checked = settings.email_enabled === 'true';
        document.getElementById('smtp_server').value = settings.smtp_server || '';
        document.getElementById('smtp_port').value = settings.smtp_port || '587';
        document.getElementById('smtp_user').value = settings.smtp_user || '';
        document.getElementById('smtp_password').value = settings.smtp_password || '';
        document.getElementById('smtp_from').value = settings.smtp_from || '';
        document.getElementById('email_recipient').value = settings.email_recipient || '';

        // LINE settings (deprecated)
        document.getElementById('line_enabled').checked = settings.line_enabled === 'true';
        document.getElementById('line_notify_token').value = settings.line_notify_token || '';

        // Telegram settings
        document.getElementById('telegram_enabled').checked = settings.telegram_enabled === 'true';
        document.getElementById('telegram_bot_token').value = settings.telegram_bot_token || '';
        document.getElementById('telegram_chat_id').value = settings.telegram_chat_id || '';

        // Escalation settings
        document.getElementById('escalation_enabled').checked = settings.escalation_enabled === 'true';
        document.getElementById('escalation_time_minutes').value = settings.escalation_time_minutes || '15';
        document.getElementById('escalation_channel_email').checked = settings.escalation_channel_email === 'true';
        document.getElementById('escalation_email_recipient').value = settings.escalation_email_recipient || '';
        document.getElementById('escalation_channel_telegram').checked = settings.escalation_channel_telegram === 'true';
        document.getElementById('escalation_telegram_chat_id').value = settings.escalation_telegram_chat_id || '';

        // Report settings
        document.getElementById('reports_enabled').checked = settings.reports_enabled === 'true';
        document.getElementById('report_time').value = settings.report_time || '08:00';
        document.getElementById('report_recipient').value = settings.report_recipient || '';

    } catch (error) {
        console.error('Error loading settings:', error);
        showAlert('Error loading settings', 'danger');
    }
}

/**
 * Save all settings
 */
async function saveSettings() {
    const settings = {
        // General
        alert_on_down: document.getElementById('alert_on_down').checked.toString(),
        alert_on_recovery: document.getElementById('alert_on_recovery').checked.toString(),
        alert_on_ssl_expiry: document.getElementById('alert_on_ssl_expiry').checked.toString(),
        alert_cooldown: document.getElementById('alert_cooldown').value,

        // Email
        email_enabled: document.getElementById('email_enabled').checked.toString(),
        smtp_server: document.getElementById('smtp_server').value,
        smtp_port: document.getElementById('smtp_port').value,
        smtp_user: document.getElementById('smtp_user').value,
        smtp_password: document.getElementById('smtp_password').value,
        smtp_from: document.getElementById('smtp_from').value,
        email_recipient: document.getElementById('email_recipient').value,

        // LINE (deprecated)
        line_enabled: document.getElementById('line_enabled').checked.toString(),
        line_notify_token: document.getElementById('line_notify_token').value,

        // Telegram
        telegram_enabled: document.getElementById('telegram_enabled').checked.toString(),
        telegram_bot_token: document.getElementById('telegram_bot_token').value,
        telegram_chat_id: document.getElementById('telegram_chat_id').value,

        // Escalation
        escalation_enabled: document.getElementById('escalation_enabled').checked.toString(),
        escalation_time_minutes: document.getElementById('escalation_time_minutes').value,
        escalation_channel_email: document.getElementById('escalation_channel_email').checked.toString(),
        escalation_email_recipient: document.getElementById('escalation_email_recipient').value,
        escalation_channel_telegram: document.getElementById('escalation_channel_telegram').checked.toString(),
        escalation_telegram_chat_id: document.getElementById('escalation_telegram_chat_id').value,

        // Reports
        reports_enabled: document.getElementById('reports_enabled').checked.toString(),
        report_time: document.getElementById('report_time').value,
        report_recipient: document.getElementById('report_recipient').value
    };

    try {
        const response = await fetch('/api/alert-settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });

        const result = await response.json();

        showAlert('Settings saved successfully!', 'success');
        
        // Also save LDAP settings if present
        await saveLDAPSettings();
        
        // Also save SSO settings if present
        await saveSSOSettings();
        
    } catch (error) {
        console.error('Error saving settings:', error);
        showAlert('Error saving settings', 'danger');
    }
}

/**
 * Load LDAP settings from API
 */
async function loadLDAPSettings() {
    try {
        const response = await fetch('/api/ldap/settings');
        const settings = await response.json();

        if (document.getElementById('ldap_enabled')) {
            document.getElementById('ldap_enabled').checked = settings.ldap_enabled === 'true';
            document.getElementById('ldap_server').value = settings.ldap_server || '';
            document.getElementById('ldap_port').value = settings.ldap_port || '389';
            document.getElementById('ldap_use_ssl').checked = settings.ldap_use_ssl === 'true';
            document.getElementById('ldap_base_dn').value = settings.ldap_base_dn || '';
            document.getElementById('ldap_bind_dn').value = settings.ldap_bind_dn || '';
            document.getElementById('ldap_bind_password').value = settings.ldap_bind_password || '';
            document.getElementById('ldap_user_filter').value = settings.ldap_user_filter || '(sAMAccountName={username})';
            document.getElementById('ldap_auto_create').checked = settings.ldap_auto_create !== 'false';
            document.getElementById('ldap_default_role').value = settings.ldap_default_role || 'viewer';
        }
        
        // After loading LDAP, load SSO
        await loadSSOSettings();
    } catch (error) {
        console.error('Error loading LDAP settings:', error);
    }
}

/**
 * Load SSO (OAuth2/OIDC) settings from API
 */
async function loadSSOSettings() {
    try {
        const response = await fetch('/api/sso/settings');
        const settings = await response.json();

        if (document.getElementById('sso_enabled')) {
            document.getElementById('sso_enabled').checked = settings.sso_enabled === 'true';
            document.getElementById('sso_provider_name').value = settings.sso_provider_name || 'SSO';
            document.getElementById('sso_client_id').value = settings.sso_client_id || '';
            document.getElementById('sso_client_secret').value = settings.sso_client_secret || '';
            document.getElementById('sso_discovery_url').value = settings.sso_discovery_url || '';
            document.getElementById('sso_authorize_url').value = settings.sso_authorize_url || '';
            document.getElementById('sso_token_url').value = settings.sso_token_url || '';
            document.getElementById('sso_userinfo_url').value = settings.sso_userinfo_url || '';
            document.getElementById('sso_scopes').value = settings.sso_scopes || 'openid email profile';
            document.getElementById('sso_auto_create').checked = settings.sso_auto_create !== 'false';
            document.getElementById('sso_default_role').value = settings.sso_default_role || 'viewer';
        }
    } catch (error) {
        console.error('Error loading SSO settings:', error);
    }
}

/**
 * Save SSO (OAuth2/OIDC) settings
 */
async function saveSSOSettings() {
    const enabledInput = document.getElementById('sso_enabled');
    if (!enabledInput) return { success: true };

    const settings = {
        sso_enabled: enabledInput.checked.toString(),
        sso_provider_name: document.getElementById('sso_provider_name').value,
        sso_client_id: document.getElementById('sso_client_id').value,
        sso_client_secret: document.getElementById('sso_client_secret').value,
        sso_discovery_url: document.getElementById('sso_discovery_url').value,
        sso_authorize_url: document.getElementById('sso_authorize_url').value,
        sso_token_url: document.getElementById('sso_token_url').value,
        sso_userinfo_url: document.getElementById('sso_userinfo_url').value,
        sso_scopes: document.getElementById('sso_scopes').value,
        sso_auto_create: document.getElementById('sso_auto_create').checked.toString(),
        sso_default_role: document.getElementById('sso_default_role').value
    };

    try {
        const response = await fetch('/api/sso/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        return await response.json();
    } catch (error) {
        console.error('Error saving SSO settings:', error);
        return { success: false, error: 'Network error' };
    }
}

/**
 * Apply SSO Presets (Google, Microsoft, GitHub)
 */
function applySSOPreset(provider) {
    const nameInput = document.getElementById('sso_provider_name');
    const discoveryInput = document.getElementById('sso_discovery_url');
    const authInput = document.getElementById('sso_authorize_url');
    const tokenInput = document.getElementById('sso_token_url');
    const userInfoInput = document.getElementById('sso_userinfo_url');
    const scopesInput = document.getElementById('sso_scopes');

    switch (provider) {
        case 'google':
            nameInput.value = 'Google';
            discoveryInput.value = 'https://accounts.google.com/.well-known/openid-configuration';
            authInput.value = '';
            tokenInput.value = '';
            userInfoInput.value = '';
            scopesInput.value = 'openid email profile';
            break;
        case 'microsoft':
            nameInput.value = 'Microsoft';
            discoveryInput.value = 'https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration';
            authInput.value = '';
            tokenInput.value = '';
            userInfoInput.value = '';
            scopesInput.value = 'openid email profile';
            break;
        case 'github':
            nameInput.value = 'GitHub';
            discoveryInput.value = '';
            authInput.value = 'https://github.com/login/oauth/authorize';
            tokenInput.value = 'https://github.com/login/oauth/access_token';
            userInfoInput.value = 'https://api.github.com/user';
            scopesInput.value = 'read:user user:email';
            break;
    }
    
    showAlert(`Applied ${provider} presets. Don't forget to enter your Client ID and Secret.`, 'info');
}

/**
 * Save LDAP settings
 */
async function saveLDAPSettings() {
    const serverInput = document.getElementById('ldap_server');
    if (!serverInput) return { success: true };

    const settings = {
        ldap_enabled: document.getElementById('ldap_enabled').checked.toString(),
        ldap_server: serverInput.value,
        ldap_port: document.getElementById('ldap_port').value,
        ldap_use_ssl: document.getElementById('ldap_use_ssl').checked.toString(),
        ldap_base_dn: document.getElementById('ldap_base_dn').value,
        ldap_bind_dn: document.getElementById('ldap_bind_dn').value,
        ldap_bind_password: document.getElementById('ldap_bind_password').value,
        ldap_user_filter: document.getElementById('ldap_user_filter').value,
        ldap_auto_create: document.getElementById('ldap_auto_create').checked.toString(),
        ldap_default_role: document.getElementById('ldap_default_role').value
    };

    try {
        const response = await fetch('/api/ldap/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        return await response.json();
    } catch (error) {
        console.error('Error saving LDAP settings:', error);
        return { success: false, error: 'Network error' };
    }
}

/**
 * Test LDAP connection
 */
async function testLDAP() {
    const resultDiv = document.getElementById('ldap-test-result');
    const testUsername = document.getElementById('ldap_test_user').value;
    const testPassword = document.getElementById('ldap_test_pw').value;

    if (!testUsername || !testPassword) {
        resultDiv.innerHTML = '<span style="color: var(--danger);">Username and password required for test</span>';
        return;
    }

    resultDiv.innerHTML = '<span style="color: var(--primary);">Testing connection...</span>';

    const settings = {
        ldap_server: document.getElementById('ldap_server').value,
        ldap_port: document.getElementById('ldap_port').value,
        ldap_use_ssl: document.getElementById('ldap_use_ssl').checked.toString(),
        ldap_base_dn: document.getElementById('ldap_base_dn').value,
        ldap_bind_dn: document.getElementById('ldap_bind_dn').value,
        ldap_bind_password: document.getElementById('ldap_bind_password').value,
        ldap_user_filter: document.getElementById('ldap_user_filter').value,
        test_username: testUsername,
        test_password: testPassword
    };

    try {
        const response = await fetch('/api/ldap/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        const result = await response.json();
        if (result.success) {
            resultDiv.innerHTML = `<span style="color: var(--success); font-weight: 500;">✅ ${result.message}</span>`;
        } else {
            resultDiv.innerHTML = `<span style="color: var(--danger); font-weight: 500;">❌ ${result.error}</span>`;
        }
    } catch (error) {
        resultDiv.innerHTML = `<span style="color: var(--danger);">❌ Error: ${error}</span>`;
    }
}

/**
 * Test email notification
 */
async function testEmail() {
    // Save settings first
    await saveSettings();

    showAlert('Sending test email...', 'info');

    try {
        const response = await fetch('/api/alert-test/email', {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            showAlert('✅ Test email sent successfully!', 'success');
        } else {
            showAlert('❌ Email failed: ' + (result.error || 'Unknown error'), 'danger');
        }
    } catch (error) {
        console.error('Error testing email:', error);
        showAlert('Error testing email', 'danger');
    }
}

/**
 * Test LINE notification
 */
async function testLine() {
    // Save settings first
    await saveSettings();

    showAlert('Sending test LINE message...', 'info');

    try {
        const response = await fetch('/api/alert-test/line', {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            showAlert('✅ Test LINE message sent successfully!', 'success');
        } else {
            showAlert('❌ LINE failed: ' + (result.error || 'Unknown error'), 'danger');
        }
    } catch (error) {
        console.error('Error testing LINE:', error);
        showAlert('Error testing LINE', 'danger');
    }
}

/**
 * Test Telegram notification
 */
async function testTelegram() {
    // Save settings first
    await saveSettings();

    showAlert('Sending test Telegram message...', 'info');

    try {
        const response = await fetch('/api/alert-test/telegram', {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            showAlert('✅ Test Telegram message sent successfully!', 'success');
        } else {
            showAlert('❌ Telegram failed: ' + (result.error || 'Unknown error'), 'danger');
        }
    } catch (error) {
        console.error('Error testing Telegram:', error);
        showAlert('Error testing Telegram', 'danger');
    }
}

/**
 * Send test scheduled report
 */
async function sendTestReport() {
    // Save settings first
    await saveSettings();

    showAlert('Generating and sending test report...', 'info');

    try {
        const response = await fetch('/api/reports/test', {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            showAlert('✅ Test report sent successfully!', 'success');
        } else {
            showAlert('❌ Report failed: ' + (result.error || 'Unknown error'), 'danger');
        }
    } catch (error) {
        console.error('Error sending test report:', error);
        showAlert('Error sending test report', 'danger');
    }
}

/**
 * Load alert history
 */
async function loadAlertHistory() {
    try {
        const response = await fetch('/api/alert-history?limit=50');
        const history = await response.json();

        const container = document.getElementById('alert-history');

        if (history.length === 0) {
            container.innerHTML = '<p class="text-center" style="color: var(--text-muted); padding: 1rem;">No alerts yet</p>';
            return;
        }

        let html = '<div class="table-responsive"><table class="table"><thead><tr><th>Time</th><th>Device</th><th>Event</th><th>Channel</th><th>Status</th></tr></thead><tbody>';

        for (const alert of history) {
            const time = new Date(alert.created_at).toLocaleString('th-TH');
            const eventBadge = getEventBadge(alert.event_type);
            const statusBadge = alert.status === 'sent'
                ? '<span class="status-badge status-up">Sent</span>'
                : '<span class="status-badge status-down">Failed</span>';
            const channelIcon = getChannelIcon(alert.channel);

            html += `
                <tr>
                    <td style="white-space: nowrap; font-size: 0.85rem;">${time}</td>
                    <td>${alert.device_name || 'Unknown'}</td>
                    <td>${eventBadge}</td>
                    <td>${channelIcon} ${alert.channel}</td>
                    <td>${statusBadge}</td>
                </tr>
            `;
        }

        html += '</tbody></table></div>';
        container.innerHTML = html;

    } catch (error) {
        console.error('Error loading alert history:', error);
        document.getElementById('alert-history').innerHTML =
            '<p class="text-center" style="color: var(--danger); padding: 1rem;">Error loading history</p>';
    }
}

/**
 * Get badge HTML for event type
 */
function getEventBadge(eventType) {
    switch (eventType) {
        case 'down':
            return '<span class="status-badge status-down">🔴 Down</span>';
        case 'recovery':
            return '<span class="status-badge status-up">🟢 Recovery</span>';
        case 'ssl_expiry':
            return '<span class="status-badge status-slow">⚠️ SSL</span>';
        default:
            return `<span class="status-badge">${eventType}</span>`;
    }
}

/**
 * Get icon for notification channel
 */
function getChannelIcon(channel) {
    switch (channel) {
        case 'email':
            return '📧';
        case 'telegram':
            return '📱';
        case 'line':
            return '💬';
        default:
            return '🔔';
    }
}

/**
 * Show alert message
 */
function showAlert(message, type) {
    const alertDiv = document.getElementById('alert-message');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.textContent = message;
    alertDiv.style.display = 'block';

    // Auto-hide after 5 seconds for success/info
    if (type === 'success' || type === 'info') {
        setTimeout(() => {
            alertDiv.style.display = 'none';
        }, 5000);
    }
}

// ============================================================================
// Maintenance Windows Functions
// ============================================================================

// Load maintenance windows on page load
document.addEventListener('DOMContentLoaded', function () {
    loadMaintenanceWindows();
    loadDevicesForMaintenance();
});

// Store devices for dropdown
let devicesForMaintenance = [];

/**
 * Load devices for maintenance dropdown
 */
async function loadDevicesForMaintenance() {
    try {
        const response = await fetch('/api/devices');
        devicesForMaintenance = await response.json();

        const select = document.getElementById('maint-device');
        devicesForMaintenance.forEach(device => {
            const option = document.createElement('option');
            option.value = device.id;
            option.textContent = `${device.name} (${device.ip_address})`;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading devices:', error);
    }
}

/**
 * Load maintenance windows list
 */
async function loadMaintenanceWindows() {
    try {
        const response = await fetch('/api/maintenance');
        const windows = await response.json();

        const container = document.getElementById('maintenance-list');

        if (windows.length === 0) {
            container.innerHTML = '<p class="text-center" style="color: var(--text-muted); padding: 1rem;">No maintenance windows scheduled</p>';
            return;
        }

        const now = new Date();

        let html = '<div style="display: flex; flex-direction: column; gap: 0.5rem;">';

        for (const w of windows) {
            const start = new Date(w.start_time);
            const end = new Date(w.end_time);
            const isActive = now >= start && now <= end;
            const isPast = now > end;

            const statusClass = isActive ? 'status-up' : (isPast ? 'status-down' : 'status-slow');
            const statusText = isActive ? '🔵 Active' : (isPast ? '⚫ Ended' : '🟡 Scheduled');

            html += `
                <div class="card" style="padding: 0.75rem; ${isActive ? 'border-left: 3px solid var(--success);' : ''}">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div>
                            <strong>${w.name}</strong>
                            <span class="status-badge ${statusClass}" style="font-size: 0.75rem; margin-left: 0.5rem;">
                                ${statusText}
                            </span>
                            <br>
                            <small style="color: var(--text-muted);">
                                📅 ${formatMaintenanceTime(start)} → ${formatMaintenanceTime(end)}
                            </small>
                            <br>
                            <small style="color: var(--text-muted);">
                                🖥️ ${w.device_name || 'All Devices'}
                            </small>
                            ${w.description ? `<br><small style="color: var(--text-muted);">📝 ${w.description}</small>` : ''}
                        </div>
                        <button class="btn btn-sm btn-danger" onclick="deleteMaintenance(${w.id})" title="Delete">
                            🗑️
                        </button>
                    </div>
                </div>
            `;
        }

        html += '</div>';
        container.innerHTML = html;

    } catch (error) {
        console.error('Error loading maintenance windows:', error);
        document.getElementById('maintenance-list').innerHTML =
            '<p class="text-center" style="color: var(--danger); padding: 1rem;">Error loading maintenance windows</p>';
    }
}

/**
 * Format maintenance time
 */
function formatMaintenanceTime(date) {
    return date.toLocaleString('th-TH', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Show add maintenance modal
 */
function showAddMaintenanceModal() {
    document.getElementById('maintenance-modal').classList.add('active');
    document.getElementById('maintenance-form').reset();

    // Set default times
    const now = new Date();
    const start = new Date(now.getTime() + 5 * 60000); // 5 min from now
    const end = new Date(now.getTime() + 2 * 3600000); // 2 hours from now

    document.getElementById('maint-start').value = start.toISOString().slice(0, 16);
    document.getElementById('maint-end').value = end.toISOString().slice(0, 16);
}

/**
 * Close maintenance modal
 */
function closeMaintenanceModal() {
    document.getElementById('maintenance-modal').classList.remove('active');
}

/**
 * Save maintenance window
 */
async function saveMaintenance(event) {
    event.preventDefault();

    const deviceId = document.getElementById('maint-device').value;

    const data = {
        name: document.getElementById('maint-name').value,
        start_time: document.getElementById('maint-start').value,
        end_time: document.getElementById('maint-end').value,
        device_id: deviceId ? parseInt(deviceId) : null,
        description: document.getElementById('maint-description').value
    };

    // Validate times
    if (new Date(data.start_time) >= new Date(data.end_time)) {
        showAlert('End time must be after start time', 'danger');
        return;
    }

    try {
        const response = await fetch('/api/maintenance', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            closeMaintenanceModal();
            loadMaintenanceWindows();
            showAlert('Maintenance window created!', 'success');
        } else {
            showAlert('Error: ' + (result.error || 'Unknown error'), 'danger');
        }
    } catch (error) {
        console.error('Error saving maintenance:', error);
        showAlert('Error saving maintenance window', 'danger');
    }
}

/**
 * Delete maintenance window
 */
async function deleteMaintenance(id) {
    if (!confirm('Delete this maintenance window?')) return;

    try {
        const response = await fetch(`/api/maintenance/${id}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            loadMaintenanceWindows();
            showAlert('Maintenance window deleted', 'success');
        } else {
            showAlert('Error deleting maintenance window', 'danger');
        }
    } catch (error) {
        console.error('Error deleting maintenance:', error);
        showAlert('Error deleting maintenance window', 'danger');
    }
}

// Handle maintenance modal click outside
document.addEventListener('click', (event) => {
    const modal = document.getElementById('maintenance-modal');
    if (event.target === modal) {
        closeMaintenanceModal();
    }
});
