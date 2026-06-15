"""UI page builders for cpupower-gtk"""
import os
import logging
from gi.repository import Gtk, Adw, Gdk
try:
    from main import APP_VER
except ImportError:
    APP_VER = "1.0.6"


from widgets import (
    get_cpu_name,
    format_freq,
    _build_section_header,
    _build_monitor_card,
    _build_monitor_card_with_bar,
    _build_frequency_card
)
import system
import settings

log = logging.getLogger(__name__)


def build_dependency_missing_page(app) -> Adw.ToolbarView:
    """Show error page when cpupower is not installed"""
    toolbar = Adw.ToolbarView()

    header = Adw.HeaderBar()
    header.add_css_class("main-header")
    win_title = Adw.WindowTitle()
    win_title.set_title("cpupower-gtk")
    win_title.set_subtitle("Dependency Missing")
    header.set_title_widget(win_title)
    toolbar.add_top_bar(header)

    status = Adw.StatusPage()
    status.set_icon_name("software-update-urgent-symbolic")
    status.set_title("cpupower Not Found")
    status.set_description(
        "The core dependency 'cpupower' is missing from your system.\n\n"
        "cpupower-gtk is a graphical wrapper and requires the command-line tool to function.\n\n"
        "Please install it using your package manager:\n"
        "  • Arch Linux: sudo pacman -S cpupower\n"
        "  • Ubuntu/Debian: sudo apt install linux-tools-generic\n"
        "  • Fedora: sudo dnf install kernel-tools\n\n"
        "After installing, please restart this application."
    )

    toolbar.set_content(status)
    return toolbar


def _interpret_cppc_rank(val: str) -> str:
    """Map raw CPPC boundary numbers to human-readable descriptions"""
    if not val or not val.isdigit():
        return val
    num = int(val)
    if num >= 200:
        return f"Extreme ({num})"
    elif num >= 150:
        return f"Max Performance ({num})"
    elif num >= 100:
        return f"Balanced ({num})"
    else:
        return f"Power Saving ({num})"


def _read_sysfs_val(base_dir: str, fname: str) -> str | None:
    """Read a single sysfs value file under base_dir, returning stripped text or None."""
    path = f"{base_dir}/{fname}"
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return f.read().strip()
        except Exception:
            pass
    return None


def _read_cppc_info() -> dict:
    """Read CPPC (Collaborative Processor Performance Control) settings if available in sysfs"""
    cppc = {}
    policy0 = "/sys/devices/system/cpu/cpufreq/policy0"

    highest_perf = _read_sysfs_val(policy0, "amd_pstate_highest_perf")
    if highest_perf:
        cppc["highest_perf"] = _interpret_cppc_rank(highest_perf)

    max_freq = _read_sysfs_val(policy0, "amd_pstate_max_freq")
    if max_freq:
        try:
            mhz = float(max_freq) / 1000.0
            cppc["max_freq"] = f"{mhz:.0f} MHz" if mhz < 1000 else f"{mhz/1000.0:.2f} GHz"
        except ValueError:
            pass

    lowest_nonlinear_freq = _read_sysfs_val(policy0, "amd_pstate_lowest_nonlinear_freq")
    if lowest_nonlinear_freq:
        try:
            mhz = float(lowest_nonlinear_freq) / 1000.0
            cppc["lowest_nonlinear_freq"] = f"{mhz:.0f} MHz" if mhz < 1000 else f"{mhz/1000.0:.2f} GHz"
        except ValueError:
            pass

    return cppc


def _read_intel_pstate_info() -> dict:
    """Read Intel P-State properties if available"""
    intel = {}
    base_dir = "/sys/devices/system/cpu/intel_pstate"

    num_pstates = _read_sysfs_val(base_dir, "num_pstates")
    if num_pstates:
        intel["num_pstates"] = num_pstates

    turbo_pct = _read_sysfs_val(base_dir, "turbo_pct")
    if turbo_pct:
        intel["turbo_pct"] = f"{turbo_pct}%"

    hwp_dynamic_boost = _read_sysfs_val(base_dir, "hwp_dynamic_boost")
    if hwp_dynamic_boost:
        intel["hwp_dynamic_boost"] = "Active" if hwp_dynamic_boost == "1" else "Inactive"

    min_perf = _read_sysfs_val(base_dir, "min_perf_pct")
    if min_perf:
        intel["min_perf_pct"] = f"{min_perf}%"

    max_perf = _read_sysfs_val(base_dir, "max_perf_pct")
    if max_perf:
        intel["max_perf_pct"] = f"{max_perf}%"

    return intel


def _layout_grid_cards(grid: Gtk.Grid, cards: list):
    """Arrange monitor cards inside a grid layout following ryzenadj-gtk rules"""
    count = len(cards)
    for i, card in enumerate(cards):
        if count % 2 == 0 or count > 4:
            col = i % 2
            row = i // 2
            grid.attach(card, col, row, 1, 1)
        elif count == 3:
            if i < 2:
                grid.attach(card, i, 0, 1, 1)
            else:
                grid.attach(card, 0, 1, 2, 1)
        else:
            grid.attach(card, 0, i, 2, 1)


def _make_page_scaffold(name: str, title: str) -> tuple[Gtk.ScrolledWindow, Gtk.Box]:
    """Create the standard scrolled window + clamped vertical box shared by every page."""
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_vexpand(True)
    scrolled.set_name(name)
    scrolled.get_title = lambda: title
    clamp = Adw.Clamp()
    clamp.set_maximum_size(1000)
    clamp.set_margin_top(24)
    clamp.set_margin_bottom(32)
    clamp.set_margin_start(16)
    clamp.set_margin_end(16)
    scrolled.set_child(clamp)
    main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    clamp.set_child(main_box)
    return scrolled, main_box


def _build_dashboard_page(app) -> Gtk.ScrolledWindow:
    """Build telemetry dashboard with active core monitoring grids"""
    scrolled, main_box = _make_page_scaffold("dashboard", "Dashboard")

    # 1. Hero Box — use CenterBox for proper responsive alignment
    hero_box = Gtk.CenterBox()
    hero_box.add_css_class("hero-box")

    status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    status_box.set_valign(Gtk.Align.CENTER)
    status_pill = Gtk.Label(label="● Live")
    status_pill.add_css_class("live-status-pill")
    status_box.append(status_pill)
    hero_box.set_start_widget(status_box)

    center_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
    center_content.set_halign(Gtk.Align.CENTER)

    hero_icon = Gtk.Image.new_from_icon_name("system-run-symbolic")
    hero_icon.set_pixel_size(48)
    hero_icon.add_css_class("hero-icon")
    center_content.append(hero_icon)

    text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    text_box.set_valign(Gtk.Align.CENTER)

    title_lbl = Gtk.Label(label="CPU Dashboard")
    title_lbl.add_css_class("hero-title")
    title_lbl.set_halign(Gtk.Align.START)
    text_box.append(title_lbl)

    subtitle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    subtitle_lbl = Gtk.Label(label="Active monitoring for")
    subtitle_lbl.add_css_class("hero-subtitle")
    subtitle_box.append(subtitle_lbl)

    cpu_badge = Gtk.Label(label=get_cpu_name())
    cpu_badge.add_css_class("hero-cpu-badge")
    subtitle_box.append(cpu_badge)
    text_box.append(subtitle_box)

    center_content.append(text_box)
    hero_box.set_center_widget(center_content)
    main_box.append(hero_box)

    # 2. General CPU telemetry
    main_box.append(_build_section_header("CPU Power State", "utilities-system-monitor-symbolic"))

    caps = app.cpu_caps
    state_grid = Gtk.Grid()
    state_grid.set_column_homogeneous(True)
    state_grid.set_column_spacing(16)
    state_grid.set_row_spacing(16)
    state_grid.set_margin_bottom(12)

    app.card_driver = _build_monitor_card("Scaling Driver", "", "cpu-symbolic", caps.get("scaling_driver", "—"), "System", "tag-system")
    app.card_gov = _build_monitor_card("Active Governor", "", "system-run-symbolic", caps.get("current_governor", "—"), "System", "tag-system")
    boost_initial = "Active" if caps.get("boost_active") else ("Inactive" if caps.get("boost_supported") else "Unsupported")
    app.card_boost = _build_monitor_card("Core Boost", "", "media-flash-symbolic", boost_initial, "Performance", "tag-performance")

    if caps.get("epp_available"):
        app.card_epp = _build_monitor_card("Energy Preference (EPP)", "", "battery-symbolic", caps.get("current_epp", "—"), "Energy", "tag-energy")
    elif caps.get("epb_available"):
        app.card_epp = _build_monitor_card("Performance Bias (EPB)", "", "battery-symbolic", str(caps.get("current_epb", "—")), "Energy", "tag-energy")
    else:
        app.card_epp = _build_monitor_card("Energy Register", "", "battery-symbolic", "Unsupported", "System", "tag-system")

    app.card_min_limit = _build_monitor_card("Min Freq Limit", "GHz", "go-down-symbolic", format_freq(caps.get("scaling_min")), "System", "tag-system")
    app.card_max_limit = _build_monitor_card("Max Freq Limit", "GHz", "go-up-symbolic", format_freq(caps.get("scaling_max")), "System", "tag-system")

    max_limit = caps.get("cpuinfo_max", 0.0) / 1000.0
    if max_limit <= 0.0:
        max_limit = 5.0

    state_cards = [
        app.card_driver, app.card_gov, app.card_boost, app.card_epp,
        app.card_min_limit, app.card_max_limit
    ]
    _layout_grid_cards(state_grid, state_cards)
    
    # Wrap in PreferencesGroup with dashboard-group class for gold standard layout
    grp_state = Adw.PreferencesGroup()
    grp_state.add_css_class("dashboard-group")
    grp_state.add(state_grid)
    main_box.append(grp_state)

    main_box.append(_build_section_header("Live CPU Readings", "utilities-system-monitor-symbolic"))
    
    live_grid = Gtk.Grid()
    live_grid.set_column_homogeneous(True)
    live_grid.set_column_spacing(16)
    live_grid.set_row_spacing(16)
    live_grid.set_margin_bottom(12)

    app.card_avg_freq = _build_monitor_card_with_bar("Average Speed", "GHz", "system-run-symbolic", max_limit, "Live", "tag-live")
    app.card_avg_load = _build_monitor_card_with_bar("Average Load", "%", "system-run-symbolic", 100.0, "Live", "tag-live")
    app.card_temp = _build_monitor_card_with_bar("CPU Temp", "°C", "display-brightness-symbolic", 100.0, "Live", "tag-live")

    live_cards = [app.card_avg_freq, app.card_avg_load, app.card_temp]
    _layout_grid_cards(live_grid, live_cards)
    
    # Wrap in PreferencesGroup with dashboard-group class
    grp_live = Adw.PreferencesGroup()
    grp_live.add_css_class("dashboard-group")
    grp_live.add(live_grid)
    main_box.append(grp_live)

    # 3. Vendor-specific telemetry (AMD CPPC or Intel P-State)
    scaling_driver = caps.get("scaling_driver", "").lower()
    is_amd = "amd" in scaling_driver
    is_intel = "intel" in scaling_driver

    if not is_amd and not is_intel:
        cpu_name_upper = get_cpu_name().upper()
        is_amd = "AMD" in cpu_name_upper
        is_intel = "INTEL" in cpu_name_upper

    cppc_data = _read_cppc_info()
    if is_amd:
        main_box.append(_build_section_header("AMD Collaborative Performance Control (CPPC)", "preferences-system-symbolic"))
        
        cppc_grid = Gtk.Grid()
        cppc_grid.set_column_homogeneous(True)
        cppc_grid.set_column_spacing(16)
        cppc_grid.set_row_spacing(16)
        cppc_grid.set_margin_bottom(12)

        card_cppc_max = _build_monitor_card("Highest Performance", "", "media-flash-symbolic", cppc_data.get("highest_perf", "—"), "AMD", "tag-amd")
        card_cppc_nom = _build_monitor_card("Hardware Max Freq", "", "media-flash-symbolic", cppc_data.get("max_freq", "—"), "AMD", "tag-amd")
        card_cppc_min_freq = _build_monitor_card("Lowest Non-linear Speed", "", "thunderbolt-symbolic", cppc_data.get("lowest_nonlinear_freq", "—"), "AMD", "tag-amd")

        _layout_grid_cards(cppc_grid, [card_cppc_max, card_cppc_nom, card_cppc_min_freq])
        
        # Wrap in PreferencesGroup with dashboard-group class
        grp_cppc = Adw.PreferencesGroup()
        grp_cppc.add_css_class("dashboard-group")
        grp_cppc.add(cppc_grid)
        main_box.append(grp_cppc)

    intel_data = _read_intel_pstate_info()
    if is_intel:
        main_box.append(_build_section_header("Intel P-State (HWP) Telemetry", "preferences-system-symbolic"))
        
        intel_grid = Gtk.Grid()
        intel_grid.set_column_homogeneous(True)
        intel_grid.set_column_spacing(16)
        intel_grid.set_row_spacing(16)
        intel_grid.set_margin_bottom(12)

        card_pstates = _build_monitor_card("HWP P-States", "", "view-grid-symbolic", intel_data.get("num_pstates", "—"), "Intel", "tag-intel")
        card_turbo = _build_monitor_card("Turbo Range", "", "media-flash-symbolic", intel_data.get("turbo_pct", "—"), "Intel", "tag-intel")
        card_hwp_boost = _build_monitor_card("HWP Dynamic Boost", "", "media-flash-symbolic", intel_data.get("hwp_dynamic_boost", "—"), "Intel", "tag-intel")
        card_min_perf = _build_monitor_card("Min Performance Limit", "", "go-down-symbolic", intel_data.get("min_perf_pct", "—"), "Intel", "tag-intel")
        card_max_perf = _build_monitor_card("Max Performance Limit", "", "go-up-symbolic", intel_data.get("max_perf_pct", "—"), "Intel", "tag-intel")

        _layout_grid_cards(intel_grid, [card_pstates, card_turbo, card_hwp_boost, card_min_perf, card_max_perf])
        
        # Wrap in PreferencesGroup with dashboard-group class
        grp_intel = Adw.PreferencesGroup()
        grp_intel.add_css_class("dashboard-group")
        grp_intel.add(intel_grid)
        main_box.append(grp_intel)

    # 4. Core Frequencies Grid
    main_box.append(_build_section_header("CPU Core Load & Speeds", "cpu-symbolic"))

    core_grid = Gtk.Grid()
    core_grid.set_column_homogeneous(True)
    core_grid.set_column_spacing(12)
    core_grid.set_row_spacing(12)
    core_grid.set_margin_bottom(24)

    clocks = system.get_live_cpu_clocks()
    app._core_freq_cards = []

    for idx, clk in enumerate(clocks):
        card = _build_frequency_card(f"Core {idx}", "cpu-symbolic", clk)
        app._core_freq_cards.append(card)
        col = idx % 2
        row = idx // 2
        core_grid.attach(card, col, row, 1, 1)

    main_box.append(core_grid)

    return scrolled


def _build_settings_page(app) -> Gtk.ScrolledWindow:
    """Build the core frequency controller and settings tuner page"""
    scrolled, main_box = _make_page_scaffold("settings", "Settings")

    caps = app.cpu_caps

    # 1. Main Tuning Parameters Section
    main_box.append(_build_section_header("Tune CPU Governor & Limits", "preferences-system-symbolic"))

    grp_tune = Adw.PreferencesGroup()
    grp_tune.set_description("Configure CPU frequency ranges and energy-efficiency behaviors")

    # Governor Dropdown Row
    gov_row = Adw.ComboRow()
    gov_row.set_title("CPU scaling governor")
    gov_row.set_subtitle("Defines policy algorithm used to scale frequencies")
    gov_row.set_icon_name("system-run-symbolic")

    governors = caps.get("governors", [])
    model_gov = Gtk.StringList.new(governors)
    gov_row.set_model(model_gov)

    current_gov = app.pending_settings.get("governor", caps.get("current_governor", ""))
    try:
        idx = governors.index(current_gov)
        gov_row.set_selected(idx)
    except ValueError:
        pass
    grp_tune.add(gov_row)
    app.settings_gov_row = gov_row

    # EPP Dropdown Row (If EPP is available on this system)
    epps = caps.get("epp_preferences", [])
    if not epps:
        epps = ["balance_performance", "performance", "power", "balance_power"]
    scaling_driver = caps.get("scaling_driver", "").lower()
    cpu_vendor = caps.get("cpu_vendor", "").lower()

    if "amd" in scaling_driver or cpu_vendor == "amd":
        epp_title = "AMD Energy Performance Preference (EPP)"
        epp_subtitle = (
            "Hint sent to AMD P-State firmware controlling the "
            "energy/performance balance for hardware-autonomous scaling"
        )
    else:
        epp_title = "Intel Energy Performance Preference (HWP)"
        epp_subtitle = (
            "Hint sent to Intel HWP firmware controlling the "
            "energy/performance balance for hardware-autonomous scaling"
        )

    epp_row = Adw.ComboRow()
    epp_row.set_title(epp_title)
    epp_row.set_subtitle(epp_subtitle)
    epp_row.set_icon_name("battery-symbolic")

    model_epp = Gtk.StringList.new(epps)
    epp_row.set_model(model_epp)

    if caps.get("epp_available"):
        current_epp = app.pending_settings.get("epp", caps.get("current_epp", ""))
        if current_epp not in epps:
            current_epp = caps.get("current_epp", "")
        try:
            idx = epps.index(current_epp)
            epp_row.set_selected(idx)
        except ValueError:
            epp_row.set_selected(0)

        if len(epps) == 1:
            epp_row.set_subtitle(
                epp_subtitle
                + " — only one option available with the current governor/driver mode"
            )
        app.settings_epp_row = epp_row
    else:
        epp_row.set_sensitive(False)
        epp_row.set_subtitle(
            epp_subtitle
            + " <span color='#e01b24' weight='bold' size='small'>(Unsupported on this CPU)</span>"
        )
        app.settings_epp_row = None

    grp_tune.add(epp_row)

    # EPB Slider Row (If available)
    if caps.get("epb_available"):
        epb_action_row = Adw.ActionRow()
        epb_action_row.set_title("Energy Performance Bias (EPB)")
        epb_action_row.set_subtitle("Intel power register bias. Range: 0 (Max Perf) to 15 (Max Power Saving)")
        epb_action_row.set_icon_name("battery-symbolic")

        current_epb = app.pending_settings.get("epb", caps.get("current_epb", 6))
        if current_epb is None:
            current_epb = 6

        epb_adj = Gtk.Adjustment(value=float(current_epb), lower=0.0, upper=15.0, step_increment=1.0, page_increment=3.0, page_size=0.0)
        epb_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=epb_adj)
        epb_scale.set_draw_value(True)
        epb_scale.set_value_pos(Gtk.PositionType.RIGHT)
        epb_scale.set_size_request(200, -1)
        epb_scale.set_valign(Gtk.Align.CENTER)

        epb_action_row.add_suffix(epb_scale)
        app.settings_epb_scale = epb_scale
        grp_tune.add(epb_action_row)
    else:
        app.settings_epb_scale = None

    # Boost Switch Row
    boost_row = Adw.SwitchRow()
    boost_row.set_title("Core Performance Boost / Turbo Boost")
    boost_row.set_subtitle("Allows cores to automatically speed up past standard stock limits if thermal budget allows")
    boost_row.set_icon_name("media-flash-symbolic")

    if caps.get("boost_supported"):
        saved_boost = app.pending_settings.get("boost", caps.get("boost_active", True))
        boost_row.set_active(saved_boost)
        app.settings_boost_row = boost_row
    else:
        boost_row.set_sensitive(False)
        boost_row.set_subtitle(
            "Allows cores to automatically speed up past standard stock limits if thermal budget allows "
            "<span color='#e01b24' weight='bold' size='small'>(Unsupported on this CPU)</span>"
        )
        app.settings_boost_row = None

    grp_tune.add(boost_row)
    main_box.append(grp_tune)

    # 2. Power Automation Profile Switcher
    main_box.append(_build_section_header("Power Automation", "battery-symbolic"))

    grp_automation = Adw.PreferencesGroup()
    grp_automation.set_description("Automatically switch profiles based on power supply charging state")

    switch_auto = Adw.SwitchRow()
    switch_auto.set_title("Auto-switch profiles on power change")
    switch_auto.set_subtitle("Automatically switch profiles when AC charger is plugged in or disconnected")
    switch_auto.set_icon_name("media-playlist-shuffle-symbolic")
    switch_auto.set_active(app.ui_settings.get("auto_switch", False))
    grp_automation.add(switch_auto)

    ac_row = Adw.ComboRow()
    ac_row.set_title("Plugged into AC Power")
    ac_row.set_subtitle("Profile applied when connected to charger")
    ac_row.set_icon_name("battery-full-charging-symbolic")
    grp_automation.add(ac_row)

    bat_row = Adw.ComboRow()
    bat_row.set_title("Running on Battery")
    bat_row.set_subtitle("Profile applied when running on battery")
    bat_row.set_icon_name("battery-symbolic")
    grp_automation.add(bat_row)

    main_box.append(grp_automation)

    def update_automation_dropdowns():
        profiles = list(sorted(settings.load_profiles().keys()))
        options = ["Stock (No Profile)", "⚡ Power Saving Preset", "🚀 Max Performance Preset"] + profiles
        option_keys = ["", "__power_saving__", "__max_performance__"] + profiles

        saved_ac = app.ui_settings.get("ac_profile", "")
        saved_bat = app.ui_settings.get("battery_profile", "")

        ac_row._option_keys = option_keys
        bat_row._option_keys = option_keys

        model_ac = Gtk.StringList.new(options)
        model_bat = Gtk.StringList.new(options)

        ac_row.set_model(model_ac)
        bat_row.set_model(model_bat)

        try:
            ac_idx = option_keys.index(saved_ac)
            ac_row.set_selected(ac_idx)
        except ValueError:
            ac_row.set_selected(0)

        try:
            bat_idx = option_keys.index(saved_bat)
            bat_row.set_selected(bat_idx)
        except ValueError:
            if not saved_bat and "__power_saving__" in option_keys:
                bat_row.set_selected(1)
            else:
                bat_row.set_selected(0)

    app.update_automation_dropdowns = update_automation_dropdowns
    update_automation_dropdowns()

    def on_auto_switch_toggled(switch_row, _spec):
        active = switch_row.get_active()
        app.ui_settings["auto_switch"] = active
        app._save_ui_settings()
        ac_row.set_sensitive(active)
        bat_row.set_sensitive(active)

    def on_ac_selected(row, _spec):
        idx = row.get_selected()
        if hasattr(row, "_option_keys") and idx < len(row._option_keys):
            app.ui_settings["ac_profile"] = row._option_keys[idx]
            app._save_ui_settings()

    def on_bat_selected(row, _spec):
        idx = row.get_selected()
        if hasattr(row, "_option_keys") and idx < len(row._option_keys):
            app.ui_settings["battery_profile"] = row._option_keys[idx]
            app._save_ui_settings()

    switch_auto.connect("notify::active", on_auto_switch_toggled)
    ac_row.connect("notify::selected", on_ac_selected)
    bat_row.connect("notify::selected", on_bat_selected)

    ac_row.set_sensitive(app.ui_settings.get("auto_switch", False))
    bat_row.set_sensitive(app.ui_settings.get("auto_switch", False))

    # 3. System and Tuning Startup Service Toggle
    main_box.append(_build_section_header("System and Tuning", "preferences-system-symbolic"))

    grp_service = Adw.PreferencesGroup()
    grp_service.set_description("Manage boot settings persistence and application cleanups")

    switch_startup = Adw.SwitchRow()
    switch_startup.set_title("Apply settings on startup")
    switch_startup.set_subtitle("Automatically write saved limits to CPU on system boot via official systemd service")
    switch_startup.set_icon_name("system-run-symbolic")
    switch_startup.set_active(settings.is_service_enabled())
    
    app.switch_startup = switch_startup
    switch_startup.connect("notify::active", app.on_startup_switch_toggled)
    grp_service.add(switch_startup)
    main_box.append(grp_service)

    # 4. About Section
    main_box.append(_build_section_header("About", "help-about-symbolic"))
    
    group_about = Adw.PreferencesGroup()
    group_about.set_title("Application Details")
    
    row_version = Adw.ActionRow()
    row_version.set_title("Version")
    row_version.set_subtitle(APP_VER)
    group_about.add(row_version)
    
    row_author = Adw.ActionRow()
    row_author.set_title("Developer")
    row_author.set_subtitle("Marley (marleylinux)")
    group_about.add(row_author)
    
    row_repo = Adw.ActionRow()
    row_repo.set_title("Repository")
    row_repo.set_subtitle("https://github.com/marleylinux/cpupower-gtk")
    
    btn_link = Gtk.Button(icon_name="document-open-symbolic")
    btn_link.set_tooltip_text("Open GitHub Repo")
    btn_link.set_valign(Gtk.Align.CENTER)
    btn_link.connect("clicked", lambda b: Gtk.show_uri(app.win, "https://github.com/marleylinux/cpupower-gtk", Gdk.CURRENT_TIME))
    row_repo.add_suffix(btn_link)
    group_about.add(row_repo)
    
    main_box.append(group_about)

    # 5. Factory Reset (Standalone placement matching Ryzenadj-gtk)
    btn_reset = Gtk.Button()
    btn_reset.set_tooltip_text("Wipe all settings, profiles, disable startup service, and revert to defaults")
    btn_reset.add_css_class("destructive-action")
    btn_reset.add_css_class("pill")
    btn_reset.set_margin_top(24)
    btn_reset.set_margin_bottom(16)
    btn_reset.set_halign(Gtk.Align.CENTER)
    
    btn_reset_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    btn_reset_icon = Gtk.Image.new_from_icon_name("edit-clear-all-symbolic")
    btn_reset_label = Gtk.Label(label="Factory Reset")
    btn_reset_content.append(btn_reset_icon)
    btn_reset_content.append(btn_reset_label)
    btn_reset.set_child(btn_reset_content)
    
    btn_reset.connect("clicked", app.on_factory_reset_clicked)
    main_box.append(btn_reset)

    return scrolled


def _build_profiles_page(app) -> Gtk.ScrolledWindow:
    """Build the profiles manager page to load and save custom tuning configurations"""
    scrolled, main_box = _make_page_scaffold("profiles", "Profiles")

    main_box.append(_build_section_header("Save Current Profile", "document-save-symbolic"))

    grp_save = Adw.PreferencesGroup()
    grp_save.set_description("Save your active frequency limit settings as a custom reusable profile")

    name_row = Adw.EntryRow()
    name_row.set_title("Profile Name")

    btn_save = Gtk.Button(label="Save Profile")
    btn_save.add_css_class("suggested-action")
    btn_save.add_css_class("pill")
    btn_save.set_valign(Gtk.Align.CENTER)

    name_row.add_suffix(btn_save)
    grp_save.add(name_row)
    main_box.append(grp_save)

    main_box.append(_build_section_header("Managed Profiles", "bookmarks-symbolic"))

    grp_list = Adw.PreferencesGroup()
    grp_list.set_description("Switch between your custom cpupower configuration profiles")
    main_box.append(grp_list)

    list_box = Gtk.ListBox()
    list_box.add_css_class("boxed-list")
    grp_list.add(list_box)

    app.profiles_listbox = list_box
    app.profile_name_row = name_row

    def refresh_profiles():
        while True:
            child = list_box.get_first_child()
            if not child:
                break
            list_box.remove(child)

        profiles = settings.load_profiles()
        if not profiles:
            empty_row = Adw.ActionRow()
            empty_row.set_title("No custom profiles saved yet")
            empty_row.set_subtitle("Name and save your active configurations above")
            list_box.append(empty_row)
            return

        for name in sorted(profiles.keys()):
            row = Adw.ActionRow()
            row.set_title(name)
            
            pdata = profiles[name]
            pdesc = f"Governor: {pdata.get('governor', 'Stock')}"
            if pdata.get("use_fixed_freq", False) and "fixed_freq" in pdata:
                pdesc += f" | Freq: Fixed {pdata['fixed_freq']/1000.0:.2f} GHz"
            elif "min_freq" in pdata and "max_freq" in pdata:
                pdesc += f" | Freq: {pdata['min_freq']/1000.0:.2f} – {pdata['max_freq']/1000.0:.2f} GHz"
            if pdata.get("boost") is not None:
                pdesc += " | Boost: On" if pdata["boost"] else " | Boost: Off"
            row.set_subtitle(pdesc)

            btn_apply = Gtk.Button(icon_name="object-select-symbolic")
            btn_apply.add_css_class("flat")
            btn_apply.set_tooltip_text(f"Apply '{name}' profile")
            btn_apply.set_valign(Gtk.Align.CENTER)

            def on_apply_prof(_b, pname=name):
                app.on_apply_custom_profile(pname)

            btn_apply.connect("clicked", on_apply_prof)
            row.add_suffix(btn_apply)

            btn_del = Gtk.Button(icon_name="user-trash-symbolic")
            btn_del.add_css_class("flat")
            btn_del.add_css_class("destructive-action")
            btn_del.set_tooltip_text(f"Delete '{name}' profile")
            btn_del.set_valign(Gtk.Align.CENTER)

            def on_del_prof(_b, pname=name):
                profs = settings.load_profiles()
                if pname in profs:
                    del profs[pname]
                    settings.save_profiles(profs)
                    refresh_profiles()
                    app._show_toast(f"Profile '{pname}' deleted.", is_error=False)
                    if app.update_automation_dropdowns:
                        app.update_automation_dropdowns()

            btn_del.connect("clicked", on_del_prof)
            row.add_suffix(btn_del)
            
            list_box.append(row)

    app.refresh_profiles = refresh_profiles
    refresh_profiles()

    def on_save_clicked(_btn):
        name = name_row.get_text().strip()
        if not name:
            app._show_toast("Profile name cannot be empty.", is_error=True)
            return

        active_settings = app.get_settings_from_ui()
        if not active_settings:
            app._show_toast("Failed to resolve current settings.", is_error=True)
            return

        profiles = settings.load_profiles()
        profiles[name] = active_settings
        settings.save_profiles(profiles)
        name_row.set_text("")
        refresh_profiles()
        app._show_toast(f"Profile '{name}' saved successfully.", is_error=False)
        if app.update_automation_dropdowns:
            app.update_automation_dropdowns()

    btn_save.connect("clicked", on_save_clicked)

    return scrolled

def _build_freq_slider_row(app, title, desc, param_key, lo, hi, current_live_val) -> Gtk.ListBoxRow:
    """Build a Ryzenadj-gtk-style frequency slider row with inline clear button and dynamic conflict checking."""
    row = Gtk.ListBoxRow()
    row.add_css_class("slider-row-item")
    row.set_selectable(False)
    row.set_activatable(False)

    main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    main_box.set_margin_start(16)
    main_box.set_margin_end(16)
    main_box.set_margin_top(12)
    main_box.set_margin_bottom(12)

    # ── Top row: flag label + CPU badge + live badge + clear btn ──
    top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

    text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    text_box.set_hexpand(True)

    flag_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

    title_label = Gtk.Label(xalign=0)
    title_label.set_markup(f"<span font_family='monospace' weight='bold' size='medium'>{title}</span>")
    title_label.add_css_class("slider-row-flag")
    flag_box.append(title_label)

    cpu_tag_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    cpu_tag_box.add_css_class("cpu-badge")
    cpu_tag_box.set_valign(Gtk.Align.CENTER)
    cpu_icon = Gtk.Image.new_from_icon_name("system-run-symbolic")
    cpu_icon.set_pixel_size(12)
    cpu_tag_box.append(cpu_icon)
    cpu_label = Gtk.Label(label="CPU")
    cpu_tag_box.append(cpu_label)
    flag_box.append(cpu_tag_box)
    text_box.append(flag_box)

    desc_label = Gtk.Label(xalign=0)
    desc_label.set_markup(f"<span style='italic' size='small'>{desc}</span>")
    desc_label.add_css_class("slider-row-desc")
    text_box.append(desc_label)
    top_box.append(text_box)

    # Live reading badge
    cur_text = f"Live: {current_live_val/1000.0:.2f} GHz" if current_live_val > 0.0 else "Live: —"
    cur_badge = Gtk.Label(label=cur_text)
    cur_badge.add_css_class("live-badge")
    cur_badge.set_tooltip_text("Live reading from hardware")
    cur_badge.set_valign(Gtk.Align.CENTER)
    top_box.append(cur_badge)

    # Clear button — removes this param from pending, reverts to Auto
    btn_clear = Gtk.Button(icon_name="edit-clear-symbolic")
    btn_clear.add_css_class("flat")
    btn_clear.set_tooltip_text("Clear — revert all limits to Auto (hardware default)")
    btn_clear.set_valign(Gtk.Align.CENTER)
    top_box.append(btn_clear)
    main_box.append(top_box)

    # ── Bottom row: step buttons + slider + target badge ──
    bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    bottom_box.set_margin_top(10)

    is_configured = param_key in app.pending_settings
    if is_configured:
        init_val = float(app.pending_settings[param_key])
    elif current_live_val > 0.0:
        init_val = max(lo, min(hi, current_live_val))
    else:
        init_val = float(lo)

    adj = Gtk.Adjustment(
        value=init_val, lower=lo, upper=hi,
        step_increment=100.0, page_increment=500.0, page_size=0,
    )
    slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
    slider.set_hexpand(True)
    slider.set_valign(Gtk.Align.CENTER)
    slider.set_draw_value(False)
    slider.set_round_digits(0)

    # Block scroll-wheel from accidentally nudging sliders
    scroll_controller = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
    scroll_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    scroll_controller.connect("scroll", lambda *args: True)
    slider.add_controller(scroll_controller)

    def adjust_slider(direction: int, steps: int):
        delta = 100.0 * steps
        a = slider.get_adjustment()
        slider.set_value(max(a.get_lower(), min(a.get_upper(), slider.get_value() + direction * delta)))

    def make_step_btn(label: str, direction: int, steps: int, tooltip: str) -> Gtk.Button:
        b = Gtk.Button(label=label)
        b.add_css_class("step-btn")
        b.set_tooltip_text(tooltip)
        b.set_valign(Gtk.Align.CENTER)
        b.connect("clicked", lambda _b: adjust_slider(direction, steps))
        return b

    btn_minus = Gtk.Button(icon_name="list-remove-symbolic")
    btn_minus.add_css_class("circular")
    btn_minus.add_css_class("flat")
    btn_minus.add_css_class("adj-btn")
    btn_minus.set_valign(Gtk.Align.CENTER)
    btn_minus.connect("clicked", lambda _b: adjust_slider(-1, 1))

    btn_plus = Gtk.Button(icon_name="list-add-symbolic")
    btn_plus.add_css_class("circular")
    btn_plus.add_css_class("flat")
    btn_plus.add_css_class("adj-btn")
    btn_plus.set_valign(Gtk.Align.CENTER)
    btn_plus.connect("clicked", lambda _b: adjust_slider(1, 1))

    btn_minus_500 = make_step_btn("−500", -1, 5, "−500 MHz")
    btn_minus_100 = make_step_btn("−100", -1, 1, "−100 MHz")
    btn_plus_100  = make_step_btn("+100",  1, 1, "+100 MHz")
    btn_plus_500  = make_step_btn("+500",  1, 5, "+500 MHz")

    target_badge = Gtk.Label()
    target_badge.add_css_class("target-badge")
    target_badge.set_valign(Gtk.Align.CENTER)
    target_badge.set_size_request(140, -1)

    bottom_box.append(btn_minus_500)
    bottom_box.append(btn_minus_100)
    bottom_box.append(btn_minus)
    bottom_box.append(slider)
    bottom_box.append(btn_plus)
    bottom_box.append(btn_plus_100)
    bottom_box.append(btn_plus_500)
    bottom_box.append(target_badge)
    main_box.append(bottom_box)
    row.set_child(main_box)

    row._updating_programmatically = False

    def update_val_label(scale, user_triggered=False):
        if getattr(row, "_updating_programmatically", False):
            return
        v = scale.get_value()

        if user_triggered:
            # If the user interacts with this slider, automatically clear the conflicting ones!
            if param_key == "fixed_freq":
                app.pending_settings.pop("min_freq", None)
                app.pending_settings.pop("max_freq", None)
            elif param_key in ("min_freq", "max_freq"):
                app.pending_settings.pop("fixed_freq", None)

            app.pending_settings[param_key] = float(v)

            # Update target badges of other rows if they were just cleared
            freq_keys = ["min_freq", "max_freq", "fixed_freq"]
            for key in freq_keys:
                if key != param_key:
                    row_widget = getattr(app, f"settings_{key.replace('_freq', '')}_row", None)
                    if row_widget:
                        row_widget._update_val_label(row_widget._slider, False)

        if user_triggered or param_key in app.pending_settings:
            target_badge.set_text(f"Target: {v/1000.0:.2f} GHz")
            app.pending_settings[param_key] = float(v)

            # Keep min <= max
            if user_triggered:
                if param_key == "min_freq" and hasattr(app, "settings_max_scale"):
                    if v > app.settings_max_scale.get_value():
                        max_row = getattr(app, "settings_max_row", None)
                        if max_row:
                            max_row._updating_programmatically = True
                            app.settings_max_scale.set_value(v)
                            max_row._updating_programmatically = False
                            max_row._update_val_label(app.settings_max_scale, True)
                elif param_key == "max_freq" and hasattr(app, "settings_min_scale"):
                    if v < app.settings_min_scale.get_value():
                        min_row = getattr(app, "settings_min_row", None)
                        if min_row:
                            min_row._updating_programmatically = True
                            app.settings_min_scale.set_value(v)
                            min_row._updating_programmatically = False
                            min_row._update_val_label(app.settings_min_scale, True)
        else:
            target_badge.set_text("Target: Auto")

        if hasattr(app, "_update_conflicts"):
            app._update_conflicts()

    def on_clear_clicked(_b):
        app.pending_settings.pop(param_key, None)

        row._updating_programmatically = True
        live_val = getattr(row, "_current_live_val", 0.0)
        if live_val > 0.0:
            row._slider.set_value(live_val)
        else:
            row._slider.set_value(row._slider.get_adjustment().get_lower())
        row._updating_programmatically = False
        row._update_val_label(row._slider, False)

        if hasattr(app, "_update_conflicts"):
            app._update_conflicts()

    slider.connect("value-changed", lambda s: update_val_label(s, True))
    btn_clear.connect("clicked", on_clear_clicked)

    row._update_val_label = update_val_label
    row._slider           = slider
    row._cur_badge        = cur_badge
    row._btn_clear        = btn_clear
    row._bottom_box       = bottom_box
    row._desc_label       = desc_label
    row._default_desc     = desc
    row._current_live_val = current_live_val

    # Initialise state
    update_val_label(slider, False)

    return row

def _build_frequency_page(app) -> Gtk.ScrolledWindow:
    """Build the CPU frequency range slider page with Ryzenadj-gtk-style per-row toggles."""
    scrolled, main_box = _make_page_scaffold("frequency", "Frequency")

    caps = app.cpu_caps
    phy_min = caps.get("cpuinfo_min", 0.0)
    if phy_min <= 0.0:
        phy_min = 600.0

    phy_max = caps.get("cpuinfo_max", 0.0)
    if phy_max <= 0.0:
        phy_max = 3000.0

    act_min = caps.get("scaling_min", 0.0)
    act_max = caps.get("scaling_max", 0.0)
    range_desc = f"Range: {phy_min/1000.0:.2f} – {phy_max/1000.0:.2f} GHz"

    # ── Section: Min / Max range ──────────────────────────────────────────────
    main_box.append(_build_section_header("Frequency Scaling Range", "system-run-symbolic"))

    grp_range = Adw.PreferencesGroup()
    grp_range.set_description("Set lower and upper clock speed boundaries. Values are saved and applied automatically.")
    main_box.append(grp_range)

    list_range = Gtk.ListBox()
    list_range.add_css_class("boxed-list")
    grp_range.add(list_range)

    min_row = _build_freq_slider_row(app, "--min-freq", range_desc, "min_freq", phy_min, phy_max, act_min)
    app.settings_min_scale = min_row._slider
    app.settings_min_row   = min_row
    list_range.append(min_row)

    max_row = _build_freq_slider_row(app, "--max-freq", range_desc, "max_freq", phy_min, phy_max, act_max)
    app.settings_max_scale = max_row._slider
    app.settings_max_row   = max_row
    list_range.append(max_row)

    # ── Section: Fixed frequency (replaces both min+max) ──────────────────────
    main_box.append(_build_section_header("Fixed Frequency Override", "media-flash-symbolic"))

    grp_fixed = Adw.PreferencesGroup()
    grp_fixed.set_description("Pin the CPU to one exact clock. This conflicts with and overrides the Min/Max range above.")
    main_box.append(grp_fixed)

    list_fixed = Gtk.ListBox()
    list_fixed.add_css_class("boxed-list")
    grp_fixed.add(list_fixed)

    fixed_row = _build_freq_slider_row(app, "--fixed-freq", range_desc, "fixed_freq", phy_min, phy_max, act_max)
    app.settings_fixed_scale = fixed_row._slider
    app.settings_fixed_row   = fixed_row
    list_fixed.append(fixed_row)

    return scrolled
