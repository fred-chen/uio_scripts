#!/usr/bin/bash
# wipe all data disks, init DP backend and reserve space for coredumps
# Maintainer: Fred Chen

CORE_MD_PATH="/dev/md/mdcore"
CORE_MNT="/var/coredumps"
CORE_SIZE_G=300  # size in GiB reserved for core dump
OP=

function usage { echo "usage: $(basename $0) [ clear|init ] [ -G dumpdev_size ]" && exit 1; }
handleopts() {
    OPTS=`getopt -o G:h  -- "$@"`
    [[ $? -eq 0 ]] || usage

    eval set -- "$OPTS"
    while true ; do
        case "$1" in
            -h) shift 1; usage;;
            -G) CORE_SIZE_G=$2; shift 2;;
            --) shift; break;;
        esac
    done
    [[ $# -ne 0 ]] && OP=$@ || OP=""
}

function clear() {
  fuser -k ${CORE_MNT}
  umount ${CORE_MNT} || { mount | grep -w ${CORE_MNT} && { echo "can't umount ${CORE_MNT}"; exit 1; } }

  mdadm --stop ${CORE_MD_PATH}
  while [[ -e ${CORE_MD_PATH} ]]; do { echo "stopping ${CORE_MD_PATH}..."; sleep 1; } done

  echo -n "clearing disks ${!devices[@]} ... "
  # clear partitions
  for d in ${!devices[@]}
  do
    wipefs -f -a ${d}  > /dev/null 2>&1
    dd if=/dev/zero of=${d} bs=1M count=16 > /dev/null 2>&1
  done
  echo "done"
}

function init() {
  echo -n "init disks ${!devices[@]} ... "
  capacity_k=
  for d in ${!devices[@]}
  do
    sz_b=`blockdev --getsize64 ${d}` && sz_k=`expr ${sz_b} / 1024`
    capacity_k=$((capacity_k+sz_k))
  done

  ratio=`echo - | awk "{ print ${CORE_SIZE_G} * 1024 * 1024 / ${capacity_k} }"`

  # make partitions for index swap, user data, and coredump device
  for d in ${!devices[@]}
  do
    sz_b=`blockdev --getsize64 ${d}` && sz_k=`expr ${sz_b} / 1024`
    sz_k_reserved=`echo - | awk "{ print ${sz_k} * ${ratio} }"` && sz_k_reserved=`printf "%.0f" ${sz_k_reserved}`
    offset_G_data=$((($sz_k - $sz_k_reserved) / 1024 / 1024))
    echo $sz_k, $offset_G_data, $sz_k_reserved

    wipefs -f -a ${d}  > /dev/null 2>&1
    dd if=/dev/zero of=${d} bs=1M count=16 > /dev/null 2>&1

    parted -s ${d} mklabel gpt
    parted -s ${d} mkpart primary 0 2%
    parted -s ${d} mkpart primary 2% ${offset_G_data}GiB
    parted -s ${d} mkpart primary ${offset_G_data}GiB 100%
  done
  echo "done."

  core_devs=
  # make a mdadm raid for coredump dev
  for d in ${!devices[@]}
  do
    core_devs="$core_devs ${d}3"
  done
  [ ! -z "$core_devs" ] && {
    mdadm --create ${CORE_MD_PATH} --level=0 --raid-devices=${#devices[@]} ${core_devs} > /dev/null 2>&1 || true;
  } || { echo "failed to create core dump raid device" && exit 1; }

  while [[ ! -e ${CORE_MD_PATH} ]]; do { sleep 1; } done

  mkdir -p ${CORE_MNT}
  # mount core dump device
  mkfs -t ext4 ${CORE_MD_PATH} && mount ${CORE_MD_PATH} ${CORE_MNT}
  sysctl -w kernel.core_pattern=/var/coredumps/core-%e-sig%s-user%u-group%g-pid%p-time%t
  ulimit -c unlimited

  # prepare config.ini for DP backend
  echo '[devicemap]' > /etc/objblk/config.ini
  i=0
  for d in ${!devices[@]}
  do
    echo "  IndexSwapDisk_${i} = /dev/disk/by-id/wwn-${devices[$d]}-part1" >> /etc/objblk/config.ini
    echo "  BackendDisk_${i} = /dev/disk/by-id/wwn-${devices[$d]}-part2" >> /etc/objblk/config.ini
    i=$((i+1))
  done
}

function main() {
  handleopts $@
  # get / filesystem device
  ROOTDEV=`mount | grep -w / | awk '{print $1}' | sed 's/[0-9]//g'`
  DEVS=`lsblk -lpn -o NAME | grep -w 'sd.' | grep -v $ROOTDEV`

  declare -A devices
  for d in $DEVS # build a device name->wwn assoc-array
  do
    read n w <<< `lsblk -lpnd -o NAME,WWN $d`
    devices["$n"]="$w"
  done
  echo "backend devices: ${!devices[@]}"
  exit 1
  [[ ! -z "$OP" ]] && [[ ! "$OP" =~ clear|init ]] && usage
  [[ "$OP" == "clear" ]] && clear
  [[ "$OP" == "init"  ]] && { clear && init; }
}

main $@
