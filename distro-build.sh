#!/bin/bash

# Notes for after this script is run, and the system boots.
# enable vnc though rpi-config
#    add `Authentication=VncAuth` to /root/.vnc/config.d/vncserver-x11
#    run `vncpasswd -service` to add hashed password to above config file
# make sure SPI is enabled in rpi-config
# Add `export DISPLAY=:0` to ~/.bashrc to make it easier to launch/test via ssh


set -ex


### CONFIG Update this first! #################################################

BOOT=/mnt/rpi/boot/
ROOT=/mnt/rpi/root/
# path to the SOURCE image being modified
IMAGE_PATH='/home/sam/Downloads/linuxcnc-2.8.1-pi4 (4)/2021-01-20-linuxcnc-pi4.img'
BOOTLOADER_PATH='/home/sam/rpi-kernel/boot_from_existing_new_working_image'

### END CONFIG SECTION ########################################################

mkdir -p rt-kernel
mkdir -p $BOOT
mkdir -p $ROOT

LOOP=$(losetup --show -f -P "$IMAGE_PATH")
mount ${LOOP}p1 $BOOT
mount ${LOOP}p2 $ROOT



git clone https://github.com/raspberrypi/linux.git -b rpi-4.19.y-rt || git -C "linux" pull
git clone https://github.com/raspberrypi/tools.git || git -C "tools" pull

# Setup variables to cross compile
export ARCH=arm
export CROSS_COMPILE=~/rpi-kernel/tools/arm-bcm2708/gcc-linaro-arm-linux-gnueabihf-raspbian-x64/bin/arm-linux-gnueabihf-
export INSTALL_MOD_PATH=~/rpi-kernel/rt-kernel
export INSTALL_DTBS_PATH=~/rpi-kernel/rt-kernel

export KERNEL=kernel7l
cd ~/rpi-kernel/linux/
make -j16 bcm2711_defconfig

make -j16 zImage 
make -j16 modules 
make -j16 dtbs 
make -j16 modules_install 
make -j16 dtbs_install

cd -
./linux/scripts/mkknlimg ./linux/arch/arm/boot/zImage $BOOT/kernel7_rt.img
sudo cp -dr $INSTALL_MOD_PATH/lib/* $ROOT/lib/
sudo cp -d $INSTALL_MOD_PATH/overlays/* $BOOT/overlays/
sudo cp -d $INSTALL_MOD_PATH/bcm* $BOOT/

echo "kernel=kernel7_rt.img" >> $BOOT/config.txt

cd ${BOOTLOADER_PATH}
cp ./fixup* $BOOT/
cp ./start* $BOOT/

cd -

sync
umount $ROOT
umount $BOOT
sync

