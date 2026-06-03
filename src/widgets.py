"""UI elements, helper formatters, and card structures for cpupower-gtk"""
import logging
import platform
from gi.repository import Gtk

log = logging.getLogger(__name__)

_cpu_name_cache: str | None = None


def get_cpu_name() -> str:
    """Get CPU model name from cpuinfo and format it nicely"""
    global _cpu_name_cache
    if _cpu_name_cache is not None:
        return _cpu_name_cache
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "model name" in line:
                    name = line.split(":", 1)[1].strip()
                    if " w/" in name:
                        name = name.split(" w/", 1)[0]
                    if " with " in name:
                        name = name.split(" with ", 1)[0]
                    name = name.replace("Processor", "")
                    name = name.replace("CPU", "")
                    if len(name) > 35:
                        name = name[:32] + "..."
                    _cpu_name_cache = name.strip()
                    return _cpu_name_cache
    except Exception:
        pass
    _cpu_name_cache = platform.processor() or "CPU"
    return _cpu_name_cache





def _bar_class(fraction: float) -> str:
    """Determine progress bar coloring classes (from green to red)"""
    if fraction < 0.5:
        return "low"
    elif fraction < 0.8:
        return "medium"
    return "high"


def format_freq(freq: float | None) -> str:
    """Format a frequency value in MHz as a GHz string, or '—' if falsy."""
    return f"{freq / 1000.0:.2f}" if freq and freq > 0.0 else "—"


def _build_section_header(title: str, icon_name: str) -> Gtk.Box:
    """Create a standard styled section header with an icon"""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    box.add_css_class("section-title-box")

    icon = Gtk.Image.new_from_icon_name(icon_name)
    icon.add_css_class("category-icon")
    box.append(icon)

    label = Gtk.Label(label=title)
    label.add_css_class("section-title-label")
    box.append(label)

    return box


def _build_monitor_card(label: str, unit: str, icon_name: str, initial_value: str = "—", tag_text: str = None, tag_class: str = None) -> Gtk.Box:
    """Build a general statistics card for dashboard telemetry (e.g. Driver, Governor)"""
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    card.add_css_class("monitor-card")
    card.set_hexpand(True)

    top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    top_row.set_hexpand(True)

    icon = Gtk.Image.new_from_icon_name(icon_name)
    icon.add_css_class("monitor-icon")
    top_row.append(icon)

    name_lbl = Gtk.Label(label=label)
    name_lbl.add_css_class("monitor-name-label")
    name_lbl.set_halign(Gtk.Align.START)
    name_lbl.set_hexpand(True)
    top_row.append(name_lbl)
    
    if tag_text and tag_class:
        tag_lbl = Gtk.Label(label=tag_text)
        tag_lbl.add_css_class("monitor-tag-badge")
        tag_lbl.add_css_class(tag_class)
        tag_lbl.set_halign(Gtk.Align.END)
        top_row.append(tag_lbl)
        
    card.append(top_row)

    val_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    val_row.set_halign(Gtk.Align.START)
    val_row.set_margin_top(8)

    val_lbl = Gtk.Label(label=initial_value)
    val_lbl.add_css_class("monitor-value-label")
    val_row.append(val_lbl)

    if unit:
        unit_lbl = Gtk.Label(label=unit)
        unit_lbl.add_css_class("monitor-unit-label")
        unit_lbl.set_valign(Gtk.Align.END)
        unit_lbl.set_margin_bottom(6)
        val_row.append(unit_lbl)
    card.append(val_row)

    card._val_lbl = val_lbl
    return card


def _build_monitor_card_with_bar(label: str, unit: str, icon_name: str, max_limit: float = 100.0, tag_text: str = None, tag_class: str = None) -> Gtk.Box:
    """Build a stats card that includes a progress bar (e.g. Load, Frequency)"""
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    card.add_css_class("monitor-card")
    card.set_hexpand(True)

    top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    top_row.set_hexpand(True)

    icon = Gtk.Image.new_from_icon_name(icon_name)
    icon.add_css_class("monitor-icon")
    top_row.append(icon)

    name_lbl = Gtk.Label(label=label)
    name_lbl.add_css_class("monitor-name-label")
    name_lbl.set_halign(Gtk.Align.START)
    name_lbl.set_hexpand(True)
    top_row.append(name_lbl)

    if tag_text and tag_class:
        tag_lbl = Gtk.Label(label=tag_text)
        tag_lbl.add_css_class("monitor-tag-badge")
        tag_lbl.add_css_class(tag_class)
        tag_lbl.set_halign(Gtk.Align.END)
        top_row.append(tag_lbl)

    card.append(top_row)

    val_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    val_row.set_halign(Gtk.Align.START)
    val_row.set_margin_top(8)

    val_lbl = Gtk.Label(label="—")
    val_lbl.add_css_class("monitor-value-label")
    val_row.append(val_lbl)

    if unit:
        unit_lbl = Gtk.Label(label=unit)
        unit_lbl.add_css_class("monitor-unit-label")
        unit_lbl.set_valign(Gtk.Align.END)
        unit_lbl.set_margin_bottom(6)
        val_row.append(unit_lbl)
    card.append(val_row)

    bar = Gtk.ProgressBar()
    bar.add_css_class("usage-bar")
    bar.set_fraction(0.0)
    card.append(bar)

    card._val_lbl = val_lbl
    card._bar = bar
    card._max_limit = max_limit

    def update_val(new_val: float | None):
        if new_val is not None:
            card._val_lbl.set_text(f"{new_val:.1f}")
            frac = min(1.0, max(0.0, new_val / card._max_limit))
            card._bar.set_fraction(frac)
            card._bar.remove_css_class("low")
            card._bar.remove_css_class("medium")
            card._bar.remove_css_class("high")
            card._bar.add_css_class(_bar_class(frac))
        else:
            card._val_lbl.set_text("—")
            card._bar.set_fraction(0.0)

    card.update_val = update_val
    return card


def _build_frequency_card(label: str, icon_name: str, current_val: float | None) -> Gtk.Box:
    """Build a monitor card specifically for CPU core load & frequency tracking"""
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    card.add_css_class("monitor-card")
    card.set_hexpand(True)

    top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    top_row.set_hexpand(True)

    icon = Gtk.Image.new_from_icon_name(icon_name)
    icon.add_css_class("monitor-icon")
    top_row.append(icon)

    name_lbl = Gtk.Label(label=label)
    name_lbl.add_css_class("monitor-name-label")
    name_lbl.set_halign(Gtk.Align.START)
    name_lbl.set_hexpand(True)
    top_row.append(name_lbl)

    lim_lbl = Gtk.Label(label="Load: 0%")
    lim_lbl.add_css_class("monitor-limit-badge")
    lim_lbl.set_halign(Gtk.Align.END)
    top_row.append(lim_lbl)
    card.append(top_row)

    val_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    val_row.set_halign(Gtk.Align.START)
    val_row.set_margin_top(8)

    val_str = f"{current_val/1000.0:.2f}" if current_val is not None else "—"
    val_lbl = Gtk.Label(label=val_str)
    val_lbl.add_css_class("monitor-value-label")
    val_row.append(val_lbl)

    unit_lbl = Gtk.Label(label="GHz")
    unit_lbl.add_css_class("monitor-unit-label")
    unit_lbl.set_valign(Gtk.Align.END)
    unit_lbl.set_margin_bottom(6)
    val_row.append(unit_lbl)
    card.append(val_row)

    bar = Gtk.ProgressBar()
    bar.add_css_class("usage-bar")
    bar.set_fraction(0.0)
    bar.add_css_class("low")
    card.append(bar)

    card._val_lbl = val_lbl
    card._lim_lbl = lim_lbl
    card._bar = bar

    def update_core(freq: float | None, load: float | None):
        if freq is not None:
            card._val_lbl.set_text(f"{freq/1000.0:.2f}")
        else:
            card._val_lbl.set_text("—")
        
        if load is not None:
            card._lim_lbl.set_text(f"Load: {int(load)}%")
            frac = min(1.0, max(0.0, load / 100.0))
            card._bar.set_fraction(frac)
            card._bar.remove_css_class("low")
            card._bar.remove_css_class("medium")
            card._bar.remove_css_class("high")
            card._bar.add_css_class(_bar_class(frac))
        else:
            card._lim_lbl.set_text("Load: —")
            card._bar.set_fraction(0.0)

    card.update_core = update_core
    return card
