#!/usr/bin/env python3
"""Backend CPU controller interface for cpupower-gtk"""
import os
import sys
import re
import json
import logging
import shutil
import glob
import subprocess
import time
from settings import SYSTEM_CONFIG_FILES

log = logging.getLogger(__name__)


def is_cpupower_installed() -> bool:
    """Check if cpupower command is installed on the system"""
    return shutil.which("cpupower") is not None


def get_cpu_capabilities() -> dict:
    """Read CPU scaling capabilities and limits from sysfs"""
    caps = {
        "scaling_driver": "Unknown",
        "governors": [],
        "current_governor": "",
        "epp_available": False,
        "epp_preferences": [],
        "current_epp": "",
        "epb_available": False,
        "current_epb": None,
        "cpuinfo_min": 0.0,
        "cpuinfo_max": 0.0,
        "scaling_min": 0.0,
        "scaling_max": 0.0,
        "boost_supported": False,
        "boost_active": False,
    }

    def read_sysfs(path: str) -> str:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return f.read().strip()
            except Exception:
                pass
        return ""

    policy0 = "/sys/devices/system/cpu/cpufreq/policy0"
    if os.path.exists(policy0):
        caps["scaling_driver"] = read_sysfs(f"{policy0}/scaling_driver") or "Unknown"
        
        govs = read_sysfs(f"{policy0}/scaling_available_governors")
        caps["governors"] = govs.split() if govs else []
        caps["current_governor"] = read_sysfs(f"{policy0}/scaling_governor")

        # EPP (Energy Performance Preference)
        epp_path = f"{policy0}/energy_performance_preference"
        if os.path.exists(epp_path):
            caps["epp_available"] = True
            epp_avail_path = f"{policy0}/energy_performance_available_preferences"
            epps_list = []
            if os.path.exists(epp_avail_path):
                epps = read_sysfs(epp_avail_path)
                epps_list = epps.split() if epps else []
            
            standard_epps = ["default", "performance", "balance_performance", "balance_power", "power"]
            for item in standard_epps:
                if item not in epps_list:
                    epps_list.append(item)
            
            caps["epp_preferences"] = epps_list
            caps["current_epp"] = read_sysfs(epp_path)

        # Frequencies (convert kHz to MHz)
        def read_freq(name: str) -> float:
            val = read_sysfs(f"{policy0}/{name}")
            try:
                return float(val) / 1000.0 if val else 0.0
            except ValueError:
                return 0.0

        caps["cpuinfo_min"] = read_freq("cpuinfo_min_freq")
        caps["cpuinfo_max"] = read_freq("cpuinfo_max_freq")
        caps["scaling_min"] = read_freq("scaling_min_freq")
        caps["scaling_max"] = read_freq("scaling_max_freq")

    # EPB (Intel Energy Performance Bias)
    epb_path = "/sys/devices/system/cpu/cpu0/power/energy_perf_bias"
    if os.path.exists(epb_path):
        caps["epb_available"] = True
        try:
            val = read_sysfs(epb_path)
            if val.isdigit():
                caps["current_epb"] = int(val)
        except Exception:
            pass

    # Boost (AMD/Intel cpufreq boost)
    boost_path = "/sys/devices/system/cpu/cpufreq/boost"
    if os.path.exists(boost_path):
        caps["boost_supported"] = True
        caps["boost_active"] = (read_sysfs(boost_path) == "1")
    else:
        no_turbo_path = "/sys/devices/system/cpu/intel_pstate/no_turbo"
        if os.path.exists(no_turbo_path):
            caps["boost_supported"] = True
            caps["boost_active"] = (read_sysfs(no_turbo_path) == "0")

    return caps


def _direct_write(pattern: str, data: str) -> bool:
    """Directly write data to files matching pattern (requires running as root).
    Returns True if files were found and at least one write succeeded.
    """
    try:
        paths = glob.glob(pattern)
        if not paths:
            return False
        
        any_success = False
        for path in paths:
            success = False
            for _ in range(5):
                try:
                    with open(path, "w") as f:
                        f.write(data.strip() + "\n")
                    success = True
                    any_success = True
                    break
                except OSError as e:
                    if getattr(e, 'errno', None) == 16:  # EBUSY
                        time.sleep(0.1)
                        continue
                    break
                except Exception:
                    break
        return any_success
    except Exception:
        return False


def _write_single(path: str, data: str) -> bool:
    """Write data directly to a single known sysfs file (no glob, requires root).
    Use this instead of _direct_write when the path is a concrete file, not a pattern.
    """
    try:
        success = False
        for _ in range(5):
            try:
                with open(path, "w") as f:
                    f.write(data.strip() + "\n")
                success = True
                break
            except OSError as e:
                if getattr(e, 'errno', None) == 16:  # EBUSY
                    time.sleep(0.1)
                    continue
                break
            except Exception:
                break
        return success
    except Exception:
        return False


def parse_freq_to_mhz(v: str) -> float | None:
    """Parse custom frequency string (e.g. 2GHz, 2000MHz, 2000000kHz) to MHz float"""
    m = re.match(r"^([\d\.]+)\s*(Hz|kHz|MHz|GHz|THz)?$", v.strip(), re.IGNORECASE)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "kHz").lower()
    if unit == "hz":
        return val / 1000000.0
    elif unit == "khz":
        return val / 1000.0
    elif unit == "mhz":
        return val
    elif unit == "ghz":
        return val * 1000.0
    elif unit == "thz":
        return val * 1000000.0
    return val / 1000.0


def parse_cpupower_config(path: str) -> dict:
    """Parse bash-style cpupower configuration variables into settings dict"""
    settings = {}
    if not os.path.exists(path):
        return settings
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k == "GOVERNOR":
                        settings["governor"] = v
                    elif k == "MIN_FREQ":
                        val = parse_freq_to_mhz(v)
                        if val is not None:
                            settings["min_freq"] = val
                    elif k == "MAX_FREQ":
                        val = parse_freq_to_mhz(v)
                        if val is not None:
                            settings["max_freq"] = val
                    elif k == "FREQ":
                        val = parse_freq_to_mhz(v)
                        if val is not None:
                            settings["fixed_freq"] = val
                            settings["use_fixed_freq"] = True
                    elif k == "EPP":
                        settings["epp"] = v
                    elif k == "PERF_BIAS":
                        try:
                            settings["epb"] = int(v)
                        except ValueError:
                            pass
                    elif k == "BOOST":
                        settings["boost"] = (v == "1" or v.lower() == "true")
    except Exception as e:
        log.error("Failed to parse config %s: %s", path, e)
    return settings


def write_cpupower_config(settings: dict) -> None:
    """Write configuration settings to the official system files in bash script format"""
    lines = [
        "# SPDX-License-Identifier: GPL-2.0-or-later",
        "# Configuration file for cpupower.service",
        "# Generated automatically by cpupower-gtk",
        ""
    ]
    
    gov = settings.get("governor")
    if gov:
        lines.append(f"GOVERNOR='{gov}'")
        
    use_fixed = settings.get("use_fixed_freq", False)
    fixed_freq = settings.get("fixed_freq")
    
    if use_fixed and fixed_freq is not None:
        lines.append(f"FREQ='{int(fixed_freq * 1000)}kHz'")
    else:
        min_freq = settings.get("min_freq")
        if min_freq is not None:
            lines.append(f"MIN_FREQ='{int(min_freq * 1000)}kHz'")
            
        max_freq = settings.get("max_freq")
        if max_freq is not None:
            lines.append(f"MAX_FREQ='{int(max_freq * 1000)}kHz'")
        
    epp = settings.get("epp")
    if epp:
        lines.append(f"EPP='{epp}'")
        
    epb = settings.get("epb")
    if epb is not None:
        lines.append(f"PERF_BIAS='{int(epb)}'")

    boost = settings.get("boost")
    if boost is not None:
        lines.append(f"BOOST='{1 if boost else 0}'")
        
    content = "\n".join(lines) + "\n"
    
    for path in SYSTEM_CONFIG_FILES:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            log.info("Wrote system settings to %s", path)
        except Exception as e:
            log.error("Failed to write system settings to %s: %s", path, e)


def apply_settings(settings: dict, save: bool = True) -> tuple[bool, str]:
    """Apply power configuration. Must be run as root (normally via pkexec)"""
    if os.geteuid() != 0:
        return False, "Permission denied: must be run as root."

    if not settings:
        return False, "No settings to apply."

    caps = get_cpu_capabilities()
    
    # 1. Apply Governor, min frequency, max frequency, or fixed frequency
    cpupower_args = []
    
    use_fixed = settings.get("use_fixed_freq", False)
    fixed_freq = settings.get("fixed_freq")
    
    if use_fixed and fixed_freq is not None:
        fixed_freq_val = float(fixed_freq)
        if caps["cpuinfo_max"] > 0:
            fixed_freq_val = max(caps["cpuinfo_min"], min(caps["cpuinfo_max"], fixed_freq_val))
        cpupower_args = ["-f", f"{int(fixed_freq_val * 1000)}kHz"]
    else:
        governor = settings.get("governor")
        if governor and governor in caps["governors"]:
            cpupower_args += ["-g", governor]

        # Min freq: if specified, use it. If not, reset to cpuinfo_min (hardware default)
        min_freq = settings.get("min_freq")
        if min_freq is not None:
            min_freq_val = float(min_freq)
        else:
            min_freq_val = caps["cpuinfo_min"]
        if min_freq_val > 0.0:
            cpupower_args += ["-d", f"{int(min_freq_val * 1000)}kHz"]

        # Max freq: if specified, use it. If not, reset to cpuinfo_max (hardware default)
        max_freq = settings.get("max_freq")
        if max_freq is not None:
            max_freq_val = float(max_freq)
        else:
            max_freq_val = caps["cpuinfo_max"]
        if max_freq_val > 0.0:
            cpupower_args += ["-u", f"{int(max_freq_val * 1000)}kHz"]

    cpupower_ok = True
    cpupower_msg = ""
    if cpupower_args:
        cmd = ["cpupower", "frequency-set"] + cpupower_args
        print(f"[cpupower-gtk] Executing: {' '.join(cmd)}")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode != 0:
                cpupower_ok = False
                cpupower_msg = (res.stderr or res.stdout or "cpupower frequency-set failed").strip()
                
                # Fallback to direct sysfs writes (fixes EBUSY race condition on shared policies)
                log.info("cpupower frequency-set failed. Falling back to direct sysfs writes.")
                fallback_ok = True
                policy_dir = "/sys/devices/system/cpu/cpufreq/policy*"
                
                if use_fixed and fixed_freq is not None:
                    if not _direct_write(f"{policy_dir}/scaling_setspeed", str(int(fixed_freq_val * 1000))):
                        fallback_ok = False
                else:
                    # Write max first to avoid EINVAL if new min > current max
                    if max_freq_val > 0.0:
                        _direct_write(f"{policy_dir}/scaling_max_freq", str(int(max_freq_val * 1000)))
                    if min_freq_val > 0.0:
                        if not _direct_write(f"{policy_dir}/scaling_min_freq", str(int(min_freq_val * 1000))):
                            fallback_ok = False
                    if max_freq_val > 0.0:
                        if not _direct_write(f"{policy_dir}/scaling_max_freq", str(int(max_freq_val * 1000))):
                            fallback_ok = False
                            
                    governor = settings.get("governor")
                    if governor and governor in caps["governors"]:
                        if not _direct_write(f"{policy_dir}/scaling_governor", governor):
                            fallback_ok = False
                            
                if fallback_ok:
                    cpupower_ok = True
                    cpupower_msg = ""
        except Exception as e:
            cpupower_ok = False
            cpupower_msg = str(e)

    # 2. Apply Boost
    boost_ok = True
    boost_msg = ""
    boost = settings.get("boost")
    if boost is not None and caps["boost_supported"]:
        boost_val = "1" if boost else "0"
        cmd = ["cpupower", "set", "--boost", boost_val]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                # Direct write fallback (single known paths — use _write_single, not glob)
                boost_path = "/sys/devices/system/cpu/cpufreq/boost"
                if os.path.exists(boost_path):
                    if not _write_single(boost_path, boost_val):
                        boost_ok = False
                        boost_msg = "Failed to toggle AMD boost in sysfs."
                else:
                    no_turbo_path = "/sys/devices/system/cpu/intel_pstate/no_turbo"
                    if os.path.exists(no_turbo_path):
                        intel_boost_val = "0" if boost else "1"
                        if not _write_single(no_turbo_path, intel_boost_val):
                            boost_ok = False
                            boost_msg = "Failed to toggle Intel no_turbo in sysfs."
        except Exception as e:
            boost_ok = False
            boost_msg = str(e)

    # 3. Apply EPP
    epp_ok = True
    epp_msg = ""
    epp = settings.get("epp")
    if epp and caps["epp_available"]:
        cmd = ["cpupower", "set", "-e", epp]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                epp_policy_pattern = "/sys/devices/system/cpu/cpufreq/policy*/energy_performance_preference"
                if not _direct_write(epp_policy_pattern, epp):
                    epp_pattern = "/sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference"
                    if not _direct_write(epp_pattern, epp):
                        epp_ok = False
                        epp_msg = "Failed to write energy_performance_preference via sysfs."
        except Exception as e:
            epp_ok = False
            epp_msg = str(e)

    # 4. Apply EPB
    epb_ok = True
    epb_msg = ""
    epb = settings.get("epb")
    if epb is not None and caps["epb_available"]:
        epb_val = str(int(epb))
        cmd = ["cpupower", "set", "-b", epb_val]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                epb_pattern = "/sys/devices/system/cpu/cpu*/power/energy_perf_bias"
                if not _direct_write(epb_pattern, epb_val):
                    epb_ok = False
                    epb_msg = "Failed to write energy_perf_bias via sysfs."
        except Exception as e:
            epb_ok = False
            epb_msg = str(e)

    # Check overall status
    overall_ok = cpupower_ok
    if overall_ok:
        if save:
            write_cpupower_config(settings)
        
        warn_msgs = [m for m in (boost_msg, epp_msg, epb_msg) if m]
        if warn_msgs:
            warn_str = " | Warnings: " + " ".join(warn_msgs)
            return True, "Settings applied." + warn_str
        return True, "Settings applied successfully."
    else:
        msgs = [m for m in (cpupower_msg, boost_msg, epp_msg, epb_msg) if m]
        return False, "\n".join(msgs)


def get_preset_settings(preset: str, caps: dict) -> dict:
    """Generate settings dict for a given preset based on CPU capabilities"""
    settings = {}
    phy_min = caps.get("cpuinfo_min", 0.0)
    if phy_min <= 0.0:
        phy_min = 600.0
        
    phy_max = caps.get("cpuinfo_max", 0.0)
    if phy_max <= 0.0:
        phy_max = 3000.0

    if preset == "power-saving":
        govs = caps.get("governors", [])
        if "powersave" in govs:
            settings["governor"] = "powersave"
        elif "conservative" in govs:
            settings["governor"] = "conservative"

        if caps.get("epp_available"):
            epps = caps.get("epp_preferences", [])
            if "power" in epps:
                settings["epp"] = "power"
            elif "balance_power" in epps:
                settings["epp"] = "balance_power"

        if caps.get("epb_available"):
            settings["epb"] = 15

        if caps.get("boost_supported"):
            settings["boost"] = False

        settings["min_freq"] = float(phy_min)
        settings["max_freq"] = float(phy_min + (phy_max - phy_min) * 0.3)

    elif preset == "balanced":
        govs = caps.get("governors", [])
        if "schedutil" in govs:
            settings["governor"] = "schedutil"
        elif "ondemand" in govs:
            settings["governor"] = "ondemand"
        elif "powersave" in govs:
            settings["governor"] = "powersave"

        if caps.get("epp_available"):
            epps = caps.get("epp_preferences", [])
            if "balance_performance" in epps:
                settings["epp"] = "balance_performance"
            elif "default" in epps:
                settings["epp"] = "default"

        if caps.get("epb_available"):
            settings["epb"] = 6

        if caps.get("boost_supported"):
            settings["boost"] = True

        settings["min_freq"] = float(phy_min)
        settings["max_freq"] = float(phy_max)

    elif preset == "max-performance":
        govs = caps.get("governors", [])
        if "performance" in govs:
            settings["governor"] = "performance"

        if caps.get("epp_available"):
            epps = caps.get("epp_preferences", [])
            if "performance" in epps:
                settings["epp"] = "performance"

        if caps.get("epb_available"):
            settings["epb"] = 0

        if caps.get("boost_supported"):
            settings["boost"] = True

        settings["min_freq"] = float(phy_max * 0.8)
        settings["max_freq"] = float(phy_max)

    return settings


if __name__ == "__main__":
    # Handle Boot / Sleep Apply — prefer user JSON/auto-switch (authoritative), fallback to bash config
    if len(sys.argv) > 1 and sys.argv[1] == "--apply-saved":
        settings = {}

        # 1. Try user configurations first.
        # When running as root under systemd, HOME=/root and SUDO_USER is unset.
        # We scan all real user homes (UID >= 1000) for settings/ui configurations.
        import pwd
        candidates = []

        # Check env vars set by sudo/pkexec in case this is called interactively
        for env_key in ("SUDO_USER", "PKEXEC_UID"):
            val = os.environ.get(env_key)
            if val:
                try:
                    if val.isdigit():
                        entry = pwd.getpwuid(int(val))
                    else:
                        entry = pwd.getpwnam(val)
                    candidates.insert(0, entry.pw_dir)
                except Exception:
                    pass

        # Also scan all system users with UID >= 1000 (real human accounts)
        for entry in pwd.getpwall():
            if entry.pw_uid >= 1000 and entry.pw_dir not in candidates:
                candidates.append(entry.pw_dir)

        caps = get_cpu_capabilities()
        for home in candidates:
            # Check for auto_switch configuration
            ui_config = os.path.join(home, ".config/cpupower-gtk/ui.json")
            if os.path.exists(ui_config):
                try:
                    with open(ui_config, "r") as f:
                        ui_settings = json.load(f)
                    if ui_settings.get("auto_switch", False):
                        import system
                        is_ac = system.is_on_ac_power()
                        profile_key = "ac_profile" if is_ac else "battery_profile"
                        profile_name = ui_settings.get(profile_key, "")
                        if profile_name:
                            if profile_name == "__power_saving__":
                                settings = get_preset_settings("power-saving", caps)
                                log.info("Auto-switch enabled: resolved to Power Saving preset (is_ac=%s)", is_ac)
                                break
                            elif profile_name == "__max_performance__":
                                settings = get_preset_settings("max-performance", caps)
                                log.info("Auto-switch enabled: resolved to Max Performance preset (is_ac=%s)", is_ac)
                                break
                            else:
                                profiles_path = os.path.join(home, ".config/cpupower-gtk/profiles.json")
                                if os.path.exists(profiles_path):
                                    with open(profiles_path, "r") as pf:
                                        profiles = json.load(pf)
                                    if profile_name in profiles:
                                        settings = profiles[profile_name]
                                        log.info("Auto-switch enabled: resolved to profile '%s' (is_ac=%s)", profile_name, is_ac)
                                        break
                except Exception as e:
                    log.warning("Failed to resolve auto-switch profile in %s: %s", home, e)

            # Fallback to standard settings.json
            path = os.path.join(home, ".config/cpupower-gtk/settings.json")
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        settings = json.load(f)
                    log.info("Loaded user settings from %s", path)
                    break
                except Exception as e:
                    log.warning("Failed to read user JSON settings in %s: %s", home, e)

        # 2. If no user config resolved, fall back to system bash config files
        if not settings:
            for path in SYSTEM_CONFIG_FILES:
                if os.path.exists(path):
                    settings = parse_cpupower_config(path)
                    if settings:
                        log.info("Loaded settings from bash config %s", path)
                        break

        if settings:
            ok, msg = apply_settings(settings, save=False)
            if ok:
                print("Successfully applied saved CPU power settings.")
                sys.exit(0)
            else:
                print(f"Failed to apply settings: {msg}", file=sys.stderr)
                sys.exit(1)
        else:
            print("No active cpupower config file variables resolved.", file=sys.stderr)
            sys.exit(0)

    # Handle Elevated Apply from User config path
    elif len(sys.argv) > 2 and sys.argv[1] == "--apply-user-config":
        user_config_path = sys.argv[2]
        if os.path.exists(user_config_path):
            try:
                with open(user_config_path, "r") as f:
                    settings = json.load(f)
                if settings:
                    ok, msg = apply_settings(settings, save=True)
                    if ok:
                        print("SUCCESS: Settings applied successfully.")
                        sys.exit(0)
                    else:
                        print(f"ERROR: {msg}", file=sys.stderr)
                        sys.exit(1)
            except Exception as e:
                print(f"ERROR: Failed to apply user config: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"ERROR: Config path {user_config_path} does not exist.", file=sys.stderr)
            sys.exit(1)
            
    # Handle system config wipe (called by factory reset via pkexec)
    elif len(sys.argv) > 1 and sys.argv[1] == "--wipe-system-config":
        # 1. Disable the cpupower systemd service first if enabled
        try:
            res_chk = subprocess.run(
                ["systemctl", "is-enabled", "cpupower.service"],
                capture_output=True, text=True
            )
            if res_chk.stdout.strip() == "enabled":
                subprocess.run(["systemctl", "disable", "--now", "cpupower.service"], capture_output=True)
                print("[cpupower-gtk] Disabled cpupower.service successfully.")
        except Exception as e:
            print(f"WARNING: Failed to disable cpupower.service: {e}", file=sys.stderr)

        # 2. Wipe config files
        wiped = []
        for path in SYSTEM_CONFIG_FILES:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    wiped.append(path)
                except Exception as e:
                    print(f"ERROR: Could not remove {path}: {e}", file=sys.stderr)
                    sys.exit(1)
        if wiped:
            print(f"SUCCESS: Wiped system config files: {', '.join(wiped)}")
        else:
            print("SUCCESS: No system config files found to wipe.")
        sys.exit(0)

    else:
        print(
            "Usage: backend.py [--apply-saved "
            "| --apply-user-config <path> "
            "| --wipe-system-config]",
            file=sys.stderr
        )
        sys.exit(1)
