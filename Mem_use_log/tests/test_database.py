import unittest
import os
import sqlite3
from app.storage.database import Database

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_data.db"
        self.db = Database(self.db_path)
        
    def tearDown(self):
        self.db.get_connection().close()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except:
                pass
                
    def test_initialization(self):
        self.assertTrue(os.path.exists(self.db_path))
        
    def test_schema_created(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cursor.fetchall()]
            
            self.assertIn("system_data", tables)
            self.assertIn("process_data", tables)
            self.assertIn("metadata", tables)

if __name__ == '__main__':
    unittest.main()
