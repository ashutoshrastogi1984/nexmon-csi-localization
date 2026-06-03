#!/bin/sh
# router_init.sh
# Place this at /jffs/scripts/init-start on the router
# It loads the nexmon-patched dhd.ko at every boot
# Merlin firmware runs this script during startup

sleep 30
/sbin/rmmod dhd
/sbin/insmod /jffs/dhd.ko
