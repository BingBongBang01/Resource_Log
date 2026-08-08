import sqlite3
import os
from config.settings import PROJECT_ROOT

class Database:
    def __init__(self, db_path: str = "data/database/system_monitor.db"):
        self.db_path = os.path.join(PROJECT_ROOT, db_path) if not os.path.isabs(db_path) else db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        # Apply performance and concurrency pragmas for long-running processes
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # System Data Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    session_id TEXT,
                    cpu_usage REAL,
                    cpu_freq_mhz REAL,
                    cpu_temperature REAL,
                    ram_total REAL,
                    ram_used REAL,
                    ram_available REAL,
                    ram_usage_percent REAL,
                    commit_used REAL,
                    commit_limit REAL,
                    commit_usage_percent REAL,
                    pagefile_total REAL,
                    pagefile_used REAL,
                    pagefile_usage_percent REAL,
                    gpu_usage REAL,
                    gpu_vram_used REAL,
                    gpu_vram_total REAL,
                    gpu_temperature REAL,
                    gpu_hotspot REAL,
                    gpu_power REAL,
                    disk_active_percent REAL,
                    disk_read_mbps REAL,
                    disk_write_mbps REAL,
                    disk_temperature REAL,
                    disk_free REAL,
                    network_download_mbps REAL,
                    network_upload_mbps REAL
                )
            ''')
            
            # Process Data Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS process_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    session_id TEXT,
                    category TEXT,  -- 'top_cpu' or 'top_ram' or 'top_gpu'
                    pid INTEGER,
                    name TEXT,
                    cpu_percent REAL,
                    ram_mb REAL,
                    gpu_percent REAL,
                    gpu_memory_mb REAL
                )
            ''')
            
            # Multi-GPU Data Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS gpu_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    session_id TEXT,
                    gpu_index INTEGER,
                    gpu_name TEXT,
                    gpu_usage REAL,
                    gpu_vram_used REAL,
                    gpu_vram_total REAL,
                    gpu_temperature REAL,
                    gpu_hotspot REAL,
                    gpu_power REAL
                )
            ''')
            
            # Disk Data Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS disk_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    session_id TEXT,
                    disk_name TEXT,
                    disk_type TEXT,
                    read_mbps REAL,
                    write_mbps REAL,
                    free_gb REAL,
                    total_gb REAL
                )
            ''')
            
            # Network Data Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS network_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    session_id TEXT,
                    interface_name TEXT,
                    is_active BOOLEAN,
                    download_mbps REAL,
                    upload_mbps REAL
                )
            ''')
            
            # Frame-rate Data Table. One row per game RTSS is measuring, so
            # a session that ran two games keeps them apart by app_name.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fps_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    session_id TEXT,
                    app_name TEXT,
                    fps REAL,
                    fps_avg REAL,
                    fps_min REAL,
                    fps_max REAL,
                    frame_time_ms REAL
                )
            ''')

            # Create indices
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_sys_session_time ON system_data(session_id, timestamp)
            ''')
            
            # Create indices for faster analysis queries
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sys_session ON system_data(session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sys_time ON system_data(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_proc_session ON process_data(session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_gpu_session ON gpu_data(session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_disk_session ON disk_data(session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_network_session ON network_data(session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_fps_session ON fps_data(session_id)')
            
            # Metadata Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # Migration system
            cursor.execute("SELECT value FROM metadata WHERE key='schema_version'")
            row = cursor.fetchone()
            current_version = int(row[0]) if row else 0
            
            if current_version < 1:
                # Version 1 migrations
                cursor.execute("PRAGMA table_info(system_data)")
                columns = [info[1] for info in cursor.fetchall()]
                
                if 'commit_usage_percent' not in columns:
                    cursor.execute('ALTER TABLE system_data ADD COLUMN commit_usage_percent REAL DEFAULT 0.0')
                if 'pagefile_total' not in columns:
                    cursor.execute('ALTER TABLE system_data ADD COLUMN pagefile_total REAL DEFAULT 0.0')
                if 'pagefile_used' not in columns:
                    cursor.execute('ALTER TABLE system_data ADD COLUMN pagefile_used REAL DEFAULT 0.0')
                    
                cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', '1')")
                current_version = 1
                
            if current_version < 2:
                # Version 2 migrations: cpu_freq_mhz
                cursor.execute("PRAGMA table_info(system_data)")
                columns = [info[1] for info in cursor.fetchall()]
                
                if 'cpu_freq_mhz' not in columns:
                    cursor.execute('ALTER TABLE system_data ADD COLUMN cpu_freq_mhz REAL DEFAULT 0.0')
                    
                cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', '2')")
                current_version = 2

            if current_version < 3:
                # Version 3: fps_data. CREATE TABLE IF NOT EXISTS above has
                # already made it; this only records that the schema moved on.
                cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', '3')")
                current_version = 3

            conn.commit()
