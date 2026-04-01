document.addEventListener('DOMContentLoaded', () => {
    loadUserProfile();
    loadMFAStatus();
    loadActivity();
});

// Load User Profile Data
async function loadUserProfile() {
    try {
        const response = await fetch('/api/users/me');
        const user = await response.json();
        
        if (user.error) {
            console.error('Error loading profile:', user.error);
            return;
        }

        document.getElementById('info-email').textContent = user.email || 'Not set';
        document.getElementById('info-telegram').textContent = user.telegram_chat_id || 'Not set';
        if (user.display_name) {
            document.getElementById('profile-display-name').textContent = user.display_name;
        }
    } catch (error) {
        console.error('Failed to load profile:', error);
    }
}

// MFA Management
async function loadMFAStatus() {
    try {
        const response = await fetch('/api/users/me/mfa/status');
        const data = await response.json();
        updateMFAUI(data.mfa_enabled);
    } catch (error) {
        console.error('Failed to load MFA status:', error);
    }
}

function updateMFAUI(isEnabled) {
    const iconBg = document.getElementById('mfa-status-icon-bg');
    const badge = document.getElementById('mfa-status-badge');
    const desc = document.getElementById('mfa-status-desc');
    const actionArea = document.getElementById('mfa-action-area');

    if (!iconBg || !badge || !desc || !actionArea) return;

    if (isEnabled) {
        iconBg.className = 'security-icon-wrapper enabled';
        badge.className = 'mfa-badge mfa-enabled';
        badge.textContent = 'Enabled';
        desc.textContent = 'Your account is protected with Two-Factor Authentication.';
        actionArea.innerHTML = `
            <button class="btn btn-danger" onclick="showDisableMFAModal()">
                <i class="fa-solid fa-shield-slash"></i> Disable MFA
            </button>
        `;
    } else {
        iconBg.className = 'security-icon-wrapper disabled';
        badge.className = 'mfa-badge mfa-disabled';
        badge.textContent = 'Disabled';
        desc.textContent = 'Protect your account with an additional layer of security using TOTP.';
        actionArea.innerHTML = `
            <button class="btn btn-primary" onclick="startMFASetup()">
                <i class="fa-solid fa-key"></i> Setup MFA
            </button>
        `;
    }
}

// MFA Setup Flow
async function startMFASetup() {
    try {
        const response = await fetch('/api/users/me/mfa/setup', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('mfa-qr-image').src = '/api/users/me/mfa/qrcode?t=' + Date.now();
            document.getElementById('mfa-secret-text').textContent = data.secret;
            
            document.getElementById('mfa-step-1').style.display = 'block';
            document.getElementById('mfa-step-2').style.display = 'none';
            document.getElementById('mfa-setup-modal').classList.add('active');
        } else {
            alert('MFA Setup failed: ' + data.error);
        }
    } catch (error) {
        alert('Error starting MFA setup');
    }
}

function showVerificationStep() {
    document.getElementById('mfa-step-1').style.display = 'none';
    document.getElementById('mfa-step-2').style.display = 'block';
}

function backToStep1() {
    document.getElementById('mfa-step-1').style.display = 'block';
    document.getElementById('mfa-step-2').style.display = 'none';
}

async function verifyMFACode() {
    const code = document.getElementById('mfa-verify-code').value.trim();
    if (code.length !== 6) {
        showMFAError('Please enter a 6-digit code');
        return;
    }

    try {
        const response = await fetch('/api/users/me/mfa/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const data = await response.json();
        
        if (data.success) {
            closeMFAModal();
            loadMFAStatus();
            alert('MFA has been successfully enabled!');
        } else {
            showMFAError(data.error || 'Invalid code');
        }
    } catch (error) {
        showMFAError('Verification failed');
    }
}

function showMFAError(msg) {
    const err = document.getElementById('mfa-verify-error');
    if (err) {
        err.textContent = msg;
        err.style.display = 'block';
    }
}

function closeMFAModal() {
    document.getElementById('mfa-setup-modal').classList.remove('active');
}

// Disable MFA
function showDisableMFAModal() {
    const passInput = document.getElementById('mfa-confirm-password');
    const err = document.getElementById('mfa-confirm-error');
    if (passInput) passInput.value = '';
    if (err) err.style.display = 'none';
    document.getElementById('mfa-disable-modal').classList.add('active');
}

function closeMFADisableModal() {
    document.getElementById('mfa-disable-modal').classList.remove('active');
}

async function confirmDisableMFA() {
    const password = document.getElementById('mfa-confirm-password').value;
    if (!password) {
        alert('Please enter your password to confirm.');
        return;
    }

    try {
        const response = await fetch('/api/users/me/mfa/disable', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        const data = await response.json();
        
        if (data.success) {
            closeMFADisableModal();
            loadMFAStatus();
            alert('MFA has been disabled.');
        } else {
            const err = document.getElementById('mfa-confirm-error');
            if (err) {
                err.textContent = data.error || 'Incorrect password';
                err.style.display = 'block';
            } else {
                alert(data.error || 'Incorrect password');
            }
        }
    } catch (error) {
        alert('Error disabling MFA');
    }
}

// Password Management
function showPasswordModal() {
    const cur = document.getElementById('current-password');
    const n1 = document.getElementById('new-password');
    const n2 = document.getElementById('confirm-password');
    const err = document.getElementById('password-error');
    
    if (cur) cur.value = '';
    if (n1) n1.value = '';
    if (n2) n2.value = '';
    if (err) err.style.display = 'none';
    
    document.getElementById('password-modal').classList.add('active');
}

function closePasswordModal() {
    document.getElementById('password-modal').classList.remove('active');
}

async function updatePassword(event) {
    event.preventDefault();
    const currentPassword = document.getElementById('current-password').value;
    const newPassword = document.getElementById('new-password').value;
    const confirmPassword = document.getElementById('confirm-password').value;

    if (newPassword !== confirmPassword) {
        showPasswordError('New passwords do not match');
        return;
    }

    try {
        const response = await fetch('/api/users/me/password', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword
            })
        });
        const data = await response.json();
        
        if (data.success) {
            closePasswordModal();
            alert('Password updated successfully!');
        } else {
            showPasswordError(data.error || 'Failed to update password');
        }
    } catch (error) {
        showPasswordError('Server error');
    }
}

function showPasswordError(msg) {
    const err = document.getElementById('password-error');
    if (err) {
        err.textContent = msg;
        err.style.display = 'block';
    } else {
        alert(msg);
    }
}

// Activity History
async function loadActivity() {
    try {
        const response = await fetch('/api/users/me/activity?limit=10');
        const logs = await response.json();
        
        const tbody = document.getElementById('activity-tbody');
        if (!tbody) return;

        if (!logs || logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-muted">No recent activity</td></tr>';
            return;
        }

        tbody.innerHTML = logs.map(log => `
            <tr>
                <td><span style="text-transform: capitalize;">${log.action}</span></td>
                <td><span class="text-muted small">${log.category}</span></td>
                <td><code>${log.ip_address || '-'}</code></td>
                <td><small>${formatDateTime(log.created_at)}</small></td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Failed to load activity:', error);
    }
}

function formatDateTime(isoString) {
    if (!isoString) return '-';
    try {
        const date = new Date(isoString);
        return date.toLocaleString('en-GB', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch(e) {
        return isoString;
    }
}
