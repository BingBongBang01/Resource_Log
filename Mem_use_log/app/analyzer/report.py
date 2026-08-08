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
        for table, prefix in (("gpu_data", "gpu"), ("process_data", "process"),
                              ("disk_data", "disk"), ("network_data", "network"),
                              ("fps_data", "fps")):
            # "system_log.csv" -> "gpu_log.csv"; anything else just gets the
            # prefix stuck on the front.
            if base_name.startswith("system_"):
                name = base_name.replace("system_", f"{prefix}_", 1)
            else:
                name = f"{prefix}_{base_name}"
            self._export_table(table, os.path.join(dir_name, name), session_id)

        return has_data
