"""PPPoE Connection Monitoring Module.

Collects PPPoE connection/disconnection events from MikroTik logs,
stores them persistently, and provides analytics about user disconnections.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import router_client
from router_client import RouterConfig, RouterError

log = logging.getLogger("pppoe_monitor")

# Timezone for displaying timestamps (Asia/Dhaka = UTC+6)
DISPLAY_TIMEZONE = timezone(timedelta(hours=6))


def to_display_time(utc_iso: str) -> str:
    """Convert UTC ISO timestamp to Asia/Dhaka timezone."""
    try:
        dt = datetime.fromisoformat(utc_iso.replace('Z', '+00:00'))
        local_dt = dt.astimezone(DISPLAY_TIMEZONE)
        return local_dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, AttributeError):
        return utc_iso


class PPPoEMonitor:
    """Monitors PPPoE connection events from MikroTik logs."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
        self.last_log_id = self._get_last_log_id()

    def _init_db(self) -> None:
        """Create tables for PPPoE monitoring if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS pppoe_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    log_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    topics TEXT NOT NULL,
                    username TEXT,
                    ip_address TEXT,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    disconnect_reason TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(log_id, timestamp, message)
                );

                CREATE INDEX IF NOT EXISTS idx_pppoe_events_username
                    ON pppoe_events(username);
                CREATE INDEX IF NOT EXISTS idx_pppoe_events_timestamp
                    ON pppoe_events(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_pppoe_events_type
                    ON pppoe_events(event_type);
                CREATE INDEX IF NOT EXISTS idx_pppoe_events_log_id
                    ON pppoe_events(log_id);

                CREATE TABLE IF NOT EXISTS pppoe_monitor_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
        finally:
            conn.close()

    def _get_last_log_id(self) -> str | None:
        """Get the last processed log ID to avoid reprocessing."""
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT value FROM pppoe_monitor_state WHERE key = ?",
                ("last_log_id",)
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def _parse_pppoe_event(self, log_entry: dict) -> dict | None:
        """Parse a log entry to extract PPPoE connection event details.

        Returns None if the log entry is not a PPPoE connection event.
        """
        message = str(log_entry.get("message", ""))
        topics = set(re.findall(r"[a-z0-9-]+", str(log_entry.get("topics", "")).lower()))

        if topics.isdisjoint({"ppp", "pppoe"}):
            return None

        # Pattern for connected events
        # Example: <pppoe-user123> connected
        # Example: user123 logged in
        connect_patterns = [
            r'<pppoe-([^>]+)>\s+connected',
            r'<([^>]+)>\s+connected',
            r'(\S+)\s+logged\s+in',
        ]

        # Pattern for disconnected events
        # Example: <pppoe-user123> disconnected
        # Example: user123 logged out (reason...)
        disconnect_patterns = [
            r'<pppoe-([^>]+)>\s+disconnected',
            r'<([^>]+)>\s+disconnected',
            r'(\S+)\s+logged\s+out',
            r'(\S+)\s+terminated',
        ]

        username = None
        event_type = "unknown"
        disconnect_reason = None
        ip_address = None

        # Try to match connected patterns
        for pattern in connect_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                username = match.group(1)
                event_type = "connected"
                break

        # Try to match disconnected patterns
        if not username:
            for pattern in disconnect_patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    username = match.group(1)
                    event_type = "disconnected"

                    # Extract disconnect reason if available
                    reason_match = re.search(r'\(([^)]+)\)', message)
                    if reason_match:
                        disconnect_reason = reason_match.group(1)
                    break

        # Try to extract IP address from message
        ip_match = re.search(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', message)
        if ip_match:
            ip_address = ip_match.group(1)

        if not username:
            # Store as raw log if we can't parse it but it's PPPoE-related
            if topics.intersection({"ppp", "pppoe"}):
                return {
                    "username": None,
                    "ip_address": None,
                    "event_type": "unknown",
                    "disconnect_reason": None,
                }
            return None

        return {
            "username": username,
            "ip_address": ip_address,
            "event_type": event_type,
            "disconnect_reason": disconnect_reason,
        }

    def fetch_and_store_logs(self, cfg: RouterConfig) -> dict[str, Any]:
        """Fetch new logs from MikroTik and store PPPoE events.

        Returns statistics about the collection.
        """
        api = None
        try:
            api = router_client._connect(cfg)

            # Fetch logs - only get recent ones
            # We'll filter by topics on the router side if possible
            logs = []
            try:
                log_entries = api.path("log").select(
                    ".id", "time", "topics", "message"
                )
                logs = [dict(entry) for entry in log_entries]
            except Exception as exc:
                log.error("Failed to read logs: %s", exc)
                return {
                    "ok": False,
                    "error": str(exc),
                    "new_events": 0,
                    "processed_logs": 0,
                }
        except RouterError as exc:
            log.error("Router connection failed: %s", exc)
            return {
                "ok": False,
                "error": str(exc),
                "new_events": 0,
                "processed_logs": 0,
            }
        except Exception as exc:
            log.exception("Unexpected error fetching logs")
            return {
                "ok": False,
                "error": "Unexpected error",
                "new_events": 0,
                "processed_logs": 0,
            }
        finally:
            router_client._close(api)

        # RouterOS log IDs are opaque and may be reused after reboot.
        # Match the last observed entry by ID, router time, topics and message.
        def fingerprint(entry):
            return json.dumps([str(entry.get(key, "")) for key in (".id", "time", "topics", "message")])

        new_events = 0
        processed_logs = 0
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                state = dict(conn.execute(
                    "SELECT key, value FROM pppoe_monitor_state "
                    "WHERE key IN ('log_cursor', 'last_log_id')"
                ))
                cursor = state.get("log_cursor")
                legacy = state.get("last_log_id") if cursor is None else None
                start = 0
                for i in range(len(logs) - 1, -1, -1):
                    entry = logs[i]
                    if (cursor and fingerprint(entry) == cursor) or (legacy and str(entry.get(".id")) == legacy):
                        start = i + 1
                        break

                timestamp = datetime.now(timezone.utc).isoformat()
                for entry in logs[start:]:
                    processed_logs += 1
                    event = self._parse_pppoe_event(entry)
                    if event is None:
                        continue
                    inserted = conn.execute(
                        """INSERT OR IGNORE INTO pppoe_events
                           (log_id, timestamp, topics, username, ip_address,
                            event_type, message, disconnect_reason)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (str(entry.get(".id", "")), timestamp, str(entry.get("topics", "")),
                         event["username"], event["ip_address"], event["event_type"],
                         str(entry.get("message", "")), event["disconnect_reason"]),
                    )
                    new_events += inserted.rowcount
                if logs:
                    self.last_log_id = str(logs[-1].get(".id", ""))
                    conn.executemany(
                        "INSERT INTO pppoe_monitor_state(key, value) VALUES(?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
                        [("log_cursor", fingerprint(logs[-1])), ("last_log_id", self.last_log_id)],
                    )
        finally:
            conn.close()

        return {
            "ok": True,
            "new_events": new_events,
            "processed_logs": processed_logs,
            "last_log_id": self.last_log_id,
        }

    def get_dashboard_stats(self) -> dict[str, Any]:
        """Get summary statistics for the dashboard."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            # Total events
            total_events = conn.execute(
                "SELECT COUNT(*) as cnt FROM pppoe_events"
            ).fetchone()["cnt"]

            # Total connections
            total_connected = conn.execute(
                "SELECT COUNT(*) as cnt FROM pppoe_events WHERE event_type = 'connected'"
            ).fetchone()["cnt"]

            # Total disconnections
            total_disconnected = conn.execute(
                "SELECT COUNT(*) as cnt FROM pppoe_events WHERE event_type = 'disconnected'"
            ).fetchone()["cnt"]

            # Currently connected (more connected than disconnected per user)
            currently_connected = conn.execute("""
                SELECT COUNT(DISTINCT username) as cnt FROM (
                    SELECT username,
                           SUM(CASE WHEN event_type = 'connected' THEN 1 ELSE 0 END) as connects,
                           SUM(CASE WHEN event_type = 'disconnected' THEN 1 ELSE 0 END) as disconnects
                    FROM pppoe_events
                    WHERE username IS NOT NULL
                    GROUP BY username
                    HAVING connects > disconnects
                )
            """).fetchone()["cnt"]

            # Users with most disconnections
            repeated_disconnects = conn.execute("""
                SELECT COUNT(*) as cnt FROM (
                    SELECT username, COUNT(*) as disconnect_count
                    FROM pppoe_events
                    WHERE event_type = 'disconnected' AND username IS NOT NULL
                    GROUP BY username
                    HAVING disconnect_count >= 5
                )
            """).fetchone()["cnt"]

            return {
                "total_events": total_events,
                "total_connected": total_connected,
                "total_disconnected": total_disconnected,
                "currently_connected": currently_connected,
                "repeated_disconnects": repeated_disconnects,
            }
        finally:
            conn.close()

    def get_recent_events(self, limit: int = 100, offset: int = 0,
                         username: str | None = None,
                         event_type: str | None = None) -> list[dict]:
        """Get recent PPPoE events."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            query = "SELECT * FROM pppoe_events WHERE 1=1"
            params = []

            if username:
                query += " AND username = ?"
                params.append(username)

            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_most_disconnected_users(self, days: int | None = None,
                                   limit: int = 100) -> list[dict]:
        """Get users with the most disconnections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            time_filter = ""
            params = []

            if days:
                cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
                time_filter = "AND timestamp >= ?"
                params.append(cutoff)

            query = f"""
                SELECT
                    username,
                    SUM(CASE WHEN event_type = 'disconnected' THEN 1 ELSE 0 END) as disconnect_count,
                    MAX(CASE WHEN event_type = 'disconnected' THEN timestamp END) as last_disconnect,
                    MAX(CASE WHEN event_type = 'connected' THEN timestamp END) as last_connected
                FROM pppoe_events
                WHERE username IS NOT NULL AND event_type IN ('connected', 'disconnected')
                {time_filter}
                GROUP BY username
                HAVING disconnect_count > 0
                ORDER BY disconnect_count DESC
                LIMIT ?
            """
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_user_connection_history(self, username: str) -> dict[str, Any]:
        """Get detailed connection history for a specific user."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            # Get all events for this user
            events = conn.execute("""
                SELECT * FROM pppoe_events
                WHERE username = ?
                ORDER BY timestamp ASC
            """, (username,)).fetchall()

            # Calculate statistics
            total_connected = sum(1 for e in events if e["event_type"] == "connected")
            total_disconnected = sum(1 for e in events if e["event_type"] == "disconnected")

            last_connected = None
            last_disconnected = None

            for event in reversed(events):
                if event["event_type"] == "connected" and not last_connected:
                    last_connected = event["timestamp"]
                if event["event_type"] == "disconnected" and not last_disconnected:
                    last_disconnected = event["timestamp"]

            return {
                "username": username,
                "total_connected": total_connected,
                "total_disconnected": total_disconnected,
                "last_connected": last_connected,
                "last_disconnected": last_disconnected,
                "events": [dict(e) for e in events],
            }
        finally:
            conn.close()

    def get_hourly_disconnect_stats(self, days: int = 7) -> list[dict]:
        """Get hourly disconnection statistics for charts."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

            rows = conn.execute("""
                SELECT
                    strftime('%Y-%m-%d %H:00:00', timestamp) as hour,
                    COUNT(*) as disconnect_count
                FROM pppoe_events
                WHERE event_type = 'disconnected' AND timestamp >= ?
                GROUP BY hour
                ORDER BY hour ASC
            """, (cutoff,)).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_daily_disconnect_stats(self, days: int = 30) -> list[dict]:
        """Get daily disconnection statistics for charts."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

            rows = conn.execute("""
                SELECT
                    strftime('%Y-%m-%d', timestamp) as day,
                    COUNT(*) as disconnect_count
                FROM pppoe_events
                WHERE event_type = 'disconnected' AND timestamp >= ?
                GROUP BY day
                ORDER BY day ASC
            """, (cutoff,)).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()
