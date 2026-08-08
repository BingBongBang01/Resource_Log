import queue
import threading
import time
from .database import Database
from typing import Dict, Any, List

class SQLiteWriter:
    def __init__(self, db: Database, batch_size=50, flush_interval=10.0):
        self.db = db
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.q = queue.Queue()
        self.running = False
        self.thread = None
        self.last_write_time = None

    def get_queue_size(self):
        return self.q.qsize()

    def get_last_write_time(self):
        return self.last_write_time

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._writer_loop, daemon=True)
            self.thread.start()

    def stop(self):
        from utils.logger import logger
        self.running = False
        if self.thread:
            logger.info("Waiting for SQLiteWriter to drain queue and flush...")
            self.thread.join(timeout=15.0)
            if self.thread.is_alive():
                logger.warning("SQLiteWriter did not finish flushing within 15 seconds!")
            else:
                logger.info("SQLiteWriter successfully flushed and stopped.")

    def write_system_data(self, data: Dict[str, Any]):
        self.q.put(("system", data))

    def write_process_data(self, session_id: str, timestamp: str, process_data: Dict[str, List[Dict[str, Any]]]):
        self.q.put(("process", (session_id, timestamp, process_data)))

    def write_gpu_data(self, session_id: str, timestamp: str, gpu_data: List[Dict[str, Any]]):
        self.q.put(("gpu", (session_id, timestamp, gpu_data)))

    def write_disk_data(self, session_id: str, timestamp: str, disk_data: List[Dict[str, Any]]):
        self.q.put(("disk", (session_id, timestamp, disk_data)))

    def write_network_data(self, session_id: str, timestamp: str, network_data: List[Dict[str, Any]]):
        self.q.put(("network", (session_id, timestamp, network_data)))

    def _writer_loop(self):
        batch_sys = []
        batch_proc = []
        batch_gpu = []
        batch_disk = []
        batch_network = []
        last_flush = time.time()
        
        while self.running or not self.q.empty():
            try:
                # Use a small timeout so we can check self.running periodically
                item_type, item = self.q.get(timeout=0.5)
                if item_type == "system":
                    batch_sys.append(item)
                elif item_type == "process":
                    batch_proc.append(item)
                elif item_type == "gpu":
                    batch_gpu.append(item)
                elif item_type == "disk":
                    batch_disk.append(item)
                elif item_type == "network":
                    batch_network.append(item)
            except queue.Empty:
                pass

            now = time.time()
            time_to_flush = (now - last_flush) >= self.flush_interval
            size_to_flush = len(batch_sys) >= self.batch_size or len(batch_proc) >= self.batch_size or len(batch_gpu) >= self.batch_size or len(batch_disk) >= self.batch_size or len(batch_network) >= self.batch_size
            
            if size_to_flush or time_to_flush or (not self.running):
                try:
                    self._flush(batch_sys, batch_proc, batch_gpu, batch_disk, batch_network)
                    batch_sys.clear()
                    batch_proc.clear()
                    batch_gpu.clear()
                    batch_disk.clear()
                    batch_network.clear()
                    last_flush = now
                except Exception as e:
                    from utils.logger import logger
                    logger.exception(f"SQLite Write Failed. Queue will retry. Error: {e}")
                    time.sleep(1.0) # Backoff before retry

    def _flush(self, batch_sys, batch_proc, batch_gpu, batch_disk, batch_network):
        if not batch_sys and not batch_proc and not batch_gpu and not batch_disk and not batch_network:
            return
            
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            if batch_sys:
                # Task 24: Model validation (ensure we only insert valid columns)
                allowed_columns = {
                    'timestamp', 'session_id', 'cpu_usage', 'cpu_freq_mhz', 'cpu_temperature',
                    'ram_total', 'ram_used', 'ram_available', 'ram_usage_percent',
                    'commit_used', 'commit_limit', 'commit_usage_percent',
                    'pagefile_total', 'pagefile_used', 'pagefile_usage_percent'
                }
                
                # Filter dictionary keys based on allowed_columns
                valid_sys_data = []
                for sys in batch_sys:
                    valid_row = {k: v for k, v in sys.items() if k in allowed_columns}
                    valid_sys_data.append(valid_row)
                    
                if valid_sys_data:
                    columns = ', '.join(valid_sys_data[0].keys())
                    placeholders = ', '.join('?' * len(valid_sys_data[0]))
                    query = f"INSERT INTO system_data ({columns}) VALUES ({placeholders})"
                    
                    values_list = [tuple(data.values()) for data in valid_sys_data]
                    cursor.executemany(query, values_list)
                
            if batch_proc:
                proc_values = []
                for session_id, timestamp, process_data in batch_proc:
                    for category, process_list in process_data.items():
                        for proc in process_list:
                            proc_values.append((
                                timestamp,
                                session_id,
                                category,
                                proc.get('pid'),
                                proc.get('name'),
                                proc.get('cpu_percent'),
                                proc.get('ram_mb'),
                                proc.get('gpu_percent', 0.0),
                                proc.get('gpu_memory_mb', 0.0)
                            ))
                            
                if proc_values:
                    cursor.executemany('''
                        INSERT INTO process_data 
                        (timestamp, session_id, category, pid, name, cpu_percent, ram_mb, gpu_percent, gpu_memory_mb)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', proc_values)
                    
            if batch_gpu:
                gpu_values = []
                for session_id, timestamp, gpus in batch_gpu:
                    for i, gpu in enumerate(gpus):
                        gpu_values.append((
                            timestamp,
                            session_id,
                            i,
                            gpu.get('name', 'Unknown'),
                            gpu.get('gpu_usage'),
                            gpu.get('gpu_vram_used'),
                            gpu.get('gpu_vram_total'),
                            gpu.get('gpu_temperature'),
                            gpu.get('gpu_hotspot'),
                            gpu.get('gpu_power')
                        ))
                        
                if gpu_values:
                    cursor.executemany('''
                        INSERT INTO gpu_data 
                        (timestamp, session_id, gpu_index, gpu_name, gpu_usage, gpu_vram_used, gpu_vram_total, gpu_temperature, gpu_hotspot, gpu_power)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', gpu_values)
                    
            if batch_disk:
                disk_values = []
                for session_id, timestamp, disks in batch_disk:
                    for disk in disks:
                        disk_values.append((
                            timestamp,
                            session_id,
                            disk.get('name', 'Unknown'),
                            disk.get('type', 'Unknown'),
                            disk.get('read_mbps'),
                            disk.get('write_mbps'),
                            disk.get('free_gb'),
                            disk.get('total_gb')
                        ))
                        
                if disk_values:
                    cursor.executemany('''
                        INSERT INTO disk_data 
                        (timestamp, session_id, disk_name, disk_type, read_mbps, write_mbps, free_gb, total_gb)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', disk_values)
                    
            if batch_network:
                net_values = []
                for session_id, timestamp, network_data in batch_network:
                    for net in network_data:
                        net_values.append((
                            timestamp,
                            session_id,
                            net.get('name'),
                            net.get('is_active', False),
                            net.get('download_mbps', 0.0),
                            net.get('upload_mbps', 0.0)
                        ))
                        
                cursor.executemany('''
                    INSERT INTO network_data 
                    (timestamp, session_id, interface_name, is_active, download_mbps, upload_mbps)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', net_values)
                
            conn.commit()
            
            from datetime import datetime
            self.last_write_time = datetime.now().strftime("%H:%M:%S")
