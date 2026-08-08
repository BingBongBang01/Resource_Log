import re
import ctypes
import threading
from ctypes import wintypes
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from utils.logger import logger

# Adapters that aren't real, loggable hardware.
_VIRTUAL_ADAPTER_MARKERS = ("microsoft basic", "parsec", "remote display", "idd ", "virtual display")


def _is_virtual_adapter(name: str) -> bool:
    low = (name or "").lower()
    return any(marker in low for marker in _VIRTUAL_ADAPTER_MARKERS)


def _empty_gpu(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "gpu_usage": None,
        "gpu_vram_used": None,
        "gpu_vram_total": None,
        "gpu_temperature": None,
        "gpu_hotspot": None,
        "gpu_power": None,
    }


# --- DXGI adapter enumeration ---

class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class _DXGI_ADAPTER_DESC(ctypes.Structure):
    _fields_ = [
        ("Description", ctypes.c_wchar * 128),
        ("VendorId", ctypes.c_uint),
        ("DeviceId", ctypes.c_uint),
        ("SubSysId", ctypes.c_uint),
        ("Revision", ctypes.c_uint),
        ("DedicatedVideoMemory", ctypes.c_size_t),
        ("DedicatedSystemMemory", ctypes.c_size_t),
        ("SharedSystemMemory", ctypes.c_size_t),
        ("AdapterLuid", _LUID),
    ]


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


_DXGI_ERROR_NOT_FOUND = 0x887A0002


def _com_method(ptr, index, restype, *argtypes):
    """Fetch a COM vtable slot as a callable (no comtypes dependency)."""
    vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return proto(vtable[index])


def dxgi_adapters() -> List[Dict[str, Any]]:
    """Enumerate GPUs through DXGI.

    DXGI is the only public API that exposes each adapter's LUID, and the
    LUID is exactly what Windows' GPU performance counters key their
    instances on. Enumeration order and the counters' `phys_N` index do
    NOT line up (on many systems every adapter reports phys_0), so the
    LUID is the only reliable way to attribute usage/VRAM to a specific
    GPU on a multi-GPU machine. Works identically for Intel, AMD and
    NVIDIA, integrated or discrete.

    Returns a list of {"name", "luid", "vram_total"} ordered as DXGI
    reports them (adapter 0 is the system's preferred/primary GPU).
    """
    adapters = []
    dxgi = ctypes.WinDLL("dxgi")

    # EnumAdapters/GetDesc live on the base IDXGIFactory/IDXGIAdapter
    # interfaces, so the plain factory is enough. Some driver stacks refuse
    # IID_IDXGIFactory1 with E_NOINTERFACE, hence the base interface first.
    candidates = [
        ("CreateDXGIFactory", _GUID(
            0x7B7166EC, 0x21C7, 0x44AE,
            (ctypes.c_ubyte * 8)(0xB2, 0x1A, 0xC9, 0xAE, 0x32, 0x1A, 0xE3, 0x69))),
        ("CreateDXGIFactory1", _GUID(
            0x770AAE78, 0xF26F, 0x4DBB,
            (ctypes.c_ubyte * 8)(0xA9, 0x1D, 0xC7, 0x8C, 0x69, 0x88, 0x6A, 0x2B))),
    ]

    factory = ctypes.c_void_p()
    last_hr = 0
    for fn_name, iid in candidates:
        try:
            create = getattr(dxgi, fn_name)
        except AttributeError:
            continue
        create.restype = ctypes.c_long
        create.argtypes = [ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
        factory = ctypes.c_void_p()
        last_hr = create(ctypes.byref(iid), ctypes.byref(factory))
        if last_hr == 0 and factory:
            break

    if not factory:
        raise OSError(f"CreateDXGIFactory failed (hr=0x{last_hr & 0xFFFFFFFF:08X})")

    try:
        # IDXGIFactory::EnumAdapters is vtable slot 7.
        enum_adapters = _com_method(
            factory, 7, ctypes.HRESULT, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)
        )
        index = 0
        while True:
            adapter = ctypes.c_void_p()
            try:
                enum_adapters(factory, index, ctypes.byref(adapter))
            except OSError as e:
                # ctypes raises on failing HRESULTs; NOT_FOUND ends the walk.
                if (getattr(e, "winerror", 0) & 0xFFFFFFFF) == _DXGI_ERROR_NOT_FOUND:
                    break
                raise
            if not adapter:
                break

            try:
                # IDXGIAdapter::GetDesc is vtable slot 8.
                get_desc = _com_method(
                    adapter, 8, ctypes.HRESULT, ctypes.POINTER(_DXGI_ADAPTER_DESC)
                )
                desc = _DXGI_ADAPTER_DESC()
                get_desc(adapter, ctypes.byref(desc))

                luid_key = f"0x{desc.AdapterLuid.HighPart & 0xFFFFFFFF:08X}_0x{desc.AdapterLuid.LowPart:08X}"
                vram_total = desc.DedicatedVideoMemory / (1024 ** 3)
                adapters.append({
                    "name": desc.Description,
                    "luid": luid_key,
                    "vram_total": round(vram_total, 2) if vram_total >= 0.01 else None,
                })
            finally:
                release = _com_method(adapter, 2, ctypes.c_ulong)
                release(adapter)

            index += 1
    finally:
        release = _com_method(factory, 2, ctypes.c_ulong)
        release(factory)

    return adapters


# --- Backends ---

class SensorBackend(ABC):
    @abstractmethod
    def get_all_gpu_data(self) -> List[Dict[str, Any]]:
        pass


class LHMBackend(SensorBackend):
    """Fetches GPU sensor data using LibreHardwareMonitor WMI namespace.
    Only backend that can supply temperature / hotspot / power."""
    def __init__(self):
        self.available = False
        self.w = None
        try:
            import wmi
            self.w = wmi.WMI(namespace="root\\LibreHardwareMonitor")
            # Probe so we fail fast when the namespace exists but is empty.
            self.w.Hardware()
            self.available = True
        except Exception:
            logger.info("LibreHardwareMonitor not available; falling back to built-in GPU counters")

    def get_all_gpu_data(self) -> List[Dict[str, Any]]:
        results = []
        if not self.available:
            return results

        try:
            for hw in self.w.Hardware():
                if "gpu" not in hw.HardwareType.lower():
                    continue

                hw_name = hw.Name if hw.Name else "Unknown GPU"
                if _is_virtual_adapter(hw_name):
                    continue

                data = _empty_gpu(hw_name)

                for s in self.w.Sensor(Parent=hw.Identifier):
                    s_name = s.Name.lower()
                    s_type = s.SensorType.lower()
                    val = float(s.Value) if s.Value is not None else None
                    if val is None:
                        continue

                    if s_type == "load" and "core" in s_name:
                        data["gpu_usage"] = round(val, 1)
                    elif s_type == "temperature":
                        if "hot spot" in s_name or "hotspot" in s_name:
                            data["gpu_hotspot"] = round(val, 1)
                        elif "core" in s_name or "gpu" in s_name:
                            if data["gpu_temperature"] is None:
                                data["gpu_temperature"] = round(val, 1)
                    elif s_type == "power" and ("package" in s_name or "gpu" in s_name):
                        if data["gpu_power"] is None:
                            data["gpu_power"] = round(val, 1)
                    elif s_type in ("data", "smalldata"):
                        # LHM reports memory in MB.
                        if "memory used" in s_name:
                            data["gpu_vram_used"] = round(val / 1024, 2)
                        elif "memory total" in s_name:
                            data["gpu_vram_total"] = round(val / 1024, 2)

                results.append(data)

        except Exception:
            logger.exception("LHMBackend get_all_gpu_data encountered an error")

        return results


class PerfCounterBackend(SensorBackend):
    """Vendor-neutral backend using Windows' built-in GPU performance
    counters (Win32_PerfFormattedData_GPUPerformanceCounters_*). These ship
    with Windows 10/11 and work for Intel, AMD and NVIDIA — integrated or
    discrete — with no third-party software. Usage % and VRAM used are
    available this way (temperature/power are not).

    Per-GPU attribution is done by LUID, matching what Task Manager shows.
    """

    _LUID_RE = re.compile(r"luid_(0x[0-9A-Fa-f]+)_(0x[0-9A-Fa-f]+)")
    _ENGTYPE_RE = re.compile(r"engtype_(.+)$")

    # The GPU engine counter has one instance per process *per engine* —
    # ~800 of them on a normal desktop, and pulling them all costs 5+
    # seconds, which would stall the whole collection loop. Idle engines
    # report 0 and can't affect a max(), so filtering them out server-side
    # returns the same answer roughly 20x faster.
    _ENGINE_QUERY = (
        "SELECT Name, UtilizationPercentage "
        "FROM Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine "
        "WHERE UtilizationPercentage > 0"
    )

    def __init__(self):
        self.available = False
        self.w = None
        try:
            import wmi
            self.w = wmi.WMI()
            # Probe once so we fail fast (and fall back) if these classes
            # aren't present on this Windows build.
            self.w.query(self._ENGINE_QUERY)
            self.available = True
        except Exception:
            logger.info("GPU performance counters unavailable on this system")

    @staticmethod
    def _normalize_luid(high: str, low: str) -> str:
        return f"0x{int(high, 16):08X}_0x{int(low, 16):08X}"

    @staticmethod
    def _registry_vram_totals():
        """Fallback VRAM totals when DXGI is unavailable. AdapterRAM on
        Win32_VideoController is a 32-bit field and wraps around for cards
        with >=4GB VRAM; the real 64-bit size lives in the driver's
        registry key, keyed by DriverDesc (same string as the WMI Name)."""
        totals = {}
        try:
            import winreg
            base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as class_key:
                i = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(class_key, i)
                    except OSError:
                        break
                    i += 1
                    try:
                        with winreg.OpenKey(class_key, sub_name) as sub_key:
                            desc = winreg.QueryValueEx(sub_key, "DriverDesc")[0]
                            size = winreg.QueryValueEx(sub_key, "HardwareInformation.qwMemorySize")[0]
                            totals[desc] = round(int(size) / (1024 ** 3), 2)
                    except OSError:
                        continue
        except Exception:
            logger.exception("PerfCounterBackend failed to read VRAM size from registry")
        return totals

    def _adapters(self):
        """Real (non-virtual) adapters with a LUID and VRAM total.

        DXGI is preferred because it gives the LUID needed to attribute
        counters per GPU. If it fails we fall back to WMI + registry, which
        still enumerates every GPU but can't split the counters apart.
        """
        try:
            adapters = [a for a in dxgi_adapters() if not _is_virtual_adapter(a["name"])]
            if adapters:
                return adapters
        except Exception:
            logger.exception("DXGI adapter enumeration failed; falling back to WMI")

        adapters = []
        registry_totals = self._registry_vram_totals()
        try:
            for gpu in self.w.Win32_VideoController():
                name = gpu.Name or "Unknown GPU"
                if _is_virtual_adapter(name):
                    continue
                vram_total = registry_totals.get(name)
                if vram_total is None and gpu.AdapterRAM:
                    raw = abs(int(gpu.AdapterRAM))
                    # 32-bit wraparound sentinel: ignore obviously-wrong values.
                    vram_total = round(raw / (1024 ** 3), 2) if raw < 4 * 1024 ** 3 else None
                adapters.append({"name": name, "luid": None, "vram_total": vram_total})
        except Exception:
            logger.exception("PerfCounterBackend failed to enumerate video controllers")
        return adapters

    def _usage_by_luid(self) -> Dict[str, float]:
        """GPU utilization per adapter, computed the way Task Manager does:
        sum each engine type across all processes, then take the busiest
        engine type. Summing every engine instead would double-count a
        GPU that's using 3D, copy and video engines at once."""
        per_engine: Dict[str, Dict[str, float]] = {}
        try:
            for engine in self.w.query(self._ENGINE_QUERY):
                name = engine.Name or ""
                m = self._LUID_RE.search(name)
                if not m:
                    continue
                luid = self._normalize_luid(m.group(1), m.group(2))

                eng_match = self._ENGTYPE_RE.search(name)
                engtype = eng_match.group(1) if eng_match else "unknown"

                util = float(engine.UtilizationPercentage or 0)
                bucket = per_engine.setdefault(luid, {})
                bucket[engtype] = bucket.get(engtype, 0.0) + util
        except Exception:
            logger.exception("PerfCounterBackend failed to read GPUEngine counters")

        return {
            luid: min(max(engines.values()), 100.0) if engines else 0.0
            for luid, engines in per_engine.items()
        }

    def _vram_by_luid(self) -> Dict[str, float]:
        """Dedicated VRAM in use per adapter, in GB. Mirrors Task Manager's
        "Dedicated GPU memory" figure."""
        vram = {}
        try:
            counters = self.w.Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory()
        except Exception:
            logger.exception("PerfCounterBackend failed to query GPUAdapterMemory counters")
            return vram

        for mem in counters:
            try:
                m = self._LUID_RE.search(mem.Name or "")
                if not m:
                    continue
                luid = self._normalize_luid(m.group(1), m.group(2))
                used_gb = float(mem.DedicatedUsage or 0) / (1024 ** 3)
                vram[luid] = vram.get(luid, 0.0) + used_gb
            except Exception:
                # Individual perf-counter instances can vanish mid-iteration
                # (they're created/destroyed as GPU memory contexts change).
                continue
        return vram

    def get_all_gpu_data(self) -> List[Dict[str, Any]]:
        results = []
        if not self.available:
            return results

        adapters = self._adapters()
        if not adapters:
            return results

        usage_by_luid = self._usage_by_luid()
        vram_by_luid = self._vram_by_luid()
        counted_luids = set(usage_by_luid) | set(vram_by_luid)

        # Some driver stacks expose one physical GPU through DXGI more than
        # once (a remote-desktop/virtual display driver borrowing the real
        # card's description, for instance). The clone never gets its own
        # perf-counter instances, so when a name repeats, keep the entry the
        # counters actually know about and drop the phantom.
        if counted_luids:
            by_name = {}
            order = []
            for adapter in adapters:
                name = adapter["name"]
                if name not in by_name:
                    by_name[name] = adapter
                    order.append(name)
                elif (adapter.get("luid") in counted_luids
                      and by_name[name].get("luid") not in counted_luids):
                    by_name[name] = adapter
            adapters = [by_name[name] for name in order]

        for adapter in adapters:
            data = _empty_gpu(adapter["name"])
            data["gpu_vram_total"] = adapter.get("vram_total")

            luid = adapter.get("luid")
            if luid is not None:
                if luid in usage_by_luid:
                    data["gpu_usage"] = round(usage_by_luid[luid], 1)
                elif luid in vram_by_luid:
                    # The engine query skips idle (0%) engines, so a GPU the
                    # counters clearly know about but that reported nothing
                    # is genuinely idle rather than unreadable.
                    data["gpu_usage"] = 0.0
                if luid in vram_by_luid:
                    data["gpu_vram_used"] = round(vram_by_luid[luid], 2)
            results.append(data)

        # No LUIDs available (DXGI failed): we can still report the machine's
        # total activity, but can't say which adapter it belongs to, so it
        # goes on the primary one rather than being silently dropped.
        if results and all(a.get("luid") is None for a in adapters):
            if usage_by_luid:
                results[0]["gpu_usage"] = round(min(sum(usage_by_luid.values()), 100.0), 1)
            if vram_by_luid:
                results[0]["gpu_vram_used"] = round(sum(vram_by_luid.values()), 2)

        return results


class WMIBackend(SensorBackend):
    """Last-resort backend: static name/VRAM info only, no live metrics."""
    def __init__(self):
        self.available = False
        self.w = None
        try:
            import wmi
            self.w = wmi.WMI()
            self.available = True
        except Exception:
            logger.exception("Failed to initialize WMIBackend")

    def get_all_gpu_data(self) -> List[Dict[str, Any]]:
        results = []

        # Prefer DXGI: it reports true 64-bit VRAM sizes, unlike WMI's
        # 32-bit AdapterRAM which wraps around on >=4GB cards.
        try:
            for adapter in dxgi_adapters():
                if _is_virtual_adapter(adapter["name"]):
                    continue
                data = _empty_gpu(adapter["name"])
                data["gpu_vram_total"] = adapter.get("vram_total")
                results.append(data)
            if results:
                return results
        except Exception:
            logger.exception("WMIBackend DXGI enumeration failed")

        if not self.available:
            return results

        try:
            for gpu in self.w.Win32_VideoController():
                name = gpu.Name if gpu.Name else "Unknown GPU"
                if _is_virtual_adapter(name):
                    continue
                data = _empty_gpu(name)
                if gpu.AdapterRAM:
                    raw = abs(int(gpu.AdapterRAM))
                    if raw < 4 * 1024 ** 3:
                        data["gpu_vram_total"] = round(raw / (1024 ** 3), 2)
                results.append(data)
        except Exception:
            logger.exception("WMIBackend get_all_gpu_data encountered an error")

        return results


# --- Providers ---

class MultiGPUProvider:
    def __init__(self, backend: SensorBackend):
        self.backend = backend
        self._wmi_fallback = None

    @property
    def wmi_fallback(self):
        if self._wmi_fallback is None:
            self._wmi_fallback = WMIBackend()
        return self._wmi_fallback

    def get_all_data(self) -> List[Dict[str, Any]]:
        try:
            data_list = self.backend.get_all_gpu_data()
        except Exception:
            logger.exception("GPU backend failed; trying WMI fallback")
            data_list = []

        # If no GPUs found, try fallback WMI
        if not data_list and not isinstance(self.backend, WMIBackend):
            data_list = self.wmi_fallback.get_all_gpu_data()

        # If the active backend missed vram_total on some GPUs, fill it in.
        if data_list and not isinstance(self.backend, WMIBackend):
            try:
                if any(gpu["gpu_vram_total"] is None for gpu in data_list):
                    wmi_data = self.wmi_fallback.get_all_gpu_data()
                    for gpu in data_list:
                        if gpu["gpu_vram_total"] is not None:
                            continue
                        for w_gpu in wmi_data:
                            a, b = gpu["name"].lower(), w_gpu["name"].lower()
                            if a in b or b in a:
                                gpu["gpu_vram_total"] = w_gpu["gpu_vram_total"]
                                break
            except Exception:
                logger.exception("MultiGPUProvider failed to backfill VRAM totals")

        return data_list


def get_multi_gpu_provider() -> MultiGPUProvider:
    """Build a provider using the richest backend available.

    IMPORTANT: the backends hold COM/WMI objects, which are apartment-bound.
    This must be called on the same thread that will consume the data (and
    that thread must have called pythoncom.CoInitialize), otherwise every
    query fails with RPC_E_WRONG_THREAD.

    LibreHardwareMonitor (if installed and running with its WMI provider
    enabled) gives the richest data: usage, VRAM, temperature, hotspot and
    power. It needs that external app though, so most installs fall back to
    Windows' own GPU performance counters, which give per-GPU usage % and
    VRAM used for any vendor with zero extra software. Last resort is plain
    WMI/DXGI, which only exposes static name/VRAM-total info.
    """
    lhm = LHMBackend()
    if lhm.available:
        backend = lhm
    else:
        perf = PerfCounterBackend()
        backend = perf if perf.available else WMIBackend()

    return MultiGPUProvider(backend)
