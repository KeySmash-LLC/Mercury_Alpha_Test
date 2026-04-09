#!/bin/bash
set -euo pipefail

# ============================================================
# One-time setup for remote pipeline triggering
# Run: sudo -E bash ~/scripts/setup-remote-pipeline.sh
# ============================================================

echo "=== Installing dependencies ==="

# tmux for detached sessions
if ! command -v tmux &>/dev/null; then
  echo "Installing tmux..."
  pacman -S --noconfirm tmux
else
  echo "tmux already installed"
fi

# tailscale for secure remote access
if ! command -v tailscale &>/dev/null; then
  echo "Installing tailscale..."
  pacman -S --noconfirm tailscale
else
  echo "tailscale already installed"
fi

echo ""
echo "=== Enabling services ==="

# Enable and start sshd
systemctl enable sshd
systemctl start sshd
echo "sshd: $(systemctl is-active sshd)"

# Enable and start tailscale
systemctl enable tailscaled
systemctl start tailscaled
echo "tailscaled: $(systemctl is-active tailscaled)"

echo ""
echo "=== Tailscale login ==="
if ! tailscale status &>/dev/null; then
  echo "Opening Tailscale login (follow the URL)..."
  tailscale up
else
  echo "Tailscale already connected"
  tailscale ip -4
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Your Tailscale IP:"
tailscale ip -4
echo ""
echo "From your phone:"
echo "  1. Install Tailscale app on your phone"
echo "  2. Log in with the same account"
echo "  3. Install an SSH app (Termux on Android, Blink Shell on iOS)"
echo "  4. SSH in:  ssh $(whoami)@$(tailscale ip -4)"
echo "  5. Run:     pipeline 10"
echo ""
echo "Subscribe to notifications:"
echo "  Open https://ntfy.sh/explorer-$(whoami) on your phone"
echo "  Or install the ntfy app and subscribe to: explorer-$(whoami)"
