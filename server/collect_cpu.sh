#!/usr/bin/bash
# a script to gather oncpu and offcpu data, then generate flame graphs
# pre-requisites:
#   - kernel version >4.8
#   - eBPF enabled with kernel
#   - bcc installed
#   - FlameGraph installed and located in ../FlameGraph
# Maintainer: Fred Chen

source scl_source enable devtoolset-7 llvm-toolset-7

PREFIX="this"
TIME=60
TYPE="oncpu offcpu wakeup offwakeup"
PID=
PROGNAME=
EXCLUDE_STACK=
KEEPFILES=false

function usage() {
  [[ -z "$1" ]] || echo "Error: $1"
  echo "usage: `basename $0` [process_name] [-w prefix] [-t time] [-g oncpu|offcpu|wakeup|offwakeup] [-x exclude_stack] [-k]"
  echo
  echo "options:"
  echo "  -k:    keep temp files."
  echo
  echo "examples:"
  echo "  `basename $0`                 # gather all types of cpu data for 60 seconds and generate flame graphs. prefix 'this'"
  echo
  echo "  `basename $0` cio_array       # gather all types of cpu data of process 'cio_array' for 60 seconds"
  echo "                                 # and generate flame graphs. prefix 'this'."
  echo
  echo "  `basename $0` -w 82rw -t 30 -g oncpu     # gather oncpu data for 30 seconds "
  echo "                                            # and generate flame graphs. prefix '82rw'"
  exit 1
}

function handleopts {
    OPTS=`getopt -o w:t:hg:x:k -l help,exclude: -- "$@"`
    [[ $? -eq 0 ]] || usage

    eval set -- "$OPTS"
    while true ; do
        case "$1" in
            -w ) PREFIX=$2; shift 2;;
            -t ) TIME="$2"; shift 2;;
            -g ) TYPE="$2"; shift 2;;
            -k ) KEEPFILES=true; shift 1;;
            -h | --help ) usage; shift;;
            -x | --exclude ) EXCLUDE_STACK="$2"; shift 2;;
            --) shift; break;;
        esac
    done
    [[ $# -ne 0 ]] && { PROGNAME="$@" && PID=`pgrep -nx "$PROGNAME"`; } || PROGNAME="allcpus"
    [[ ${PROGNAME} != "allcpus" ]] && [[ -z "$PID" ]] && usage "no running process named: \"$@\""
    [[ "$TIME" =~ ^[0-9]+$ ]] || usage "-t must be followed by a number."
    for t in $TYPE
    do
      [[ "$t" =~ oncpu|offcpu|wakeup|offwakeup ]] || usage "\"$t\" is not one of [oncpu|offcpu|wakeup|offwakeup]."
    done
}

function main() {
  handleopts "$@"
  SCRIPT_PATH=$(dirname $0)
  
  ARGPID=
  EXCL_SUFFIX=
  declare -A COLLECT__CMD FLAME_GRAPH_CMD
  [[ -z "$PID" ]] || ARGPID="-p ${PID}"
  [[ -z "${EXCLUDE_STACK}" ]] && { EXCLUDE_STACK='_NOTHINGEXCLUDED_' && EXCL_SUFFIX=""; } || EXCL_SUFFIX="no_${EXCLUDE_STACK}."

  COLLECT__CMD=(
    ["oncpu"]="/usr/share/bcc/tools/profile -F999 -afd  --stack-storage-size=2024000 ${ARGPID} ${TIME} > ${PREFIX}.oncpu.${PROGNAME}.${TIME}s.stacks" # collect on-cpu data
    ["offcpu"]="/usr/share/bcc/tools/offcputime ${ARGPID} --stack-storage-size=2024000 -df ${TIME} > ${PREFIX}.offcpu.${PROGNAME}.${TIME}s.stacks"  # collect off-cpu stacks
    ["wakeup"]="/usr/share/bcc/tools/wakeuptime ${ARGPID} --stack-storage-size=2024000 -f ${TIME} > ${PREFIX}.wakeup.${PROGNAME}.${TIME}s.stacks" # collect wakeup stacks
    ["offwakeup"]="/usr/share/bcc/tools/offwaketime ${ARGPID} --stack-storage-size=2024000 -f ${TIME} > ${PREFIX}.offwakeup.${PROGNAME}.${TIME}s.stacks" # collect offcpu+wakeup stacks
  )
  FLAME_GRAPH_CMD=(
    ["oncpu"]="grep -v ${EXCLUDE_STACK} ${PREFIX}.oncpu.${PROGNAME}.${TIME}s.stacks | ${SCRIPT_PATH}/../FlameGraph/flamegraph.pl > ${PREFIX}.oncpu.${PROGNAME}.${TIME}s.perf.${EXCL_SUFFIX}svg" # on-cpu flame graph
    ["offcpu"]="grep -v ${EXCLUDE_STACK} ${PREFIX}.offcpu.${PROGNAME}.${TIME}s.stacks | ${SCRIPT_PATH}/../FlameGraph/flamegraph.pl --color=io --title='Off-CPU Time Flame Graph' --countname=us > ${PREFIX}.offcpu.${PROGNAME}.${TIME}s.${EXCL_SUFFIX}svg" # off-cpu flame graph
    ["wakeup"]="grep -v ${EXCLUDE_STACK} ${PREFIX}.wakeup.${PROGNAME}.${TIME}s.stacks | ${SCRIPT_PATH}/../FlameGraph/flamegraph.pl --color=wakeup --title='Wakeup Time Flame Graph' --countname=us > ${PREFIX}.wakeup.${PROGNAME}.${TIME}s.${EXCL_SUFFIX}svg" # wakeup flame graph
    ["offwakeup"]="grep -v ${EXCLUDE_STACK} ${PREFIX}.offwakeup.${PROGNAME}.${TIME}s.stacks | ${SCRIPT_PATH}/../FlameGraph/flamegraph.pl --color=chain --title='Off-Wakeup Time Flame Graph' --countname=us > ${PREFIX}.offwakeup.${PROGNAME}.${TIME}s.${EXCL_SUFFIX}svg"  # off-wakeup flame graph
  )

  WCOUNT=`echo ${TYPE} | grep -w wakeup | wc -l`
  [[ ${PROGNAME} = "allcpus" && $WCOUNT -gt 0 ]] && { echo "WARNING: remove 'wakeup' due to a hang BUG of 'wakeup with allcpus'" && TYPE=`sed 's/\bwakeup\b//' <<< "${TYPE}"`; }  # removing 'wakeup' type if run on allcpus, due to a bug ( wakeuptime never ends )
  # collect data
  echo "Start Gathering \"${TYPE}\" data for ${TIME} seconds for '${PROGNAME}' ... "
  printf '=%.0s' {1..40} && echo
  for profiling_type in ${TYPE}
  do
    echo -n "collecting ${profiling_type} data for ${TIME} seconds for '${PROGNAME}'... "
    # echo "CMD: ${COLLECT__CMD[${profiling_type}]} "
    eval "${COLLECT__CMD[${profiling_type}]}" >/dev/null 2>&1
    echo "done"
  done
  [[ -z $EXCLUDE_STACK || $EXCLUDE_STACK = "_NOTHINGEXCLUDED_" ]] && MSGX="" || MSGX="(excluding ${EXCLUDE_STACK})"
  echo -n "generating FlameGraphs $MSGX ... "
  for profiling_type in ${TYPE}
  do
    #echo "CMD: ${FLAME_GRAPH_CMD[${profiling_type}]} "
    eval "${FLAME_GRAPH_CMD[${profiling_type}]}" >/dev/null 2>&1
  done
  echo "done" && echo
  echo "FlameGraphs Generated:"
  printf '=%.0s' {1..40} && echo
  for t in ${TYPE}
  do
    ls -la `pwd`/${PREFIX}*.${t}.*${TIME}*${EXCL_SUFFIX}*svg
  done

  [[ $KEEPFILES = false ]] && rm -f *.data *.folded *.stacks *.data.old
}

main "$@"
