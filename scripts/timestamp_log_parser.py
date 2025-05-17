# AI assited (gpt o3)
"""
proposer_log_aggregator.py
--------------------------

Scan a Lighthouse/Nimbus validator-client log window and emit **one** CSV row
per invocation that consolidates all proposer-related events:

* `relay_response_ms`, `relay_reveal_ms`, `broadcast_delay_ms` → **average**
* `local_response_ms`                                         → **max**
* `final_status`                                              → “included” if we
  ever saw a “Signed block received” line, else “not_included”.

Usage
=====
    python proposer_log_aggregator.py \
        "Apr-23-2025 07:25:25 PM" output.csv --window 15

The default `log_files` list can be edited below or replaced via `--logs`.
"""

import argparse
import csv
import re
from collections import defaultdict
import requests
from datetime import datetime, timedelta
from statistics import mean
from pathlib import Path
import json


# --------------------------------------------------------------------------- #
#  Core parser/aggregator                                                     #
# --------------------------------------------------------------------------- #
def parse_window_and_aggregate(log_files, target_timestamp, window_secs=15, slot=0):
    """
    Return ONE aggregated dict for all lines within ±window_secs of
    target_timestamp (string in “%b-%d-%Y %I:%M:%S %p”, e.g. “Apr-23-2025 07:25:25 PM”).
    """

    target_dt = datetime.strptime(target_timestamp, "%b-%d-%Y %I:%M:%S %p")
    start_dt  = target_dt - timedelta(seconds=window_secs)
    end_dt    = target_dt + timedelta(seconds=window_secs)

    # ---- helpers ----------------------------------------------------------- #

    # Relay checking functionality
    def check_relays(slot):
        relay_name = ""
        relays = [
            {"name": "hoodi.flashbots", "url": f"https://boost-relay-hoodi.flashbots.net/relay/v1/data/bidtraces/proposer_payload_delivered?slot={slot}"},
            {"name": "hoodi.aestus", "url": f"https://hoodi.aestus.live/relay/v1/data/bidtraces/proposer_payload_delivered?slot={slot}"},
            {"name": "hoodi.titanrelay", "url": f"https://hoodi.titanrelay.xyz/relay/v1/data/bidtraces/proposer_payload_delivered?slot={slot}"},
            {"name": "bloxroute.hoodi", "url": f"https://bloxroute.hoodi.blxrbdn.com/relay/v1/data/bidtraces/proposer_payload_delivered?slot={slot}"}
        ]

        for relay in relays:
            try:
                response = requests.get(relay["url"])
                if response.status_code == 200:
                    try:
                        data = response.json()  # Parse the response as JSON
                        if isinstance(data, list) and data:  # Check if it's a non-empty list
                            relay_name = relay["name"]
                            print(f"Relay {relay['name']} responded successfully with valid data.")
                        else:
                            print(f"Relay {relay['name']} responded successfully but the response is empty or invalid.")
                    except json.JSONDecodeError:
                        print(f"Relay {relay['name']} responded successfully but the response is not valid JSON.")
                else:
                    print(f"Relay {relay['name']} responded with status code {response.status_code}.")
            except Exception as e:
                print(f"Error checking relay {relay['name']}: {e}")
        return relay_name
        
    ts_pat   = re.compile(r"^(?P<ts>\w{3} \d{2} \d{2}:\d{2}:\d{2})")
    num_pat  = lambda k: re.compile(fr"{k}: (\d+)")
    hash_pat = lambda k: re.compile(fr"{k}: (0x[0-9a-fA-F]+)")

    delay_fields = ("relay_response_ms", "relay_reveal_ms", "broadcast_delay_ms")
    sums, counts = defaultdict(int), defaultdict(int)     # for averages
    local_max    = 0

    agg = {
        "slot": "",
        "request_ts": "",
        "parent_hash": "",
        "block_root": "",
        "local_block_hash": "",
        "relay_block_hash": "",
        "final_status": "not_included",  # default
        "local_response_ms": "",
        "relay_response_ms": "",
        "relay_reveal_ms": "",
        "broadcast_delay_ms": "",
        "relay_success": "F",
        "relay": ""
    }

    # ---- scan files -------------------------------------------------------- #
    for lf in log_files:
        if not Path(lf).is_file():
            continue                                       # skip missing files
        with open(lf, encoding="utf-8", errors="ignore") as f:
            for line in f:
                m_ts = ts_pat.match(line)
                if not m_ts:
                    continue
                ts_str = m_ts.group("ts")
                log_dt = datetime.strptime(ts_str, "%b %d %H:%M:%S").replace(
                    year=target_dt.year
                )
                if not (start_dt <= log_dt <= end_dt):
                    continue

                # -------- Broadcast delay --------------------------------- #
                elif "Block broadcast was delayed" in line:
                    if (m := num_pat("delay_ms").search(line)):
                        sums["broadcast_delay_ms"]  += int(m.group(1))
                        counts["broadcast_delay_ms"] += 1

                # -------- Requested blinded execution payload ------------- #
                if "Requested blinded execution payload" in line:
                    agg.setdefault("request_ts", ts_str)
                    if (m := hash_pat("parent_hash").search(line)):
                        agg.setdefault("parent_hash", m.group(1))

                    if (m := num_pat("local_response_ms").search(line)):
                        local_max = max(local_max, int(m.group(1)))

                    if (m := num_pat("relay_response_ms").search(line)):
                        sums["relay_response_ms"]  += int(m.group(1))
                        counts["relay_response_ms"] += 1

                # -------- Received local and builder payloads ------------- #
                elif "Received local and builder payloads" in line:
                    if (m := hash_pat("local_block_hash").search(line)):
                        agg.setdefault("local_block_hash", m.group(1))
                    if (m := hash_pat("relay_block_hash").search(line)):
                        agg.setdefault("relay_block_hash", m.group(1))
                        
                # -------- Builder successfully revealed payload ----------- #
                elif "Builder successfully revealed payload" in line:
                    if (m := hash_pat("block_root").search(line)):
                        agg.setdefault("block_root", m.group(1))
                    if (m := num_pat("relay_response_ms").search(line)):
                        sums["relay_reveal_ms"]  += int(m.group(1))
                        counts["relay_reveal_ms"] += 1
                        agg["relay_success"] = "T"
                        agg["relay"] = check_relays(slot)

                # -------- Signed block received in HTTP API -------------- #
                elif "Signed block received in HTTP API" in line:
                    agg["final_status"] = "included"

    # ---- finalise numeric aggregations ------------------------------------ #
    for fld in delay_fields:
        if counts[fld]:
            agg[fld] = str(round(sums[fld] / counts[fld], 2))
    agg["local_response_ms"] = str(local_max)
    agg["slot"]=str(slot)

    return agg


# --------------------------------------------------------------------------- #
#  Main CLI                                                                   #
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(
        description="Aggregate proposer-window delays into one CSV row."
    )
    parser.add_argument(
        "timestamp",
        help='Target timestamp, e.g. "Apr-23-2025 07:25:25 PM" (in node local time)',
    )
    parser.add_argument("output_csv", help="Output CSV file path")
    
    parser.add_argument("slot", help="Slot number")
    
    parser.add_argument(
        "--window",
        type=int,
        default=15,
        help="Seconds before/after timestamp to include (default: 15)",
    )
    parser.add_argument(
        "--logs",
        nargs="+",
        metavar="FILE",
        help="Log files to scan (default: hard-coded list below)",
    )
    args = parser.parse_args()

    default_logs = [
        "beacon.log",
        "beacon.log.1",
        "beacon.log.2",
        "beacon.log.3",
        "beacon.log.4",
        "beacon.log.5",
        "beacon.log.6",
        "beacon.log.7",
        "beacon.log.8",
        "beacon.log.9",
        "beacon.log.10"
    ]

    log_files = args.logs if args.logs else default_logs

    agg = parse_window_and_aggregate(log_files, args.timestamp, args.window, args.slot)
    if not agg:
        print("No matching lines found in the requested window.")
        return

    headers = [
        "slot",
        "request_ts",
        "parent_hash",
        "block_root",
        "local_block_hash",
        "relay_block_hash",
        "final_status",
        "local_response_ms",
        "relay_response_ms",
        "relay_reveal_ms",
        "broadcast_delay_ms",
        "relay_success",
        "relay",
    ]
    headers = [h for h in headers if h in agg]  # drop cols we didn't find

    with open(args.output_csv, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        writer.writerow(agg)

    print(f"Wrote aggregated record to {args.output_csv}")


if __name__ == "__main__":
    main()
