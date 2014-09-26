########################## CentOS 6 AMI Kickstart ############################
# CentOS 6 kickstart designed to install over an amazon linux HVM AMI

# Install Linux in non-interactive text mode
install
text

########################## Repositories ##########################
# Base URL of CentOS 6 repository. Should pick a fast, geographically close location
url --url=http://mirror.san.fastserv.com/pub/linux/centos/6/os/x86_64/
repo --name=updates --mirrorlist=http://mirrorlist.centos.org/?release=6&arch=x86_64&repo=updates
# Epel repository is needed for cloud-init
repo --name=epel --mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-6&arch=x86_64

########################## System configuration ##############################
skipx
lang en_US.UTF-8
keyboard us
timezone --utc Etc/UTC
network --bootproto=dhcp --onboot=on --noipv6
firewall --disabled
selinux --disabled
logging --level=info
authconfig --enableshadow --passalgo=sha512
firstboot --disabled
rootpw --iscrypted !!

# Request reboot|poweroff after installation -- poweroff if packaging AMI immediately after install
poweroff
#reboot

services --enabled="acpid"
#services --enabled=acpid,ntpd,sshd,cloud-init

############################# Disk partitioning ##############################
# We are using existing partition from amazon AMI which has label "/" for root
bootloader --location=partition
part / --onpart=/dev/xvda1 --label=/

############################### Packages #####################################
%packages --excludedocs --nobase
@Core
epel-release
cloud-init
cloud-utils-growpart
dracut-modules-growroot
gdisk


######################### Pre-install script #################################
#%pre

######################### Post-install script ################################
%post
# Fix network config to remove UUID and mac address references
sed -i '/^HWADDR\|^UUID/d' /etc/sysconfig/network-scripts/ifcfg-eth0

# Fix grub and fstab to refer to LABEL instead of UUID
sed -i 's#UUID=.* / #LABEL=/                 / #' /etc/fstab
sed -i 's#root=UUID=[0-9a-f-]* #root=LABEL=/ #' /etc/grub.conf

# Fix grub to enable PV-HVM kernel drivers
grep -q xen_pv_hvm=enable /etc/grub.conf ||
    sed -i 's#\(^[[:space:]]*kernel.*\)$#\1 xen_pv_hvm=enable#' /etc/grub.conf

# Add cloud-user (cloud-init default user) to sudoers
/bin/echo -e 'cloud-user\tALL=(ALL)\tNOPASSWD: ALL' >> /etc/sudoers.d/cloud-init
chmod 440 /etc/sudoers.d/cloud-init

# Change login.defs to use 1000 as first UID and GID for normal users
sed -i 's/^\(.ID_MIN\s*\)500$/\11000/' /etc/login.defs

# Rebuild initrd to support growing root on first boot
# note: growroot needs sgdisk for gpt partition & doesn't include it by default
echo "dracut_install sgdisk" >> /usr/share/dracut/modules.d/50growroot/install
kernel=`ls /boot/vmlinu* | cut -d - -f 2-`
dracut --force -H /boot/initramfs-$kernel.img $kernel

# Clean yum up a bit (rm -rf /var/yum/cache/* might be better)
yum clean all