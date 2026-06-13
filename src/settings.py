"""Settings management and system service configuration for cpupower-gtk"""
import os
import json
import logging
import subprocess

log = logging.getLogger(__name__)

CONFIG_FILE = os.path.expanduser("~/.config/cpupower-gtk/settings.json")
PROFILES_FILE = os.path.expanduser("~/.config/cpupower-gtk/profiles.json")

# System official cpupower configuration paths
SYSTEM_CONFIG_FILES = [
    "/etc/default/cpupower-service.conf",
    "/etc/default/cpupower"
]


def load_settings() -> dict:
    """Load settings from settings.json"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            log.error("Failed to load settings: %s", e)
    return {}


def save_settings(settings: dict) -> None:
    """Save settings to settings.json"""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        log.error("Failed to save settings: %s", e)


def is_service_enabled() -> bool:
    """Check if the system's official cpupower.service is enabled"""
    try:
        res = subprocess.run(
            ["systemctl", "is-enabled", "cpupower.service"],
            capture_output=True, text=True
        )
        return res.stdout.strip() == "enabled"
    except Exception:
        return False


def set_service_enabled(enabled: bool) -> tuple[bool, str]:
    """Enable or disable the system's official cpupower.service"""
    action = "enable" if enabled else "disable"
    cmd = ["systemctl", action, "--now", "cpupower.service"]
    try:
        # Prompt for password via graphical pkexec for systemctl
        res = subprocess.run(["pkexec"] + cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            status = "enabled and started" if enabled else "disabled and stopped"
            return True, f"Official cpupower.service {status} successfully."
        else:
            err = res.stderr or res.stdout or ""
            return False, f"Failed to modify systemd service: {err.strip()}"
    except Exception as e:
        return False, f"Error controlling systemd service: {e}"


def factory_reset() -> tuple[bool, str]:
    """Delete all user configurations, profiles and system boot config"""
    errors = []

    # Wipe user-space config files
    for path in [CONFIG_FILE, PROFILES_FILE]:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                errors.append(f"Failed to delete {os.path.basename(path)}: {e}")

    # Wipe system config files (requires root via pkexec)
    try:
        backend_path = "/usr/share/cpupower-gtk/backend.py"
        if not os.path.exists(backend_path):
            # Fall back to local dev path
            backend_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "backend.py"
            )
        res = subprocess.run(
            ["pkexec", backend_path, "--wipe-system-config"],
            capture_output=True, text=True, timeout=15
        )
        if res.returncode != 0:
            err = (res.stderr or res.stdout or "").strip()
            errors.append(f"Could not wipe system config: {err}")
    except Exception as e:
        errors.append(f"Could not wipe system config: {e}")

    if errors:
        return False, "\n".join(errors)
    return True, "Factory reset completed successfully."


def load_profiles() -> dict:
    """Load user profiles"""
    if os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            log.error("Failed to load profiles: %s", e)
    return {}


def save_profiles(profiles: dict) -> None:
    """Save user profiles"""
    os.makedirs(os.path.dirname(PROFILES_FILE), exist_ok=True)
    try:
        with open(PROFILES_FILE, "w") as f:
            json.dump(profiles, f, indent=2)
    except Exception as e:
        log.error("Failed to save profiles: %s", e)
