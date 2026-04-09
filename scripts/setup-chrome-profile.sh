#!/usr/bin/env bash
# Launch Chrome with the automation profile so you can log into job sites.
# The playwright multiplexer copies auth from this profile for each browser instance.
#
# Usage: ./scripts/setup-chrome-profile.sh
#
# Log into these sites, then close Chrome:
#   - LinkedIn (linkedin.com)
#   - Indeed (indeed.com)
#   - Upwork (upwork.com)
#   - Any other job boards you use

PROFILE_DIR="${CHROME_AUTOMATION_PROFILE:-$HOME/.config/chrome-automation}"
ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"

# ---------------------------------------------------------------------------
# Generate a unique analytics ID if one isn't set yet
# ---------------------------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
    echo "Warning: .env not found — run 'cp .env.example .env' first, then re-run this script."
    echo ""
else
    current_id=$(grep -E "^POSTHOG_DISTINCT_ID=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '[:space:]')
    if [ -z "$current_id" ]; then
        new_id=$(python3 -c "import uuid; print(uuid.uuid4())")
        if grep -q "^POSTHOG_DISTINCT_ID=" "$ENV_FILE"; then
            sed -i "s/^POSTHOG_DISTINCT_ID=.*/POSTHOG_DISTINCT_ID=$new_id/" "$ENV_FILE"
        else
            echo "" >> "$ENV_FILE"
            echo "POSTHOG_DISTINCT_ID=$new_id" >> "$ENV_FILE"
        fi
        echo "Analytics ID generated and saved to .env: $new_id"
    else
        echo "Analytics ID already set: $current_id"
    fi
    echo ""
fi

echo "Launching Chrome with profile: $PROFILE_DIR"
echo ""
echo "Log into your job sites (LinkedIn, Indeed, Upwork, etc.)"
echo "Then close Chrome to save the profile."
echo ""

google-chrome-stable --user-data-dir="$PROFILE_DIR" \
  --no-first-run \
  --no-default-browser-check \
  "https://www.linkedin.com/login" \
  "https://secure.indeed.com/auth" \
  "https://www.upwork.com/ab/account-security/login" 2>/dev/null
