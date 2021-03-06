#!/bin/sh

PIDFILE="/opt/ETS/cron/often.pid"

if test -r $PIDFILE ; then

  if $(kill -CHLD `cat $PIDFILE` >/dev/null 2>&1) ; then
    echo "pid is alive, exiting"
    exit 0
  else
    echo "pid is dead, continue"
  fi

fi
echo $$ > $PIDFILE

#Submit waybills to COMPAS
./bin/instance submit_waybills 2>&1
./bin/instance order_percentage 2>&1
rm -f $PIDFILE
