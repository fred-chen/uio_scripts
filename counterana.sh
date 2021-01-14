#!/usr/bin/env bash
# a tool to analyse uniio counter logs
# functions: plotting a graph for counters
#            print mean_squared_deviation and standard_deviation for counters
# requirements:
#   gnuplot installed
#   gnu-getopt installed (macos)
# maintainer: Fred Chen

COUNTER_PATTERN=
LOG_LIST=
GRAPH=
RAMP_LINES=5  # removing first and last few lines to ramp up data

declare -A counter_sum counter_lines counter_unit counter_min counter_max data

function usage {
  [[ ! -z $1 ]] && {
    echo
    >&2 echo "ERROR:" $1
    echo
  }
  echo "usage:"
  echo "  $(basename $0) <logname> [-e counter_pattern] [ -g|--graph ] [-r num_ramplines]"
  echo
  exit 1
}
function handleopts {
    OPTS=`getopt -o 'he:gr:' -l 'help,graph,ramplines' -- "$@"`
    [[ $? -eq 0 ]] || usage

    eval set -- "$OPTS"
    while true ; do
        case "$1" in
            -e) COUNTER_PATTERN=$2; shift 2;;
            -g | --graph) GRAPH=1; shift 1;;
            -r | --ramplines) RAMP_LINES=$2; shift 2;;
            -h | --help) shift 1; usage;;
            --) shift; break;;
        esac
    done
    [[ $# -ne 0 ]] && LOG_LIST="$@" || usage "must specify a logname."
    [[ "$GRAPH" == 1 && -z "${COUNTER_PATTERN}" ]] && usage "'-e counter_pattern' must be specified when '-g' is specified."
    [[ -z "${COUNTER_PATTERN}" ]] && COUNTER_PATTERN="."
}

is_counter_log() {
  cnt=`cat $LOG_LIST | grep -vE '([0-9]{2}:){2}[0-9]{2}' | grep ':' | grep -iE "${COUNTER_PATTERN}" | head -1 | wc -l`
  [[ ${cnt} -gt 0 ]] && return 0 || echo "no data matches '${COUNTER_PATTERN}' in ${LOG_LIST}." && return 1
}
sample_count() {
  echo `cat $LOG_LIST | grep -E '([0-9]{2}:){2}[0-9]{2}' | wc -l`
}
counter_list() {
  cat $LOG_LIST | grep -vE '([0-9]{2}:){2}[0-9]{2}' | grep ':' | grep -iE "${COUNTER_PATTERN}" | awk -F ':' '{print $1}' | sort -k1 | uniq
}
counter_count() {
  cat $LOG_LIST | grep -vE '([0-9]{2}:){2}[0-9]{2}' | grep ':' | grep -iE "${COUNTER_PATTERN}" | awk -F ':' '{print $1}' | sort -k1 | uniq | wc -l
}
build_data() {
  # counter value could be:
  #   Time in Seconds: e.g. ss.luns.lun4.writetime.maximum: 2.08 Sec
  #   Time in Mili Seconds: e.g.  ss.luns.lun4.writetime.average: 4.61 mSec
  #   Time in Micro Seconds: e.g.  ss.luns.lun7.readrefreadtime.maximum: 562.57 uSec
  #   Time in Nano Seconds: e.g.  ss.luns.lun4.writetimesync.average: 0.00 nSec
  #   count: e.g.  ss.obs.cacheWriteBufferAlloc.average: '474'
  #   size in KiB: e.g. ss.dp.compressed_bytes: 4.00KiB
  #   size in GiB: e.g. ss.dp.compressed_bytes: 794.00MiB
  #   size in GiB: e.g. ss.dp.compressed_bytes: 794.00GiB
  #   size in TiB: e.g. ss.dp.uncompressed_bytes: 1.00TiB
  is_counter_log && {
    i=0
    cnt=`cat $LOG_LIST | grep -vE '([0-9]{2}:){2}[0-9]{2}' | grep ':' | grep -iE "${COUNTER_PATTERN}" | wc -l`
    while read -r line
    do
      pct=`bc <<< "$i * 100 / $cnt"` && i=$((i+1))
      [[ $((i%50)) -eq 0 ]] && echo -ne \\r"building aggregated array ... $pct% ($i/$cnt )"
      read counter_name counter_value <<< $line
      ctype=  # counter type, can be either a 'time' type or a 'count' type
      unit=   # unit of time, can be one of: Sec, mSec, uSec, nSec
      [[ ${counter_value: -1: 1} == 'c' ]] && ctype='time' || {
      [[ ${counter_value: -1: 1} == 'B' ]] && ctype='size' || ctype='count'
      }
      [[ $ctype == 'time' ]] && read counter_value unit <<< ${counter_value}
      [[ $ctype == 'count' ]] && counter_value=`echo $counter_value | sed s/\'//g` && unit="counts"
      [[ $ctype == 'size' ]] && {
        counter_value=`echo $counter_value | sed -E 's/([KGT]iB)/ \1/g'`
        read counter_value unit <<< ${counter_value}
        case $unit in
          KiB) counter_value=`bc <<< "scale=4; $counter_value / 1024"`;;
          GiB) counter_value=`bc <<< "scale=2; $counter_value * 1024"`;;
          TiB) counter_value=`bc <<< "scale=2; $counter_value * 1024 * 1024"`;;
        esac
        unit="MiB"
      }

      [[ `echo "$counter_value < ${counter_min[$counter_name]:=999999999999999999}" | bc -l` -eq 1 ]] && counter_min[$counter_name]=$counter_value
      [[ `echo "$counter_value > ${counter_max[$counter_name]:=-999999999999999999}" | bc -l` -eq 1 ]] && counter_max[$counter_name]=$counter_value

      counter_sum["${counter_name}"]=`bc <<< "scale=4; ${counter_value:=0} + ${counter_sum["${counter_name}"]:=0}"`
      counter_lines["${counter_name}"]=$((${counter_lines["$counter_name"]:=0} + 1))
      counter_unit["${counter_name}"]=${unit}
      line_num=${counter_lines["${counter_name}"]}
      data["${counter_name}","$line_num"]=${counter_value}
    done < <(cat $LOG_LIST | grep -vE '([0-9]{2}:){2}[0-9]{2}' | grep ':' | grep -iE "${COUNTER_PATTERN}" | awk -F ':' '{print $1  $2}')
    echo -e \\r"building aggregated array ... done.               "
    # for u in ${!counter_unit[@]}
    # do
    #   unit=${counter_unit[$u]}
    #   echo "counter name: $u unit: $unit"
    # done
  }
}
print_sepline() {
  printf '=%.0s' {1..80} && echo
}
counter_deviate() {
  build_data && {
    declare -A counter_mean counter_mean_squared_deviation counter_std_deviation
    cur=1
    for counter_name in ${!counter_sum[@]}
    do
      echo -n "calculating deviations for '${counter_name}($cur/${#counter_sum[@]})'... "
      mean=`bc <<< "scale=4; ${counter_sum[$counter_name]} / ${counter_lines[${counter_name}]}"`
      sse=0  # sum of squared errors
      for i in `seq 1 ${counter_lines[${counter_name}]}`
      do
        [[ $i -le ${RAMP_LINES} || $i -gt $((${counter_lines[${counter_name}]}-${RAMP_LINES})) ]] && continue
        squared_dev=`bc <<< "scale=4; (${data[$counter_name,$i]} - $mean)^2" | awk '{printf "%f", $0}'`
        # echo sum: ${counter_sum[$counter_name]} mean: $mean counter_value: ${data[$counter_name,$i]} squared_dev: $squared_dev
        sse=`bc <<< "scale=4; $sse + $squared_dev"`
      done

      mean_squared_deviation=`bc <<< "scale=2; ${sse} / ${counter_lines[${counter_name}]}"`
      std_deviation=`bc <<< "scale=2; sqrt(${mean_squared_deviation})"`
      counter_mean["$counter_name"]="$mean"
      counter_mean_squared_deviation["$counter_name"]="$mean_squared_deviation"
      counter_std_deviation["$counter_name"]="$std_deviation"
      echo "done."
      cur=$((cur+1))
    done
    print_sepline
    for counter_name in ${!counter_sum[@]}
    do
      [[ ${counter_mean[$counter_name]} == 0 ]] && pct_stddev_to_mean=0 || pct_stddev_to_mean=`bc <<< "scale=1; ${counter_std_deviation[$counter_name]} * 100/${counter_mean[$counter_name]}"`
      echo "${counter_name}[${counter_lines[${counter_name}]}][${counter_unit[${counter_name}]}]: mean=${counter_mean["$counter_name"]} min=${counter_min["$counter_name"]}  max=${counter_max["$counter_name"]} sqdev=${counter_mean_squared_deviation["$counter_name"]} stddev=${counter_std_deviation["$counter_name"]} stddev:mean=${pct_stddev_to_mean}%"
    done
  }
}

get_counter_lines() {
  counter_name=$1
  [[ -z "$counter_name" ]] && echo "${FUNCNAME[0]}: counter name not given." && return 1
  cat $LOG_LIST | grep -vE '([0-9]{2}:){2}[0-9]{2}' | grep ':' | grep -iE "${counter_name}"
}
plot_counter() {
  [[ -z "$1" ]] && xlable="Minutes"
  build_data

  for name in ${!counter_sum[@]}
  do
    echo -n "plotting $name ... "
    declare -A line_value
    for name_linenum in ${!data[@]}
    do
      IFS="," read cnter_name line_num <<< $name_linenum
      [[ $cnter_name == $name ]] && value=${data[$name_linenum]} && line_value["$line_num"]="$value"
    done

    fn="$name.plotdata"
    unit=${counter_unit[$name]}
    echo "#counter_name line_number value" > $fn
    for line_num in ${!line_value[@]}
    do
      [[ $line_num -le ${RAMP_LINES} || $line_num -gt $((${counter_lines["${counter_name}"]}-${RAMP_LINES})) ]] && continue
      value=${line_value[$line_num]}
      printf "%s\t%s\t%s\n" "$name $line_num $value"
    done | sort -k2n >> $fn

    gnuplot -e " set grid; set autoscale; set key spacing 2;
      set xlabel 'Time (Minute)';
      set ylabel '$name [$unit]';
      set title '$name chart' font ',20' ;
      set terminal png size 1800,600; set output 'plot_$name.png';
      plot '$fn' using 2:3 title '$name' with lines lw 3 lc rgb '#00FF00'
     "
     echo "done."
  done
  ls *${COUNTER_PATTERN}*.png
}

main() {
  handleopts $@

  echo "pattern '$COUNTER_PATTERN' has `counter_count` matched counters in '$LOG_LIST' `sample_count` samples."
  print_sepline
  [[ $GRAPH == 1 ]] && plot_counter && exit 0
  [[ $GRAPH != 1 ]] && counter_deviate
}

main $@
