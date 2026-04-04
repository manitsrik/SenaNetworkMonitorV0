# Deployment Ready Checklist

This checklist is for taking the current `NW Monitor` build from development into a real environment with the new incidents, anomalies, and plugin integrations enabled.

## 1. Environment Secrets

- [ ] Set `SECRET_KEY` to a strong production value
- [ ] Set `SECRET_ENCRYPTION_KEY` to a strong production value
- [ ] Ensure production secrets are stored outside source control
- [ ] Confirm SMTP, Telegram, webhook, LDAP, and SSO secrets are not using defaults
- [ ] Back up the current values before rotating any existing secrets

Recommended:

- `SECRET_KEY`: random high-entropy string
- `SECRET_ENCRYPTION_KEY`: separate value from `SECRET_KEY`

## 2. Python Dependencies

- [ ] Install dependencies from [requirements.txt](/C:/Project/NW%20MonitorV0/requirements.txt)
- [ ] Confirm `cryptography` is installed for secret encryption
- [ ] Confirm database driver matches target DB (`psycopg2-binary` for PostgreSQL)
- [ ] Confirm optional monitoring dependencies exist for features you use:
  - `pysnmp`
  - `paramiko`
  - `pywinrm`
  - `ldap3`
  - `Authlib`

## 3. Database Readiness

- [ ] Confirm PostgreSQL connection settings are correct in environment
- [ ] Verify database user has permission to create/alter tables
- [ ] Start app once in staging and confirm schema migrations complete successfully
- [ ] Verify incident/anomaly/plugin tables/settings exist after startup
- [ ] Back up the database before first production rollout

High-value checks:

- alert settings table exists
- incident workflow tables exist
- anomaly workflow tables exist
- plugin-related settings are readable and writable

## 4. Security Settings

- [ ] Replace all default credentials
- [ ] Confirm admin accounts use strong passwords
- [ ] Enable MFA for admin users
- [ ] Review LDAP/SSO configuration before exposing externally
- [ ] Restrict network access to admin endpoints where possible
- [ ] Use HTTPS in front of the app
- [ ] For webhook integrations, use TLS and bearer/header secrets where applicable

## 5. Plugin System Checks

- [ ] Open `/plugins` and confirm all expected plugins load
- [ ] Configure integration plugins from the Plugins page
- [ ] Verify secrets show as stored but are not returned to the browser
- [ ] Send test events through each enabled integration plugin
- [ ] Remove or disable sample plugins you do not want in production

Current built-in plugin examples:

- `tcp_banner`
- `jsonl_alert_sink`
- `generic_webhook`

## 6. Alerting Checks

- [ ] Review global alert settings
- [ ] Confirm email test succeeds
- [ ] Confirm Telegram test succeeds if used
- [ ] Confirm built-in webhook test succeeds if used
- [ ] Confirm integration plugin test succeeds for `generic_webhook` if used
- [ ] Confirm escalation settings are correct
- [ ] Confirm alert cooldown values are appropriate for production

## 7. Monitoring Checks

- [ ] Verify at least one device for each monitor type you plan to use
- [ ] Test SNMP v2c/v3 devices
- [ ] Test SSH/WinRM metrics if enabled
- [ ] Test bandwidth polling on an SNMP device
- [ ] Test traps/syslog receivers if those services are enabled in your environment
- [ ] Confirm response-time history and alert history are being written

## 8. Incident and Anomaly Workflow Checks

- [ ] Open `/incidents` and verify correlated incidents render correctly
- [ ] Update incident status and confirm activity timeline updates
- [ ] Assign incident owner and confirm change persists
- [ ] Open `/anomalies` and verify anomalies render correctly
- [ ] Update anomaly status and owner
- [ ] Confirm anomaly-to-incident suggestions appear when data matches
- [ ] Confirm manual link/unlink between anomaly and incident works

## 9. Scheduled Jobs

- [ ] Confirm scheduler starts successfully
- [ ] Confirm `incident_materialize` runs
- [ ] Confirm `anomaly_detection` runs
- [ ] Confirm monitoring job runs on expected interval
- [ ] Confirm daily report and cleanup schedules match your requirements

If using production service management:

- [ ] Verify logs capture scheduler start/stop
- [ ] Verify background jobs recover after app restart

## 10. Webhook Integration Hardening

- [ ] For `generic_webhook`, verify:
  - target URL is correct
  - retry count is appropriate
  - backoff is appropriate
  - TLS verification is enabled unless explicitly required otherwise
  - auth headers are configured correctly
- [ ] Confirm downstream system can handle retries without duplicate side effects

## 11. Test Commands

Run these before production cutover:

```powershell
python -m unittest tests.test_plugin_integrations -v
python -m py_compile app.py alerter.py plugin_manager.py routes\plugins.py routes\devices.py secret_store.py
```

Recommended manual checks:

- [ ] Login flow works
- [ ] Devices page works
- [ ] Plugins page works
- [ ] Incidents page works
- [ ] Anomalies page works

## 12. Rollback Preparation

- [ ] Keep a database backup from before deployment
- [ ] Keep a copy of previous environment variable values
- [ ] Record plugin settings changed during rollout
- [ ] Prepare a simple rollback plan:
  - disable new integration plugins
  - restore previous secrets
  - restore DB backup if required

## 13. Go-Live Signoff

- [ ] Secrets configured
- [ ] Database backed up
- [ ] Core pages tested
- [ ] Alerts tested
- [ ] Plugins tested
- [ ] Scheduler verified
- [ ] Incidents and anomalies verified
- [ ] Team has rollback instructions

## Notes

- The application now encrypts integration plugin secrets before storing them.
- Secret rotation should be planned carefully if `SECRET_ENCRYPTION_KEY` changes.
- Existing plaintext plugin secrets remain readable for backward compatibility, but new saves will be encrypted.
