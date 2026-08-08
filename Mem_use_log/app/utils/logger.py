import logging
import os
from logging.handlers import RotatingFileHandler

from utils.paths import PROJECT_ROOT

def setup_logger():
    log_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "application.log")

    logger = logging.getLogger("SystemMonitor")
    
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Max 5MB per file, keep 3 backups
        handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
        
    return logger

logger = setup_logger()
