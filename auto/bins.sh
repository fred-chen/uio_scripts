#!/usr/bin/env bash
# a very simple script to replace cio_array bins and threadtable.ini then perform a perf test

BINDIR=./bins
THREADTABLEDIR=./threadtables
ONLY="tblonly"  # or "binonly" or "both"
FILLTIME=300
CONF=
TBLS=

function usage() {
  [[ ! -z $1 ]] && {
    echo
    >&2 echo "ERROR:" $1
    echo
  }
  len=$(expr length "usage: `basename $0`")
  printf "usage: `basename $0` -c conf [ -o binonly|tblonly|both ] [ --bindir bin_dir ] [ --tbldir threadtable_dir ] tbl1 tbl2 ...\n"
  echo
  echo "options:"
  echo "  -c conf    : config file path"
  echo "  -o binonly : only replace binaries in bin_dir"
  echo "  -o tblonly : only replace threadtable.ini in threadtable_dir"
  echo "  -o both    : replace threadtable.ini and binaries ( taking long time ...)"
  echo "  --bindir   : the folder path that contains cio_array binaries"
  echo "  --tbldir   : the folder path that contains threadtable.ini config files"

  exit 1
}

handleopts() {
  OPTS=`getopt -o o:hc: -l help,bindir:,tbldir: -- "$@"`
  [[ $? -eq 0 ]] || usage
  eval set -- "$OPTS"
  while true ; do
      case "$1" in
          -o ) ONLY=$2; shift 2;;
          -c ) CONF=$2; shift 2;;
          --bindir) BINDIR=$2; shift 2;;
          --tbldir) THREADTABLEDIR=$2; shift 2;;
          -h | --help) shift 1; usage;;
          --) shift; break;;
      esac
  done
  
  [[ $# -ne 0 ]] && TBLS="$@"
  [[ "$ONLY" != "tblonly" ]] && [[ "$ONLY" != "binonly" ]] && [[ "$ONLY" != "both" ]] && usage "-o must be followed by 'tblonly' or 'binonly'"
  [[ "$ONLY" == "binonly" || "$ONLY" == "both" ]] && [[ ! -e "$BINDIR" ]] && echo "'$BINDIR' doesn't exist." && exit 1
  [[ "$ONLY" == "tblonly" || "$ONLY" == "both" && -z "$TBLS" ]] && [[ ! -e "$THREADTABLEDIR" ]] && echo "'$THREADTABLEDIR' doesn't exist." && exit 1
  [[ -z "$TBLS" ]] && TBLS=`ls -d $THREADTABLEDIR/*.ini`
  [[ -z "$CONF" ]] && { usage "must specify a config file with '-c'"; }
}


main() {
    handleopts "$@"
    SCRIPTDIR=$(dirname $0)
    PERFAUTO=$SCRIPTDIR/perfauto.py
    BINS=`ls -d $BINDIR/*`

    if [[ $ONLY == "binonly" ]]; then
        echo "PERFORMING 'BINARY REPLACEMENT' TEST BINS='$BINS' ... "
        for bin in $BINS; do
            CMD="$PERFAUTO -c $CONF -u --binonly=$bin -p --fill=$FILLTIME"
            echo "  '$bin' CMD: '$CMD'"
            eval $CMD || break
        done
    elif [[ $ONLY == "tblonly" ]]; then
        echo "PERFORMING 'THREADTABLE REPLACEMENT' TEST THREADTABLES='$TBLS' ... "
        for tbl in $TBLS; do
            CMD="$PERFAUTO -c $CONF --threadtable=$tbl -fsdi -p --fill=$FILLTIME"
            echo "  '$tbl' CMD: '$CMD'"
            eval $CMD || break
        done
    else
        echo "PERFORMING 'BINARY AND THREADTABLE REPLACEMENT' TEST... "
        echo "BINS='$BINS'"
        echo "THREADTABLES='$TBLS'"
        for bin in $BINS; do
            for tbl in $TBLS; do
                CMD="$PERFAUTO -c $CONF -u --binonly=$bin --threadtable=$tbl -p --fill=$FILLTIME"
                echo "  '$bin' and '$tbl' CMD: '$CMD'"
                eval $CMD || break
            done
        done
    fi
}

main "$@"