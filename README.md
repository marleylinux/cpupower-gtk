<p align="center">
  <img src="src/assets/com.marley.cpupower-gtk.png" width="128" height="128" alt="cpupower-gtk logo" />
</p>

# cpupower-gtk

GTK4 frontend for cpupower. Just lets you adjust CPU governors, frequency limits, EPP/EPB preferences, and boost states without living in the terminal.

Powered by [cpupower](https://github.com/torvalds/linux/tree/master/tools/power/cpupower) ❤️

## What it does

- Dashboard showing active governor, driver, temperatures, and live core speeds
- Tune frequency limits dynamically (min/max range or fixed frequency override)
- Dynamic conflict resolution (adjusting one slider automatically clears conflicting settings, no grayed out inputs)
- Adjust energy preferences (EPP for AMD, EPB for Intel) based on what CPU you have
- Toggles for Core Boost / Intel Turbo Boost
- Save custom configuration profiles and switch between them easily
- Auto switch profiles when you plug or unplug the charger
- Works after sleep (restores your active settings automatically when the machine wakes up)
- Integrates directly with the official systemd `cpupower.service` to apply settings on boot
## Requirements

- Python 3.11+
- gtk4 + libadwaita + python-gobject
- cpupower installed

## Install

**Arch (easiest):**

```bash
yay -S cpupower-gtk
```

Or build from this repo:

```bash
git clone https://github.com/marleylinux/cpupower-gtk
```
```bash
cd cpupower-gtk
makepkg -si
```

**Other distros:**

```bash
git clone https://github.com/marleylinux/cpupower-gtk
```
```bash
cd cpupower-gtk
sudo ./install.sh
```

Then launch "cpupower-gtk" from your menu or just run `cpupower-gtk`.

## Uninstall

```bash
sudo ./uninstall.sh
```

## License

GPL-3.0

---

### Check out my other apps:

| [<img src="https://raw.githubusercontent.com/marleylinux/cpupower-gtk/main/src/assets/com.marley.cpupower-gtk.png" width="48" height="48" /><br/>cpupower-gtk](https://github.com/marleylinux/cpupower-gtk) | [<img src="https://raw.githubusercontent.com/marleylinux/Ryzenadj-gtk/main/src/assets/com.marley.ryzenadj-gtk.png" width="48" height="48" /><br/>Ryzenadj-gtk](https://github.com/marleylinux/Ryzenadj-gtk) | [<img src="https://raw.githubusercontent.com/marleylinux/FastFlowLM-gtk/main/src/assets/com.marley.FastFlowLM-gtk.png" width="48" height="48" /><br/>FastFlowLM-gtk](https://github.com/marleylinux/FastFlowLM-gtk) | [<img src="https://raw.githubusercontent.com/marleylinux/fetch-gtk/main/src/assets/com.marley.fetch-gtk.png" width="48" height="48" /><br/>fetch-gtk](https://github.com/marleylinux/fetch-gtk) |
|---|---|---|---|

