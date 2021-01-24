#!/usr/bin/env python
"""
    a faster version of 'counterana.sh'
    # a tool to analyse uniio counter logs
    # functions:
        1. indicating counters that have no change through out all time
        2. identify counters that keep rising 'UP'
        3. identify counters that keep dropping 'DOWN'
        4. identify counters that are 'FLAT'
        5. print histogram
        6. print min, max, mean, and standard deviation for counters
        7. plotting a graph for counters
        8. can skip first or last few samples
        9. can skip samples with given values # will not implement because it's confusing
        10. can specify a time windows to analyze ("--startline --endline")
    # prerequisites:
        1. gnuplot installed
    # maintainer: Fred Chen
"""
import sys, getopt, subprocess, re, math, os
from functools import reduce

g_counter_pattern = []  # counter pattern to match counter lines "^.+: .+$",
g_plot = False
g_combine = False
g_log_list = ""
g_ramplines = 0
data=[]             # raw data: counter_name, value, unit
aggregated_array={} # raw data: { counter_name -> ([value1, value2 ...], unit) }
g_ignore_case = False
g_histogram = False
g_keepfile = False
g_startline = 0
g_endline = 0
g_dedup_rate = 50
g_compress_rate = 0
g_diff = False

def usage(errmsg=""):
    if(errmsg != ""):
        sys.stderr.write("\nERROR: %s\n" % errmsg)
    print("usage:%s [logname] [-e counter_pattern] [-i] [-m|--histogram] [-r|--ramplines] [-k] [--startline n] [--endline n]" % sys.argv[0])
    print("%s [-g|--graph] [-c|--combine] [-d|--diff]" % (' '.rjust(len("usage:%s [logname]" % (sys.argv[0])))))
    print(
        "\n" "Analyze UniIO counter log files." "\n" 
        "\n" 
        "options:" "\n"
        "  -e pattern:       filter of counter names" "\n"
        "  -i:               ignore case" "\n"
        "  -g, --graph:      plot a scatter graph for counters" "\n"
        "  -c, --combine:    use with '-g', plot all data onto a single chart"
        "  -d, --diff:       use with '-g', plot changes between values of a counter"
        "  -m, --histogram:  print histogram (log2 buckets)" "\n"
        "  -r, --ramplines:  ramping lines. to skip first and last few lines of data" "\n"
        "  --startline:      specify a start line, to only analyze lines after that line" "\n"
        "  --endline:        specify an end line, to only analyze lines before that line"
        "  -k:               keep temp files" "\n"
         "\n"
        "if no 'logname' given in command line, counterana.py reads counter data from stdin\n"
        "\n" 
        "examples:" "\n"
        "  counterana.py counter.log                # report all counters in 'counter.log' (massive lines will slow down the analysis)" "\n" 
        "  cat counter.log | counterana.py          # same as above" "\n"
         "\n" 
        "  counterana.py counter.log -e ss.obs      # only report counters that contain 'ss.obs'" "\n" 
        "  grep ss.obs counter.log | counterana.py  # same as above" "\n"
         "\n"
        "  counterana.py counter.log -e ss.obs -g   # report counters that contains 'ss.obs' and plot a graph for each of the counters" "\n" 
        "  counterana.py counter.log -e ss.obs -gc  # report counters that contains 'ss.obs' and plot all counter data onto a single graph" "\n" 
        "  counterana.py counter.log -e ss.obs -m   # report counters that contains 'ss.obs' and print the histogram for each of the counters" "\n"
         "\n"
        "  counterana.py counter.log --startline=60 --endline=120   # report all conter data betwen 60min ~ 120min (if sample interval is 60s) " "\n" 
        "\n"
        "output format:" "\n"
        "  counter_name[sample_count][unit][trends]: min, max, mean, mean_squared_deviation, standard_deviation, pct_stddev:mean, slop" "\n"
        "  * each line summarizes a unique counter * " "\n"
         "\n"
        "how to intepret:" "\n"
        "  sample_count:   how many samples(lines) have been aggregated for a counter" "\n"
        "  unit:           the unit of a counter (counts, uSec, KiB)" "\n"
        "  trends:         trends of the sample value from the first sample to the last in [UP|DOWN|FLAT|NOCHANGE|SPIKES]" "\n"
        "  slop:           result of linear regression(the 'a' in y=ax+b). how fast the sample value increase|decreases" "\n"
        "  self explained: min, max, mean, mean_squared_deviation, standard_deviation, pct_stddev:mean" "\n"
        "\n"
         )
    exit(1)
 
def runcmd(cmd):
    """
        return: stdout, stderr, exit value
    """
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = p.stdout.readlines()
    err = p.stderr.readlines()
    value = p.wait()
    return (out, err, value)

def getint(cmd):
    out,err,rt = runcmd(cmd)
    return int(out)
def printsepline(file):
    file.write( "%s\n" % ("=" * 80) )
    file.flush()
def E(msg):
    sys.stderr.write("Error: {0}\n".format(msg))
    sys.stderr.flush()
    exit(1)

def log_names():
    return ' '.join(g_log_list)

def sample_count():
    out, err, v = runcmd("cat %s | grep -E '([0-9]{2}:){2}[0-9]{2}' | wc -l" % (log_names()))
    return int("".join(out))

def handleopts():
    global g_counter_pattern, g_log_list, g_plot, g_ramplines, g_histogram, g_keepfile, g_startline, g_endline, g_combine, g_diff
    try:
        options, args = getopt.gnu_getopt(sys.argv[1:], "he:gr:mcd", ["help","graph","ramplines=","histogram","startline=","endline=","combine","diff"])
    except getopt.GetoptError as err:
        usage(err)
    for o, a in options:
        if(o in ('-e')):
            g_counter_pattern.append(a)
        if(o in ('-g', '--graph')): 
            g_plot = True
        if(o in ('-c', '--combine')): 
            g_combine = True
        if(o in ('-d', '--diff')): 
            g_diff = True
        if(o in ('-h', '--help')): 
            usage() 
        if(o in ('-r','--ramplines')):
            g_ramplines=int(a)
        if(o in ('-i')):
            g_ignore_case = True
        if(o in ('-k')):
            g_keepfile = True
        if(o in ('-m', '--histogram')):
            g_histogram = True
        if(o == '--startline'):
            g_startline = int(a)
        if(o == '--endline'):
            g_endline = int(a)

    g_log_list = args
    if (not g_counter_pattern):
        g_counter_pattern=["^.+: .+$",]

def suitable_unit(v, u):
    """
        find the most suitable unit
        return: (unit, factor)
    """
    factor = 1; unit = u
    if (u == 'nSec'):  # time
        if ( 10**3 <= v < 10**6 ):
            unit = 'uSec'; factor = 10**3
        elif ( 10**6 <= v < 10**9 ):
            unit = 'mSec'; factor = 10**6
        elif (10**9 <= v):
            unit = 'Sec'; factor = 10**9
        else:
            pass
    elif (u == 'B'):   # size
        if ( 2**10 <= v < 2**20 ):
            unit = 'KiB'; factor = 2**10
        elif ( 2**20 <= v < 2**30 ):
            unit = 'MiB'; factor = 2**20
        elif ( 2**30 <= v < 2**40 ):
            unit = 'GiB'; factor = 2**30
        elif ( 2**40 <= v < 2**50 ):
            unit = 'TiB'; factor = 2**40
        elif (2**50 <= v):
            unit = 'PiB'; factor = 2**50
        else:
            pass
    else: pass
    return unit, factor

def build_data():
    """
        read all counters to a global array 'data': [ counter_name, value, unit ]
    """
    # read counter lines from log files and build the dict
    # conter line format: "countername: value unit" or "countername: value(nospace)size "
    # counter units could be:
    #   Time in Seconds: e.g. ss.luns.lun4.writetime.maximum: 2.08 Sec
    #   Time in Mili Seconds: e.g.  ss.luns.lun4.writetime.average: 4.61 mSec
    #   Time in Micro Seconds: e.g.  ss.luns.lun7.readrefreadtime.maximum: 562.57 uSec
    #   Time in Nano Seconds: e.g.  ss.luns.lun4.writetimesync.average: 0.00 nSec
    #   count: e.g.  ss.obs.cacheWriteBufferAlloc.average: '474'
    #   size in KiB: e.g. ss.dp.compressed_bytes: 4.00KiB
    #   size in GiB: e.g. ss.dp.compressed_bytes: 794.00MiB
    #   size in GiB: e.g. ss.dp.compressed_bytes: 794.00GiB
    #   size in TiB: e.g. ss.dp.uncompressed_bytes: 1.00TiB
    #   size in Byte: e.g. ss.dp.localcache_bytes: 0.00B 
    global data, g_ignore_case, aggregated_array, g_keepfile, g_startline, g_endline, g_ramplines

    file_names = " ".join(g_log_list)
    if(not file_names.strip()):
        file_in = sys.stdin
    else:
        subprocess.call("cat %s > counters_tmp.txt" % (file_names), shell=True)
        file_in = open("counters_tmp.txt", 'r')

    regNumber = re.compile("^\d+$")
    regCounters = []
    for pattern in g_counter_pattern:
        if g_ignore_case:
            regCounter = re.compile(pattern, re.IGNORECASE)
        else:
            regCounter = re.compile(pattern)
        regCounters.append(regCounter)
    lines = file_in.readlines()
    totallinenum = len(lines)
    curlinenum = 0
    for line in lines:
        curlinenum += 1
        pct = "%d" % (curlinenum * 100 / totallinenum)
        found = False
        for reg in regCounters:
            if (not reg.search(line)): 
                continue
            else:
                found = True
                break
        if (not found): continue
        if (curlinenum % 50 == 0): 
            sys.stderr.write("\rbuilding aggregated array ...%s%%(%d/%d)" % (pct, curlinenum, totallinenum))
            sys.stderr.flush()

        line = line.rstrip()
        lst = line.replace(':',"").replace("'","").split(' ')
        counter_name = lst[0]
        if (len(lst) == 2):   # size or counts
            value = lst[1] if regNumber.match(lst[1]) else lst[1][:-3]
            if regNumber.match(lst[1]):
                unit = "counts"
                value = float(value)
            else:
                unit = lst[1][-3:]
                if (unit == "PiB"): 
                    value = float(value) * 1024 * 1024 * 1024 * 1024 * 1024
                elif (unit == "TiB"):
                    value = float(value) * 1024 * 1024 * 1024 * 1024
                elif (unit == "GiB"):
                    value = float(value) * 1024 * 1024 * 1024
                elif (unit == "MiB"):
                    value = float(value) * 1024 * 1024
                elif (unit == "KiB"):
                    value = float(value) * 1024
                elif (unit[2] == "B"):  # for counters like: countername: 0.00B
                    value = float(lst[1][:-1])
                else:
                    print("unknown unit: %s" % (line))
                    exit(1)
                unit = "B"
            # print unit
            # print("name:{0}\tvalue:{1}\tunit:{2}\n".format(counter_name, value, unit))
        elif (len(lst) == 3): # time
            value = float(lst[1])
            unit = lst[2]
            if (unit == "Sec"):
                value = value * 1000.0 * 1000.0 * 1000.0
            if (unit == "mSec"):
                value = value * 1000.0 * 1000.0
            if (unit == "uSec"):
                value = value * 1000.0
            if (unit == "nSec"):
                pass
            unit = "nSec"
        else:
            sys.stderr.write("unidentified counter: %s\n" % (line))
            value = unit = "exception value and unit"
        try:
            data.append((counter_name, value, unit))
        except Exception as err:
            print(line)
            print("append exception: %s" % err)
    if (not data):
        print ("no data that matches '%s'." % (g_counter_pattern))
        exit(1)
    
    # build a dict { counter_name -> ([value1, value2 ...], unit) }
    aggregated_array = {} 
    for c in data: # [ counter_name, value, unit ]
        counter_name = c[0]; value = c[1]; unit = c[2]
        if (aggregated_array.has_key(counter_name)):
            aggregated_array[counter_name][0].append(value)
        else:
            aggregated_array[counter_name] = ([value], unit)
    # filter out lines that aren't in range
    for counter_name in aggregated_array.keys():
        unit = aggregated_array[counter_name][1]
        values = aggregated_array[counter_name][0]
        endline = g_endline-g_ramplines if g_endline else len(aggregated_array[counter_name][0])-g_ramplines
        aggregated_array[counter_name] = (values[ g_startline + g_ramplines : endline ], unit)

    if (not g_keepfile):
        runcmd("rm -f %s" % ("counters_tmp.txt"))
    sys.stderr.write("\rbuilding aggregated array ... done.%s\n" % (' ' * 40))

def average(val_list):
    return sum(val_list) / len(val_list)

def deviate():
    """
        calculate deviations
        output format: counter_name[samplen_count][unit]["UP|DOWN|FLAT|NOCHANGE"]: min, max, mean, mean_squared_deviation, standard_deviation, pct_stddev:mean
        return a dict: d{ counter_name={ "min"=min, "max"=max ... } }
    """
    global data, g_ramplines, aggregated_array, g_startline, g_endline
    
    printsepline(sys.stderr)
    d = {}
    for counter_name in aggregated_array.keys():
        values = aggregated_array[counter_name][0]; values = values[:]
        unit = aggregated_array[counter_name][1]
        min = 9999999999999999999999999.0
        max = -999999999999999999999999.0
        sum = 0
        for v in values:
            if v < min: min = v 
            elif v > max: max = v
            try:
                sum += v
            except TypeError as err:
                print (values)
                print ("TypeError: %s" % (err), counter_name, unit)
                exit(1)
        unit, factor = suitable_unit(min, unit)
        min = min / factor
        max = max / factor
        sum = sum / factor

        sample_count = len(values)
        mean = sum / sample_count
        sse = 0 # sum of squared deviation(error)
        x = 0; xl = range(len(values)); xmean = average(xl)
        sigmaXY = 0; sigmaXX = 0
        for v in values:
            v = v / factor
            sse += (v-mean)**2
            # linear regression of slop
            sigmaXY += (xl[x] - xmean) * (v - mean)
            sigmaXX += (xl[x] - xmean) ** 2
            x += 1
        slop = sigmaXY / sigmaXX
        # print("xmean=%.4f sigmaXY=%.4f sigmaXX=%.4f slop=%.4f" % (xmean, sigmaXY, sigmaXX, slop))
        mean_squared_deviation = sse / len(values)
        standard_deviation = math.sqrt(mean_squared_deviation)
        pct_stddev = standard_deviation * 100.0 / mean if mean !=0 else 0
        if (slop == 0): trend = "NOCHANGE"
        elif (slop > 0.005 and pct_stddev<=100): trend = "UP"
        elif (slop < -0.005 and pct_stddev<=100): trend = "DOWN"
        elif (pct_stddev > 50): trend = "SPIKES"
        else: trend = "FLAT"
        d[counter_name] = {}
        d[counter_name]["min"] = min
        d[counter_name]["max"] = max
        d[counter_name]["mean"] = mean
        d[counter_name]["mean_squared_deviation"] = mean_squared_deviation
        d[counter_name]["standard_deviation"] = standard_deviation
        d[counter_name]["pct_stddev"] = pct_stddev
        d[counter_name]["trend"] = trend
        
        print("%s[%d][%s][%s]: min=%.1f max=%.1f mean=%.1f stddev=%.1f stddev:mean=%.1f%% slop=%.3f" % 
            (counter_name, len(values), unit, trend, min, max, mean, standard_deviation, pct_stddev, slop))
    return d

"""
    combine counter data and plot them onto a single chart
"""
def plot_counter_combined():
    global aggregated_array, g_keepfile, g_startline, g_endline, g_ramplines

    printsepline(sys.stderr)

    # build a new dict for matched lines and convert values to with unit 
    min = 9999999999999999999999999.0
    max = -999999999999999999999999.0
    unit = None; yunit = None; maxline = 0
    counter_revalues = {}  # new dict { counter_name : [ [ revalue1, revalue2, ... ], unit ]}
    for counter_name in aggregated_array.keys():  # find out min and max of all counters
        unit = aggregated_array[counter_name][1]
        values = aggregated_array[counter_name][0]; values = values[:]
        counter_revalues[counter_name] = [values, unit]
        maxline = len(values) if len(values) > maxline else maxline
        for v in values:
            if v < min: min = v
            elif v > max: max = v; yunit = unit
    
    unit, factor = suitable_unit(min, yunit) # find the most suitable unit
    for counter_name in counter_revalues.keys():
        counter_revalues[counter_name][0] = [ x / factor for x in counter_revalues[counter_name][0] ]
        counter_revalues[counter_name][1] = unit
        if (g_diff):  # plot difference between counter values
            counter_revalues[counter_name][0] = [ x - y for x,y in zip(counter_revalues[counter_name][0][1:],counter_revalues[counter_name][0][:-1]) ]
            counter_revalues[counter_name][0].insert(0,0)

    """
      generating plot data file
      output format:   minute counter_name1 counter_name2 counter_name3 ...
                       0      1_v1          2_v1          3_v1
                       ...
    """
    counter_names = counter_revalues.keys()
    header = "Minute"; chart_title = "combined chart"
    for counter_name in counter_names:
        header += " " + counter_name
    if len(counter_names) > 1:
        plotdatafilename = ("%s...%d_counters.combined" % (counter_names[0], len(counter_names))).replace('/','_')
        chart_title = "combined %s chart" % ("differential" if g_diff else "")
    else:
        plotdatafilename = ("%s.plotdata" % (counter_names[0])).replace('/','_')
        chart_title = "%s chart" % (counter_names[0] + ("differential" if g_diff else ""))

    f = open(plotdatafilename, 'w')
    f.write("%s\n" % (header))
    line=""
    for i in range(maxline):
        line = "%d" % (i + g_startline + g_ramplines)
        for counter_name in counter_names:
            try:
                line += " %f" % (counter_revalues[counter_name][0][i])
            except Exception as err:
                print("aggregated_array[%s][%d]: %s" % (counter_name, i, err))
                line += " 0"
        f.write("%s\n" % (line))
    f.close()
    linewidth = 4.0 / len(counter_names); linewidth = 1 if linewidth < 1 else linewidth; linewidth = 3 if linewidth > 3 else linewidth
    print (linewidth)
    plotfilename = ("%s.png" % (plotdatafilename + (".differential" if g_diff else ""))).replace('/','_')
    plotcmd = ( "gnuplot -e \"set grid; set autoscale; set key spacing 2; "
                "set xlabel 'Time (Minute)'; set ylabel '[%s]'; "
                "set xtics autofreq; "
                "set title '%s' font ',20'; "
                "set terminal png size 1600,900; set output '%s'; "
                "set key autotitle columnheader; "
                "plot for [i=2:%s] '%s' using 1:i with lines lw %.1f\"" %
                (unit, chart_title, plotfilename, len(counter_names)+1, plotdatafilename, linewidth)
                )
    out, err, rt = runcmd(plotcmd)
    if (rt != 0):
        print("out=%s\nerr=%s\nrt=%d" % ("".join(out), "".join(err), rt))
    if (not g_keepfile):
        runcmd("rm -f %s" % (plotdatafilename))
    subprocess.call("ls %s/%s" % ( os.getcwd(), plotfilename ), shell=True)

"""
    plot a chart for each counter
"""
def plot_counter():
    global aggregated_array, g_keepfile, g_startline, g_endline, g_ramplines

    printsepline(sys.stderr)
    for counter_name in aggregated_array.keys():
        unit = aggregated_array[counter_name][1]
        values = aggregated_array[counter_name][0]; values = values[:]
        chart_title = counter_name + " chart"
        if (g_diff):  # plot difference between counter values
            values = [ x - y for x,y in zip(values[1:],values[:-1]) ]
            values.insert(0,0)
            chart_title = counter_name + " differential chart"

        min = 9999999999999999999999999.0
        max = -999999999999999999999999.0
        sum = 0
        for v in values:
            if v < min: min = v
            elif v > max: max = v
            
        unit, factor = suitable_unit(min, unit)
        values = [ x / factor for x in values ]

        values_zipped = zip(range(len(values)),values)
        plotdatafilename = ("%s.plotdata" % (counter_name)).replace('/','_')
        f = open(plotdatafilename, 'w')
        f.write("# counter_name minute value\n")
        for v in values_zipped:
            f.write("%s\t%s\t%s\n" % (counter_name, v[0], v[1]))
        f.close()
        plotfilename = ("%s.png" % (counter_name + (".differential" if g_diff else ""))).replace('/','_')
        plotcmd = ( "gnuplot -e \"set grid; set autoscale; set key spacing 2; "
                    "set xlabel 'Time (Minute)'; set ylabel '%s [%s]'; "
                    "set xtics autofreq; "
                    "set title '%s' font ',20'; "
                    "set terminal png size 1600,900; set output '%s'; "
                    "plot '%s' using 2:3 title '%s' with lines lw 3 lc rgb '#00FF00'\"" %
                    (counter_name, unit, chart_title, plotfilename, plotdatafilename, counter_name)
                  )
        out, err, rt = runcmd(plotcmd)
        if (rt != 0):
            print("out=%s\nerr=%s\nrt=%d" % ("".join(out), "".join(err), rt))
        if (not g_keepfile):
            runcmd("rm -f %s" % (plotdatafilename))
        subprocess.call("ls %s/%s" % ( os.getcwd(), plotfilename ), shell=True)


def hist():
    """
        print a histogram of values
        bucket_num: how many buckets
    """
    printsepline(sys.stderr)
    global aggregated_array
    for counter_name in aggregated_array.keys():
        values = aggregated_array[counter_name][0]; 
        unit = aggregated_array[counter_name][1]
        print("\nHistogram for %s (%s) ... %d samples." % (counter_name, unit, len(values)))
        min = max = values[0]
        for v in values:
            if v < min: min = v
            if v > max: max = v
        # span = max - min if max - min > 0 else 1
        try:
            bucket_num = int(math.log(max, 2)) + 2
        except ValueError as err:
            E("%s\nmin=%d max=%d" % (err,min,max))
            
        buckets = [ 0 for i in range(bucket_num) ]
        for v in values:
            for i in range(bucket_num):
                if (v <= 2**i):
                    buckets[i] += 1
                    break
        maxl = 0
        for i in range(bucket_num):
            str = "(%d...%d]" % (2**(i-1), 2**i)
            if len(str) > maxl: maxl = len(str)
        for i in range(bucket_num):
            str = "(%d...%d]" % (2**(i-1), 2**i)
            print ("%s    %d" % (str.rjust(maxl, ' '), buckets[i] ))

if __name__ == "__main__":
    handleopts()
    build_data()
    deviate()
    if (g_histogram): hist()
    if (g_plot): 
        if (g_combine): 
            plot_counter_combined()
        else:
            plot_counter()

