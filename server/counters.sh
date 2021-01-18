#!/usr/bin/env bash
# usage: ./counters.sh [interval] [runtime]

runtime=36000  # how long, default 10 hours
interval=60    # how often, default every 60 seconds

[[ ! -z "$1" ]] && runtime=$1
[[ ! -z "$2" ]] && interval=$2

total=0
while true
do
  date
  arrayctl counters
  sleep $interval
  total=$((total+$interval))
  [[ $total -ge $runtime ]] && break
done
