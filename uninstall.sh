#!/bin/bash
# cpupower-gtk uninstaller
# run with: sudo ./uninstall.sh

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo ./uninstall.sh)"
  exit 1
fi

echo "==> Removing cpupower-gtk..."

rm -rf /usr/share/cpupower-gtk
rm -f  /usr/bin/cpupower-gtk
rm -f  /usr/share/applications/com.marley.cpupower-gtk.desktop
for size in 256 512; do
    rm -f "/usr/share/icons/hicolor/${size}x${size}/apps/com.marley.cpupower-gtk.png"
done

# remove systemd service override
echo "  -> Removing systemd service override..."
rm -f /usr/lib/systemd/system/cpupower.service.d/cpupower-gtk.conf
rmdir /usr/lib/systemd/system/cpupower.service.d 2>/dev/null || true

# clean up legacy service if present
if [ -f /usr/lib/systemd/system/cpupower-gtk-apply.service ]; then
    echo "  -> Removing legacy systemd service..."
    systemctl disable cpupower-gtk-apply.service 2>/dev/null || true
    rm -f /usr/lib/systemd/system/cpupower-gtk-apply.service
fi

# clean up legacy sudoers file if present
if [ -f /etc/sudoers.d/cpupower-gtk ]; then
    echo "  -> Removing legacy sudoers drop-in..."
    rm -f /etc/sudoers.d/cpupower-gtk
fi

systemctl daemon-reload

# remove polkit policy
echo "  -> Removing Polkit policy..."
rm -f /usr/share/polkit-1/actions/com.marley.cpupower-gtk.policy

update-desktop-database -q 2>/dev/null || true
gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true

echo "==> Uninstall complete."
