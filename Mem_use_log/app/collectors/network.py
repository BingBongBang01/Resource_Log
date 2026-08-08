import psutil
import time
from .base import BaseCollector
from typing import Dict, Any, List

class NetworkCollector(BaseCollector):
    def __init__(self):
        self.last_net = psutil.net_io_counters(pernic=True)
        self.last_time = time.time()

    def collect(self) -> Dict[str, Any]:
        current_net = psutil.net_io_counters(pernic=True)
        current_time = time.time()
        
        time_delta = current_time - self.last_time
        if time_delta == 0:
            time_delta = 1
            
        mb = 1024 * 1024
        
        # Get active status for interfaces
        if_stats = psutil.net_if_stats()
        
        networks = []
        
        if current_net:
            for nic_name, io_counters in current_net.items():
                # Filter out obvious Loopback interfaces to reduce noise
                nic_lower = nic_name.lower()
                if "loopback" in nic_lower or nic_lower == "lo":
                    continue
                    
                last_nic_io = self.last_net.get(nic_name)
                
                if last_nic_io:
                    bytes_recv = io_counters.bytes_recv - last_nic_io.bytes_recv
                    bytes_sent = io_counters.bytes_sent - last_nic_io.bytes_sent
                    
                    is_active = False
                    if nic_name in if_stats:
                        is_active = if_stats[nic_name].isup
                        
                    networks.append({
                        "name": nic_name,
                        "is_active": is_active,
                        "download_mbps": round((bytes_recv / mb) / time_delta, 2),
                        "upload_mbps": round((bytes_sent / mb) / time_delta, 2)
                    })
                    
        self.last_net = current_net
        self.last_time = current_time
        
        return {"networks": networks}
