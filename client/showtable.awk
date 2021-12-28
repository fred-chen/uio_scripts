#!/usr/bin/gawk -f

# print multiple results of 'show.py' in a table
# record format:
#   randwnvme.qd4.njobs8.bs4k.600s.json[OK]
#   ================================================================================
#   localhost  [time=45] : Read_IOPS: 0@0.00us Read_BW: 0MiB/s Write_IOPS: 140476@224.14us Write_BW: 548MiB/s [OK]
#   Total      [bs=4k,njobs=8,iodepth=4]: IOPS: 140476@224.14us BW: 548MiB/s READ_IOPS: 0@0.00us WRITE_IOPS: 140476@224.14us READ_BW: 0MiB/s WRITE_BW: 548MiB/s
#   ================================================================================

BEGIN {
    RS="=\n\n"
    printf "%-10s %-10s %-10s %-10s %-10s %-10s %-10s %-15s %-10s %-15s %-15s %-15s\n", \
           "qdepth", "njobs", "bs(Bytes)","iops","lat(us)","bw(MiB/s)","read_iops","read_lat(us)","write_iops","write_lat(us)","read_bw(MiB/s)","write_bw(MiB/s)"
    for(c=0;c<140;c++) printf "="; printf "\n"
};


{
    match($0, "qd([0-9]+).njobs([0-9]+)(.bs([0-9]+[a-zA-Z]*))*", arr)
    qdepth     = arr[1]
    njobs      = arr[2]
    if(length(arr[4]) == 0)
        bs = 0
    else
        bs = arr[4]

    match($0, "Total[[:space:]]+\\[bs=(.+),njobs=(.+),iodepth=(.+)\\][[:space:]]*: IOPS: ([0-9]+)@([0-9.]+)us BW: ([0-9]+)MiB/s READ_IOPS: ([0-9]+)@([0-9.]+)us WRITE_IOPS: ([0-9]+)@([0-9.]+)us READ_BW: ([0-9]+)MiB/s WRITE_BW: ([0-9]+)MiB/s", arr)
    
    # get actual bs,njobs,qdepth from json file
    # in case the numbers extracted from jobfile name are wrong
    if(length(arr[1]) != 0)
        bs = arr[1]
    if(length(arr[2]) != 0)
        njobs = arr[2]
    if(length(arr[3]) != 0)
        qdepth = arr[3]
    # matched performance values
    iops           = arr[4]
    iops_lat       = arr[5]
    band_width     = arr[6]
    read_iops      = arr[7]
    read_iops_lat  = arr[8]
    write_iops     = arr[9]
    write_iops_lat = arr[10]
    read_bw        = arr[11]
    write_bw       = arr[12]
    if(length(iops) != 0)
        printf "%-10s %-10s %-10s %-10s %-10s %-10s %-10s %-15s %-10s %-15s %-15s %-15s\n", \
               qdepth, njobs, bs, iops, iops_lat, band_width, read_iops, read_iops_lat, write_iops, write_iops_lat, read_bw, write_bw
}
