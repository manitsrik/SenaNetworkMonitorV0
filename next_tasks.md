# NW MonitorV0 Next Tasks

ตารางนี้สรุปงานถัดไปที่ควรทำต่อจากสถานะปัจจุบัน โดยอิงจาก:

- `enterprise_comparison_analysis.md`
- `verification_table.md`
- การตรวจสอบโค้ดจริงในโปรเจกต์

## Recommended Order

| ลำดับ | Task | Priority | ความยาก | สถานะปัจจุบัน | เหตุผลที่ควรทำต่อ | ผลลัพธ์ที่คาดหวัง |
|---|---|---|---|---|---|---|
| 1 | Event Correlation | สูง | Hard | ยังไม่พบ implementation ชัดเจน | ระบบ alert มีพื้นฐานครบแล้ว เช่น escalation, dependency suppression, webhook จึงต่อยอดได้ทันที | ลด alert storm และรวม incident ที่เกี่ยวข้องกันให้ operator เห็นภาพเดียว |
| 2 | Anomaly Detection | สูง | Hard | ยังไม่พบ implementation ชัดเจน | มีข้อมูล monitoring, bandwidth, response time, SSH/WinRM metrics พร้อมใช้งานแล้ว | แจ้งเตือนความผิดปกติเชิงพฤติกรรมได้ก่อนถึง threshold แบบตายตัว |
| 3 | Distributed Task Queue | กลาง-สูง | Medium-Hard | ปัจจุบันใช้ APScheduler + eventlet | ถ้าต้องการ scale จริง งาน polling, reports, traps, syslog ควรแยกจาก web process | รองรับ worker หลายตัว, ลด coupling, เพิ่มเสถียรภาพเวลาโหลดสูง |
| 4 | Production Architecture Hardening | กลาง-สูง | Medium | มี production runtime แล้ว แต่ยังไม่ถึงระดับ enterprise เต็มรูป | ควรทำให้ deployment pattern ชัดเจนสำหรับ production จริง | แยก web / worker / db / reverse proxy และทำให้ deploy/operate ง่ายขึ้น |
| 5 | Plugin System | กลาง | Hard | ยังไม่พบ implementation | เป็นงานสำคัญแต่กระทบ architecture เยอะ ควรทำหลัง core intelligence และ infra นิ่ง | เปิดทางให้เพิ่ม monitor/alerter/integration ใหม่โดยไม่แก้ core มาก |

## Task Details

### 1. Event Correlation

| หัวข้อ | รายละเอียด |
|---|---|
| เป้าหมาย | จับกลุ่มเหตุการณ์ที่เกี่ยวข้องกันเป็น incident เดียว |
| Input ที่มีอยู่แล้ว | device status, alert history, topology relationship, parent-child dependency, traps, syslog |
| งานย่อย | สร้าง correlation rules, incident grouping, root-cause candidate, suppression/merge logic, UI แสดง correlated incidents |
| ความคุ้มค่า | สูงมาก เพราะช่วยลด noise และเพิ่มคุณภาพการแจ้งเตือนทันที |

### 2. Anomaly Detection

| หัวข้อ | รายละเอียด |
|---|---|
| เป้าหมาย | ตรวจจับพฤติกรรมผิดปกติจาก baseline ไม่ใช่ threshold อย่างเดียว |
| Input ที่มีอยู่แล้ว | response time history, bandwidth history, SNMP metrics, SSH/WinRM metrics |
| งานย่อย | เก็บ baseline รายชั่วโมง/รายวัน, คำนวณ deviation, anomaly scoring, alert policy, dashboard visualization |
| ความคุ้มค่า | สูง เพราะเพิ่มความฉลาดของระบบโดยไม่ต้องเพิ่ม protocol ใหม่ |

### 3. Distributed Task Queue

| หัวข้อ | รายละเอียด |
|---|---|
| เป้าหมาย | ย้าย background execution ออกจาก web process |
| สถานะปัจจุบัน | ใช้ `APScheduler + eventlet` ใน process เดียวเป็นหลัก |
| งานย่อย | เลือก `Celery` หรือ `RQ`, แยก jobs polling/reports/escalation, เพิ่ม retry, queue routing, worker supervision |
| ความคุ้มค่า | สูงในเชิง infrastructure และรองรับการ scale ระยะถัดไป |

### 4. Production Architecture Hardening

| หัวข้อ | รายละเอียด |
|---|---|
| เป้าหมาย | ทำให้ระบบพร้อม production มากขึ้นในเชิง deployment และ operations |
| สถานะปัจจุบัน | มี production runner แต่ยังไม่ใช่ enterprise deployment เต็มรูป |
| งานย่อย | แยก service roles, เพิ่ม reverse proxy, logging strategy, health checks, config separation, deployment docs |
| ความคุ้มค่า | สูงถ้าจะใช้งานจริงหลาย site หรือมีผู้ใช้หลายทีม |

### 5. Plugin System

| หัวข้อ | รายละเอียด |
|---|---|
| เป้าหมาย | รองรับการขยาย monitor / alert / integration แบบ modular |
| สถานะปัจจุบัน | ยังไม่พบ plugin framework ที่ใช้งานจริง |
| งานย่อย | ออกแบบ plugin contract, loading lifecycle, config schema, sandboxing, developer docs |
| ความคุ้มค่า | สูงระยะยาว แต่ไม่ใช่งานที่ควรเริ่มก่อนสุด |

## Recommended Milestones

| Milestone | ขอบเขต |
|---|---|
| M1 | Event Correlation MVP |
| M2 | Anomaly Detection MVP |
| M3 | Queue / Worker Refactor |
| M4 | Production Deployment Hardening |
| M5 | Plugin System Foundation |

## Suggested MVP Scope

| Task | MVP ที่แนะนำ |
|---|---|
| Event Correlation | รวม alerts ที่เกิดในช่วงเวลาใกล้กันตาม topology/parent-child และสร้าง incident เดียว |
| Anomaly Detection | เริ่มจาก response time และ bandwidth ก่อน โดยใช้ rolling baseline + standard deviation |
| Distributed Task Queue | ย้าย scheduled jobs หลัก 2-3 ตัวออกไป worker ก่อน |
| Production Hardening | ทำ deployment guide + process split + health endpoint ก่อน |
| Plugin System | เริ่มจาก monitor plugin แบบ read-only 1 ประเภทก่อน |

## Summary

ถ้าต้องเลือกทำงานต่อแบบคุ้มค่าที่สุดในตอนนี้:

1. ทำ `Event Correlation`
2. ทำ `Anomaly Detection`
3. ทำ `Distributed Task Queue`

ถ้าต้องการเน้น roadmap เดิมแบบตรงเอกสาร:

1. `Event Correlation`
2. `Anomaly Detection`
3. `Plugin System`

