#!/usr/bin/env bash
import re
from datetime import datetime, timedelta

def parse_logs(log_files, target_timestamp):
    # Parse the input timestamp and convert to log file format
    target_time = datetime.strptime(target_timestamp, "%b-%d-%Y %I:%M:%S %p")
    start_time = target_time
    end_time = target_time + timedelta(seconds=13)

    # Convert the start and end times to the log file timestamp format
    log_time_format = "%b %d %H:%M:%S"
    start_time_str = start_time.strftime(log_time_format)
    end_time_str = end_time.strftime(log_time_format)

    time_pattern = re.compile(r"(\w{3} \d{2} \d{2}:\d{2}:\d{2})")  # Matches timestamps in log format
    matching_logs = []

    for file in log_files:
        with open(file, 'r') as f:
            for line in f:
                match = time_pattern.search(line)
                if match:
                    # Parse log line timestamp
                    log_time = datetime.strptime(match.group(1), log_time_format)
                    # Adjust the year to the target year (log format lacks year info)
                    log_time = log_time.replace(year=target_time.year)
                    if start_time <= log_time <= end_time:
                        matching_logs.append(line)

    return matching_logs


def main():
    # List of log files to process (adjust the path if needed)
    log_files = [
        "beacon.log", "beacon.log.1", "beacon.log.2", "beacon.log.3", "beacon.log.4",
        "beacon.log.5", "beacon.log.6", "beacon.log.7", "beacon.log.8", "beacon.log.9",
        "beacon.log.10"
    ]

    # Target timestamp to search for
    target_timestamp = input("Enter the timestamp (Apr-26-2025 06:06:24 PM): ")

    # Fetch logs around the given timestamp
    matching_logs = parse_logs(log_files, target_timestamp)

    # Print the matching logs
    print("\nMatching Logs:")
    for log in matching_logs:
        print(log, end='')


if __name__ == "__main__":
    main()


set -euo pipefail

# --- CONFIGURE THESE ---
BEACON_NODE="http://localhost:5052"
RELAY_URL="http://localhost:18550"
PUBKEY="0x80036144fcbe30ef66300c7ff0bd3beaab708f50b23ee941645143fda791eddea5b1e8a5e70128a8a0efd02d340a7186"
# -----------------------

if ! command -v jq &>/dev/null; then
  echo "Error: this script requires 'jq'." >&2
  exit 1
fi

# Get genesis time
genesis_time=$(curl -s "${BEACON_NODE}/eth/v1/beacon/genesis" | jq -r '.data.genesis_time')
now_ms=$(date +%s%3N)
genesis_ms=$(( genesis_time * 1000 ))

slot_duration_ms=12000
elapsed_ms=$(( now_ms - genesis_ms ))
current_slot=$(( elapsed_ms / slot_duration_ms ))
next_slot=$(( current_slot + 1 ))
next_slot_start_ms=$(( genesis_ms + next_slot * slot_duration_ms ))
ms_until_next_slot=$(( next_slot_start_ms - now_ms + 110))

if (( ms_until_next_slot > 0 )); then
  echo "⏳ Waiting ${ms_until_next_slot}ms for start of slot $next_slot..."
  sleep_sec=$(awk "BEGIN { print $ms_until_next_slot / 1000 }")
  sleep "$sleep_sec"
fi

# Measure slot entry time
slot_entry_ms=$(date +%s%3N)

# Fetch parent root (for the upcoming slot, head still works)
echo "⏳ Fetching head header..."
resp=$(curl -s "${BEACON_NODE}/eth/v2/beacon/blocks/head")
parent_root=$(jq -r '.data.message.body.execution_payload.parent_hash' <<<"$resp")

echo "✅ Slot:        $next_slot"
echo "✅ Parent root: $parent_root"

endpoint="${RELAY_URL}/eth/v1/builder/header/${next_slot}/${parent_root}/${PUBKEY}"
echo "⏳ Querying relay builder endpoint..."

# Make request and track timing
raw=$(curl -s -w "\n%{http_code}" -X GET "$endpoint" -H "Accept: application/json")
http_code=$(tail -n1 <<<"$raw")
body=$(sed '$d' <<<"$raw")

# Timing after relay call
now_after=$(date +%s%3N)
ms_into_slot=$(( now_after - slot_entry_ms ))

echo "🕒 Time into slot: ${ms_into_slot}ms"
if (( ms_into_slot > 2000 )); then
  echo "⚠️  Late in slot, skipping relay request (ms_into_slot=$ms_into_slot > 2000)"
  exit 0
fi

echo "HTTP status: $http_code"
echo "Raw response body:"
echo "$body" | sed 's/^/  /'

if [[ "$http_code" =~ ^2[0-9][0-9]$ ]]; then
  echo "⏳ Parsing JSON…"
  echo "$body" | jq .
else
  echo "❌ Relay returned an error (status $http_code). See raw output above." >&2
  exit 1
fi

echo "🚀 Done."
