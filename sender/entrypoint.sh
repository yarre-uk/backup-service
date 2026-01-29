#!/bin/bash
set -e

echo "Starting backup sender with 15-minute intervals..."

while true; do
    python sender.py --config /config.yml
    echo "Sleeping for 15 minutes..."
    sleep 900  # 15 minutes
done
