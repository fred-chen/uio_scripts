#!/usr/bin/gawk -f

# print multiple results of 'show.py' in a table
# record format:
#   randwsata.qd8.njobs8.600s.json[OK]
#   ================================================================================
#   localhost[337]: Read_IOPS: 0@0us Read_BW: 0MiB/s Write_IOPS: 504968@2024us Write_BW: 1972MiB/s [OK]
#   Total: IOPS: 504968@2024us BW: 1972MiB/s READ_IOPS: 0@0us WRITE_IOPS: 504968@2024us READ_BW: 0MiB/s WRITE_BW: 1972MiB/s
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

    match($0, "Total: IOPS: ([0-9]+)@([0-9.]+)us BW: ([0-9]+)MiB/s READ_IOPS: ([0-9]+)@([0-9.]+)us WRITE_IOPS: ([0-9]+)@([0-9.]+)us READ_BW: ([0-9]+)MiB/s WRITE_BW: ([0-9]+)MiB/s", arr)

    iops           = arr[1]
    iops_lat       = arr[2]
    band_width     = arr[3]
    read_iops      = arr[4]
    read_iops_lat  = arr[5]
    write_iops     = arr[6]
    write_iops_lat = arr[7]
    read_bw        = arr[8]
    write_bw       = arr[9]
    if(length(iops) != 0)
        printf "%-10s %-10s %-10s %-10s %-10s %-10s %-10s %-15s %-10s %-15s %-15s %-15s\n", \
               qdepth, njobs, bs, iops, iops_lat, band_width, read_iops, read_iops_lat, write_iops, write_iops_lat, read_bw, write_bw
}
