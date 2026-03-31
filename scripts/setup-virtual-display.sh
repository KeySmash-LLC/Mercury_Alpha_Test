#!/bin/bash
set -euo pipefail

# ============================================================
# Setup Xvfb virtual display + x11vnc for headless browser automation
# Run: sudo -E bash Explorer/scripts/setup-virtual-display.sh
#
# After running:
#   - Xvfb runs on :99 as a systemd service (survives reboots)
#   - x11vnc listens on port 5900 for VNC connections
#   - Pipeline auto-uses :99 (no monitor needed)
#   - VNC in from phone/laptop to watch browsers live
# ============================================================

DISPLAY_NUM=99
VNC_PORT=5900
RESOLUTION="1920x1080x24"

echo "=== Installing packages ==="

for pkg in xorg-server-xvfb x11vnc; do
  if ! pacman -Qi "$pkg" &>/dev/null; then
    echo "Installing $pkg..."
    pacman -S --noconfirm "$pkg"
  else
    echo "$pkg already installed"
  fi
done

echo ""
echo "=== Creating Xvfb systemd service ==="

cat > /etc/systemd/system/xvfb.service <<EOF
[Unit]
Description=X Virtual Frame Buffer on :${DISPLAY_NUM}
After=network.target

[Service]
ExecStart=/usr/bin/Xvfb :${DISPLAY_NUM} -screen 0 ${RESOLUTION} -ac +extension GLX +render -noreset
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable xvfb
systemctl restart xvfb
echo "xvfb: $(systemctl is-active xvfb) on :${DISPLAY_NUM}"

echo ""
echo "=== Creating x11vnc systemd service ==="

cat > /etc/systemd/system/x11vnc.service <<EOF
[Unit]
Description=x11vnc VNC server for :${DISPLAY_NUM}
After=xvfb.service
Requires=xvfb.service

[Service]
ExecStart=/usr/bin/x11vnc -display :${DISPLAY_NUM} -forever -shared -nopw -rfbport ${VNC_PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable x11vnc
systemctl restart x11vnc
echo "x11vnc: $(systemctl is-active x11vnc) on port ${VNC_PORT}"

echo ""
echo "=== Setting DISPLAY=:${DISPLAY_NUM} in shell profile ==="

SHELL_RC="$HOME/.bashrc"
if [ -n "${ZSH_VERSION:-}" ] || [ -f "$HOME/.zshrc" ]; then
  SHELL_RC="$HOME/.zshrc"
fi

if ! grep -q "DISPLAY=:${DISPLAY_NUM}" "$SHELL_RC" 2>/dev/null; then
  echo "" >> "$SHELL_RC"
  echo "# Virtual display for headless browser automation" >> "$SHELL_RC"
  echo "export DISPLAY=:${DISPLAY_NUM}" >> "$SHELL_RC"
  echo "Added DISPLAY=:${DISPLAY_NUM} to $SHELL_RC"
else
  echo "DISPLAY=:${DISPLAY_NUM} already in $SHELL_RC"
fi

echo ""
echo "=== Done ==="
echo ""
echo "Services running:"
echo "  Xvfb    :${DISPLAY_NUM}  (virtual display — survives screen off, reboots)"
echo "  x11vnc  :${VNC_PORT}   (VNC server — watch browsers live)"
echo ""
echo "VNC connect from your phone/laptop:"
if command -v tailscale &>/dev/null && tailscale status &>/dev/null; then
  TS_IP=$(tailscale ip -4 2>/dev/null || echo "<tailscale-ip>")
  echo "  vnc://${TS_IP}:${VNC_PORT}"
else
  echo "  vnc://<your-ip>:${VNC_PORT}"
fi
echo ""
echo "NOTE: VNC has no password (-nopw). This is fine over Tailscale."
echo "      If exposed to the internet, re-run with a password:"
echo "      x11vnc -storepasswd && edit the service to add -usepw"
echo ""
echo "Restart your shell or run: export DISPLAY=:${DISPLAY_NUM}"
