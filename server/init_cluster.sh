#!/usr/bin/bash
# UniIO node manipulation script
# Functions:
#   start, stop uniio ode
#   reinstall rpms
#   init DP backend ( calling init_backend.sh in the same directory )
#   push topology and create luns
# Maintainer: Fred Chen

REPLACE=false       # default rpm packages
INIT_BACKEND=false  # no init backend by default
INIT_ARRAY=false
TOPOLOGY="192.168.101.169,192.168.103.248,192.168.100.206"
MANAGEMENT_IP="192.168.103.253"
ISCSI_IP="192.168.60.253"
STOP_ONLY=false
FORCE=false
BOOT_ONLY=false
CREATE_LUNS=false
ATTACH_LUNS=false
RPMDIR=
CORE_DEV_SIZE_G=300
NUM_LUNS=18

usage() {
  [[ -z "$1" ]] || echo "Error: $1"
  len=$(expr length "usage: `basename $0`")
  printf "usage: `basename $0` %s\n" "[-f] [-s|--stoponly]"
  printf "%${len}s %s\n" " " "[-b|--bootonly]"
  printf "%${len}s %s\n" " " "[-r|--replace rpm_dir]"
  printf "%${len}s %s\n" " " "[-d|--initbackend] [-G dump_size]"
  printf "%${len}s %s\n" " " "[-i|--initarray]"
  printf "%${len}s %s\n" " " "[-c|--createluns num_luns]"
  printf "%${len}s %s\n" " " "[--management_ip ip --iscsi_ip ip --topology ip,ip...]"
  printf "%${len}s %s\n" " " "[-a|--attachluns]"
  echo " -f: force (killing cio_array)"
  echo " -s: stop only"
  echo " -r: replace rpm packages"
  echo " -b: start objmgr and objmgr-fab"
  echo " -d: initialize backend"
  echo " -G: prereserve size for coredump device"
  echo " -i: initialize array"
  echo " -c: create new luns and mappings"
  echo " -a: attach all existing luns and mappings"
  echo " --management_ip: specify the management IP address for the federation"
  echo " --iscsi_ip:      specify the management IP address for the federation"
  echo " --topology:      specify the node IP addresses for the federation"
  exit 1
}
handleopts() {
    OPTS=`getopt -o r::dsfhbic::G:a -l replace:,initbackend,stoponly,initarray,createluns::,management_ip:,iscsi_ip:,topology:attachluns -- "$@"`
    [[ $? -eq 0 ]] || usage

    eval set -- "$OPTS"
    while true ; do
        case "$1" in
            -r | --replace )
              REPLACE=true
              [[ -z "$2" ]] && RPMDIR="./rpm" || RPMDIR=$2
              shift 2
              ;;
            -d | --initbackend ) INIT_BACKEND=true; shift 1;;
            -i | --initarray ) INIT_ARRAY=true; shift 1;;
            -s | --stoponly ) STOP_ONLY=true; shift 1;;
            -b | --bootonly ) BOOT_ONLY=true; shift 1;;
            -c | --createluns ) CREATE_LUNS=true; NUM_LUNS=$2; shift 2;;
            -a | --attachluns ) ATTACH_LUNS=true; shift 1;;
            --management_ip ) MANAGEMENT_IP=$2; shift 2;;
            --iscsi_ip ) ISCSI_IP=$2; shift 2;;
            --topology ) TOPOLOGY=$2; shift 2;;
            -f ) FORCE=true; shift 1;;
            -G ) CORE_DEV_SIZE_G=$2; shift 2;;
            -h ) shift 1 && usage;;
            --) shift; break;;
        esac
    done
    [[ -z "$NUM_LUNS" ]] && NUM_LUNS=18
}
is_ciorunning() {
  [[ $(ps -ef|grep fabric-manager.jar|grep -v grep|wc -l) -gt 0 ]] && return 0 || return 1
}
is_arrayrunning() {
  [[ `pgrep -nx cio_array|wc -l` -gt 0 ]] && return 0 || return 1
}
detach_luns() {
  echo -n "detaching luns... "
  is_ciorunning && {
    for n in `cioctl list | grep GB | awk '{print $2}' | grep -v '^-'`; do cioctl detach $n  > /dev/null 2>&1; done
    for n in `cioctl snapshot list | grep GiB | awk '{print $2}'`; do cioctl detach $n  > /dev/null 2>&1; done;
  }
  echo 'done.'
}
attach_luns() {
  echo -n "attaching luns... "
  is_ciorunning && {
    for n in `cioctl list | grep GB | awk '{print $2}' | grep -v '^-'`; do cioctl attach $n  > /dev/null 2>&1; done
    for n in `cioctl snapshot list | grep GiB | awk '{print $2}'`; do cioctl attach $n  > /dev/null 2>&1; done;
  }
  echo 'done.'
}
delete_luns() {
  echo -n "deleting luns... "
  is_ciorunning && {
    for n in `cioctl iscsi mapping list | grep iqn | awk '{print $2}'`; do cioctl iscsi mapping delete --blockdevice $n --yes-i-really-really-mean-it; done
    for n in `cioctl iscsi target list | grep iqn | awk '{print $2}'`; do cioctl iscsi target delete --name $n --yes-i-really-really-mean-it; done
    for n in `cioctl snapshot list | grep GiB | awk '{print $2}'`; do cioctl detach $n; done
    for n in `cioctl list | grep GiB | awk '{print $2}' | grep -v '^-'`; do cioctl delete $n; done
    for n in `cioctl iscsi initiatorgroup list | grep -E '.+-[0-9]+-' | awk '{print $2}'` ; do cioctl iscsi initiatorgroup delete --name $n --yes-i-really-really-mean-it; done
    for n in `cioctl iscsi initiator list | grep -E '.+-[0-9]+-' | awk '{print $2}'` ; do cioctl iscsi initiator delete --name $n --yes-i-really-really-mean-it; done;
  }
  echo "done."
}
create_luns() {
  is_ciorunning && is_arrayrunning && {
    cioctl iscsi initiator create --name i155 --iqn iqn.1994-05.com.redhat:c031f7521388
    cioctl iscsi initiator create --name i169 --iqn iqn.1994-05.com.redhat:2e515e5f713
    cioctl iscsi initiator create --name i156 --iqn iqn.2020-02.naming.authority:unique-156
    # cioctl iscsi initiatorgroup create --name igall --initiators i155,i156,i169
    cioctl iscsi initiatorgroup create --name ig155 --initiators i155
    cioctl iscsi initiatorgroup create --name ig156 --initiators i156
    cioctl iscsi initiatorgroup create --name ig169 --initiators i169


    for n in `seq 1 $NUM_LUNS`; do cioctl create lun$n 500G; done
    for n in `seq 1 $NUM_LUNS`; do cioctl iscsi target create --name tgt-$n; done
    for n in `seq 1 6`; do cioctl iscsi mapping create --blockdevice lun$n --target tgt-$n --initiatorgroup ig155; done
    for n in `seq 7 12`; do cioctl iscsi mapping create --blockdevice lun$n --target tgt-$n --initiatorgroup ig156; done
    for n in `seq 13 18`; do cioctl iscsi mapping create --blockdevice lun$n --target tgt-$n --initiatorgroup ig169; done
  }
  cioctl list
}

stop_array() {
  is_arrayrunning && {
    [[ ${FORCE} == true ]] && { echo -n "force stopping array... "; [[ ! -z "`pidof cio_array`" ]] && kill `pidof cio_array`; } || { echo -n "stopping array... "; detach_luns; }
    systemctl stop objmgr  > /dev/null 2>&1 || { echo "failed 'systemctl stop objmgr'."; return 1; }
    systemctl stop objmgr-fab  > /dev/null 2>&1 || { echo "failed 'systemctl stop objmgr-fab'."; return 1; }
    rmmod objblk > /dev/null 2>&1 || true
    echo "done."
  } || return 0
}

start_array() {
  echo -n "starting array... "
  modprobe scst_vdisk
  modprobe isert_scst
  modprobe iscsi_scst
  modprobe scst
  modprobe dlm
  modprobe rdma_cm
  modprobe ib_core
  modprobe libcrc32c
  modprobe objblk
  systemctl restart scst
  systemctl start objmgr objmgr-fab
  echo "done."
}
push_topology() {
  is_ciorunning && {
    echo -n "pushing topology ..."
    cioctl topology $TOPOLOGY > /dev/null 2>&1
    cioctl portal --management_ip $MANAGEMENT_IP --iscsi_ip $ISCSI_IP > /dev/null 2>&1 || { echo "failed 'cioctl portal --management_ip $MANAGEMENT_IP --iscsi_ip $ISCSI_IP'"; return 1; }
    echo "done."
  } || echo "cio is not running."
}
replace_rpm() {
  for n in ${RPMDIR}/*.rpm
  do
    echo -n "installing $n ..."
    rpm -Uvh --replacepkgs --replacefiles --force $n > /dev/null 2>&1 && echo "done." || { echo "failed."; return 1; }
  done
}
uninit_array() {
  stop_array || return 1
  echo -n "uninitializing array... "
  /opt/uniio/sbin/objmgr uninit > /dev/null 2>&1 || { echo "failed 'objmgr uninit'" && return 1; }
  rmmod objblk > /dev/null 2>&1 || true
  rm -rf /opt/uniio/cio* > /dev/null 2>&1
  ndctl create-namespace --force --reconfig=namespace0.0 --mode=raw > /dev/null 2>&1 || { echo "failed ndctl create-namespace" && return 1; }
  dd if=/dev/zero of=/dev/pmem0 bs=4k count=10000000 > /dev/null 2>&1
  echo "done."
}
init_backend() {
  echo -n "initializing backend ..."
  SCRIPT_PATH=$(dirname $0)
  ${SCRIPT_PATH}/init_backend.sh init -G $CORE_DEV_SIZE_G > /dev/null 2>&1 || { echo "failed init backend." && return 1; }
  echo "done"
}
init_array() {
  uninit_array && init_backend || return 1
  echo -n "initializing array... "
  /opt/uniio/sbin/objmgr init > /dev/null 2>&1 || { echo "failed 'objmgr init'" && return 1; }
  echo "done."
}

main() {
  handleopts "$@"
  echo "INIT_BACKEND=$INIT_BACKEND", "REPLACE=$REPLACE", "RPMDIR=$RPMDIR", "FORCE=$FORCE", "STOP_ONLY=$STOP_ONLY", "BOOT_ONLY=$BOOT_ONLY"
  [[ $STOP_ONLY == true ]] && stop_array && exit 0
  [[ $REPLACE == true ]] && stop_array && replace_rpm
  [[ $BOOT_ONLY == true ]] && start_array && exit 0
  [[ ${INIT_BACKEND} == true ]] && uninit_array && init_backend
  [[ ${INIT_ARRAY} == true ]] && init_array && start_array
  [[ ${CREATE_LUNS} == true ]] && { push_topology; create_luns; }
  [[ ${ATTACH_LUNS} == true ]] && { push_topology; attach_luns; }
}

main "$@"
