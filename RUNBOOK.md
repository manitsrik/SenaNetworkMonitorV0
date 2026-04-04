# Runbook

This runbook covers the practical steps to deploy, start, verify, and roll back the current `NW Monitor` build.

## 1. Pre-Deploy

Before touching production:

1. Back up the database.
2. Save a copy of the current environment variables.
3. Review [DEPLOYMENT_READY_CHECKLIST.md](/C:/Project/NW%20MonitorV0/DEPLOYMENT_READY_CHECKLIST.md).
4. Confirm `.env` or your secret manager contains real production values based on [.env.example](/C:/Project/NW%20MonitorV0/.env.example).

## 2. Install / Update

Run from the repo root:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If you use PostgreSQL, confirm the target database is reachable before starting the app.

## 3. Configure Environment

Set these as a minimum:

```powershell
$env:SECRET_KEY="replace-with-production-secret"
$env:SECRET_ENCRYPTION_KEY="replace-with-separate-production-secret"
$env:DB_TYPE="postgresql"
$env:PG_HOST="localhost"
$env:PG_PORT="5432"
$env:PG_DATABASE="network_monitor"
$env:PG_USER="netmonitor"
$env:PG_PASSWORD="replace-with-db-password"
$env:DEBUG="false"
```

Optional but recommended:

```powershell
$env:MONITOR_MAX_WORKERS="12"
$env:PG_POOL_MIN="2"
$env:PG_POOL_MAX="30"
```

## 4. Start the Application

Recommended command:

```powershell
python run_production.py
```

This starts the eventlet-based production entrypoint in [run_production.py](/C:/Project/NW%20MonitorV0/run_production.py).

Watch for:

- database pool created
- scheduler started
- plugin manager loaded plugins
- no fatal import errors

Notes:

- Syslog receiver may report port conflicts if another service already owns UDP 514.
- That is only acceptable if you intentionally run syslog elsewhere.

## 5. Post-Start Smoke Checks

Open the app and verify:

1. Login works.
2. `/devices` loads.
3. `/plugins` loads.
4. `/incidents` loads.
5. `/anomalies` loads.

Quick API checks after login:

- `GET /api/plugins`
- `GET /api/plugins/integration-types`
- `GET /api/alert-incidents`
- `GET /api/anomalies`

## 6. Alerting Verification

From the UI:

1. Test Email.
2. Test Telegram if used.
3. Test built-in webhook if used.
4. Test integration plugin `generic_webhook` if used.

Expected results:

- test succeeds in UI
- entry appears in alert history when applicable
- downstream system receives payload

## 7. Plugin Verification

On `/plugins`:

1. Confirm required plugins are listed.
2. Configure `generic_webhook` if used.
3. Confirm secret fields show as stored after save.
4. Confirm secret values are not returned visibly after refresh.
5. Send test event through each enabled integration plugin.

Current plugin examples:

- `tcp_banner`
- `jsonl_alert_sink`
- `generic_webhook`

## 8. Incident / Anomaly Verification

Check:

1. Incident list renders.
2. Incident status update works.
3. Incident assignment works.
4. Activity timeline updates.
5. Anomaly list renders.
6. Anomaly status and owner updates work.
7. Anomaly link/unlink to incident works.

## 9. Scheduled Job Verification

Look at app logs after startup and during the first few minutes.

Confirm these jobs run without failure:

- monitoring job
- incident materialization
- anomaly detection
- alert escalation
- cleanup

If custom reports are used, confirm the report scheduler is active as well.

## 10. Recommended Validation Commands

Run these before or right after deploy:

```powershell
python -m unittest tests.test_plugin_integrations -v
python -m py_compile app.py alerter.py plugin_manager.py routes\plugins.py routes\devices.py secret_store.py
```

## 11. Secret Rotation Notes

Important:

- Integration plugin secrets are encrypted before storage.
- Existing plaintext plugin secrets remain readable for backward compatibility.
- New saves are encrypted using `SECRET_ENCRYPTION_KEY`.

If you rotate `SECRET_ENCRYPTION_KEY`:

1. Export or re-enter current secrets first.
2. Update the key.
3. Re-save integration plugin settings so secrets are re-encrypted with the new key.

## 12. Rollback

If deployment fails:

1. Stop the app process.
2. Restore the previous environment values.
3. Restore the database backup if schema/data rollback is required.
4. Disable new integration plugins if the issue is isolated there.
5. Start the previous known-good build.

Minimal rollback approach:

```powershell
# stop current process
# restore previous env
# restore previous code or artifact
python run_production.py
```

## 13. Go-Live Signoff

Use this before handing over:

- [ ] Environment set
- [ ] Database backup taken
- [ ] App starts cleanly
- [ ] Plugins page verified
- [ ] Alerts verified
- [ ] Incidents verified
- [ ] Anomalies verified
- [ ] Scheduler verified
- [ ] Rollback plan prepared
