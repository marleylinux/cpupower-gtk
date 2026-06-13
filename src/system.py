"""Hardware state querying (AC/battery, CPU clocks, CPU temperature, model name, and CPU ticks)"""
import os
import re
import logging

log = logging.getLogger(__name__)


def is_on_ac_power() -> bool:
    """Check if the system is running on AC power"""
    has_mains = False
    try:
        if os.path.exists("/sys/class/power_supply"):
            for name in os.listdir("/sys/class/power_supply"):
                base = f"/sys/class/power_supply/{name}"
                type_path = f"{base}/type"
                if os.path.exists(type_path):
                    try:
                        with open(type_path, "r") as f:
                            psu_type = f.read().strip().lower()
                        if psu_type != "mains":
                            continue
                    except Exception:
                        continue
                else:
                    name_lower = name.lower()
                    if not (
                        name_lower.startswith("ac")
                        or name_lower.startswith("adp")
                        or "charger" in name_lower
                    ):
                        continue
                has_mains = True
                online_path = f"{base}/online"
                if os.path.exists(online_path):
                    try:
                        with open(online_path, "r") as f:
                            if f.read().strip() == "1":
                                return True
                    except Exception:
                        pass
    except Exception as e:
        log.debug("Failed to check AC power supply: %s", e)
    return not has_mains


def get_live_cpu_clocks() -> list[float]:
    """Get live frequencies of all CPU cores in MHz"""
    freqs = []
    try:
        base_dir = "/sys/devices/system/cpu"
        if os.path.exists(base_dir):
            cpu_dirs = sorted(
                [d for d in os.listdir(base_dir) if re.match(r"^cpu\d+$", d)],
                key=lambda x: int(x[3:])
            )
            for cpu in cpu_dirs:
                path = f"{base_dir}/{cpu}/cpufreq/scaling_cur_freq"
                if os.path.exists(path):
                    try:
                        with open(path, "r") as f:
                            khz = float(f.read().strip())
                            freqs.append(khz / 1000.0)
                    except Exception:
                        pass
    except Exception as e:
        log.debug("Failed to read scaling_cur_freq: %s", e)

    if not freqs:
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.strip().startswith("cpu MHz"):
                        try:
                            mhz = float(line.split(":", 1)[1].strip())
                            freqs.append(mhz)
                        except ValueError:
                            pass
        except Exception:
            pass
    return freqs


def get_live_cpu_clock_avg() -> float | None:
    """Get average CPU frequency in MHz"""
    clocks = get_live_cpu_clocks()
    if clocks:
        return sum(clocks) / len(clocks)
    return None


def get_cpu_temperature() -> float | None:
    """Find CPU temperature from k10temp, coretemp, acpitz, or fallback thermal zones"""
    try:
        hwmon_dir = "/sys/class/hwmon"
        if os.path.exists(hwmon_dir):
            for name in sorted(os.listdir(hwmon_dir)):
                path = f"{hwmon_dir}/{name}"
                name_file = f"{path}/name"
                if os.path.exists(name_file):
                    try:
                        with open(name_file, "r") as f:
                            sensor_name = f.read().strip().lower()
                        if sensor_name in ("k10temp", "coretemp", "zenpower"):
                            for tfile in ("temp1_input", "temp2_input", "temp3_input"):
                                tpath = f"{path}/{tfile}"
                                if os.path.exists(tpath):
                                    with open(tpath, "r") as tf:
                                        val = float(tf.read().strip())
                                        return val / 1000.0
                    except Exception:
                        pass

            for name in sorted(os.listdir(hwmon_dir)):
                path = f"{hwmon_dir}/{name}"
                name_file = f"{path}/name"
                if os.path.exists(name_file):
                    try:
                        with open(name_file, "r") as f:
                            sensor_name = f.read().strip().lower()
                        if "acpitz" in sensor_name or "cpu" in sensor_name:
                            tpath = f"{path}/temp1_input"
                            if os.path.exists(tpath):
                                with open(tpath, "r") as tf:
                                    return float(tf.read().strip()) / 1000.0
                    except Exception:
                        pass

        thermal_dir = "/sys/class/thermal"
        if os.path.exists(thermal_dir):
            for name in sorted(os.listdir(thermal_dir)):
                if name.startswith("thermal_zone"):
                    type_file = f"{thermal_dir}/{name}/type"
                    temp_file = f"{thermal_dir}/{name}/temp"
                    if os.path.exists(type_file) and os.path.exists(temp_file):
                        try:
                            with open(type_file, "r") as tf:
                                ttype = tf.read().strip().lower()
                            if "acpi" in ttype or "cpu" in ttype or "soc" in ttype:
                                with open(temp_file, "r") as tempf:
                                    return float(tempf.read().strip()) / 1000.0
                        except Exception:
                            pass
    except Exception as e:
        log.debug("Failed to read CPU temperature: %s", e)
    return None


def get_cpu_usage_ticks() -> dict:
    """Read CPU time ticks from /proc/stat for load calculations"""
    ticks = {}
    try:
        if os.path.exists("/proc/stat"):
            with open("/proc/stat", "r") as f:
                for line in f:
                    if line.startswith("cpu"):
                        parts = line.split()
                        name = parts[0]
                        # Sum: user, nice, system, idle, iowait, irq, softirq, steal
                        vals = [float(x) for x in parts[1:9]]
                        total = sum(vals)
                        idle = vals[3] + vals[4]  # idle + iowait
                        ticks[name] = {"total": total, "idle": idle}
    except Exception as e:
        log.debug("Failed to read /proc/stat ticks: %s", e)
    return ticks
