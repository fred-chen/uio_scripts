#!/usr/bin/env bash
# fio wrapper
# requirements:
#   - fio installed
# Maintainer: Fred Chen

clients="192.168.100.155,192.168.100.156,192.168.100.169" # fio clients running "fio --server --daemonize"
outputdir=./fio_output   # the directory where fio saves *.json files to
logdir=./fio_log         # the directory where fio saves the bandwidth, iops, latency logs
profiledir=./fio_jobfile # the directory where fio find its job files
qds="1"                  # iodepths fio will use in job files. multiple q depth can be specified: '1,2,3'
njobs="1"                # numjobs fio will use in job files. multiple numjobs can be specified: '1,2,3'
runtime=600              # the time that fio will run
jobtype=                 # job type, a prefix of fio job files
duprate=                 # dedup ratio. (dedupe_percentage=xxx in fio profile)
comprate=                # compression ratio. (buffer_compress_percentage=xxx in fio profile)

function usage() {
  [[ ! -z $1 ]] && {
    echo
    >&2 echo "ERROR:" $1
    echo
  }
  len=$(expr length "usage: `basename $0`")
  printf "usage: `basename $0` <job_type> [-j|--jobs job_str] [-q|--qdepth qd_str]\n"
  printf "%${len}s            [-t|--time secs] [-d|--devices dev_str] [-c|--clients client_str]\n" " "
  printf "%${len}s            [--duprate pct] [--comprate pct]\n" " "
  echo
  echo "options:"
  echo "job_type:        job type, a prefix of fio job files"
  echo "  -j | --jobs:   specify numjobs fio will use in job files. multiple numjobs can be specified: '1,2,3'"
  echo "  -q | --qdepth: specify iodepth fio will use in job files. multiple q depth can be specified: '1,2,3'"
  echo "  -t | --time:   specify runtime in fio profile"
  echo "  --duprate:     specify dedupe_percentage in fio profile"
  echo "  --comprate:    specify buffer_compress_percentage in fio profile"

  exit 1
}

handleopts() {
  OPTS=`getopt -o hc:q:t:j:d: -l help,clients:,jobs:,qdepth:,time:,devices:,duprate:,comprate: -- "$@"`
  [[ $? -eq 0 ]] || usage
  eval set -- "$OPTS"
  while true ; do
      case "$1" in
          -c | --client_str) client_str=$2; shift 2;;
          -j | --jobs) njobs=$2; shift 2;;
          -q | --qdepth) qds=$2; shift 2;;
          -t | --time) runtime=$2; shift 2;;
          -d | --devices) devlist=$2; shift 2;;
          -h | --help) shift 1; usage;;
          --duprate) duprate=$2; shift 2;;
          --comprate) comprate=$2; shift 2;;
          --) shift; break;;
      esac
  done
  [[ $# -ne 0 ]] && jobtype="$@" || usage "must specify a job type."
  njobs=`echo $njobs|sed 's/,/ /g'`
  qds=`echo $qds|sed 's/,/ /g'`
  clients=`echo $clients|sed 's/,/ /g'`
  devs=$devlist && devlist=
  for n in `echo $devs|sed 's/,/ /g'`
  do
    devlist="$devlist /dev/$n"
  done

  echo "njobs=$njobs"
  echo "qds=$qds"
  echo "clients=$clients"
  echo "time=$runtime"
  echo "jobtype=$jobtype"
}

main() {
  handleopts "$@"
  mkdir -p $outputdir && mkdir -p $logdir && mkdir -p $profiledir

  for qd in $qds
  do
    for nj in $njobs
    do
      client_args=
      joblogdir=$logdir/$jobtype.qd$qd.njobs$nj.${runtime}s && mkdir -p $joblogdir
      jsonfn=$outputdir/$jobtype.qd$qd.njobs$nj.json
      logfn=$joblogdir/$jobtype.qd$qd.njobs$nj.${runtime}s
      for client in $clients
      do
        jobfn=$profiledir/${jobtype}_$client.fio
        [[ ! -e $jobfn ]] && echo "$jobfn doesn't exist." && exit 1 || {
          [[ ! -z "$qd" ]] && sed -i "s/iodepth=[0-9]\+/iodepth=${qd}/g" $jobfn
          [[ ! -z "$nj" ]] && sed -i "s/numjobs=[0-9]\+/numjobs=${nj}/g" $jobfn
          [[ ! -z "$runtime" ]] && sed -i "s/runtime=[0-9]\+/runtime=${runtime}/g" $jobfn
          [[ ! -z "$logfn" ]] && sed -i "s|write_bw_log=.\+|write_bw_log=${logfn}|g" $jobfn &&
                                sed -i "s|write_lat_log=.\+|write_lat_log=${logfn}|g" $jobfn &&
                                sed -i "s|write_iops_log=.\+|write_iops_log=${logfn}|g" $jobfn

          [[ ! -z "$duprate" ]] && sed -i "s|dedupe_percentage=.\+|dedupe_percentage=${duprate}|g" $jobfn
          [[ ! -z "$comprate" ]] && sed -i "s|buffer_compress_percentage=.\+|buffer_compress_percentage=${comprate}|g" $jobfn
        }

        client_args="$client_args --client $client $jobfn"
      done
      args="--output=$jsonfn --output-format=json"
      echo -n "starting ${jobtype} iodepth=$qd njobs=$nj ... "
      fio $args $client_args
      echo "done"
    done
  done

}

main "$@"

# rm -fr $outputdir
# for qd in $qds
# do
#   for nj in $njobs
#   do
#     client_args=""
#     jsonfn=$outputdir/json.qd$qd.njobs$nj.$jobtype
#     logfn=$logdir/$jobtype.qd$qd.njobs$nj
#     for client in $clients
#     do
#       jobfn=${jobtype}_$client.fio
#       sed -i "s/iodepth=[0-9]\+/iodepth=${qd}/g" $jobfn &&
#       sed -i "s/numjobs=[0-9]\+/numjobs=${nj}/g" $jobfn &&
#       sed -i "s/runtime=[0-9]\+/runtime=${runtime}/g" $jobfn &&
#       sed -i "s|write_bw_log=.\+|write_bw_log=${logfn}|g" $jobfn &&
#       sed -i "s|write_lat_log=.\+|write_lat_log=${logfn}|g" $jobfn &&
#       sed -i "s|write_iops_log=.\+|write_iops_log=${logfn}|g" $jobfn

#       client_args="$client_args --client $client $jobfn"
#     done
#     args="--output=$jsonfn --output-format=json"
#     echo "starting ${jobtype} iodepth=$qd njobs=$nj ..."
#     fio $args $client_args
#   done
# done
# exit 0
