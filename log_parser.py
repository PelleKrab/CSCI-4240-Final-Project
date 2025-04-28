# AI assisted (gpt o3)

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
