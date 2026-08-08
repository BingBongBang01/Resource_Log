import time
import uuid
import threading
from datetime import datetime

from config.settings import config
from storage.sqlite_writer import SQLiteWriter
from storage.database import Database

from collectors.cpu import CPUCollector
from collectors.memory import MemoryCollector
from collectors.storage import StorageCollector
from collectors.network import NetworkCollector
from collectors.process import ProcessCollector
from collectors.gpu import GPUCollector

class CollectorLoop:
    def __init__(self):
        self.running = False
        self.stop_event = threading.Event()
        self.thread = None
        self.error_callback = None
        self.consecutive_errors = 0
        self.run_id = None  # in-memory grouping id for this recording run

        self.db = Database()
        self.writer = SQLiteWriter(self.db)
        
        # Initialize collectors
        self.cpu_col = CPUCollector()
        self.mem_col = MemoryCollector()
        self.storage_col = StorageCollector()
        self.network_col = NetworkCollector()
        self.process_col = ProcessCollector()
        self.gpu_col = GPUCollector()
        
        # Warmup for intervals
        time.sleep(1)

    def start(self):
        if not self.running:
            self.running = True
            self.stop_event.clear()
            self.run_id = f"run_{uuid.uuid4().hex}"
            self.writer.start()
            self.sys_thread = threading.Thread(target=self._system_loop, daemon=True)
            self.proc_thread = threading.Thread(target=self._process_loop, daemon=True)
            self.gpu_thread = threading.Thread(target=self._gpu_loop, daemon=True)
            self.sys_thread.start()
            self.proc_thread.start()
            self.gpu_thread.start()

    def stop(self, timeout: float = 15.0):
        """Stop sampling and write everything still queued to the database.

        `timeout` is the total budget for draining; the Windows-shutdown
        path passes a smaller one because the OS kills us if we dawdle.
        """
        self.running = False
        self.stop_event.set()
        # The collector threads wake on stop_event immediately, so this only
        # ever costs real time when a sensor query (GPU/WMI) is mid-flight.
        join_timeout = max(0.5, min(2.0, timeout / 8.0))
        for attr in ("sys_thread", "proc_thread", "gpu_thread"):
            thread = getattr(self, attr, None)
            if thread:
                thread.join(timeout=join_timeout)
        self.run_id = None
        self.writer.stop(timeout=timeout)

    def save_and_stop(self, timeout: float = 15.0):
        """Everything that has to happen before this process may die.

        Called from every exit path — window close, Ctrl+C, Windows
        shutdown — via utils.shutdown, so it must be safe to run twice.
        """
        run_id = self.run_id
        was_recording = self.running

        self.stop(timeout=timeout)

        if was_recording and config.AUTO_EXPORT_ON_EXIT:
            self._export_session_csv(run_id)

    def _export_session_csv(self, run_id):
        """Drop a CSV copy of the run that just ended into the export folder.

        Only this run's rows are written: the database accumulates every
        session ever recorded, and re-dumping all of it on each exit would
        get slower every time the app is used.
        """
        import os
        from analyzer.report import CSVExporter
        from utils.logger import logger

        try:
            export_dir = config.EXPORT_DIRECTORY
            os.makedirs(export_dir, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = os.path.join(export_dir, f"system_log_{stamp}.csv")

            if CSVExporter(self.db).export_system_data(path, session_id=run_id):
                logger.info(f"Auto-exported session {run_id} to {path}")
            else:
                logger.info("Auto-export skipped: this run recorded no system data.")
        except Exception:
            logger.exception("Auto-export on exit failed")

    @staticmethod
    def _with_com(fn):
        """Run a collector loop with COM initialized on its own thread.
        WMI-backed sensors (GPU, CPU temperature) are apartment-bound and
        fail with RPC_E_WRONG_THREAD without this."""
        com_ready = False
        try:
            import pythoncom
            pythoncom.CoInitialize()
            com_ready = True
        except Exception:
            from utils.logger import logger
            logger.exception("CoInitialize failed; WMI-backed sensors may be unavailable")
        try:
            fn()
        finally:
            if com_ready:
                import pythoncom
                pythoncom.CoUninitialize()

    def _system_loop(self):
        self._with_com(self._run_system_loop)

    def _run_system_loop(self):
        system_interval = max(0.1, config.SYSTEM_COLLECTION_INTERVAL_MS / 1000.0)
        next_run = time.monotonic()

        while self.running:
            run_id = self.run_id
            timestamp = datetime.now().isoformat()

            sys_data = {
                "timestamp": timestamp,
                "session_id": run_id
            }

            error_msgs = []
            disk_collection = {}
            net_collection = {}

            if config.group_enabled("cpu"):
                try:
                    sys_data.update(self.cpu_col.collect())
                except Exception as e:
                    error_msgs.append(f"CPU: {str(e)}")

            if config.group_enabled("memory"):
                try:
                    sys_data.update(self.mem_col.collect())
                except Exception as e:
                    error_msgs.append(f"Memory: {str(e)}")

            log_fields = config.LOG_FIELDS
            loggable_sys_data = {
                k: v for k, v in sys_data.items()
                if k in ("timestamp", "session_id") or log_fields.get(k, True)
            }
            # Nothing but the bookkeeping keys left: skip the write entirely
            # rather than inserting an empty row every interval.
            if len(loggable_sys_data) > 2:
                self.writer.write_system_data(loggable_sys_data)

            try:
                disk_collection = self.storage_col.collect()
                # Only rows carrying new information; capacity figures are
                # refreshed once a minute, so re-inserting them every cycle
                # wrote far more disk rows than there was data to record.
                new_rows = disk_collection.get("new_rows")
                if new_rows:
                    self.writer.write_disk_data(run_id, timestamp, new_rows)
            except Exception as e:
                error_msgs.append(f"Storage: {str(e)}")

            try:
                net_collection = self.network_col.collect()
                if "networks" in net_collection:
                    self.writer.write_network_data(run_id, timestamp, net_collection["networks"])
            except Exception as e:
                error_msgs.append(f"Network: {str(e)}")

            try:
                self._collect_fps(run_id, timestamp)
            except Exception as e:
                error_msgs.append(f"FPS: {str(e)}")

            # Always publish to app_state: the overlay reads these values
            # directly and has to keep working while the main window is
            # minimised. AppState itself suppresses the expensive part —
            # notifying widget listeners — whenever the UI is hidden.
            from ui.state_manager import app_state

            update_dict = {
                "cpu_usage": sys_data.get("cpu_usage", 0.0),
                "cpu_freq": sys_data.get("cpu_freq_mhz", 0.0),
                "cpu_temp": sys_data.get("cpu_temperature"),
                "ram_total": sys_data.get("ram_total", 0.0),
                "ram_used": sys_data.get("ram_used", 0.0),
                "ram_available": sys_data.get("ram_available", 0.0),
                "ram_percent": sys_data.get("ram_usage_percent", 0.0),
                "commit_limit": sys_data.get("commit_limit", 0.0),
                "commit_used": sys_data.get("commit_used", 0.0),
                "commit_percent": sys_data.get("commit_usage_percent", 0.0),
                "pagefile_used": sys_data.get("pagefile_used", 0.0),
            }
            if "disks" in disk_collection:
                update_dict["storage_data"] = disk_collection["disks"]
            if "networks" in net_collection:
                update_dict["network_data"] = net_collection["networks"]

            app_state.update(update_dict)

            if not error_msgs:
                if self.consecutive_errors > 0 and self.error_callback:
                    self.error_callback(None)
                self.consecutive_errors = 0
            else:
                self.consecutive_errors += 1
                if self.error_callback and self.consecutive_errors >= 3:
                    self.error_callback(f"Collector errors ({self.consecutive_errors} times): {', '.join(error_msgs)}")
            
            # Read interval dynamically in case it's changed by UI
            system_interval = max(0.1, config.SYSTEM_COLLECTION_INTERVAL_MS / 1000.0)
            next_run += system_interval
            now = time.monotonic()
            
            # If we fell way behind (e.g. sleep/hibernate), reset next_run
            if now > next_run + system_interval:
                next_run = now + system_interval
                
            sleep_time = max(0, next_run - now)
            if self.stop_event.wait(sleep_time):
                break

    def _collect_fps(self, run_id, timestamp):
        """Record the frame rate of whatever RTSS is currently measuring.

        Reading RTSS's shared memory is cheap enough to sit inline here, and
        cheap enough to keep doing even when nothing is being logged — the
        live monitor still wants numbers to show. Nothing is written when no
        game is running, or an idle desktop would fill the table with rows
        that say nothing.
        """
        from providers.fps_provider import get_fps_provider
        from ui.state_manager import app_state

        apps = get_fps_provider().get_apps()
        app_state.set("fps_data", apps)

        if not apps or not config.group_enabled("fps"):
            return

        log_fields = config.LOG_FIELDS
        # The per-item checkboxes are the same ones the overlay offers, so an
        # unticked field is blanked rather than dropping the whole row.
        blanked = []
        for app in apps:
            row = dict(app)
            for field, column in (
                ("fps", "fps"), ("fps_avg", "fps_avg"), ("fps_min", "fps_min"),
                ("fps_max", "fps_max"), ("frame_time", "frame_time_ms"),
            ):
                if not log_fields.get(field, True):
                    row[column] = None
            blanked.append(row)

        self.writer.write_fps_data(run_id, timestamp, blanked)

    def _gpu_loop(self):
        """GPU sampling runs here, apart from the system loop.

        Windows' GPU performance counters take ~350ms to answer, which is
        longer than a typical sampling interval — collecting them inline
        dragged every CPU/RAM sample late by that much. On its own thread
        the cost overlaps the idle time between system samples instead.
        """
        self._with_com(self._run_gpu_loop)

    def _run_gpu_loop(self):
        next_run = time.monotonic()

        while self.running:
            interval = max(1.0, config.GPU_COLLECTION_INTERVAL_MS / 1000.0)

            # Unchecking every GPU item in the live monitor skips the query
            # altogether — this is the single biggest CPU saving available.
            if config.group_enabled("gpu"):
                try:
                    gpus = self.gpu_col.collect().get("gpus", [])

                    log_fields = config.LOG_FIELDS
                    loggable = []
                    for gpu in gpus:
                        g = dict(gpu)
                        for field in ("gpu_usage", "gpu_vram_used", "gpu_temperature"):
                            if not log_fields.get(field, True):
                                g[field] = None
                        loggable.append(g)

                    if loggable:
                        self.writer.write_gpu_data(self.run_id, datetime.now().isoformat(), loggable)

                    from ui.state_manager import app_state
                    app_state.set("gpu_data", gpus)
                except Exception:
                    from utils.logger import logger
                    logger.exception("GPU collector error")

            next_run += interval
            now = time.monotonic()
            if now > next_run + interval:
                next_run = now + interval
            if self.stop_event.wait(max(0, next_run - now)):
                break

    def _process_loop(self):
        process_interval = config.PROCESS_COLLECTION_INTERVAL
        next_run = time.monotonic() + 1.0 # Initial slight delay

        if self.stop_event.wait(1.0):
            return

        while self.running:
            try:
                run_id = self.run_id
                timestamp = datetime.now().isoformat()
                proc_data = self.process_col.collect()
                self.writer.write_process_data(run_id, timestamp, proc_data)

                from ui.state_manager import app_state
                app_state.update({"process_data": proc_data})
            except Exception as e:
                from utils.logger import logger
                logger.exception("Process collector error")
                
            process_interval = max(1.0, config.PROCESS_COLLECTION_INTERVAL)
            next_run += process_interval
            now = time.monotonic()
            
            if now > next_run + process_interval:
                next_run = now + process_interval
                
            sleep_time = max(0, next_run - now)
            if self.stop_event.wait(sleep_time):
                break
