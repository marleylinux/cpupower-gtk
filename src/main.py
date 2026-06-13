"""Main GTK application coordinator for cpupower-gtk"""
import os
import json
import logging
import threading
import subprocess
import init_gi  # noqa: F401

from gi.repository import Gtk, Adw, Gdk, Gio, GLib

import backend
import system
import settings as settings_module
import styles
import ui as ui_module
from widgets import format_freq

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

APP_ID = "com.marley.cpupower-gtk"
APP_NAME = "cpupower-gtk"
APP_VER = "1.0.1"


def get_backend_path() -> str:
    """Return the path to backend.py, preferring the installed system copy."""
    installed_backend = "/usr/share/cpupower-gtk/backend.py"
    if os.path.exists(installed_backend):
        return installed_backend
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend.py")


class CpupowerApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.win = None
        self.css_provider = Gtk.CssProvider()
        self.theme_css_provider = Gtk.CssProvider()
        self.cpu_caps: dict = {}
        self.pending_settings: dict = {}
        self.applied_settings: dict = {}
        self._refresh_timer_id: int | None = None
        self._refreshing: bool = False
        self.ui_settings: dict = {
            "theme": "default",
            "auto_switch": False,
            "ac_profile": "",
            "battery_profile": "",
        }
        self.last_ac_state: bool | None = None
        self.last_cpu_ticks: dict = {}

        # UI controls
        self.btn_refresh = None
        self.btn_apply = None
        self.window_title = None

        self._load_ui_settings()

    def _load_ui_settings(self):
        self.ui_config_path = os.path.expanduser("~/.config/cpupower-gtk/ui.json")
        if os.path.exists(self.ui_config_path):
            try:
                with open(self.ui_config_path, "r") as f:
                    self.ui_settings.update(json.load(f))
            except Exception as e:
                log.warning("Failed to load UI settings: %s", e)

    def _save_ui_settings(self):
        try:
            os.makedirs(os.path.dirname(self.ui_config_path), exist_ok=True)
            with open(self.ui_config_path, "w") as f:
                json.dump(self.ui_settings, f)
        except Exception as e:
            log.error("Failed to save UI settings: %s", e)

    # ── Application lifecycle ──────────────────────────────────────────────────

    def do_activate(self) -> None:
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)

        # Load CSS
        self.css_provider.load_from_data(styles.CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self.theme_css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_USER,
        )

        # Look for assets
        try:
            display = Gdk.Display.get_default()
            if display:
                theme = Gtk.IconTheme.get_for_display(display)
                curr_dir = os.path.dirname(os.path.abspath(__file__))
                theme.add_search_path(os.path.join(curr_dir, "assets"))
        except Exception as e:
            log.debug("Failed to register icon search path: %s", e)

        self._register_actions()

        # Load saved settings
        saved = settings_module.load_settings()
        if saved:
            self.pending_settings.update(saved)
        self.applied_settings = dict(self.pending_settings)

        # Check if cpupower is installed
        if not backend.is_cpupower_installed():
            self.win = Adw.ApplicationWindow(application=self)
            self.win.set_default_size(600, 450)
            self.win.set_title("cpupower-gtk")
            missing_page = ui_module.build_dependency_missing_page(self)
            self.win.set_content(missing_page)
            self.win.present()
            return

        # Fetch capabilities from sysfs
        self.cpu_caps = backend.get_cpu_capabilities()

        # Build main window
        self.win = ui_module.build_main_window(self)
        self.win.set_icon_name(APP_ID)

        GLib.set_prgname(APP_ID)
        GLib.set_application_name(APP_NAME)

        self.win.present()

        # Wake-from-sleep settings restoration is now handled silently at the system level
        # via the systemd system-sleep hook script.

        # Load settings into UI components
        self._load_pending_settings_to_ui()

        # Start timer loop
        self._start_refresh_timer()

        # Auto AC switch profile check
        if self.ui_settings.get("auto_switch", False):
            current_ac = system.is_on_ac_power()
            self.last_ac_state = current_ac
            self._apply_auto_power_profile(current_ac)

    # ── Actions Registration ───────────────────────────────────────────────────

    def _register_actions(self) -> None:
        action_reload = Gio.SimpleAction.new("reload", None)
        action_reload.connect("activate", lambda a, p: self.on_refresh_clicked(None))
        self.add_action(action_reload)
        self.set_accels_for_action("app.reload", ["F5"])

        action_apply = Gio.SimpleAction.new("apply", None)
        action_apply.connect("activate", lambda a, p: self.on_settings_apply_clicked(None))
        self.add_action(action_apply)
        self.set_accels_for_action("app.apply", ["<Ctrl>s"])

        action_about = Gio.SimpleAction.new("about", None)
        action_about.connect("activate", self.on_about_activated)
        self.add_action(action_about)

        # Theme color choice action
        initial_theme = self.ui_settings.get("theme", "default")
        action_theme = Gio.SimpleAction.new_stateful(
            "theme-color",
            GLib.VariantType.new("s"),
            GLib.Variant.new_string(initial_theme)
        )
        action_theme.connect("change-state", self.on_theme_color_changed)
        self.add_action(action_theme)

        # Set initial color theme
        self.on_theme_color_changed(action_theme, GLib.Variant.new_string(initial_theme))

    def on_theme_color_changed(self, action, state) -> None:
        action.set_state(state)
        color = state.get_string()

        self.ui_settings["theme"] = color
        self._save_ui_settings()

        theme_palettes = {
            "default": {
                "accent": "@accent_bg_color",
            },
            "ryzen": {
                "accent": "#ff3b30",
            },
            "geforce": {
                "accent": "#76ff03",
            },
            "intel": {
                "accent": "#0071e3",
            },
            "arch": {
                "accent": "#1793d1",
            },
            "saints": {
                "accent": "#af52de",
            },
            "noctua": {
                "accent": "#9c6644",
            }
        }

        palette = theme_palettes.get(color, theme_palettes["default"])
        accent = palette["accent"]

        css_lines = []
        if color != "default":
            css_lines.append(f"@define-color accent_color {accent};")
            css_lines.append(f"@define-color accent_bg_color {accent};")
            css_lines.append("@define-color accent_fg_color #ffffff;")
            css_lines.append(f"@define-color suggested_bg_color {accent};")
            css_lines.append("@define-color suggested_fg_color #ffffff;")
            css_lines.append(f"@define-color selection_bg_color {accent};")
            css_lines.append("@define-color selection_fg_color #ffffff;")

            css_lines.append(".suggested-action { background-color: @accent_bg_color; color: @accent_fg_color; }")
            css_lines.append(".apply-btn { background-color: @accent_bg_color; color: @accent_fg_color; box-shadow: 0 6px 16px alpha(@accent_bg_color, 0.35); }")
            css_lines.append(".apply-btn:hover { background-color: shade(@accent_bg_color, 1.25); box-shadow: 0 12px 28px alpha(@accent_bg_color, 0.5); }")

        # Fun color palettes for dashboard tags based on the theme
        tag_palettes = {
            "ryzen": {
                "amd": "#ed0022", "intel": "#0071c5", "system": "#bf5af2",
                "live": "#30d158", "energy": "#28a745", "perf": "#ff9500"
            },
            "intel": {
                "amd": "#ed0022", "intel": "#0071c5", "system": "#5ac8fa",
                "live": "#30d158", "energy": "#34c759", "perf": "#af52de"
            },
            "arch": {
                "amd": "#f4a261", "intel": "#34e8eb", "system": "#1793d1",
                "live": "#30d158", "energy": "#a8e6cf", "perf": "#e63946"
            },
            "geforce": {
                "amd": "#ccff00", "intel": "#00e5ff", "system": "#76b900",
                "live": "#30d158", "energy": "#00c853", "perf": "#d50000"
            },
            "saints": {
                "amd": "#ffd700", "intel": "#00bfff", "system": "#af52de",
                "live": "#30d158", "energy": "#00fa9a", "perf": "#ff4500"
            },
            "noctua": {
                "amd": "#ddb892", "intel": "#bde0fe", "system": "#9c6644",
                "live": "#30d158", "energy": "#a3b18a", "perf": "#e07a5f"
            },
            "default": {
                "amd": "#ff3b30", "intel": "#007aff", "system": accent,
                "live": "#30d158", "energy": "#30d158", "perf": "#ff9500"
            }
        }

        tags = tag_palettes.get(color, tag_palettes["default"])

        for t_name, t_color in tags.items():
            css_lines.append(f"@define-color {t_name}_badge_fg {t_color};")
            css_lines.append(f"@define-color {t_name}_badge_bg alpha({t_color}, 0.15);")
            css_lines.append(f"@define-color {t_name}_badge_border alpha({t_color}, 0.3);")

        full_css = "\n".join(css_lines)
        self.theme_css_provider.load_from_data(full_css.encode())

    # ── Background telemetry refresh loop ──────────────────────────────────────

    def _start_refresh_timer(self) -> None:
        self._refresh_timer_id = GLib.timeout_add(1000, self._auto_refresh)

    def _auto_refresh(self) -> bool:
        # AC power check
        self._check_power_source()

        # Execute refresh async
        if not self._refreshing:
            self._do_refresh_async()
        return True

    def _do_refresh_async(self) -> None:
        self._refreshing = True

        def fetch():
            try:
                temp = system.get_cpu_temperature()
                avg_clk = system.get_live_cpu_clock_avg()
                clocks = system.get_live_cpu_clocks()
                ticks = system.get_cpu_usage_ticks()
                caps = backend.get_cpu_capabilities()
                GLib.idle_add(self._on_refresh_done, temp, avg_clk, clocks, ticks, caps)
            except Exception:
                log.error("Refresh fetch error", exc_info=True)
                GLib.idle_add(self._on_refresh_done, None, None, [], {}, {})

        threading.Thread(target=fetch, daemon=True).start()

    def _on_refresh_done(self, temp: float | None, avg_clk: float | None, clocks: list[float], ticks: dict, caps: dict) -> bool:
        self._refreshing = False
        self.cpu_caps = caps

        if self.btn_refresh:
            self.btn_refresh.set_sensitive(True)

        # 1. Calculate CPU usages
        usages = {}
        if ticks and self.last_cpu_ticks:
            for name, tick in ticks.items():
                last = self.last_cpu_ticks.get(name)
                if last:
                    tot_diff = tick["total"] - last["total"]
                    idle_diff = tick["idle"] - last["idle"]
                    if tot_diff > 0:
                        usages[name] = max(0.0, min(100.0, (tot_diff - idle_diff) / tot_diff * 100.0))
                    else:
                        usages[name] = 0.0
        self.last_cpu_ticks = ticks

        # 2. Update general dashboard cards
        if hasattr(self, "card_driver"):
            self.card_driver._val_lbl.set_text(caps.get("scaling_driver", "—"))
        if hasattr(self, "card_gov"):
            self.card_gov._val_lbl.set_text(caps.get("current_governor", "—"))
        if hasattr(self, "card_boost"):
            if caps.get("boost_supported"):
                self.card_boost._val_lbl.set_text("Active" if caps.get("boost_active") else "Inactive")
            else:
                self.card_boost._val_lbl.set_text("Unsupported")
            
        if hasattr(self, "card_min_limit"):
            self.card_min_limit._val_lbl.set_text(format_freq(caps.get("scaling_min")))
        if hasattr(self, "card_max_limit"):
            self.card_max_limit._val_lbl.set_text(format_freq(caps.get("scaling_max")))

        # Temp card (with progress bar)
        if hasattr(self, "card_temp"):
            self.card_temp.update_val(temp)

        # Avg frequency card (with progress bar)
        if hasattr(self, "card_avg_freq"):
            self.card_avg_freq.update_val(avg_clk / 1000.0 if avg_clk is not None else None)

        # Avg load card (with progress bar)
        if hasattr(self, "card_avg_load"):
            overall_load = usages.get("cpu", 0.0)
            self.card_avg_load.update_val(overall_load if ticks else None)

        # EPP / EPB
        if hasattr(self, "card_epp"):
            if caps.get("epp_available"):
                self.card_epp._val_lbl.set_text(caps.get("current_epp", "—"))
            elif caps.get("epb_available"):
                self.card_epp._val_lbl.set_text(str(caps.get("current_epb", "—")))

        # 3. Update individual core cards
        if hasattr(self, "_core_freq_cards"):
            for idx, card in enumerate(self._core_freq_cards):
                freq = clocks[idx] if idx < len(clocks) else None
                load = usages.get(f"cpu{idx}", 0.0) if ticks else None
                card.update_core(freq, load)

        # 4. Update frequency slider row live badges
        if hasattr(self, "settings_min_row") and self.settings_min_row:
            act_min = caps.get("scaling_min", 0.0)
            self.settings_min_row._current_live_val = act_min
            lbl = f"Live: {act_min/1000.0:.2f} GHz" if act_min > 0.0 else "Live: —"
            self.settings_min_row._cur_badge.set_text(lbl)

        if hasattr(self, "settings_max_row") and self.settings_max_row:
            act_max = caps.get("scaling_max", 0.0)
            self.settings_max_row._current_live_val = act_max
            lbl = f"Live: {act_max/1000.0:.2f} GHz" if act_max > 0.0 else "Live: —"
            self.settings_max_row._cur_badge.set_text(lbl)

        if hasattr(self, "settings_fixed_row") and self.settings_fixed_row:
            act_max = caps.get("scaling_max", 0.0)
            self.settings_fixed_row._current_live_val = act_max
            lbl = f"Live: {act_max/1000.0:.2f} GHz" if act_max > 0.0 else "Live: —"
            self.settings_fixed_row._cur_badge.set_text(lbl)

        return False

    def on_refresh_clicked(self, _btn) -> None:
        if self._refreshing:
            return
        if self.btn_refresh:
            self.btn_refresh.set_sensitive(False)
        self._do_refresh_async()

    # ── UI Actions & Settings management ───────────────────────────────────────

    def _load_pending_settings_to_ui(self) -> None:
        """Force load the UI sliders, switches, and combos to match pending_settings or fallback hardware caps"""
        caps = self.cpu_caps
        pending = self.pending_settings

        # Gov
        gov = pending.get("governor", caps.get("current_governor", ""))
        govs = caps.get("governors", [])
        if govs and gov in govs:
            self.settings_gov_row.set_selected(govs.index(gov))

        # EPP
        if self.settings_epp_row and caps.get("epp_available"):
            epp = pending.get("epp", caps.get("current_epp", ""))
            epps = caps.get("epp_preferences", [])
            if epps and epp in epps:
                self.settings_epp_row.set_selected(epps.index(epp))

        # EPB
        if self.settings_epb_scale and caps.get("epb_available"):
            epb = pending.get("epb", caps.get("current_epb", 6))
            if epb is not None:
                self.settings_epb_scale.set_value(float(epb))

        # Boost
        if self.settings_boost_row and caps.get("boost_supported"):
            boost = pending.get("boost", caps.get("boost_active", True))
            self.settings_boost_row.set_active(boost)

        # Min / Max frequency
        min_val = pending.get("min_freq", caps.get("scaling_min", caps.get("cpuinfo_min", 600.0)))
        max_val = pending.get("max_freq", caps.get("scaling_max", caps.get("cpuinfo_max", 3000.0)))

        if hasattr(self, "settings_min_row") and self.settings_min_row:
            self.settings_min_row._updating_programmatically = True
            self.settings_min_scale.set_value(float(min_val))
            self.settings_min_row._updating_programmatically = False
            self.settings_min_row._update_val_label(self.settings_min_scale, False)

        if hasattr(self, "settings_max_row") and self.settings_max_row:
            self.settings_max_row._updating_programmatically = True
            self.settings_max_scale.set_value(float(max_val))
            self.settings_max_row._updating_programmatically = False
            self.settings_max_row._update_val_label(self.settings_max_scale, False)

        # Fixed frequency
        if hasattr(self, "settings_fixed_row") and self.settings_fixed_row:
            fixed_val = pending.get("fixed_freq", caps.get("scaling_max", caps.get("cpuinfo_max", 3000.0)))
            self.settings_fixed_row._updating_programmatically = True
            self.settings_fixed_scale.set_value(float(fixed_val))
            self.settings_fixed_row._updating_programmatically = False
            self.settings_fixed_row._update_val_label(self.settings_fixed_scale, False)

        self._update_conflicts()

    def _update_conflicts(self) -> None:
        """Dynamically manage UI sensitivity and description warnings for conflicting frequency limits"""
        has_min_max = ("min_freq" in self.pending_settings) or ("max_freq" in self.pending_settings)
        has_fixed = "fixed_freq" in self.pending_settings

        # Min freq row
        min_row = getattr(self, "settings_min_row", None)
        if min_row:
            if has_fixed:
                min_row._desc_label.set_markup(
                    f"<span style='italic' size='small'>{min_row._default_desc} "
                    f"<span color='#e01b24' weight='bold' size='small'>(Unsupported: conflicts with Fixed Frequency override)</span></span>"
                )
            else:
                min_row._desc_label.set_markup(f"<span style='italic' size='small'>{min_row._default_desc}</span>")

        # Max freq row
        max_row = getattr(self, "settings_max_row", None)
        if max_row:
            if has_fixed:
                max_row._desc_label.set_markup(
                    f"<span style='italic' size='small'>{max_row._default_desc} "
                    f"<span color='#e01b24' weight='bold' size='small'>(Unsupported: conflicts with Fixed Frequency override)</span></span>"
                )
            else:
                max_row._desc_label.set_markup(f"<span style='italic' size='small'>{max_row._default_desc}</span>")

        # Fixed freq row
        fixed_row = getattr(self, "settings_fixed_row", None)
        if fixed_row:
            if has_min_max:
                fixed_row._desc_label.set_markup(
                    f"<span style='italic' size='small'>{fixed_row._default_desc} "
                    f"<span color='#e01b24' weight='bold' size='small'>(Unsupported: conflicts with Min/Max range limits)</span></span>"
                )
            else:
                fixed_row._desc_label.set_markup(f"<span style='italic' size='small'>{fixed_row._default_desc}</span>")

    def get_settings_from_ui(self) -> dict:
        """Gather configured values from the settings UI page elements"""
        caps = self.cpu_caps
        settings = {}

        # Gov
        govs = caps.get("governors", [])
        idx = self.settings_gov_row.get_selected()
        if govs and idx < len(govs):
            settings["governor"] = govs[idx]

        # EPP
        if self.settings_epp_row:
            epps = caps.get("epp_preferences", [])
            epp_idx = self.settings_epp_row.get_selected()
            if epps and epp_idx < len(epps):
                settings["epp"] = epps[epp_idx]

        # EPB
        if self.settings_epb_scale:
            settings["epb"] = int(self.settings_epb_scale.get_value())

        # Boost
        if self.settings_boost_row:
            settings["boost"] = self.settings_boost_row.get_active()

        # Frequencies
        if "min_freq" in self.pending_settings:
            settings["min_freq"] = float(self.settings_min_scale.get_value())
        if "max_freq" in self.pending_settings:
            settings["max_freq"] = float(self.settings_max_scale.get_value())

        if "fixed_freq" in self.pending_settings:
            settings["fixed_freq"] = float(self.settings_fixed_scale.get_value())
            settings["use_fixed_freq"] = True
        else:
            settings["use_fixed_freq"] = False

        return settings

    def on_settings_apply_clicked(self, _btn) -> None:
        """Write the UI configuration to hardware via Polkit (pkexec) elevation"""
        if not self.btn_apply.get_sensitive():
            return
        settings = self.get_settings_from_ui()

        # Check diff (including deleted/cleared settings)
        diff = {}
        all_keys = set(settings.keys()) | set(self.applied_settings.keys())
        for k in all_keys:
            if settings.get(k) != self.applied_settings.get(k):
                diff[k] = settings.get(k)

        if not diff and _btn is not None:
            self._show_toast("No changes to apply.", is_error=False)
            return

        # Save configuration locally first
        settings_module.save_settings(settings)

        self._set_actions_sensitive(False)
        self.btn_apply.set_label("Applying…")

        backend_path = get_backend_path()
        user_config_path = os.path.expanduser("~/.config/cpupower-gtk/settings.json")

        def run_write_pkexec():
            cmd = ["pkexec", backend_path, "--apply-user-config", user_config_path]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if res.returncode == 0:
                    GLib.idle_add(self._on_apply_done, True, "Settings applied successfully.", settings)
                else:
                    err = (res.stderr or res.stdout or "Authorization cancelled.").strip()
                    GLib.idle_add(self._on_apply_done, False, f"Elevation failed: {err}", settings)
            except Exception as e:
                GLib.idle_add(self._on_apply_done, False, f"Execution failed: {e}", settings)

        threading.Thread(target=run_write_pkexec, daemon=True).start()

    def _on_apply_done(self, ok: bool, msg: str, settings: dict) -> bool:
        self._set_actions_sensitive(True)
        self.btn_apply.set_label("Apply Settings")
        self._show_toast(msg, is_error=not ok)

        if ok:
            self.applied_settings = dict(settings)
            self.pending_settings = dict(settings)
            self._do_refresh_async()
        else:
            self._load_pending_settings_to_ui()
        return False

    def _set_actions_sensitive(self, sensitive: bool) -> None:
        btns = [self.btn_refresh, self.btn_apply, self.btn_ps, self.btn_bal, self.btn_mp]
        for btn in btns:
            if btn:
                btn.set_sensitive(sensitive)
        action_reload = self.lookup_action("reload")
        if action_reload:
            action_reload.set_enabled(sensitive)
        action_apply = self.lookup_action("apply")
        if action_apply:
            action_apply.set_enabled(sensitive)

    # ── Presets ────────────────────────────────────────────────────────────────

    def on_power_saving_clicked(self, _btn) -> None:
        self.apply_preset_to_ui("power-saving")

    def on_balanced_clicked(self, _btn) -> None:
        self.apply_preset_to_ui("balanced")

    def on_max_performance_clicked(self, _btn) -> None:
        self.apply_preset_to_ui("max-performance")

    def apply_preset_to_ui(self, preset: str):
        caps = self.cpu_caps
        phy_min = caps.get("cpuinfo_min", 0.0)
        if phy_min <= 0.0:
            phy_min = 600.0
            
        phy_max = caps.get("cpuinfo_max", 0.0)
        if phy_max <= 0.0:
            phy_max = 3000.0

        self._set_actions_sensitive(False)

        # Clear any conflicting fixed frequency settings when applying a range preset
        self.pending_settings.pop("use_fixed_freq", None)
        self.pending_settings.pop("fixed_freq", None)

        if preset == "power-saving":
            govs = caps.get("governors", [])
            if "powersave" in govs:
                self.pending_settings["governor"] = "powersave"
            elif "conservative" in govs:
                self.pending_settings["governor"] = "conservative"

            if caps.get("epp_available"):
                epps = caps.get("epp_preferences", [])
                if "power" in epps:
                    self.pending_settings["epp"] = "power"
                elif "balance_power" in epps:
                    self.pending_settings["epp"] = "balance_power"

            if caps.get("epb_available"):
                self.pending_settings["epb"] = 15

            if caps.get("boost_supported"):
                self.pending_settings["boost"] = False

            self.pending_settings["min_freq"] = float(phy_min)
            self.pending_settings["max_freq"] = float(phy_min + (phy_max - phy_min) * 0.3)

        elif preset == "balanced":
            govs = caps.get("governors", [])
            if "schedutil" in govs:
                self.pending_settings["governor"] = "schedutil"
            elif "ondemand" in govs:
                self.pending_settings["governor"] = "ondemand"
            elif "powersave" in govs:
                self.pending_settings["governor"] = "powersave"

            if caps.get("epp_available"):
                epps = caps.get("epp_preferences", [])
                if "balance_performance" in epps:
                    self.pending_settings["epp"] = "balance_performance"
                elif "default" in epps:
                    self.pending_settings["epp"] = "default"

            if caps.get("epb_available"):
                self.pending_settings["epb"] = 6

            if caps.get("boost_supported"):
                self.pending_settings["boost"] = True

            self.pending_settings["min_freq"] = float(phy_min)
            self.pending_settings["max_freq"] = float(phy_max)

        elif preset == "max-performance":
            govs = caps.get("governors", [])
            if "performance" in govs:
                self.pending_settings["governor"] = "performance"

            if caps.get("epp_available"):
                epps = caps.get("epp_preferences", [])
                if "performance" in epps:
                    self.pending_settings["epp"] = "performance"

            if caps.get("epb_available"):
                self.pending_settings["epb"] = 0

            if caps.get("boost_supported"):
                self.pending_settings["boost"] = True

            self.pending_settings["min_freq"] = float(phy_max * 0.8)
            self.pending_settings["max_freq"] = float(phy_max)

        self._load_pending_settings_to_ui()
        self._set_actions_sensitive(True)
        self.on_settings_apply_clicked(None)

    # ── Power automation AC / battery profile triggers ─────────────────────────

    def _check_power_source(self) -> None:
        current_ac = system.is_on_ac_power()
        if self.last_ac_state is None:
            self.last_ac_state = current_ac
            return

        if current_ac != self.last_ac_state:
            self.last_ac_state = current_ac
            log.info("Power source changed to %s", "AC" if current_ac else "Battery")
            if self.ui_settings.get("auto_switch", False):
                self._apply_auto_power_profile(current_ac)

    def _apply_auto_power_profile(self, is_ac: bool) -> None:
        profile_key = "ac_profile" if is_ac else "battery_profile"
        profile_name = self.ui_settings.get(profile_key, "")

        if not profile_name:
            return

        source_label = "AC power" if is_ac else "battery"
        profiles = settings_module.load_profiles()

        if profile_name == "__power_saving__":
            self._show_toast(f"Applying Power Saving preset (on {source_label})", is_error=False)
            self.apply_preset_to_ui("power-saving")
        elif profile_name == "__max_performance__":
            self._show_toast(f"Applying Max Performance preset (on {source_label})", is_error=False)
            self.apply_preset_to_ui("max-performance")
        elif profile_name in profiles:
            self._show_toast(f"Applying profile '{profile_name}' (on {source_label})", is_error=False)
            self.on_apply_custom_profile(profile_name)

    def on_apply_custom_profile(self, pname: str) -> None:
        if getattr(self, "_toggling_profile", False):
            return
        self._toggling_profile = True
        profiles = settings_module.load_profiles()
        if pname in profiles:
            pdata = profiles[pname]
            self.pending_settings.update(pdata)
            self._load_pending_settings_to_ui()

            self._set_actions_sensitive(False)

            backend_path = get_backend_path()
            temp_config_path = os.path.expanduser("~/.config/cpupower-gtk/temp_profile.json")
            try:
                os.makedirs(os.path.dirname(temp_config_path), exist_ok=True)
                with open(temp_config_path, "w") as f:
                    json.dump(pdata, f)
            except Exception as e:
                self._show_toast(f"Failed to initiate write: {e}", is_error=True)
                self._set_actions_sensitive(True)
                return

            def go():
                cmd = ["pkexec", backend_path, "--apply-user-config", temp_config_path]
                try:
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    if res.returncode == 0:
                        GLib.idle_add(self._on_custom_profile_applied, True, f"Profile '{pname}' applied successfully.", pname, pdata)
                    else:
                        err = (res.stderr or res.stdout or "Authorization cancelled.").strip()
                        GLib.idle_add(self._on_custom_profile_applied, False, f"Elevation failed: {err}", pname, pdata)
                except Exception as e:
                    GLib.idle_add(self._on_custom_profile_applied, False, str(e), pname, pdata)

            threading.Thread(target=go, daemon=True).start()

    def _on_custom_profile_applied(self, ok: bool, msg: str, pname: str, pdata: dict) -> bool:
        self._toggling_profile = False
        self._set_actions_sensitive(True)
        if ok:
            self.applied_settings.update(pdata)
            self._show_toast(msg, is_error=False)
            self._do_refresh_async()
        else:
            self._show_toast(msg, is_error=True)
            self.pending_settings = dict(self.applied_settings)
            self._load_pending_settings_to_ui()
        return False

    # ── UI Toast & About dialog helpers ────────────────────────────────────────

    def _show_toast(self, text: str, is_error: bool = False) -> None:
        title = f"⚠️ {text}" if is_error else text
        toast = Adw.Toast(title=title)
        self.toast_overlay.add_toast(toast)

    def on_about_activated(self, _action, _param) -> None:
        about = Adw.AboutDialog()
        about.set_application_name(APP_NAME)
        about.set_application_icon(APP_ID)
        about.set_version(APP_VER)
        about.set_developer_name("Marley")
        about.set_website("https://github.com/marleylinux/cpupower-gtk")
        about.set_issue_url("https://github.com/marleylinux/cpupower-gtk/issues")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_comments(
            "A modern GTK4 / Libadwaita graphical wrapper for cpupower.\n"
            "Manage CPU frequency scaling and governors with ease."
        )
        about.set_developers(["Marley"])
        about.present(self.win)

    def on_startup_switch_toggled(self, switch_row, _spec) -> None:
        """Enable or disable the startup systemd service via settings helper"""
        active = switch_row.get_active()
        if getattr(self, "_toggling_startup", False):
            return

        current_status = settings_module.is_service_enabled()
        if active == current_status:
            return

        self._toggling_startup = True
        switch_row.set_sensitive(False)

        def run_toggle():
            ok, msg = settings_module.set_service_enabled(active)
            GLib.idle_add(self._on_startup_toggle_done, ok, msg, active)

        threading.Thread(target=run_toggle, daemon=True).start()

    def _on_startup_toggle_done(self, ok: bool, msg: str, active: bool) -> bool:
        self._toggling_startup = False
        if hasattr(self, "switch_startup") and self.switch_startup:
            self.switch_startup.set_sensitive(True)
            if not ok:
                self._toggling_startup = True
                self.switch_startup.set_active(not active)
                self._toggling_startup = False
        self._show_toast(msg, is_error=not ok)
        return False

    def on_factory_reset_clicked(self, _btn) -> None:
        """Prompt confirmation and perform factory reset"""
        dialog = Adw.MessageDialog(
            transient_for=self.win,
            heading="Factory Reset?",
            body="This will delete all custom profiles, wipe saved startup configurations, disable the startup service, and reset the interface. This cannot be undone.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset Everything")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(dlg, response):
            if response == "reset":
                self._do_factory_reset()

        dialog.connect("response", on_response)
        dialog.present()

    def _do_factory_reset(self) -> None:
        ok, msg = settings_module.factory_reset()
        if ok:
            self.pending_settings.clear()
            self.applied_settings.clear()
            self.ui_settings = {
                "theme": "default",
                "auto_switch": False,
                "ac_profile": "",
                "battery_profile": "",
            }
            self._save_ui_settings()

            action = self.lookup_action("theme-color")
            if action:
                action.change_state(GLib.Variant.new_string("default"))

            self._load_pending_settings_to_ui()

            if hasattr(self, "refresh_profiles"):
                self.refresh_profiles()
            if hasattr(self, "update_automation_dropdowns"):
                self.update_automation_dropdowns()

            self._show_toast("Factory reset complete. Settings reverted.", is_error=False)
        else:
            self._show_toast(f"Reset failed: {msg}", is_error=True)


