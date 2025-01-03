#!/usr/bin/env bash
# fio wrapper
# requirements:
#   - fio installed
# Maintainer: Fred Chen

clients="192.168.100.155,192.168.100.156,192.168.100.169" # fio clients running "fio --server --daemonize"
outputdir=fio_output     # the directory where fio saves *.json files to
logdir=fio_log           # the directory where fio saves the bandwidth, iops, latency logs
profiledir=./            # the directory where fio find its job files
qds="1"                  # iodepths fio will use in job files. multiple q depth can be specified: '1,2,3'
njobs="1"                # numjobs fio will use in job files. multiple numjobs can be specified: '1,2,3'
szs="4096"               # bytes per io, will be used in job files. multiple szs can be specified: '512,1024,4096,8192'
runtime=600              # the time that fio will run
jobtype=                 # job type, a prefix of fio job files
duprate=                 # dedup ratio. (dedupe_percentage=xxx in fio profile)
comprate=                # compression ratio. (buffer_compress_percentage=xxx in fio profile)
steadytime=              # steady state time last for n seconds before stop ()
rws="read"               # rw types: read/write/randread/randwrite
overwrite=false          # do not overwrite existing test result files if they exist (will skip those tests)
comm_before_write=""     # insert a customized command between write jobs (for example, discard ssd before next task.)
comm_before_read=""      # insert a customized command between read jobs (for example, fill in some data.)

function usage() {
  [[ ! -z $1 ]] && {
    echo
    >&2 echo "ERROR:" $1
    echo
  }
  len=$(expr length "usage: `basename $0`")
  printf "usage: `basename $0` <job_type> [-p|--profiledir dir] [-j|--jobs job_str] [-q|--qdepth qd_str] [-b|--bs bs_str]\n"
  printf "%${len}s            [-t|--time secs] [-c|--clients client_str]\n" " "
  printf "%${len}s            [--duprate pct] [--comprate pct]\n" " "
  echo
  echo "job_type:        job type, a prefix of fio job files"
  echo "options:"
  echo "  -p | --profiledir: specify the dir that contains fio job files"
  echo "  -s | --steadytime: specify the run time in steady state in seconds"
  echo "  -j | --jobs:   specify numjobs fio will use in job files. multiple numjobs can be specified: '1,2,3'"
  echo "  -q | --qdepth: specify iodepth fio will use in job files. multiple q depth can be specified: '1,2,3'"
  echo "  -t | --time:   specify runtime in fio profile"
  echo "  -b | --bs:     specify io size in fio profile"
  echo "  -w | --rw:     specify work type: read/write/randread/randwrite/rw/randrw"
  echo "  --duprate:     specify dedupe_percentage in fio profile"
  echo "  --comprate:    specify buffer_compress_percentage in fio profile"
  echo "  --overwrite:   force overwrite existing output json files"
  echo "  --comm_before_write:   specify a customized command before write (e.g. discard ssd before next write task.)"
  echo "  --comm_before_read:    specify a customized command before read (e.g. fill in some data.)"

  exit 1
}

handleopts() {
  OPTS=`getopt -o hc:q:t:j:d:p:b:s:w: -l help,clients:,jobs:,qdepth:,bs:,time:,devices:,duprate:,comprate:,profiledir:,overwrite,steadytime:,rw:,comm_before_write: -- "$@"`
  [[ $? -eq 0 ]] || usage
  eval set -- "$OPTS"
  while true ; do
      case "$1" in
          -c | --clients) clients=$2; shift 2;;
          -j | --jobs) njobs=$2; shift 2;;
          -w | --rw) rws=$2; shift 2;;
          -q | --qdepth) qds=$2; shift 2;;
          -b | --bs) szs=$2; shift 2;;
          -t | --time) runtime=$2; shift 2;;
          -d | --devices) devlist=$2; shift 2;;
          -p | --profiledir) profiledir=$2; shift 2;;
          -s | --steadytime) steadytime=$2; shift 2;;
          -h | --help) shift 1; usage;;
          --duprate) duprate=$2; shift 2;;
          --comprate) comprate=$2; shift 2;;
          --comm_before_write) comm_before_write=$2; shift 2;;
          --comm_before_read) comm_before_read=$2; shift 2;;
          --overwrite) shift 1; overwrite=true;;
          --) shift; break;;
      esac
  done
  [[ $# -ne 0 ]] && jobtype="$@" || usage "must specify a job type."
  njobs=`echo $njobs|sed 's/,/ /g'`
  qds=`echo $qds|sed 's/,/ /g'`
  szs=`echo $szs|sed 's/,/ /g'`
  clients=`echo $clients|sed 's/,/ /g'`
  outputdir="${profiledir}/${outputdir}"
  logdir="${profiledir}/${logdir}"
  rws=`echo $rws|sed 's/,/ /g'`
  echo "njobs=$njobs" "rws=$rws" "qds=$qds" "szs=$szs" "clients=$clients" "time=$runtime" "jobtype=$jobtype"
}

main() {
  handleopts "$@"
  mkdir -p $outputdir && mkdir -p $logdir && mkdir -p $profiledir

  for nj in $njobs
  do
    for qd in $qds
    do
      for rw in $rws
      do
        for sz in $szs
        do
          client_args=
          jobstr="$jobtype.$rw.qd$qd.njobs$nj.bs$sz"
          [[ ! -z "$duprate" ]] && jobstr="${jobstr}.${duprate}dup"
          [[ ! -z "$comprate" ]] && jobstr="${jobstr}.${comprate}comp"
          [[ ! -z "$runtime" ]] && jobstr="${jobstr}.${runtime}s"
 
          joblogdir="$logdir/${jobstr}" && mkdir -p $joblogdir
          jsonfn=$outputdir/$jobstr.json
          [[ $overwrite == false ]] && [[ -f $jsonfn ]] && echo "skipping this task, $jsonfn exists." && continue
          [[ $comm_before_write ]] && [[ $rw == "write" || $rw == "randwrite" || $rw == "rw" || $rw == "randrw" ]] && echo "running '$comm_before_write'" && eval $comm_before_write
          [[ $comm_before_read ]] && [[ $rw == "read" || $rw == "randread" || $rw == "rw" || $rw == "randrw" ]] && echo "running '$comm_before_read'" && eval $comm_before_read
          logfn=$joblogdir/$jobstr
          for client in $clients
          do
            jobfn=$profiledir/${jobtype}_$client.fio
            [[ ! -e $jobfn ]] && echo "$jobfn doesn't exist." && exit 1 || {
              [[ ! -z "$qd" ]] && sed -i "s/iodepth=[0-9]\+/iodepth=${qd}/g" $jobfn
              [[ ! -z "$nj" ]] && sed -i "s/numjobs=[0-9]\+/numjobs=${nj}/g" $jobfn
              [[ ! -z "$sz" ]] && sed -i "s/^bs=[0-9]\+[a-zA-Z]*/bs=${sz}/g" $jobfn
              [[ ! -z "$rw" ]] && sed -i "s/^rw=[a-zA-Z]*/rw=${rw}/g" $jobfn
              [[ ! -z "$runtime" ]] && sed -i "s/runtime=[0-9]\+/runtime=${runtime}/g" $jobfn
              [[ ! -z "$logfn" ]] && sed -i "s|write_bw_log=.\+|write_bw_log=${logfn}|g" $jobfn &&
                                    sed -i "s|write_lat_log=.\+|write_lat_log=${logfn}|g" $jobfn &&
                                    sed -i "s|write_iops_log=.\+|write_iops_log=${logfn}|g" $jobfn
  
              [[ ! -z "$duprate" ]] && sed -i "s|dedupe_percentage=.\+|dedupe_percentage=${duprate}|g" $jobfn
              [[ ! -z "$comprate" ]] && sed -i "s|buffer_compress_percentage=.\+|buffer_compress_percentage=${comprate}|g" $jobfn
              [[ ! -z "$steadytime" ]] && sed -i "s|ss_dur=.\+|ss_dur=${steadytime}|g" $jobfn
            }
            client_args="$client_args --client $client $jobfn"
         done
         args="--output=$jsonfn --output-format=json"
         echo "$(date) starting ${jobstr} ... "
         fio $args $client_args
         echo "$(date) done"
       done
      done
    done
  done
  return 0
}

main "$@"
