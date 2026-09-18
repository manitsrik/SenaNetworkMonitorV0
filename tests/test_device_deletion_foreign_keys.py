"""Every table that points at a device must be handled when one is deleted.

A device that had been the root cause of a persistent incident could not be
deleted at all: nothing cleared `persistent_incidents.root_cause_device_id`,
so the final DELETE hit the foreign key and the browser showed only "Error
deleting device". This checks the whole schema rather than those two tables,
so the next table someone adds cannot reintroduce it quietly.
"""
import re
from pathlib import Path


def _database_source():
    return (Path(__file__).resolve().parents[1] / "database.py").read_text(encoding="utf-8")


def _delete_device_body(source):
    body = source.split("    def delete_device(self, device_id):", 1)[1]
    return body.split("\n    def ", 1)[0]


def _tables_referencing_devices_without_cascade(source):
    """Map table name -> the FK lines that need cleaning up by hand.

    A reference that declares its own ON DELETE behaviour is the database's
    job, not delete_device's, so those are left out.
    """
    tables = {}
    current = None
    for line in source.splitlines():
        created = re.search(r"CREATE TABLE IF NOT EXISTS (\w+)", line)
        if created:
            current = created.group(1)
            continue
        if "REFERENCES devices(id)" not in line:
            continue
        if "ON DELETE" in line:
            continue
        if current and current != "devices":
            tables.setdefault(current, []).append(line.strip())
    return tables


def test_every_device_reference_is_cleaned_up_when_a_device_is_deleted():
    source = _database_source()
    body = _delete_device_body(source)

    unhandled = [
        table for table in _tables_referencing_devices_without_cascade(source)
        if table not in body
    ]

    assert not unhandled, (
        "delete_device never touches %s, so deleting a device with rows there "
        "fails on the foreign key" % ", ".join(sorted(unhandled))
    )


def test_incident_and_anomaly_history_survives_the_device_it_described():
    # Both tables store the device name beside the id, so clearing the link
    # keeps the record readable. Deleting the rows instead would throw away
    # an incident that may well have spanned other devices too.
    body = _delete_device_body(_database_source())

    assert "UPDATE persistent_incidents SET root_cause_device_id = NULL" in body
    assert "UPDATE anomaly_snapshots SET device_id = NULL" in body
    assert "DELETE FROM persistent_incidents" not in body
    assert "DELETE FROM anomaly_snapshots" not in body
