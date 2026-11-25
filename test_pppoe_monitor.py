"""Test script for PPPoE monitoring functionality.

Run this to verify the PPPoE monitoring feature is working correctly.
"""
import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from pppoe_monitor import PPPoEMonitor
from router_client import RouterConfig, RouterError

def test_database_schema():
    """Test that database tables are created correctly."""
    print("Testing database schema...")

    db_path = "instance/app.db"
    monitor = PPPoEMonitor(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pppoe_events'")
    if cursor.fetchone():
        print("✓ pppoe_events table exists")
    else:
        print("✗ pppoe_events table not found")
        return False

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pppoe_monitor_state'")
    if cursor.fetchone():
        print("✓ pppoe_monitor_state table exists")
    else:
        print("✗ pppoe_monitor_state table not found")
        return False

    # Check indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='pppoe_events'")
    indexes = [row[0] for row in cursor.fetchall()]
    expected_indexes = ['idx_pppoe_events_username', 'idx_pppoe_events_timestamp',
                       'idx_pppoe_events_type', 'idx_pppoe_events_log_id']

    for idx in expected_indexes:
        if idx in indexes:
            print(f"✓ Index {idx} exists")
        else:
            print(f"✗ Index {idx} not found")

    conn.close()
    return True


def test_log_parsing():
    """Test log message parsing."""
    print("\nTesting log parsing...")

    monitor = PPPoEMonitor("instance/app.db")

    test_cases = [
        {
            "message": "<pppoe-user123> connected",
            "topics": "pppoe,ppp,info",
            "expected": {
                "username": "user123",
                "event_type": "connected"
            }
        },
        {
            "message": "<pppoe-user456> disconnected",
            "topics": "pppoe,ppp,info",
            "expected": {
                "username": "user456",
                "event_type": "disconnected"
            }
        },
        {
            "message": "user789 logged in",
            "topics": "ppp,info",
            "expected": {
                "username": "user789",
                "event_type": "connected"
            }
        },
        {
            "message": "<pppoe-testuser> disconnected (user request)",
            "topics": "pppoe,info",
            "expected": {
                "username": "testuser",
                "event_type": "disconnected",
                "disconnect_reason": "user request"
            }
        }
    ]

    all_passed = True
    for i, test in enumerate(test_cases, 1):
        log_entry = {
            "message": test["message"],
            "topics": test["topics"],
            ".id": f"*TEST{i}",
            "time": "nov/04/2026 11:00:00"
        }

        result = monitor._parse_pppoe_event(log_entry)

        if result is None:
            print(f"✗ Test {i}: Failed to parse '{test['message']}'")
            all_passed = False
            continue

        passed = True
        for key, expected_value in test["expected"].items():
            if result.get(key) != expected_value:
                print(f"✗ Test {i}: {key} mismatch. Expected '{expected_value}', got '{result.get(key)}'")
                passed = False
                all_passed = False

        if passed:
            print(f"✓ Test {i}: Correctly parsed '{test['message']}'")

    return all_passed


def test_router_connection():
    """Test connection to MikroTik router."""
    print("\nTesting router connection...")

    try:
        config = RouterConfig.from_env()
        print(f"Router config: {config.host}:{config.port}")

        monitor = PPPoEMonitor("instance/app.db")
        result = monitor.fetch_and_store_logs(config)

        if result["ok"]:
            print(f"✓ Successfully connected to router")
            print(f"  - Processed {result['processed_logs']} log entries")
            print(f"  - Found {result['new_events']} new PPPoE events")
            return True
        else:
            print(f"✗ Router connection failed: {result.get('error')}")
            return False

    except RouterError as e:
        print(f"✗ Router error [{e.kind}]: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


def test_statistics():
    """Test statistics generation."""
    print("\nTesting statistics...")

    monitor = PPPoEMonitor("instance/app.db")

    try:
        stats = monitor.get_dashboard_stats()

        print(f"✓ Dashboard stats:")
        print(f"  - Total events: {stats['total_events']}")
        print(f"  - Total connected: {stats['total_connected']}")
        print(f"  - Total disconnected: {stats['total_disconnected']}")
        print(f"  - Currently connected: {stats['currently_connected']}")
        print(f"  - Repeated disconnects: {stats['repeated_disconnects']}")

        # Test time-based stats
        hourly = monitor.get_hourly_disconnect_stats(days=1)
        print(f"✓ Hourly stats: {len(hourly)} data points")

        daily = monitor.get_daily_disconnect_stats(days=7)
        print(f"✓ Daily stats: {len(daily)} data points")

        # Test user stats
        users = monitor.get_most_disconnected_users(limit=5)
        print(f"✓ Most disconnected users: {len(users)} users")

        if users:
            top_user = users[0]
            print(f"  - Top user: {top_user['username']} ({top_user['disconnect_count']} disconnects)")

        return True

    except Exception as e:
        print(f"✗ Statistics error: {e}")
        return False


def test_event_storage():
    """Test that events are stored without duplicates."""
    print("\nTesting event storage...")

    monitor = PPPoEMonitor("instance/app.db")
    conn = sqlite3.connect("instance/app.db")

    # Count events before
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pppoe_events")
    count_before = cursor.fetchone()[0]
    print(f"Events before: {count_before}")

    # Attempt to fetch logs twice (should not create duplicates)
    try:
        config = RouterConfig.from_env()

        result1 = monitor.fetch_and_store_logs(config)
        new_events_1 = result1.get("new_events", 0)

        result2 = monitor.fetch_and_store_logs(config)
        new_events_2 = result2.get("new_events", 0)

        cursor.execute("SELECT COUNT(*) FROM pppoe_events")
        count_after = cursor.fetchone()[0]

        print(f"Events after first fetch: +{new_events_1}")
        print(f"Events after second fetch: +{new_events_2}")
        print(f"Total events: {count_after}")

        if new_events_2 == 0 and count_after == count_before + new_events_1:
            print("✓ Duplicate prevention working correctly")
            conn.close()
            return True
        else:
            print("⚠ Duplicate prevention may not be working as expected")
            conn.close()
            return False

    except Exception as e:
        print(f"✗ Event storage test error: {e}")
        conn.close()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("PPPoE Monitoring Test Suite")
    print("=" * 60)

    results = {
        "Database Schema": test_database_schema(),
        "Log Parsing": test_log_parsing(),
        "Router Connection": test_router_connection(),
        "Statistics": test_statistics(),
        "Event Storage": test_event_storage(),
    }

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name}: {status}")

    all_passed = all(results.values())

    print("\n" + "=" * 60)
    if all_passed:
        print("All tests passed! ✓")
    else:
        print("Some tests failed. Please review the output above.")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
