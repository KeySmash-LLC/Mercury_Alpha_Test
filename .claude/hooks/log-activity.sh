#!/bin/bash
# Logs all tool calls to Explorer/logs/ with clear job/contract attribution.
# Uses a session→job mapping so browser tools (which don't contain file paths)
# still get routed to the correct job/contract.

INPUT=$(cat)
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TODAY=$(date -u +%Y-%m-%d)
PROJECT_DIR="${CLAUDE_PROJECT_DIR}"
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
HOOK_EVENT=$(echo "$INPUT" | jq -r '.hook_event_name // empty')
MAPPING_DIR="${PROJECT_DIR}/.claude/hooks/.sessions"
LOG_DIR="${PROJECT_DIR}/logs"

mkdir -p "$MAPPING_DIR" "$LOG_DIR"

# Try to extract a job/contract folder from anywhere in the input (file paths, URLs, etc.)
JOB_SLUG=$(echo "$INPUT" | grep -oP 'data/(jobs|contracts)/\K[^/"+]+' | head -1)
DATA_TYPE=$(echo "$INPUT" | grep -oP 'data/\K(jobs|contracts)' | head -1)

# If we found a slug, save the session→slug mapping (include data type)
if [ -n "$JOB_SLUG" ] && [ -n "$SESSION_ID" ]; then
  echo "${DATA_TYPE}/${JOB_SLUG}" > "${MAPPING_DIR}/${SESSION_ID}"
fi

# If we didn't find a slug in this call, look up the cached mapping
if [ -z "$JOB_SLUG" ] && [ -n "$SESSION_ID" ] && [ -f "${MAPPING_DIR}/${SESSION_ID}" ]; then
  CACHED=$(cat "${MAPPING_DIR}/${SESSION_ID}")
  DATA_TYPE="${CACHED%%/*}"
  JOB_SLUG="${CACHED#*/}"
fi

# Build the "belongs to" label
if [ -n "$JOB_SLUG" ] && [ -n "$DATA_TYPE" ]; then
  BELONGS_TO="${DATA_TYPE}/${JOB_SLUG}"
else
  BELONGS_TO=null
fi

# All logs go to a single daily file in logs/
LOG_FILE="${LOG_DIR}/${TODAY}.jsonl"

# Write log entry with clear job/contract attribution
echo "$INPUT" | jq -c \
  --arg ts "$TIMESTAMP" \
  --arg event "$HOOK_EVENT" \
  --arg belongs_to "$BELONGS_TO" \
  '{
    timestamp: $ts,
    event: $event,
    belongs_to: (if $belongs_to == "null" then null else $belongs_to end),
    session: .session_id,
    tool: .tool_name,
    input: .tool_input,
    response: (if .tool_response then (.tool_response | tostring | if length > 500 then .[:500] + "...[truncated]" else . end) else null end)
  }' >> "$LOG_FILE" 2>/dev/null

exit 0
