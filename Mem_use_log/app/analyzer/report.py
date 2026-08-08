import csv
from storage.database import Database

class CSVExporter:
    def __init__(self, db: Database):
        self.db = db

    def _export_table(self, table_name: str, output_path: str, session_id: str = None) -> bool:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                if session_id:
                    cursor.execute(f"SELECT * FROM {table_name} WHERE session_id = ?", (session_id,))
                else:
                    cursor.execute(f"SELECT * FROM {table_name}")
                rows = cursor.fetchall()
                
                if not rows:
                    return False
                    
                col_names = [description[0] for description in cursor.description]
                
                with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(col_names)
                    writer.writerows(rows)
                    
                return True
            except Exception as e:
                from utils.logger import logger
                logger.exception(f"Failed to export {table_name} to {output_path}")
                return False

    def export_system_data(self, output_path: str = "data/exports/system_data.csv", session_id: str = None):
        """Export every table to CSVs sharing `output_path`'s base name.

        Passing `session_id` narrows the dump to a single recording run —
        that's what the automatic export on exit uses, so each run gets its
        own file instead of re-dumping the whole history every time.
        """
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 1. Export main system data
        has_data = self._export_table("system_data", output_path, session_id)
        
        # 2. Export GPU, Process, Disk, and Network data using the same base name
        dir_name = os.path.dirname(output_path)
        base_name = os.path.basename(output_path)
        
        # If user named it "system_data.csv", the others will be "gpu_system_data.csv". 
        # For better naming, if it starts with "system_", we can replace it, else prepend.
        if base_name.startswith("system_"):
            gpu_name = base_name.replace("system_", "gpu_", 1)
            proc_name = base_name.replace("system_", "process_", 1)
            disk_name = base_name.replace("system_", "disk_", 1)
            net_name = base_name.replace("system_", "network_", 1)
        else:
            gpu_name = f"gpu_{base_name}"
            proc_name = f"process_{base_name}"
            disk_name = f"disk_{base_name}"
            net_name = f"network_{base_name}"
            
        gpu_path = os.path.join(dir_name, gpu_name)
        process_path = os.path.join(dir_name, proc_name)
        disk_path = os.path.join(dir_name, disk_name)
        net_path = os.path.join(dir_name, net_name)
        
        self._export_table("gpu_data", gpu_path, session_id)
        self._export_table("process_data", process_path, session_id)
        self._export_table("disk_data", disk_path, session_id)
        self._export_table("network_data", net_path, session_id)
        
        return has_data
