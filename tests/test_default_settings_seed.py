"""Default alert settings have to actually reach the database.

The seeding loop referenced an undefined `ph` and swallowed the NameError, so
for a long time no default was ever written. Nothing looked broken: every
feature fell through to its own hard-coded fallback, and a setting the operator
expected to find in Settings simply was not there to edit.
"""
import pytest

import database as database_module
from config import Config
from database import Database


def fresh(tmp_path, monkeypatch, name='settings.db'):
    monkeypatch.setattr(Config, 'DB_TYPE', 'sqlite')
    monkeypatch.setattr(database_module.Config, 'DB_TYPE', 'sqlite')
    monkeypatch.setattr(Database, '_pool', None)
    return Database(db_path=str(tmp_path / name))


@pytest.mark.parametrize('key,value', [
    ('vpn_degraded_p95_ms', '100'),
    ('vpn_degraded_jitter_ms', '30'),
    ('escalation_enabled', 'false'),
    ('server_reports_enabled', 'false'),
])
def test_a_new_database_carries_its_default_settings(tmp_path, monkeypatch, key, value):
    db = fresh(tmp_path, monkeypatch)
    assert db.get_alert_setting(key) == value


def test_seeding_again_does_not_overwrite_what_the_operator_chose(tmp_path, monkeypatch):
    path = tmp_path / 'settings.db'
    db = fresh(tmp_path, monkeypatch)
    db.save_alert_setting('vpn_degraded_p95_ms', '150')

    # Every startup re-runs init_db; the operator's 150 has to survive it.
    db.init_db()
    assert db.get_alert_setting('vpn_degraded_p95_ms') == '150'
    assert path.exists()


def test_the_settings_page_can_edit_the_vpn_thresholds():
    """The VPN dashboard tells operators these live in Settings, so they must."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    page = (root / 'templates' / 'settings.html').read_text(encoding='utf-8')
    script = (root / 'static' / 'js' / 'settings.js').read_text(encoding='utf-8')

    for key in ('vpn_degraded_p95_ms', 'vpn_degraded_jitter_ms'):
        assert 'id="%s"' % key in page, '%s has no field on the settings page' % key
        assert "getElementById('%s').value = settings.%s" % (key, key) in script
        assert "%s: document.getElementById('%s').value," % (key, key) in script
