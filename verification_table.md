# NW MonitorV0 Feature Verification Table

ตารางนี้สรุปการตรวจสอบว่า "ฟีเจอร์ที่เอกสาร `enterprise_comparison_analysis.md` ระบุว่าทำแล้ว" มีหลักฐานอยู่ในโค้ดจริงหรือไม่

| ฟีเจอร์ | สถานะจริง | หลักฐานในโค้ด |
|---|---|---|
| PostgreSQL + SQLite fallback | ยืนยันแล้ว | `database.py`, `config.py`, `migrate_to_postgres.py` |
| Modular backend (Blueprints) | ยืนยันแล้ว | `routes/__init__.py`, `app.py` |
| Task Queue / background jobs | เจอบางส่วน | `task_scheduler.py`, `app.py` |
| Production runtime | เจอบางส่วน | `run_production.py`, `app.py` |
| Auto-discovery | ยืนยันแล้ว | `discovery.py`, `routes/discovery.py`, `templates/discovery.html` |
| SNMP v3 | ยืนยันแล้ว | `monitor.py`, `templates/devices.html` |
| SNMP Traps | ยืนยันแล้ว | `snmp_trap_receiver.py`, `routes/traps.py`, `database.py`, `templates/traps.html` |
| Bandwidth Monitoring | ยืนยันแล้ว | `monitor.py`, `routes/bandwidth.py`, `database.py`, `templates/bandwidth.html` |
| SSH / WinRM monitoring | ยืนยันแล้ว | `monitor.py`, `requirements.txt` |
| Syslog Receiver | ยืนยันแล้ว | `syslog_receiver.py`, `routes/syslog.py`, `database.py`, `templates/syslog.html` |
| Custom SNMP OID | ยืนยันแล้ว | `database.py`, `monitor.py`, `routes/devices.py` |
| Alert Escalation | ยืนยันแล้ว | `app.py`, `database.py`, `alerter.py` |
| Alert Dependencies | ยืนยันแล้ว | `database.py`, `alerter.py`, `templates/devices.html` |
| Webhook alerting | ยืนยันแล้ว | `alerter.py` |
| Audit Log | ยืนยันแล้ว | `database.py`, `routes/audit.py`, `templates/audit_log.html` |
| Dashboard builder | ยืนยันแล้ว | `routes/dashboards.py`, `templates/dashboard_builder.html`, `static/js/dashboard_builder.js` |
| Dashboard templates / variables | ยืนยันแล้ว | `database.py`, `routes/dashboards.py`, `static/js/dashboard_builder.js` |
| Real-time WebSocket updates | ยืนยันแล้ว | `app.py` |
| Topology + Sub-topology | ยืนยันแล้ว | `routes/topology.py`, `templates/topology.html`, `templates/sub_topology_builder.html`, `static/js/topology.js` |
| GIS Map | ยืนยันแล้ว | `templates/map.html`, `static/js/map.js` |
| Daily scheduled reports | ยืนยันแล้ว | `scheduler_reports.py`, `app.py` |
| Custom Report Builder | ยืนยันแล้ว | `routes/reports.py`, `templates/reports_builder.html`, `database.py` |
| PDF / SLA export | ยืนยันแล้ว | `templates/reports/sla_print.html`, `routes/sla.py` |
| LDAP / Active Directory | ยืนยันแล้ว | `routes/ldap.py`, `database.py`, `templates/settings.html` |
| SSO / OIDC | ยืนยันแล้ว | `routes/sso.py`, `templates/settings.html`, `templates/login.html` |
| MFA / TOTP | ยืนยันแล้ว | `routes/auth.py`, `routes/users.py`, `templates/login_mfa.html` |
| Swagger API docs | ยืนยันแล้ว | `app.py`, `static/swagger/openapi.yaml` |
| PWA | ยืนยันแล้ว | `templates/layout.html`, `app.py`, `static/manifest.json`, `static/sw.js` |
| Dark / Light theme | ยืนยันแล้ว | `static/css/style.css`, `static/js/theme.js`, `templates/layout.html` |
| i18n | ยืนยันแล้ว | `app.py`, `translations/en/LC_MESSAGES/messages.po`, `translations/th/LC_MESSAGES/messages.po` |

## หมายเหตุ

- `ยืนยันแล้ว` หมายถึงพบ implementation จริงในโค้ด และส่วนใหญ่มีมากกว่า 1 ชั้น เช่น DB, API, UI หรือ runtime logic
- `เจอบางส่วน` หมายถึงมี implementation จริง แต่ยังไม่ตรงระดับ enterprise ตามคำอธิบายในเอกสาร 100%
- จุดที่ควรตีความแบบระวัง:
  - `Task Queue / background jobs` ในโค้ดปัจจุบันใช้ `APScheduler + eventlet` ไม่ใช่ distributed queue แบบ `Celery/RQ`
  - `Production runtime` มีโหมด production จริง แต่ยังไม่ใช่ `Gunicorn/uWSGI + Nginx` ตามข้อความในเอกสาร
