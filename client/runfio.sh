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
devlist="sdb,sdc,sdd,sde,sdf,sdg,sdh,sdi,sdj,sdk,sdl,sdm,sdn,sdo,sdp,sdq,sdr,sds"
jobtype=                 # job type, a prefix of fio job files


function usage() {
  [[ ! -z $1 ]] && {
    echo
    >&2 echo "ERROR:" $1
    echo
  }
  echo "usage: `basename $0` <job_type> [-c|--clients client_str] [-j|--jobs job_str] [-q|--qdepth qd_str] [-t|--time secs] [-d|--devices dev_str]"
  exit 0
}

handleopts() {
  OPTS=`getopt -o hc:q:t:j:d: -l help,clients:,jobs:,qdepth:,time:,devices: -- "$@"`
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
  echo "devlist=$devlist"
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
      jsonfn=$outputdir/$jobtype.qd$qd.njobs$nj.json
      logfn=$logdir/$jobtype.qd$qd.njobs$nj
      for client in $clients
      do
        jobfn=$profiledir/${jobtype}_$client.fio
        [[ ! -e $jobfn ]] && echo "$jobfn doesn't exist." && exit 1 || {
          sed -i "s/iodepth=[0-9]\+/iodepth=${qd}/g" $jobfn &&
          sed -i "s/numjobs=[0-9]\+/numjobs=${nj}/g" $jobfn &&
          sed -i "s/runtime=[0-9]\+/runtime=${runtime}/g" $jobfn &&
          sed -i "s|write_bw_log=.\+|write_bw_log=${logfn}|g" $jobfn &&
          sed -i "s|write_lat_log=.\+|write_lat_log=${logfn}|g" $jobfn &&
          sed -i "s|write_iops_log=.\+|write_iops_log=${logfn}|g" $jobfn
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
