#!/bin/bash

rm -f idle_shutdown.c idle_shutdown.o idle_shutdown.ko
halcompile --install ./idle_shutdown.comp
