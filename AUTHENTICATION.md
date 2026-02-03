# Authentication System Documentation

## Overview
Added session-based authentication system to Network Monitor to protect all routes and require login before accessing the application.

## Credentials
- **Username**: `admin`
- **Password**: `admin`

## Implementation Details

### Backend Changes

**File**: [app.py](file:///c:/Project/NW%20MonitorV0/app.py)

1. **Added Imports**:
```python
from flask import session, redirect, url_for
from functools import wraps
```

2. **Hardcoded Credentials**:
```python
USERNAME = 'admin'
PASSWORD = 'admin'
```

3. **Login Required Decorator**:
```python
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
```

4. **Login Route** (`/login`):
   - GET: Display login form
   - POST: Validate credentials and create session
   - Redirects to dashboard on success
   - Shows error message on failure

5. **Logout Route** (`/logout`):
   - Clears session
   - Redirects to login page

6. **Protected Routes**:
   - `/` (Dashboard) - `@login_required`
   - `/topology` - `@login_required`
   - `/devices` - `@login_required`

### Frontend Changes

**File**: [login.html](file:///c:/Project/NW%20MonitorV0/templates/login.html)

- Modern dark theme matching the application design
- Gradient background
- Glassmorphism card design
- Form validation
- Error message display
- Responsive layout

**Navigation Updates**:
- Added "🚪 Logout" button to all pages:
  - [index.html](file:///c:/Project/NW%20MonitorV0/templates/index.html)
  - [topology.html](file:///c:/Project/NW%20MonitorV0/templates/topology.html)
  - [devices.html](file:///c:/Project/NW%20MonitorV0/templates/devices.html)

## Testing Results

### Test 1: Unauthenticated Access
![Login Page Redirect](file:///C:/Users/manits/.gemini/antigravity/brain/088445eb-0bbc-45b0-ab7e-75694e56f6fe/login_page_redirect_1767949115883.png)

**Result**: ✅ PASS
- Accessing `http://localhost:5000/` redirects to login page
- All protected routes require authentication

### Test 2: Invalid Credentials
![Login Error Message](file:///C:/Users/manits/.gemini/antigravity/brain/088445eb-0bbc-45b0-ab7e-75694e56f6fe/login_error_message_1767949158015.png)

**Result**: ✅ PASS
- Error message displayed: "❌ ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"
- User remains on login page
- No session created

### Test 3: Valid Credentials & Navigation
![Topology Page Authenticated](file:///C:/Users/manits/.gemini/antigravity/brain/088445eb-0bbc-45b0-ab7e-75694e56f6fe/topology_page_authenticated_1767949198840.png)

**Result**: ✅ PASS
- Login with `admin`/`admin` successful
- Redirected to dashboard
- Can navigate to all pages (Dashboard, Topology, Devices)
- Logout button visible in navigation

### Test 4: Logout
![Logout Success](file:///C:/Users/manits/.gemini/antigravity/brain/088445eb-0bbc-45b0-ab7e-75694e56f6fe/logout_success_redirect_1767949231906.png)

**Result**: ✅ PASS
- Clicking "Logout" clears session
- Redirects to login page
- Cannot access protected routes after logout

## Features

### Login Page
- Clean, modern design
- Username and password fields
- Form validation
- Error message display
- Auto-focus on username field
- Responsive layout

### Session Management
- Flask session-based authentication
- Secure session storage
- Session cleared on logout
- Automatic redirect to login if not authenticated

### Route Protection
- All main routes protected with `@login_required`
- Automatic redirect to login page
- Session persistence across page navigation

### Logout
- Accessible from all pages via navigation
- Clears all session data
- Immediate redirect to login

## Security Notes

⚠️ **For Production Use**:
1. **Change Credentials**: Update hardcoded username/password
2. **Use Database**: Store hashed passwords in database
3. **Password Hashing**: Use `werkzeug.security` or `bcrypt`
4. **HTTPS**: Enable SSL/TLS for encrypted communication
5. **Session Security**: Configure secure session cookies
6. **CSRF Protection**: Add CSRF tokens to forms
7. **Rate Limiting**: Implement login attempt limits

## Usage

1. **Access Application**: Navigate to `http://localhost:5000`
2. **Login**: Enter credentials (admin/admin)
3. **Navigate**: Use navigation menu to access different pages
4. **Logout**: Click "🚪 Logout" button in navigation

## Error Handling

- **Invalid Credentials**: Shows error message
- **Empty Fields**: Shows "กรุณากรอกชื่อผู้ใช้และรหัสผ่าน"
- **Already Logged In**: Redirects to dashboard if accessing `/login`

## Summary

✅ Complete authentication system implemented
✅ All routes protected
✅ Modern, user-friendly login interface
✅ Secure session management
✅ Logout functionality working
✅ Fully tested and operational
