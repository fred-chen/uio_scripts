#!/usr/bin/env bash
# aggregate multiple fio log files and plot a chart
# requirements:
#   - gnuplot installed
# Maintainer: Fred Chen

PLOT_INTERVAL=60  # plot PLOT_INTERVAL on x: 60 seconds
TYPE=
COUNTER_PATTERN=
TITLE=
FN=
KEEPFILES=false
DEDUP_RATE=
COMPRESS_RATE=

function usage {
  [[ ! -z $1 ]] && {
    echo
    >&2 echo "ERROR:" $1
    echo
  }
  len=$(expr length "usage: `basename $0`")
  printf "usage: `basename $0` <logname> [-t iops|clat|slat|lat]%s\n"
  printf "%${len}s [--title chart_title] [-k|--keep]\n" " "
  echo
  echo "options:"
  echo "  -k: keep temp files."
  echo "  -t: type of plots, can be one of: iops, clat, slat, lat."
  echo
  echo "examples:"
  echo "  $(basename $0) log/82rw*iops* -t iops  # plot iops chart for logs that the path match 'log/82rw*iops*' "
  echo

  exit 1
}

handleopts() {
  OPTS=`getopt -o ht:d:e:g:k -l help,title:,keep -- "$@"`
  [[ $? -eq 0 ]] || usage
  eval set -- "$OPTS"
  while true ; do
      case "$1" in
          -t) TYPE=$2; shift 2;;
          -e) COUNTER_PATTERN=$2; shift 2;;
          -g | --title) TITLE=$2; shift 2;;
          -k | --keep) KEEPFILES=true; shift 1;;
          -h | --help) shift 1; usage;;
          --) shift; break;;
      esac
  done
  [[ $# -ne 0 ]] && LOG_LIST="$@" || usage "must specify a logname(s)."
  for n in $LOG_LIST; do [[ ! -e $n ]] && { echo "'$n' doesn't exist."; exit 1; } ; done
  if [[ -z "$TYPE" ]]; then
    for n in $LOG_LIST
    do 
      [[ $n =~ "_iops" ]] && TYPE="iops" && break
      [[ $n =~ "_lat" ]] && TYPE="lat" && break
      [[ $n =~ "_clat" ]] && TYPE="clat" && break
      [[ $n =~ "_slat" ]] && TYPE="slat" && break
    done
    [[ -z "$TYPE" ]] && TYPE="iops"
    echo "warning: type not given(-t), using default: '$TYPE'"
  fi

  [[ -z "$TITLE" ]] && TITLE="$(basename `dirname $(echo ${LOG_LIST[0]} | cut -d' ' -f1)`) $TYPE chart"
  FN=`echo $TITLE | sed 's/ /_/g'`
}

list_files() {
  # get the fio log interval from one of the log files
  LOG_INTERVAL=`head -1 $(echo ${LOG_LIST} | awk '{print $1}') | awk -F "," '{print $1}'` && LOG_INTERVAL=$((${LOG_INTERVAL}/1000))
  for n in ${LOG_LIST}
  do
    echo $n
  done
  echo "`echo ${LOG_LIST} | wc -w` files will be aggregated." "fio_log_interval: $LOG_INTERVAL"
}
file_count() {
  # get the fio log file number
  echo "`echo ${LOG_LIST} | wc -w`"
}
plot_iops() {
  list_files
  # aggregate all fio logs and output a single file for plotting
  # output format is like: "time read_iops write_iops total_iops"
  AVG_FACTOR=$((${PLOT_INTERVAL}/${LOG_INTERVAL}))
  echo -n "plotting IOPS chart..."
  cat ${LOG_LIST} | \
  awk -F ',' "
          { t=int(\$1/1000/${PLOT_INTERVAL}); arr[t,int(\$3)]+=\$2; T[t] }
      END { for(time in T) printf(\"%d\t%d\t%d\t%d\n\",
                              time,arr[time,0]/${AVG_FACTOR},
                              arr[time,1]/${AVG_FACTOR},
                              (arr[time,0]+arr[time,1])/${AVG_FACTOR})
          }" | \
  sort -k1 -n > plot_$FN.plotdata
  gnuplot -e " set grid; set autoscale; set key spacing 2;
    set xlabel 'Time (Minute)';
    set ylabel 'IOPS (K)';
    set title '${TITLE} chart' font ',20' ;
    set terminal png size 1800,600; set output 'plot_$FN.png';
    plot 'plot_$FN.plotdata' using 1:(\$2/1000) title 'read ${TYPE}' with lines lw 3 lc rgb '#00FF00',
                                                  '' using 1:(\$3/1000) title 'write ${TYPE}' with lines lw 3 lc rgb '#0000FF',
                                                  '' using 1:(\$4/1000) title 'total ${TYPE}' with lines lw 3 lc rgb '#FF0000'
   "
   echo "done."
   [[ ${KEEPFILES} == false ]] && rm -f plot_$FN.plotdata
   ls `pwd`/plot_$FN.png
}
plot_lat() {
  list_files
  # aggregate all fio logs and output a single file for plotting
  # output format is like: "time read_latency write_latency"
  AVG_FACTOR=$((${PLOT_INTERVAL}/${LOG_INTERVAL}))
  FILECOUNT=`file_count`

  echo -n "plotting '${TYPE}' chart..."
  cat ${LOG_LIST} | \
  awk -F ',' "
          { t=int(\$1/1000/${PLOT_INTERVAL}); arr[t,int(\$3)]+=\$2; T[t] }
      END { for(time in T) printf(\"%d\t%d\t%d\n\",
                              time,
                              arr[time,0]/${PLOT_INTERVAL},
                              arr[time,1]/${PLOT_INTERVAL})
          }" | \
  sort -k1 -n > plot_$FN.plotdata

  gnuplot -e " set grid; set autoscale; set key spacing 2;
    set xlabel 'Time (Minute)';
    set ylabel '${TYPE} (us)';
    set title '${TITLE} chart' font ',20' ;
    set terminal png size 1800,600; set output 'plot_$FN.png';
    plot 'plot_$FN.plotdata' using 1:(\$2/${FILECOUNT}/1000) title 'read ${TYPE}' with lines lw 3 lc rgb '#00FF00',
                          '' using 1:(\$3/${FILECOUNT}/1000) title 'write ${TYPE}' with lines lw 3 lc rgb '#0000FF'
   "
   echo "done."
   [[ ${KEEPFILES} == false ]] && rm -f plot_$FN.plotdata
   ls `pwd`/plot_$FN.png
}

main() {
  handleopts "$@"
  case "${TYPE}" in
    iops)
      plot_iops
    ;;
    clat | slat | lat)
      plot_lat
    ;;
    *)
      echo "no such type '${TYPE}'"
    ;;
  esac
}

main "$@"
