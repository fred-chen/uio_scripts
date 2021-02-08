#!/usr/bin/bash
# wipe all data disks, init DP backend and reserve space for coredumps
# Maintainer: Fred Chen

CORE_MD_PATH="/dev/md127"
CORE_MNT="/var/coredumps"
CORE_SIZE_G=300  # size in GiB reserved for core dump
DISK_SIZE_G=480  # size in GiB for disks
OP=

function usage { echo "usage: $(basename $0) [ clear|init ] [ -G dumpdev_size ] [ -S disk_size ]" && exit 1; }
handleopts() {
    OPTS=`getopt -o G:hS:  -- "$@"`
    [[ $? -eq 0 ]] || usage

    eval set -- "$OPTS"
    while true ; do
        case "$1" in
            -h) shift 1; usage;;
            -G) CORE_SIZE_G=$2; shift 2;;
            -S) DISK_SIZE_G=$2; shift 2;;
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
  mdadm --zero-superblock ${!devices[@]}
  # clear partitions
  for d in ${!devices[@]}
  do
    wipefs -f -a ${d}  > /dev/null 2>&1
    dd if=/dev/zero of=${d} bs=1M count=16 > /dev/null 2>&1
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
  for d in ${!devices[@]}
  do
    sz_b=`blockdev --getsize64 ${d}` && sz_k=`expr ${sz_b} / 1024`
    capacity_k=$((capacity_k+sz_k))
  done

  ratio=`echo - | awk "{ print ${CORE_SIZE_G} * 1024 * 1024 / ${capacity_k} }"`

  # discard ssd
  for d in ${!devices[@]}
  do
    # Discard the content of sectors on a device.
    wipefs -f -a ${d}  > /dev/null 2>&1
    dd if=/dev/zero of=${d} bs=1M count=16 > /dev/null 2>&1
    reload_partitions
  done

  for d in ${!devices[@]}
  do
    # make partitions for index swap, user data, and coredump device ( only if disk number >= 3 )
    if [[ -z "${DISK_SIZE_G}" ]]; then
      sz_b=`blockdev --getsize64 ${d}` && sz_k=`expr ${sz_b} / 1024`
      sz_k_reserved=`echo - | awk "{ print ${sz_k} * ${ratio} }"` && sz_k_reserved=`printf "%.0f" ${sz_k_reserved}`
      offset_G_data=$((($sz_k - $sz_k_reserved) / 1024 / 1024))
      echo $sz_k, $offset_G_data, $sz_k_reserved
      parted -s ${d} mklabel gpt
      parted -s ${d} mkpart primary 0 2%
      parted -s ${d} mkpart primary 2% ${offset_G_data}GiB
      parted -s ${d} mkpart primary ${offset_G_data}GiB 100%
    else
      sz_k=`expr ${DISK_SIZE_G} \* 1024 \* 1024`
      sz_k_reserved=`echo - | awk "{ print ${sz_k} * ${ratio} }"` && sz_k_reserved=`printf "%.0f" ${sz_k_reserved}`
      offset_G_data=$((($sz_k - $sz_k_reserved) / 1024 / 1024))
      offset_G_Idx=$(($sz_k * 2 / 1024 / 1024 / 100))
      echo ${DISK_SIZE_G}, $sz_k, $offset_G_data, $sz_k_reserved, $offset_G_Idx
      parted -s ${d} mklabel gpt
      parted -s ${d} mkpart primary 0 ${offset_G_Idx}GiB
      parted -s ${d} mkpart primary ${offset_G_Idx}GiB ${offset_G_data}GiB
      parted -s ${d} mkpart primary ${offset_G_data}GiB ${DISK_SIZE_G}
    fi
    reload_partitions
  done

  core_devs=
  make a mdadm raid for coredump dev
  for d in ${!devices[@]}
  do
    core_devs="$core_devs ${d}3"
    wipefs -f -a ${d}3  > /dev/null 2>&1
  done
  [ ! -z "$core_devs" ] && {
    yes | mdadm --create ${CORE_MD_PATH} --level=raid0 --raid-devices=${#devices[@]} ${core_devs};
  } || { echo "failed to create core dump raid device" && exit 1; }

  while [[ ! -e ${CORE_MD_PATH} ]]; do { sleep 1; } done

  # discard index and data partitions
  for d in ${!devices[@]}
  do
    blkdiscard ${d}1 &
    blkdiscard ${d}2 &
  done && wait

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
  [[ ! -z "$OP" ]] && [[ ! "$OP" =~ clear|init ]] && usage
  [[ "$OP" == "clear" ]] && clear && exit 0
  [[ "$OP" == "init"  ]] && { clear && init; } && exit 0
}

main $@
