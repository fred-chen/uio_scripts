#!/usr/bin/env bash
# a very simple script to show results of a bisect perf test

LOG=$1

while read s 
do
  commit=`echo $s|awk '{print $4}'|awk 'BEGIN{FS="|"} {print $1}'`
  runlog=`echo $s|awk '{print $NF}'`
  echo "RUN:" $commit $runlog
  dir=`dirname $(find . -name $runlog)`/fio_output

  uio_scripts/client/showfio.py $dir
done < <(grep log: $LOG | grep IOPS:)
