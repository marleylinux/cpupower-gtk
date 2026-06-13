# cpupower-gtk

GTK4 frontend for cpupower. Just lets you adjust CPU governors, frequency limits, EPP/EPB preferences, and boost states without living in the terminal.

It looks and works very similarly to my other tool, `Ryzenadj-gtk`.

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

## Installation

### Arch (makepkg)

```bash
git clone https://github.com/marleylinux/cpupower-gtk
cd cpupower-gtk
makepkg -si
```

### Other Distros (Installer Script)

```bash
git clone https://github.com/marleylinux/cpupower-gtk
cd cpupower-gtk
sudo ./install.sh
```

Then launch "cpupower-gtk" from your application menu or run `cpupower-gtk`.

### Uninstall

```bash
sudo ./uninstall.sh
```

## License

GPL-3.0

