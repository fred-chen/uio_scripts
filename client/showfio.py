#!/usr/bin/env python
"""
    python version of showfio.sh
    show fio JSON format output
    requirements:
        - jq installed
    Maintainer: Fred Chen
"""

import os, sys, json

sys.path.append("%s/../cctf/cctf" % (os.path.dirname(os.path.realpath(__file__))))
import me


def E(msg, term=True):
    sys.stderr.write("Error: {0}\n".format(msg))
    if term:
        exit(1)


def parse(path):
    if not os.path.exists(path):
        E("'{}' doesn't exist.".format(path))
    err = me.getint(
        "egrep 'error=' {0} | wc -l".format(path)
    )  # error message outside of json string

    f = open(path, encoding="latin-1")
    lines = f.readlines()
    for i in range(len(lines)):
        if lines[i].strip() == "{":
            break

    j = None
    try:
        lines = lines[i:]
        j = json.loads("".join(lines))
    except:
        E("Error can't parse json: {}\n".format(path), False)
        return None

    global_options = j["global options"] if "global options" in j else []
    bs = global_options["bs"] if "bs" in global_options else ""
    njobs = global_options["numjobs"] if "numjobs" in global_options else ""
    iodepth = global_options["iodepth"] if "iodepth" in global_options else ""
    rw = global_options["rw"] if "rw" in global_options else ""

    # client_stats for remote fio server, jobs for local
    stats = []
    stats += j["client_stats"] if "client_stats" in j else []
    stats += j["jobs"] if "jobs" in j else []

    data = {}  # { entry_name : {
    #                  read: [iops, lat_ns, bw_bytes, ios, runtime, total_lat, iops_dev, lat_dev, bw_dev],
    #                  write: [iops, lat_ns, bw_bytes, ios, runtime, total_lat, iops_dev, lat_dev, bw_dev],
    #                  error: num_errors,
    #                  numjobs: num_jobs,
    #                  max_runtime: max_runtime
    #                }
    # }
    for stat in stats:
        if stat["jobname"] == "All clients":
            continue
        entry_name = stat["hostname"] if "hostname" in stat else stat["jobname"]
        read_iops = stat["read"]["iops"]
        read_iops_dev = stat["read"]["iops_stddev"]
        read_lat = stat["read"]["lat_ns"]["mean"]
        read_lat_dev = stat["read"]["lat_ns"]["stddev"]
        read_bw = (
            stat["read"]["bw_bytes"]
            if "bw_bytes" in stat["read"]
            else int(stat["read"]["bw"]) * 1024
        )
        read_bw_dev = stat["read"]["bw_dev"]
        read_ios = stat["read"]["total_ios"]
        read_runtime = stat["read"]["runtime"]  # ms
        read_total_lat = read_ios * read_lat
        write_iops = stat["write"]["iops"]
        write_iops_dev = stat["write"]["iops_stddev"]
        write_lat = stat["write"]["lat_ns"]["mean"]
        write_lat_dev = stat["write"]["lat_ns"]["stddev"]
        write_bw = (
            stat["write"]["bw_bytes"]
            if "bw_bytes" in stat["write"]
            else int(stat["write"]["bw"]) * 1024
        )
        write_bw_dev = stat["read"]["bw_dev"]
        write_ios = stat["write"]["total_ios"]
        write_runtime = stat["write"]["runtime"]
        write_total_lat = write_ios * write_lat
        num_errors = stat["error"]
        runtime = read_runtime if read_runtime >= write_runtime else write_runtime

        if entry_name in data:
            data[entry_name]["read"][0] += read_iops
            data[entry_name]["read"][1] += read_lat
            data[entry_name]["read"][2] += read_bw
            data[entry_name]["read"][3] += read_ios
            data[entry_name]["read"][4] += read_runtime
            data[entry_name]["read"][5] += read_total_lat
            data[entry_name]["read"][6] += read_iops_dev
            data[entry_name]["read"][7] += read_lat_dev
            data[entry_name]["read"][8] += read_bw_dev
            data[entry_name]["write"][0] += write_iops
            data[entry_name]["write"][1] += write_lat
            data[entry_name]["write"][2] += write_bw
            data[entry_name]["write"][3] += write_ios
            data[entry_name]["write"][4] += write_runtime
            data[entry_name]["write"][5] += write_total_lat
            data[entry_name]["write"][6] += write_iops_dev
            data[entry_name]["write"][7] += write_lat_dev
            data[entry_name]["write"][8] += write_bw_dev
            data[entry_name]["error"] += num_errors
            data[entry_name]["numjobs"] += 1
            data[entry_name]["max_runtime"] = (
                runtime
                if data[entry_name]["max_runtime"] < runtime
                else data[entry_name]["max_runtime"]
            )
        else:
            data[entry_name] = {}
            data[entry_name]["read"] = [
                read_iops,
                read_lat,
                read_bw,
                read_ios,
                read_runtime,
                read_total_lat,
                read_iops_dev,
                read_lat_dev,
                read_bw_dev,
            ]
            data[entry_name]["write"] = [
                write_iops,
                write_lat,
                write_bw,
                write_ios,
                write_runtime,
                write_total_lat,
                write_iops_dev,
                write_lat_dev,
                write_bw_dev,
            ]
            data[entry_name]["error"] = num_errors
            data[entry_name]["numjobs"] = 1
            data[entry_name]["max_runtime"] = runtime

    for entry_name in data.keys():
        err += data[entry_name]["error"]  # ioerror of jobs added to err
    print("%s[%s]" % (os.path.basename(path), "OK" if not err else "ERR:%d" % (err)))
    print("=" * 80)
    TOTAL_READ_IOS = 0
    TOTAL_READ_LAT = 0
    TOTAL_READ_LAT_DEV = 0
    TOTAL_WRITE_IOS = 0
    TOTAL_WRITE_LAT = 0
    TOTAL_WRITE_LAT_DEV = 0
    TOTAL_READ_IOPS = 0
    TOTAL_READ_IOPS_DEV = 0
    TOTAL_WRITE_IOPS = 0
    TOTAL_WRITE_IOPS_DEV = 0
    TOTAL_READ_BW = 0
    TOTAL_READ_BW_DEV = 0
    TOTAL_WRITE_BW = 0
    TOTAL_WRITE_BW_DEV = 0
    for entry_name in data.keys():
        # print("%s: %s" % (entry_name, data[entry_name]))
        Read_IOPS = data[entry_name]["read"][0]
        Read_LAT = (
            data[entry_name]["read"][5] / (data[entry_name]["read"][3] or 1) / 1000
        )  # total_lat / ios
        Read_BW = data[entry_name]["read"][2] / 1024 / 1024  # MiB
        Write_IOPS = data[entry_name]["write"][0]
        Write_LAT = (
            data[entry_name]["write"][5] / (data[entry_name]["write"][3] or 1) / 1000
        )  # total_lat / ios
        Write_BW = data[entry_name]["write"][2] / 1024 / 1024  # MiB
        error = data[entry_name]["error"]
        max_runtime = data[entry_name]["max_runtime"] / 1000  # seconds
        print(
            "%-10s %-10s: Read_IOPS: %d@%.2fus Read_BW: %dMiB/s Write_IOPS: %d@%.2fus Write_BW: %dMiB/s [%s]"
            % (
                entry_name,
                "[time={runtime}]".format(runtime=max_runtime),
                Read_IOPS,
                Read_LAT,
                Read_BW,
                Write_IOPS,
                Write_LAT,
                Write_BW,
                "OK" if error == 0 else "ERR:%d" % (error),
            )
        )

        TOTAL_READ_IOPS += Read_IOPS
        TOTAL_READ_IOS += data[entry_name]["read"][3]
        TOTAL_READ_LAT += data[entry_name]["read"][5]
        TOTAL_READ_BW += Read_BW
        TOTAL_WRITE_IOPS += Write_IOPS
        TOTAL_WRITE_IOS += data[entry_name]["write"][3]
        TOTAL_WRITE_LAT += data[entry_name]["write"][5]
        TOTAL_WRITE_BW += Write_BW
        TOTAL_READ_IOPS_DEV += data[entry_name]["read"][6]
        TOTAL_READ_LAT_DEV += data[entry_name]["read"][7]
        TOTAL_READ_BW_DEV += data[entry_name]["read"][8]
        TOTAL_WRITE_IOPS_DEV += data[entry_name]["write"][6]
        TOTAL_WRITE_LAT_DEV += data[entry_name]["write"][7]
        TOTAL_WRITE_BW_DEV += data[entry_name]["write"][8]

    if TOTAL_READ_IOS == 0 and TOTAL_WRITE_IOS == 0:
        E("Deviding Zero... json: {}".format(path), False)
        return data
    TOTAL_IOPS = TOTAL_READ_IOPS + TOTAL_WRITE_IOPS
    TOTAL_BW = TOTAL_READ_BW + TOTAL_WRITE_BW
    AVG_LAT = (
        (TOTAL_READ_LAT + TOTAL_WRITE_LAT) / (TOTAL_READ_IOS + TOTAL_WRITE_IOS) / 1000
    )  # ms
    AVG_READ_LAT = TOTAL_READ_LAT / (TOTAL_READ_IOS or 1) / 1000
    AVG_WRITE_LAT = TOTAL_WRITE_LAT / (TOTAL_WRITE_IOS or 1) / 1000
    IOPS_DEVIATION = TOTAL_READ_IOPS_DEV + TOTAL_WRITE_IOPS_DEV
    OVERALL_DEVIATION_RATIO = (
        IOPS_DEVIATION / TOTAL_IOPS
    )  # IOPS deviation is the overall measurement of all deviations
    print(
        "%-10s %-10s: IOPS: %d@%.2fus BW: %dMiB/s READ_IOPS: %d@%.2fus WRITE_IOPS: %d@%.2fus READ_BW: %dMiB/s WRITE_BW: %dMiB/s DEVIATION: %.2f%%"
        % (
            "Total",
            "[bs={blksz},njobs={njobs},iodepth={iodepth},rw={rw}]".format(
                blksz=bs, njobs=njobs, iodepth=iodepth, rw=rw
            ),
            TOTAL_IOPS,
            AVG_LAT,
            TOTAL_BW,
            TOTAL_READ_IOPS,
            AVG_READ_LAT,
            TOTAL_WRITE_IOPS,
            AVG_WRITE_LAT,
            TOTAL_READ_BW,
            TOTAL_WRITE_BW,
            OVERALL_DEVIATION_RATIO * 100,
        )
    )
    print("=" * 80)

    return data


if __name__ == "__main__":
    files = sys.argv[1:]
    if not files:
        files = ["fio_output"]
    jsons = []
    for f in files:
        if not os.path.exists(f):
            E("%s doesn't exist." % (f))
        if os.path.isdir(f):  # try all json files if it's a dir
            for jfile in os.listdir(f):
                jsons.append("%s/%s" % (f, jfile))
        else:
            jsons.append(f)
    for j in jsons:
        parse(j)
        print("\n")
