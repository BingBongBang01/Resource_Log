from abc import ABC, abstractmethod
from typing import Tuple, Optional

class CPUTemperatureProvider(ABC):
    @abstractmethod
    def get_temperature(self) -> Tuple[Optional[float], str]:
        """Returns a tuple of (temperature_celsius, provider_name)."""
        pass

class LHMProvider(CPUTemperatureProvider):
    """Provider for LibreHardwareMonitor WMI endpoint."""
    def __init__(self):
        self.available = False
        try:
            import wmi
            self.w = wmi.WMI(namespace="root\\LibreHardwareMonitor")
            self.available = True
        except Exception:
            pass

    def get_temperature(self) -> Tuple[Optional[float], str]:
        if not self.available:
            return None, "LibreHardwareMonitor"
        try:
            sensors = self.w.Sensor(SensorType="Temperature")
            for sensor in sensors:
                name = sensor.Name.lower() if sensor.Name else ""
                # Prioritize CPU Package or Core
                if "cpu package" in name or "cpu core" in name:
                    return round(float(sensor.Value), 1), "LibreHardwareMonitor"
        except Exception:
            pass
        return None, "LibreHardwareMonitor"

class HWiNFOProvider(CPUTemperatureProvider):
    """Provider for HWiNFO Shared Memory (Requires specific memory struct parsing)."""
    def get_temperature(self) -> Tuple[Optional[float], str]:
        # Implementation left for future extension
        return None, "HWiNFO"

class WMIProvider(CPUTemperatureProvider):
    """Provider for standard WMI MSAcpi_ThermalZoneTemperature."""
    def __init__(self):
        self.available = False
        try:
            import wmi
            self.w = wmi.WMI(namespace="root\\wmi")
            self.available = True
        except Exception:
            pass

    def get_temperature(self) -> Tuple[Optional[float], str]:
        if not self.available:
            return None, "WMI (ACPI)"
        try:
            temperature_info = self.w.MSAcpi_ThermalZoneTemperature()
            if temperature_info and len(temperature_info) > 0:
                temp_k = temperature_info[0].CurrentTemperature / 10.0
                return round(temp_k - 273.15, 1), "WMI (ACPI)"
        except Exception:
            pass
        return None, "WMI (ACPI)"

class UnsupportedProvider(CPUTemperatureProvider):
    def get_temperature(self) -> Tuple[Optional[float], str]:
        return None, "Unsupported"

def get_cpu_temp_provider() -> CPUTemperatureProvider:
    # 1. Try LibreHardwareMonitor first (most accurate if running)
    lhm = LHMProvider()
    if lhm.available:
        temp, _ = lhm.get_temperature()
        if temp is not None:
            return lhm
            
    # 2. Try HWiNFO
    hw = HWiNFOProvider()
    temp, _ = hw.get_temperature()
    if temp is not None:
        return hw
        
    # 3. Fallback to generic WMI ACPI
    wmi_prov = WMIProvider()
    if wmi_prov.available:
        temp, _ = wmi_prov.get_temperature()
        if temp is not None:
            return wmi_prov
            
    return UnsupportedProvider()
