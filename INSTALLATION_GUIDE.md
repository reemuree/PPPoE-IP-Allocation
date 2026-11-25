# PPPoE Connection Monitoring - Installation & Quick Start Guide

## Quick Start

Your PPPoE IP Allocation Manager now includes connection monitoring! The feature has been fully integrated and will start working immediately.

## What's New

### New Navigation Menu Items
1. **Connection Monitoring** - Dashboard with statistics and charts
2. **Recent Events** - Live feed of PPPoE connections/disconnections  
3. **Most Disconnected Users** - Identify problematic connections

### Automatic Background Monitoring
The application now automatically:
- Collects PPPoE logs every 12 seconds
- Stores connection events permanently
- Prevents duplicate entries
- Handles router disconnections gracefully

## Installation Steps

### 1. No Additional Dependencies Required
All features use existing dependencies from your project:
- Flask (already installed)
- SQLite3 (Python built-in)
- librouteros (already installed)

### 2. Database Migration (Automatic)
The new database tables are created automatically when you start the application:
```bash
python app.py
```

The following tables will be created:
- `pppoe_events` - Stores all connection/disconnection events
- `pppoe_monitor_state` - Tracks the monitoring state

### 3. Verify Installation
Run the test script to verify everything is working:
```bash
python test_pppoe_monitor.py
```

This will test:
- Database schema creation
- Log message parsing
- Router connectivity
- Statistics generation
- Duplicate prevention

## First Run

1. **Start the application:**
   ```bash
   python app.py
   ```

2. **Check the logs:**
   Look for this message in the console:
   ```
   PPPoE monitor thread started (polling every 12 seconds)
   ```

3. **Wait for first collection:**
   Within 12-15 seconds, you should see:
   ```
   PPPoE monitor: collected X new events
   ```

4. **Open the web interface:**
   Navigate to your application (e.g., `http://localhost:5000`)
   
5. **Explore new features:**
   - Click "Connection Monitoring" in the sidebar
   - View statistics and charts
   - Check "Recent Events" for live data
   - Explore "Most Disconnected Users"

## Configuration

No additional configuration needed! The monitoring uses your existing router settings:

```env
# Your existing .env file
ROUTER_HOST=192.168.1.1
ROUTER_USER=api_user
ROUTER_PASSWORD=your_password
ROUTER_PORT=8728
ROUTER_USE_SSL=false
```

### Router Permissions

Your router user needs **read access** to:
- `/log` (to read log entries)
- `/ppp/secret` (already configured)
- `/ppp/active` (already configured)

The standard `read,api` policy group is sufficient.

## Usage Examples

### View Real-Time Events
1. Navigate to **Recent Events**
2. Watch as users connect/disconnect
3. Filter by event type or search by username

### Identify Problem Users
1. Navigate to **Most Disconnected Users**
2. See users ranked by disconnection count
3. Filter by time range (Today, Last 7 days, etc.)
4. Click "View History" for detailed timeline

### Monitor Trends
1. Navigate to **Connection Monitoring**
2. View hourly disconnection trends (last 24 hours)
3. View daily disconnection trends (last 30 days)
4. See top 10 most disconnected users at a glance

### Investigate Specific User
1. Go to **Most Disconnected Users** or **Recent Events**
2. Click "View History" next to any username
3. See complete connection timeline
4. View disconnect reasons and raw log messages

## Troubleshooting

### No Events Appearing

**Check 1: Router Connection**
- Verify main dashboard shows "Connected"
- Check that IP allocation features are working

**Check 2: Application Logs**
```bash
# Look for errors in the console
# Should see: "PPPoE monitor thread started"
```

**Check 3: Router Permissions**
Test router access:
```bash
python router_client.py
```

**Check 4: PPPoE Activity**
- Ensure users are actually connecting/disconnecting
- Initial collection may take 12-15 seconds

### Events Not Parsing

Some RouterOS versions may use different log formats. Check:
1. **Recent Events** page - look at raw messages
2. Events marked as "Unknown" type are stored but not parsed
3. Check application logs for parsing warnings

### Database Issues

**Reset Database (if needed):**
```bash
# Backup first!
cp instance/app.db instance/app.db.backup

# Delete monitoring tables
sqlite3 instance/app.db
> DROP TABLE IF EXISTS pppoe_events;
> DROP TABLE IF EXISTS pppoe_monitor_state;
> .quit

# Restart application (tables will be recreated)
python app.py
```

## Performance Notes

### Database Growth
- Each event: ~200-500 bytes
- 1,000 events/day ≈ 200-500 KB/day
- 10,000 events ≈ 2-5 MB

### System Resources
- Background thread: Minimal CPU usage
- Memory: ~5-10 MB for monitoring
- Network: One API call every 12 seconds to router

### Optimization Tips
1. **Archive old data** (optional):
   ```sql
   -- Delete events older than 90 days
   DELETE FROM pppoe_events 
   WHERE timestamp < datetime('now', '-90 days');
   ```

2. **Vacuum database** (optional):
   ```bash
   sqlite3 instance/app.db "VACUUM;"
   ```

## File Changes Summary

### New Files
- `pppoe_monitor.py` - Core monitoring logic
- `PPPOE_MONITORING.md` - Detailed documentation
- `test_pppoe_monitor.py` - Test suite
- `INSTALLATION_GUIDE.md` - This file

### Modified Files
- `app.py` - Added API endpoints and background thread
- `templates/index.html` - Added new UI sections
- `static/js/app.js` - Added JavaScript for monitoring features

### Existing Features Unchanged
All existing IP allocation features remain unchanged:
- Dashboard
- IP Inventory
- Assigned/Free IPs
- Reports
- Network configuration
- User traffic monitoring

## Next Steps

1. **Run the application** and let it collect data for a few hours
2. **Generate test events** by connecting/disconnecting PPPoE users
3. **Explore the dashboards** to see statistics and trends
4. **Review the documentation** in `PPPOE_MONITORING.md` for detailed API info

## Support & Documentation

- **Full Documentation**: See `PPPOE_MONITORING.md`
- **Test Suite**: Run `test_pppoe_monitor.py`
- **Application Logs**: Check console output for monitoring status
- **Database**: Located at `instance/app.db`

## Feature Highlights

✅ **Automatic monitoring** - No manual intervention required  
✅ **Persistent storage** - Data survives restarts  
✅ **Duplicate prevention** - Smart deduplication  
✅ **Real-time dashboards** - Live statistics and charts  
✅ **User analytics** - Identify connection issues  
✅ **Searchable history** - Find specific events quickly  
✅ **Time-based filtering** - Analyze trends over time  
✅ **Asia/Dhaka timezone** - All times displayed in UTC+6  

## Upgrade Path

This is a **non-breaking update**:
- Existing data is preserved
- No configuration changes required
- New features available immediately
- Old features work exactly as before

Enjoy your enhanced PPPoE monitoring capabilities! 🚀
