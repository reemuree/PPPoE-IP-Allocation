# PPPoE Connection Monitoring & Analytics

## Overview

This document describes the PPPoE connection monitoring feature added to the MikroTik PPPoE IP Allocation Manager. This feature tracks PPPoE user connections and disconnections by reading logs from your MikroTik router.

## Features

### 1. Automatic Log Collection
- Polls MikroTik router logs every 12 seconds
- Extracts PPPoE connection and disconnection events
- Stores events permanently in SQLite database
- Prevents duplicate entries
- Continues collecting after application restarts
- Handles temporary router disconnections gracefully

### 2. Connection Monitoring Dashboard
Located at: **Connection Monitoring** navigation menu

Displays:
- **Summary Statistics**:
  - Total connection events
  - Total connections
  - Total disconnections
  - Currently connected users
  - Users with repeated disconnections (5+ disconnects)

- **Hourly Disconnection Trend**: Line chart showing disconnections in the last 24 hours
- **Daily Disconnection Trend**: Bar chart showing disconnections over the last 30 days
- **Top 10 Most Disconnected Users**: Quick overview with links to detailed history

### 3. Recent PPPoE Events
Located at: **Recent Events** navigation menu

Features:
- Real-time list of the last 100 PPPoE events
- Filter by event type (Connected/Disconnected/Unknown)
- Search by username
- Status badges (Green=Connected, Red=Disconnected, Gray=Unknown)
- Shows timestamp, username, IP address, and full log message

### 4. Most Disconnected Users
Located at: **Most Disconnected Users** navigation menu

Features:
- List of users ranked by disconnection count
- Filter by time range (Today, Last 7 days, Last 30 days, All time)
- Search by username
- Shows:
  - Disconnect count
  - Last disconnection time
  - Last connection time
- Click "View History" to see detailed connection timeline

### 5. User Connection History
Shows detailed history for a specific user:
- Total connections and disconnections
- Last connected and disconnected times
- Chronological timeline of all events
- Disconnect reasons (when available)
- Raw RouterOS log messages for troubleshooting

## Database Schema

### Table: `pppoe_events`
Stores all PPPoE connection events.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| log_id | TEXT | RouterOS log entry ID |
| timestamp | TEXT | Event timestamp (ISO 8601 UTC) |
| topics | TEXT | RouterOS log topics |
| username | TEXT | PPPoE username |
| ip_address | TEXT | IP address (if found in log) |
| event_type | TEXT | 'connected', 'disconnected', or 'unknown' |
| message | TEXT | Full RouterOS log message |
| disconnect_reason | TEXT | Reason for disconnection (if available) |
| created_at | TEXT | When this record was inserted |

**Indexes:**
- `idx_pppoe_events_username` on `username`
- `idx_pppoe_events_timestamp` on `timestamp`
- `idx_pppoe_events_type` on `event_type`
- `idx_pppoe_events_log_id` on `log_id`

**Unique Constraint:** `(log_id, timestamp, message)` prevents duplicates

### Table: `pppoe_monitor_state`
Tracks monitoring state.

| Column | Type | Description |
|--------|------|-------------|
| key | TEXT | State key (e.g., 'last_log_id') |
| value | TEXT | State value |
| updated_at | TEXT | Last update timestamp |

## API Endpoints

### GET /api/pppoe/dashboard
Returns dashboard statistics and chart data.

**Response:**
```json
{
  "ok": true,
  "stats": {
    "total_events": 1234,
    "total_connected": 650,
    "total_disconnected": 584,
    "currently_connected": 45,
    "repeated_disconnects": 8
  },
  "hourly_disconnects": [
    {"hour": "2026-11-04 00:00:00", "disconnect_count": 5},
    ...
  ],
  "daily_disconnects": [
    {"day": "2026-11-04", "disconnect_count": 42},
    ...
  ],
  "top_disconnected_users": [
    {
      "username": "user123",
      "disconnect_count": 25,
      "last_disconnect": "2026-11-04T10:30:15+00:00",
      "last_connected": "2026-11-04T10:35:20+00:00"
    },
    ...
  ]
}
```

### GET /api/pppoe/recent-events
Returns recent PPPoE events.

**Query Parameters:**
- `limit` (default: 100, max: 500)
- `offset` (default: 0)
- `username` (optional): filter by username
- `event_type` (optional): 'connected', 'disconnected', or 'unknown'

**Response:**
```json
{
  "ok": true,
  "events": [
    {
      "id": 123,
      "log_id": "*ABC123",
      "timestamp": "2026-11-04T10:30:15+00:00",
      "topics": "pppoe,ppp,info",
      "username": "user123",
      "ip_address": "10.10.10.50",
      "event_type": "disconnected",
      "message": "<pppoe-user123> disconnected",
      "disconnect_reason": null
    },
    ...
  ],
  "limit": 100,
  "offset": 0
}
```

### GET /api/pppoe/most-disconnected
Returns users with the most disconnections.

**Query Parameters:**
- `limit` (default: 100, max: 500)
- `days` (optional): filter by last N days

**Response:**
```json
{
  "ok": true,
  "users": [
    {
      "username": "user123",
      "disconnect_count": 25,
      "last_disconnect": "2026-11-04T10:30:15+00:00",
      "last_connected": "2026-11-04T10:35:20+00:00"
    },
    ...
  ],
  "days": null,
  "limit": 100
}
```

### GET /api/pppoe/user/<username>/history
Returns detailed connection history for a specific user.

**Response:**
```json
{
  "ok": true,
  "history": {
    "username": "user123",
    "total_connected": 150,
    "total_disconnected": 148,
    "last_connected": "2026-11-04T11:00:00+00:00",
    "last_disconnected": "2026-11-04T10:30:15+00:00",
    "events": [
      {
        "id": 1,
        "timestamp": "2026-11-03T08:00:00+00:00",
        "event_type": "connected",
        "ip_address": "10.10.10.50",
        "message": "<pppoe-user123> connected",
        "disconnect_reason": null
      },
      ...
    ]
  }
}
```

## Log Parsing

The system parses MikroTik RouterOS log messages to extract connection events. It recognizes common patterns:

### Connected Events
- `<pppoe-username> connected`
- `<username> connected`
- `username logged in`

### Disconnected Events
- `<pppoe-username> disconnected`
- `<username> disconnected`
- `username logged out`
- `username terminated`

### Disconnect Reasons
When available, disconnect reasons are extracted from parentheses in log messages:
- Example: `<pppoe-user123> disconnected (user request)`
- Reason stored: "user request"

### IP Address Extraction
IP addresses are extracted using regex pattern matching from log messages when present.

## Timezone Handling

All timestamps are:
- Stored in UTC in the database
- Displayed in **Asia/Dhaka timezone (UTC+6)** in the UI
- Formatted as: `YYYY-MM-DD HH:MM:SS`

## Background Monitoring

The PPPoE monitoring runs in a background thread that:
1. Starts automatically when the application starts
2. Polls router logs every 12 seconds (configurable)
3. Processes only new logs since last collection
4. Handles router connection failures gracefully
5. Logs errors without crashing the main application

## Configuration

The monitoring system uses the same router configuration as the IP allocation features:

```env
ROUTER_HOST=192.168.1.1
ROUTER_USER=api_user
ROUTER_PASSWORD=your_password
ROUTER_PORT=8728
ROUTER_USE_SSL=false
ROUTER_TIMEOUT=10
```

## Router Permissions

The router user needs **read access** to:
- `/log` - to read log entries

The existing permissions for PPPoE IP allocation (`read,api` policies on `/ip/route`, `/ppp/secret`, `/ppp/active`) are sufficient. The monitoring feature adds log reading capability.

## Performance Considerations

- **Database Size**: Each event is ~200-500 bytes. 10,000 events ≈ 2-5 MB
- **Log Polling**: 12-second intervals keep data fresh without overloading the router
- **Duplicate Prevention**: UNIQUE constraint prevents duplicate entries
- **Indexes**: Optimized for common queries (username, timestamp, event_type)
- **Chart Data**: Hourly/daily aggregations are computed on-demand

## Troubleshooting

### No Events Appearing

1. **Check router connectivity**: Ensure the main IP allocation dashboard shows "Connected"
2. **Verify log access**: The router user must have permission to read `/log`
3. **Check application logs**: Look for errors from `pppoe_monitor`
4. **Verify PPPoE activity**: Ensure users are actually connecting/disconnecting

### Events Not Parsing Correctly

Some RouterOS versions may use different log message formats. Check:
1. Raw messages in the "Recent Events" table
2. Application logs for parsing warnings
3. The `event_type` field - unknown events are stored as `type='unknown'`

### Missing Historical Data

The monitoring only captures events **after** it starts running:
- Historical logs in RouterOS buffer are collected on first run
- RouterOS log buffer is limited (default ~1000 entries)
- For complete history, ensure the application runs continuously

### High Database Size

To manage database size:
1. Consider archiving old events (>90 days)
2. Implement a retention policy if needed
3. The database will grow proportionally to PPPoE activity

## Testing Instructions

### 1. Initial Setup
```bash
# Ensure database is initialized
python app.py

# Check that tables were created
sqlite3 instance/app.db ".schema pppoe_events"
```

### 2. Test Log Collection
1. Start the application
2. Wait 15-30 seconds for the first log collection
3. Check application logs for: `PPPoE monitor: collected X new events`
4. Navigate to "Recent Events" in the web UI

### 3. Test with Real Disconnections
1. Disconnect a PPPoE user from MikroTik
2. Wait 12-15 seconds for log collection
3. Check "Recent Events" - should show the disconnection
4. Reconnect the user
5. Check "Recent Events" - should show the connection

### 4. Verify Duplicate Prevention
1. Restart the application
2. Check that events are not duplicated in the database
3. The monitoring should continue from the last processed log

### 5. Test Analytics
1. Generate multiple connect/disconnect events
2. Check "Connection Monitoring" dashboard for updated stats
3. Verify charts show correct trends
4. Check "Most Disconnected Users" for accurate counts

### 6. Test User History
1. Click "View History" for a user with multiple events
2. Verify the timeline shows events in chronological order
3. Check that statistics match the events shown

## Migration Notes

This feature extends the existing application without modifying IP allocation functionality:
- New database tables are created automatically on first run
- Existing tables and data are not modified
- Background monitoring starts automatically
- No configuration changes required

## Future Enhancements

Possible improvements:
- Export PPPoE events to CSV
- Email/SMS alerts for users with excessive disconnections
- Session duration calculations (matching connect/disconnect pairs)
- Average session length and offline duration statistics
- Disconnect reason analysis and categorization
- Integration with external monitoring systems (Prometheus, Grafana)

## Support

For issues or questions:
1. Check application logs: Look for `pppoe_monitor` entries
2. Verify router connectivity: Check main dashboard status
3. Review this documentation
4. Check RouterOS log format compatibility
