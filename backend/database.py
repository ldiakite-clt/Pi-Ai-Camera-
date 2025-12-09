
# This file handles all the database stuff for our Pi-Ai-Camera project
# We use SQLite because it's simple and works great for small projects
import sqlite3
from pathlib import Path
import time

# Where we keep our database file
DB_PATH = Path(__file__).resolve().parents[1] / "data" / "database.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)



# Get a connection to our SQLite database
def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn



# Set up all our tables if they don't exist yet
def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # Table for people enrolled (if you use face recognition)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        created_at INTEGER NOT NULL
    )
    """)
    # Table for images linked to enrollments
    cur.execute("""
    CREATE TABLE IF NOT EXISTS enrollment_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        enrollment_id INTEGER NOT NULL,
        path TEXT NOT NULL,
        FOREIGN KEY(enrollment_id) REFERENCES enrollments(id)
    )
    """)
    # Table for detection events (person detected, etc)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER NOT NULL,
        label TEXT,
        confidence REAL,
        snapshot_path TEXT
    )
    """)
    # Table for photos captured
    cur.execute("""
    CREATE TABLE IF NOT EXISTS photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER NOT NULL,
        path TEXT NOT NULL
    )
    """)
    # Table for saved video replays
    cur.execute("""
    CREATE TABLE IF NOT EXISTS replays (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER NOT NULL,
        duration INTEGER NOT NULL,
        frame_count INTEGER NOT NULL,
        file_size INTEGER NOT NULL,
        path TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()



# Add a new person to the enrollments table
def add_enrollment(name):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO enrollments (name, created_at) VALUES (?, ?)", (name, int(time.time())))
    conn.commit()
    cur.execute("SELECT id FROM enrollments WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()
    return row["id"] if row else None



# Link an image to an enrollment
def add_enrollment_image(enrollment_id, path):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO enrollment_images (enrollment_id, path) VALUES (?, ?)", (enrollment_id, str(path)))
    conn.commit()
    conn.close()



# Get all enrollments (people)
def list_enrollments():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, created_at FROM enrollments ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows



# Add a detection event (like a person detected)
def add_event(timestamp, label, confidence, snapshot_path=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO events (timestamp, label, confidence, snapshot_path) VALUES (?, ?, ?, ?)",
                (int(timestamp), label, confidence, snapshot_path))
    conn.commit()
    conn.close()


def clear_events_without_snapshots():
    """Delete all events that don't have associated snapshots (false positives from old detection)"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM events WHERE snapshot_path IS NULL")
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def clear_all_events():
    """Delete all events (for resetting heatmap)"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM events")
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def add_photo(timestamp, path):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO photos (timestamp, path) VALUES (?, ?)", (int(timestamp), str(path)))
    conn.commit()
    cur.execute("SELECT id FROM photos WHERE path = ?", (str(path),))
    row = cur.fetchone()
    conn.close()
    return row["id"] if row else None


def list_photos(limit=100):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, timestamp, path FROM photos ORDER BY timestamp DESC LIMIT ?", (int(limit),))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def delete_photo(photo_id):
    """Delete a photo by ID and return its path for file cleanup"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT path FROM photos WHERE id = ?", (int(photo_id),))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    path = row["path"]
    cur.execute("DELETE FROM photos WHERE id = ?", (int(photo_id),))
    conn.commit()
    conn.close()
    return path


def delete_all_photos():
    """Delete all photos and return their paths for file cleanup"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT path FROM photos")
    rows = cur.fetchall()
    paths = [row["path"] for row in rows]
    cur.execute("DELETE FROM photos")
    conn.commit()
    conn.close()
    return paths


def add_replay(timestamp, duration, frame_count, file_size, path):
    """Add a replay to the database"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO replays (timestamp, duration, frame_count, file_size, path) VALUES (?, ?, ?, ?, ?)",
                (int(timestamp), int(duration), int(frame_count), int(file_size), str(path)))
    conn.commit()
    cur.execute("SELECT id FROM replays WHERE path = ?", (str(path),))
    row = cur.fetchone()
    conn.close()
    return row["id"] if row else None


def list_replays(limit=100):
    """List replays sorted by timestamp descending"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, timestamp, duration, frame_count, file_size, path FROM replays ORDER BY timestamp DESC LIMIT ?", (int(limit),))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def delete_replay(replay_id):
    """Delete a replay by ID and return its path for file cleanup"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT path FROM replays WHERE id = ?", (int(replay_id),))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    path = row["path"]
    cur.execute("DELETE FROM replays WHERE id = ?", (int(replay_id),))
    conn.commit()
    conn.close()
    return path


def delete_all_replays():
    """Delete all replays and return their paths for file cleanup"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT path FROM replays")
    rows = cur.fetchall()
    paths = [row["path"] for row in rows]
    cur.execute("DELETE FROM replays")
    conn.commit()
    conn.close()
    return paths


def cleanup_old_replays(keep_count=100):
    """Delete replays beyond the keep_count limit (keeps newest)"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, path FROM replays ORDER BY timestamp DESC LIMIT -1 OFFSET ?", (int(keep_count),))
    rows = cur.fetchall()
    deleted_paths = []
    for row in rows:
        cur.execute("DELETE FROM replays WHERE id = ?", (row["id"],))
        deleted_paths.append(row["path"])
    conn.commit()
    conn.close()
    return deleted_paths


def list_events(limit=100, label=None, start_ts=None, end_ts=None):
    conn = get_conn()
    cur = conn.cursor()
    q = "SELECT id, timestamp, label, confidence, snapshot_path FROM events"
    conds = []
    params = []
    if label:
        conds.append("label = ?")
        params.append(label)
    if start_ts:
        conds.append("timestamp >= ?")
        params.append(int(start_ts))
    if end_ts:
        conds.append("timestamp <= ?")
        params.append(int(end_ts))
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY timestamp DESC LIMIT ?"
    params.append(int(limit))
    cur.execute(q, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def heatmap_last_days(days=30):
    # return simple bucket counts for last `days` days by weekday (0-6) and hour (0-23)
    import time
    end = int(time.time())
    start = end - days * 86400
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT timestamp FROM events WHERE timestamp >= ?", (start,))
    rows = cur.fetchall()
    buckets = {str(d): {str(h): 0 for h in range(24)} for d in range(7)}
    for r in rows:
        ts = r[0]
        lt = time.localtime(ts)
        wd = lt.tm_wday
        hr = lt.tm_hour
        buckets[str(wd)][str(hr)] += 1
    conn.close()
    return buckets


def get_heatmap_photos(weekday: int, hour: int, days: int = 7, limit: int = 3, label: str = 'person'):
    """Get photos for a specific heatmap cell (weekday/hour)."""
    import time
    end = int(time.time())
    start = end - days * 86400
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, timestamp, label, confidence, snapshot_path 
        FROM events 
        WHERE timestamp >= ? 
          AND label = ?
          AND snapshot_path IS NOT NULL
        ORDER BY timestamp DESC
    """, (start, label))
    rows = cur.fetchall()
    conn.close()
    
    # Filter by weekday and hour
    results = []
    for r in rows:
        ts = r[1]
        lt = time.localtime(ts)
        if lt.tm_wday == weekday and lt.tm_hour == hour:
            snapshot_path = r[4]
            # Extract filename to build thumb and web paths
            fname = snapshot_path.split('/')[-1] if snapshot_path else None
            # Convert absolute path to web-accessible path
            web_path = f"/data/photos/{fname}" if fname else None
            thumb_path = f"/data/photos/thumbs/{fname}" if fname else None
            
            results.append({
                'id': r[0],
                'timestamp': r[1],
                'label': r[2],
                'confidence': r[3],
                'path': web_path,  # Web-accessible path
                'thumb': thumb_path  # Thumbnail for gallery
            })
            if len(results) >= limit:
                break
    return results


# initialize DB on import
init_db()
