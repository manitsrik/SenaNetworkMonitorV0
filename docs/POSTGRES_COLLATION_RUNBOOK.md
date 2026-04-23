# PostgreSQL Collation Mismatch Runbook

This project currently reports a PostgreSQL warning like:

`database "network_monitor" has a collation version mismatch`

This usually appears after a Windows or PostgreSQL runtime update changed the
OS collation libraries used by PostgreSQL.

## What This Means

- The database is still reachable and the application can start.
- Text indexes or ordering behavior that depend on the default collation may be
  stale until the collation metadata is refreshed.
- Refreshing the collation version alone does not rebuild affected indexes.

## Safe Order Of Operations

1. Schedule a maintenance window.
2. Stop the application services that write to PostgreSQL.
3. Take a fresh backup.
4. Reindex the database objects that depend on the default collation.
5. Refresh the database collation version metadata.
6. Start the application and verify the warning is gone.

## Check Current State

Run this in `psql`:

```sql
SELECT datname, datcollate, datctype, datcollversion
FROM pg_database
WHERE datname = 'network_monitor';
```

## Maintenance Commands

Connect as a privileged PostgreSQL user and run:

```sql
REINDEX DATABASE network_monitor;
ALTER DATABASE network_monitor REFRESH COLLATION VERSION;
```

If you want a more targeted approach, inspect indexes first:

```sql
SELECT indexrelid::regclass AS index_name, indrelid::regclass AS table_name
FROM pg_index
WHERE indrelid IN (
    SELECT oid
    FROM pg_class
    WHERE relkind = 'r'
);
```

## Verification

After maintenance:

1. Start the app.
2. Check the PostgreSQL log for new collation warnings.
3. Verify login, dashboard load, and a few API reads.

## Notes

- Do not run `ALTER DATABASE ... REFRESH COLLATION VERSION` without planning the
  matching reindex step.
- On large databases, `REINDEX DATABASE` can take time and should be done during
  a maintenance window.
