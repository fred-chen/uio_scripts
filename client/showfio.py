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
    err = me.getint("egrep 'error=' {0} | wc -l".format(path))  # error message outside of json string
    
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

    global_options = j["global options"] if j.has_key("global options") else []
    bs      = global_options["bs"] if global_options.has_key("bs") else ""
    njobs   = global_options["numjobs"] if global_options.has_key("numjobs") else ""
    iodepth = global_options["iodepth"] if global_options.has_key("iodepth") else ""
    
    # client_stats for remote fio server, jobs for local
    stats = []
    stats += j["client_stats"] if j.has_key("client_stats") else []
    stats += j["jobs"] if j.has_key("jobs") else []
    
    data={}  # { entry_name : {
             #                  read: [iops, lat_ns, bw_bytes, ios, runtime, total_lat],
             #                  write: [iops, lat_ns, bw_bytes, ios, runtime, total_lat],
             #                  error: num_errors,
             #                  numjobs: num_jobs,
             #                  max_runtime: max_runtime
             #                }
             # }
    for stat in stats:
        if stat["jobname"] == "All clients": continue
        entry_name      = stat["hostname"] if stat.has_key("hostname") else stat["jobname"]
        read_iops       = stat["read"]["iops"]
        read_lat        = stat["read"]["lat_ns"]["mean"]
        read_bw         = stat["read"]["bw_bytes"] if stat["read"].has_key("bw_bytes") else int(stat["read"]["bw"]) * 1024
        read_ios        = stat["read"]["total_ios"]
        read_runtime    = stat["read"]["runtime"]  # ms
        read_total_lat  = read_ios * read_lat
        write_iops      = stat["write"]["iops"]
        write_lat       = stat["write"]["lat_ns"]["mean"]
        write_bw        = stat["write"]["bw_bytes"] if stat["write"].has_key("bw_bytes") else int(stat["write"]["bw"]) * 1024
        write_ios       = stat["write"]["total_ios"]
        write_runtime   = stat["write"]["runtime"]
        write_total_lat = write_ios * write_lat
        num_errors      = stat["error"]
        runtime         = read_runtime if read_runtime >= write_runtime else write_runtime

        if data.has_key(entry_name):
            data[entry_name]["read"][0]  += read_iops
            data[entry_name]["read"][1]  += read_lat
            data[entry_name]["read"][2]  += read_bw
            data[entry_name]["read"][3]  += read_ios
            data[entry_name]["read"][4]  += read_runtime
            data[entry_name]["read"][5]  += read_total_lat
            data[entry_name]["write"][0] += write_iops
            data[entry_name]["write"][1] += write_lat
            data[entry_name]["write"][2] += write_bw
            data[entry_name]["write"][3] += write_ios
            data[entry_name]["write"][4] += write_runtime
            data[entry_name]["write"][5] += write_total_lat
            data[entry_name]["error"]    += num_errors
            data[entry_name]["numjobs"]  += 1
            data[entry_name]["max_runtime"] = runtime if data[entry_name]["max_runtime"] < runtime else data[entry_name]["max_runtime"]
        else:
            data[entry_name] = {}
            data[entry_name]["read"]    = [read_iops, read_lat, read_bw, read_ios, read_runtime, read_total_lat]
            data[entry_name]["write"]   = [write_iops, write_lat, write_bw, write_ios, write_runtime, write_total_lat]
            data[entry_name]["error"]   = num_errors
            data[entry_name]["numjobs"] = 1
            data[entry_name]["max_runtime"] = runtime
    
    for entry_name in data.keys():
        err += data[entry_name]["error"]   # ioerror of jobs added to err
    print ( "%s[%s]" % (os.path.basename(path), "OK" if not err else "ERR:%d" % (err)) )
    print ( "=" * 80 )
    TOTAL_READ_IOS = 0
    TOTAL_READ_LAT = 0
    TOTAL_WRITE_IOS = 0
    TOTAL_WRITE_LAT = 0
    TOTAL_READ_IOPS = 0
    TOTAL_WRITE_IOPS = 0
    TOTAL_READ_BW = 0
    TOTAL_WRITE_BW = 0
    for entry_name in data.keys():
        # print("%s: %s" % (entry_name, data[entry_name]))
        Read_IOPS  = data[entry_name]["read"][0]
        Read_LAT   = data[entry_name]["read"][5] / (data[entry_name]["read"][3] or 1) / 1000  # total_lat / ios
        Read_BW    = data[entry_name]["read"][2] / 1024 / 1024  # MiB
        Write_IOPS = data[entry_name]["write"][0]
        Write_LAT  = data[entry_name]["write"][5] / (data[entry_name]["write"][3] or 1) / 1000  # total_lat / ios
        Write_BW   = data[entry_name]["write"][2] / 1024 / 1024  # MiB
        error      = data[entry_name]["error"]
        max_runtime = data[entry_name]["max_runtime"] / 1000     # seconds
        print ("%-10s %-10s: Read_IOPS: %d@%.2fus Read_BW: %dMiB/s Write_IOPS: %d@%.2fus Write_BW: %dMiB/s [%s]" % \
                (entry_name, "[time={runtime}]".format(runtime=max_runtime), Read_IOPS, Read_LAT, Read_BW, \
                Write_IOPS, Write_LAT, Write_BW, "OK" if error == 0 else "ERR:%d"%(error)))
        
        TOTAL_READ_IOPS  += Read_IOPS
        TOTAL_READ_IOS   += data[entry_name]["read"][3]
        TOTAL_READ_LAT   += data[entry_name]["read"][5]
        TOTAL_READ_BW    += Read_BW
        TOTAL_WRITE_IOPS += Write_IOPS
        TOTAL_WRITE_IOS  += data[entry_name]["write"][3]
        TOTAL_WRITE_LAT  += data[entry_name]["write"][5]
        TOTAL_WRITE_BW   += Write_BW
    
    TOTAL_IOPS    = TOTAL_READ_IOPS + TOTAL_WRITE_IOPS
    TOTAL_BW      = TOTAL_READ_BW + TOTAL_WRITE_BW
    AVG_LAT       = ( TOTAL_READ_LAT + TOTAL_WRITE_LAT ) / ( TOTAL_READ_IOS + TOTAL_WRITE_IOS ) / 1000 # ms
    AVG_READ_LAT  = TOTAL_READ_LAT / (TOTAL_READ_IOS or 1) / 1000
    AVG_WRITE_LAT = TOTAL_WRITE_LAT / (TOTAL_WRITE_IOS or 1) / 1000
    print ("%-10s %-10s: IOPS: %d@%.2fus BW: %sMiB/s READ_IOPS: %d@%.2fus WRITE_IOPS: %d@%.2fus READ_BW: %dMiB/s WRITE_BW: %dMiB/s" % \
            ("Total", "[bs={blksz},njobs={njobs},iodepth={iodepth}]".format(blksz=bs, njobs=njobs, iodepth=iodepth), TOTAL_IOPS, AVG_LAT, TOTAL_BW, TOTAL_READ_IOPS, AVG_READ_LAT, TOTAL_WRITE_IOPS, AVG_WRITE_LAT, TOTAL_READ_BW, TOTAL_WRITE_BW))    
    print ("=" * 80)
    
    return data

if __name__ == "__main__":
    files = sys.argv[1:]
    if not files: files = ['fio_output']
    jsons = []
    for f in files:
        if not os.path.exists(f): E("%s doesn't exist." % (f))
        if os.path.isdir(f): # try all json files if it's a dir
            for jfile in os.listdir(f):
                jsons.append("%s/%s" % (f, jfile))
        else:
            jsons.append(f)
    for j in jsons:
        parse(j)
        print("\n")