#!/usr/bin/env python
'''
    python version of showfio.sh
    show fio JSON format output
    requirements:
      - jq installed
    Maintainer: Fred Chen
'''

import os, sys, json
sys.path.append('%s/../cctf/cctf' % (os.path.dirname(os.path.realpath(__file__))))
import me

def E(msg):
    sys.stderr.write("Error: {0}\n".format(msg))
    exit(1)

def parse(path):
    if not os.path.exists(path):
        E("'{}' doesn't exist.".format(path))
    err = me.getint("egrep 'error=' {0} | wc -l".format(path))
    
    f = open(path)
    lines = f.readlines()
    for i in range(len(lines)):
        if lines[i].strip() == "{":
            break
    lines = lines[i:]

    j = None
    try:
        j = json.loads("".join(lines))
    except:
        E("can't parse json: {}".format(path))
    

    ALL_READ_IOPS = 0
    ALL_READ_BW = 0
    ALL_READ_IOS = 0
    ALL_READ_LAT = 0
    ALL_WRITE_IOPS = 0
    ALL_WRITE_BW = 0
    ALL_WRITE_IOS = 0
    ALL_WRITE_LAT = 0
    TOTAL_IOS = 0
    TOTAL_LAT = 0
    TOTAL_IOPS = 0
    TOTAL_BW = 0
    AVG_LAT = 0
    AVG_READ_LAT = 0
    AVG_WRITE_LAT = 0
    
    client_stats = j["client_stats"]
    hostnames = []
    for cs in client_stats:


# num_entries=`egrep -v $filterstr $n | jq '.client_stats[] | select(.jobname != "All clients") | .hostname' 2>/dev/null | wc -l`
# if [ $num_entries = 0 ]; then
# num_entries=`egrep -v $filterstr $n | jq '.jobs[].jobname' 2>/dev/null | wc -l`
# entry_name="jobs"
# itemname="jobname"
# else
# entry_name="client_stats"
# itemname="hostname"
# fi
# echo $n[$ERR_STAT]:
# echo =============================================================
# for h in `seq 0 $(($num_entries-1))`
# do
# host=`cat $n | egrep -v $filterstr | jq .$entry_name[$h].$itemname`
# r_iops=`cat $n | egrep -v $filterstr | jq .$entry_name[$h].read.iops` && r_iops=${r_iops%.*}
# r_bw_bytes=`cat $n | egrep -v $filterstr | jq .$entry_name[$h].read.bw_bytes` && r_bw_megabytes=$((r_bw_bytes / 1024 /1024 ))
# r_lat=`cat $n | egrep -v $filterstr | jq .$entry_name[$h].read.lat_ns.mean` && r_lat=${r_lat%.*} && r_lat=$((r_lat / 1000))
# r_ios=`cat $n | egrep -v $filterstr | jq .$entry_name[$h].read.total_ios`

# w_iops=`cat $n | egrep -v $filterstr | jq .$entry_name[$h].write.iops` && w_iops=${w_iops%.*}
# w_bw_bytes=`cat $n | egrep -v $filterstr | jq .$entry_name[$h].write.bw_bytes` && w_bw_megabytes=$((w_bw_bytes / 1024 /1024 ))
# w_lat=`cat $n | egrep -v $filterstr | jq .$entry_name[$h].write.lat_ns.mean` && w_lat=${w_lat%.*} && w_lat=$((w_lat / 1000))
# w_ios=`cat $n | egrep -v $filterstr | jq .$entry_name[$h].write.total_ios`

# r_job_runtime=`cat $n | egrep -v $filterstr | jq .$entry_name[$h].read.runtime` && r_job_runtime=$((r_job_runtime / 1000))
# w_job_runtime=`cat $n | egrep -v $filterstr | jq .$entry_name[$h].write.runtime` && w_job_runtime=$((w_job_runtime / 1000))
# if [ $r_job_runtime -ge $w_job_runtime ]; then
#   job_runtime=$r_job_runtime
# else
#   job_runtime=$w_job_runtime
# fi

# ALL_READ_IOPS=$((ALL_READ_IOPS+r_iops))
# ALL_READ_BW=$((ALL_READ_BW+r_bw_megabytes))
# ALL_READ_IOS=$((ALL_READ_IOS+r_ios))
# ALL_READ_LAT=$((ALL_READ_LAT+r_lat*r_ios))
# ALL_WRITE_IOPS=$((ALL_WRITE_IOPS+w_iops))
# ALL_WRITE_BW=$((ALL_WRITE_BW+w_bw_megabytes))
# ALL_WRITE_IOS=$((ALL_WRITE_IOS+w_ios))
# ALL_WRITE_LAT=$((ALL_WRITE_LAT+w_lat*w_ios))
# TOTAL_IOS=$((TOTAL_IOS+r_ios+w_ios))
# TOTAL_LAT=$((TOTAL_LAT+r_ios*r_lat+w_ios*w_lat))

# echo $host[$job_runtime] Read_IOPS: ${r_iops}@${r_lat}us Read_BW: ${r_bw_megabytes}MB/s Write_IOPS: ${w_iops}@${w_lat}us Write_BW: ${w_bw_megabytes}MB/s
# done

# TOTAL_IOPS=$((ALL_READ_IOPS+ALL_WRITE_IOPS))
# TOTAL_BW=$((ALL_READ_BW+ALL_WRITE_BW))

# if [ $TOTAL_IOS == 0 ]; then
# AVG_LAT=0
# else
# AVG_LAT=$((TOTAL_LAT/TOTAL_IOS))
# fi

# if [ $ALL_READ_IOS == 0 ]; then
# AVG_READ_LAT=0
# else
# AVG_READ_LAT=$((ALL_READ_LAT/ALL_READ_IOS))
# fi
# if [ $ALL_WRITE_IOS == 0 ]; then
# AVG_WRITE_LAT=0
# else
# AVG_WRITE_LAT=$((ALL_WRITE_LAT/ALL_WRITE_IOS))
# fi

# echo Total: IOPS: $TOTAL_IOPS@${AVG_LAT}us  BW: ${TOTAL_BW}MB/s  READ_BW: ${ALL_READ_BW}MB/s  WRITE_BW: ${ALL_WRITE_BW}MB/s READ_IOPS: ${ALL_READ_IOPS}@${AVG_READ_LAT}us WRITE_IOPS: ${ALL_WRITE_IOPS}@${AVG_WRITE_LAT}us
# echo =============================================================
# done


if __name__ == "__main__":
    files = sys.argv[1:]
    for f in files:
        parse(f)