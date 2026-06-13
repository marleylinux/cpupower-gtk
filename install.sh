#!/bin/bash
# cpupower-gtk installer
# run with: sudo ./install.sh

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo ./install.sh)"
  exit 1
fi

echo "==> Installing cpupower-gtk..."

INSTALL_DIR="/usr/share/cpupower-gtk"
BIN_DIR="/usr/bin"
APP_DIR="/usr/share/applications"

# make the folders we need
mkdir -p "$INSTALL_DIR"
mkdir -p "$APP_DIR"

# copy python files and assets and set up permissions
echo "  -> Copying Python files and assets..."
cp src/*.py "$INSTALL_DIR/"
cp -r src/assets "$INSTALL_DIR/"
chmod 644 "$INSTALL_DIR"/*.py
chmod 755 "$INSTALL_DIR/app.py"
chmod 755 "$INSTALL_DIR/backend.py"
find "$INSTALL_DIR/assets" -type d -exec chmod 755 {} +
find "$INSTALL_DIR/assets" -type f -exec chmod 644 {} +

# copy the app icons to the system icon folder
for size in 256 512; do
    ICON_DIR="/usr/share/icons/hicolor/${size}x${size}/apps"
    mkdir -p "$ICON_DIR"
    cp src/assets/com.marley.cpupower-gtk.png "$ICON_DIR/com.marley.cpupower-gtk.png"
    chmod 644 "$ICON_DIR/com.marley.cpupower-gtk.png"
done

# Install desktop entry
echo "  -> Installing .desktop file..."
cp com.marley.cpupower-gtk.desktop "$APP_DIR/com.marley.cpupower-gtk.desktop"
chmod 644 "$APP_DIR/com.marley.cpupower-gtk.desktop"

# create launcher
echo "  -> Creating launcher..."
cat > "$BIN_DIR/cpupower-gtk" << EOF
#!/bin/sh
export PYTHONPATH="$INSTALL_DIR:\$PYTHONPATH"
exec python3 "$INSTALL_DIR/app.py" "\$@"
EOF
chmod 755 "$BIN_DIR/cpupower-gtk"

# update databases
update-desktop-database -q 2>/dev/null || true
gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true

# systemd service override drop-in
echo "  -> Installing systemd service override..."
mkdir -p /usr/lib/systemd/system/cpupower.service.d
cp cpupower-gtk.conf /usr/lib/systemd/system/cpupower.service.d/cpupower-gtk.conf
chmod 644 /usr/lib/systemd/system/cpupower.service.d/cpupower-gtk.conf

# systemd sleep hook
echo "  -> Installing systemd sleep hook..."
mkdir -p /usr/lib/systemd/system-sleep
cp cpupower-gtk-sleep /usr/lib/systemd/system-sleep/cpupower-gtk
chmod 755 /usr/lib/systemd/system-sleep/cpupower-gtk


# Install polkit policy
echo "  -> Installing Polkit policy..."
mkdir -p /usr/share/polkit-1/actions
cp com.marley.cpupower-gtk.policy /usr/share/polkit-1/actions/
chmod 644 /usr/share/polkit-1/actions/com.marley.cpupower-gtk.policy

# clean up legacy service if present
if [ -f /usr/lib/systemd/system/cpupower-gtk-apply.service ]; then
    echo "  -> Cleaning up legacy cpupower-gtk-apply.service..."
    systemctl disable --now cpupower-gtk-apply.service 2>/dev/null || true
    rm -f /usr/lib/systemd/system/cpupower-gtk-apply.service
fi

# clean up legacy sudoers file if present
if [ -f /etc/sudoers.d/cpupower-gtk ]; then
    echo "  -> Cleaning up legacy sudoers drop-in..."
    rm -f /etc/sudoers.d/cpupower-gtk
fi

systemctl daemon-reload

echo ""
echo "==> Installation complete!"
echo "    Launch 'cpupower-gtk' from your application menu, or run: cpupower-gtk"
echo ""

if [ -t 0 ]; then
    read -p "Press Enter to exit..."
fi
