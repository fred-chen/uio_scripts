#!/usr/bin/bash
# wipe all data disks, init DP backend and reserve space for coredumps
# Maintainer: Fred Chen

CORE_MD_PATH="/dev/md/mdcore"
CORE_MNT="/var/coredumps"
CORE_SIZE_G=300  # size in GiB reserved for core dump
DISK_SIZE_G=""   # size in GiB for disks
OP=
DISCARD_RUNS=0
DEVS=

function usage { echo "usage: $(basename $0) [ -O clear|init ] [ -G dumpdev_size ] [ -S disk_size ] devs..." && exit 1; }
handleopts() {
    OPTS=`getopt -o G:hS:O:  -- "$@"`
    [[ $? -eq 0 ]] || usage

    eval set -- "$OPTS"
    while true ; do
        case "$1" in
            -h) shift 1; usage;;
            -G) CORE_SIZE_G=$2; shift 2;;
            -S) DISK_SIZE_G=$2; shift 2;;
            -O) OP=$2; shift 2;;
            --) shift; break;;
        esac
    done
    [[ -z "$OP" ]] && echo "must specify an operation with '-O'" && exit 1;
    [[ $# -ne 0 ]] && DEVS=$@
}

function clear() {
  fuser -k ${CORE_MNT}
  umount ${CORE_MNT} || { mount | grep -w ${CORE_MNT} && { echo "can't umount ${CORE_MNT}"; exit 1; } }
  while [[ `grep -E '^md[0-9a-zA-Z]+ : .+sd.3' /proc/mdstat | wc -l` -gt 0 ]]; do mdadm --stop --scan; done
  sync

  echo -n "clearing disks ${!devices[@]} ... "
  # clear partitions
  for d in ${!devices[@]}
  do
    wipefs -f -a ${d}  > /dev/null 2>&1
    dd if=/dev/zero of=${d} bs=1M count=16 > /dev/null 2>&1
    mdadm --zero-superblock ${d}
  done
  echo "done"
}

function reload_partitions() {
    partprobe ${d}
    blockdev --rereadpt -v ${d}
}

function init() {
  echo -n "init disks ${!devices[@]} ... "
  capacity_k=

  if [[ -z "${DISK_SIZE_G}" ]]; then
    for d in ${!devices[@]}
    do
      sz_b=`blockdev --getsize64 ${d}` && sz_k=`expr ${sz_b} / 1024`
      capacity_k=$((capacity_k+sz_k))
    done
  else
    capacity_k=`expr ${DISK_SIZE_G} \* ${#devices[@]} \* 1024 \* 1024`
  fi
  ratio=`echo - | awk "{ print ${CORE_SIZE_G} * 1024 * 1024 / ${capacity_k} }"`

  # wipe ssd
  for d in ${!devices[@]}
  do
    # Discard the content of sectors on a device.
    wipefs -f -a ${d}  > /dev/null 2>&1
    dd if=/dev/zero of=${d} bs=1M count=16 > /dev/null 2>&1
  done

  for d in ${!devices[@]}
  do
    # make partitions for index swap, user data, and coredump device ( only if disk number >= 3 )
    if [[ -z "${DISK_SIZE_G}" ]]; then
      sz_b=`blockdev --getsize64 ${d}` && sz_k=`expr ${sz_b} / 1024`
      sz_k_reserved=`echo - | awk "{ print ${sz_k} * ${ratio} }"` && sz_k_reserved=`printf "%.0f" ${sz_k_reserved}`
      offset_G_data=$((($sz_k - $sz_k_reserved) / 1024 / 1024))
      parted -a optimal -s ${d} mklabel gpt
      parted -a optimal -s ${d} mkpart primary 1024KiB 2%
      parted -a optimal -s ${d} mkpart primary 2% ${offset_G_data}GiB
      parted -a optimal -s ${d} mkpart primary ${offset_G_data}GiB 100%
    else
      sz_k=`expr ${DISK_SIZE_G} \* 1024 \* 1024`
      sz_k_reserved=`echo - | awk "{ print ${sz_k} * ${ratio} }"` && sz_k_reserved=`printf "%.0f" ${sz_k_reserved}`
      offset_G_data=$((($sz_k - $sz_k_reserved) / 1024 / 1024))
      offset_G_Idx=$(($sz_k * 2 / 1024 / 1024 / 100))
      parted -a optimal -s ${d} mklabel gpt
      parted -a optimal -s ${d} mkpart primary 1024KiB ${offset_G_Idx}GiB
      parted -a optimal -s ${d} mkpart primary ${offset_G_Idx}GiB ${offset_G_data}GiB
      parted -a optimal -s ${d} mkpart primary ${offset_G_data}GiB ${DISK_SIZE_G}GiB
    fi
    reload_partitions
  done

  core_devs=
  # make a mdadm raid for coredump dev
  for d in ${!devices[@]}
  do
    core_devs="$core_devs ${d}3"
    wipefs -f -a ${d}1  > /dev/null 2>&1
    wipefs -f -a ${d}2  > /dev/null 2>&1
    wipefs -f -a ${d}3  > /dev/null 2>&1
  done

  [ ! -z "$core_devs" ] && {
    yes | mdadm --create ${CORE_MD_PATH} --level=raid0 --raid-devices=${#devices[@]} ${core_devs};
  } || { echo "failed to create core dump raid device" && return 1; }
  sync

  # discard index and data partitions
  [[ ${DISCARD_RUNS} -eq 0 ]] && {
    for d in ${!devices[@]}
    do
      blkdiscard ${d}1 &
      blkdiscard ${d}2 &
    done && wait
    DISCARD_RUNS=$((DISCARD_RUNS+1))
  }

  mkdir -p ${CORE_MNT}
  # mount core dump device
  mkfs -t ext4 ${CORE_MD_PATH} && mount ${CORE_MD_PATH} ${CORE_MNT}
  mounted=`df -h | grep /var/coredumps | wc -l`
  [[ $mounted -eq 0 ]] && retuen 1

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
  handleopts "$@"
  if [[ -z "$DEVS" ]]; then
    # get / filesystem device
    ROOTDEV=`mount | grep -w / | awk '{print $1}' | sed 's/[0-9]//g'`
    DEVS="`lsblk -lpn -o NAME | grep -w 'sd.' | grep -v $ROOTDEV`"
  fi

  for d in $DEVS
  do
    [[ -e "$d" ]] && continue || { echo "'$d' does not exist."; exit 1; }
  done

  declare -A devices
  for d in $DEVS # build a device name->wwn assoc-array
  do
    read n w <<< `lsblk -lpnd -o NAME,WWN $d`
    devices["$n"]="$w"
  done
  echo "backend devices: ${!devices[@]}"
  [[ ! -z "$OP" ]] && [[ ! "$OP" =~ clear|init ]] && usage
  [[ "$OP" == "clear" ]] && clear && exit 0
  if [[ "$OP" == "init"  ]]; then
    i=0
    while [[ $i -le 3 ]]; do
      clear
      if init; then
        exit 0
      fi
      i=$((i+1))
      echo "faied. retry ... $i"
    done
  fi
}

main "$@"
