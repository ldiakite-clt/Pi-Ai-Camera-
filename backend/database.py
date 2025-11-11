import sqlite3
from pathlib import Path
import time

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "database.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        created_at INTEGER NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS enrollment_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        enrollment_id INTEGER NOT NULL,
        path TEXT NOT NULL,
        FOREIGN KEY(enrollment_id) REFERENCES enrollments(id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER NOT NULL,
        label TEXT,
        confidence REAL,
        snapshot_path TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER NOT NULL,
        path TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()


def add_enrollment(name):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO enrollments (name, created_at) VALUES (?, ?)", (name, int(time.time())))
    conn.commit()
    cur.execute("SELECT id FROM enrollments WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()
    return row["id"] if row else None


def add_enrollment_image(enrollment_id, path):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO enrollment_images (enrollment_id, path) VALUES (?, ?)", (enrollment_id, str(path)))
    conn.commit()
    conn.close()


def list_enrollments():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, created_at FROM enrollments ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def add_event(timestamp, label, confidence, snapshot_path=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO events (timestamp, label, confidence, snapshot_path) VALUES (?, ?, ?, ?)",
                (int(timestamp), label, confidence, snapshot_path))
    conn.commit()
    conn.close()


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


# initialize DB on import
init_db()
