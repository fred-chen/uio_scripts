PID=`pgrep -nx cio_array`
for pid in `ls /proc/$PID/task/`
do
  name=`cat /proc/$PID/task/$pid/comm`
  #echo -n $pid ":" $name && echo
  [[ $name =~ ^(networker|IOThread) ]] && echo "renice $pid: $name"
  renice -20 -p $pid
done

#cat /proc/31289/task/*/comm | grep -i -E '^(networker|iothread)'
