########################## CentOS 7 AMI Kickstart ############################
# CentOS 7 kickstart designed to install over an existing linux (HVM) image
#
# Based on https://github.com/CentOS/sig-cloud-instance-build/blob/master/cloudimg/CentOS-7-x86_64-GenericCloud-201606-r1.ks
#

# Install Linux in non-interactive text mode
install
text

########################## Repositories ##########################
# Base URL of repository. Should pick a fast, geographically close location
url --url=http://mirror.san.fastserv.com/pub/linux/centos/7/os/x86_64/
#url --url="http://mirror.centos.org/centos/7/os/x86_64/"
repo --name=updates --mirrorlist=http://mirrorlist.centos.org/?release=7&arch=x86_64&repo=updates
# Epel repository is needed for cloud-init
repo --name=epel --mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-7&arch=x86_64

########################## System configuration ##############################
skipx
lang en_US.UTF-8
keyboard us
timezone UTC --isUtc
network --bootproto=dhcp --onboot=on --noipv6
firewall --disabled
selinux --disabled
#selinux --permissive
eula --agreed
logging --level=info
authconfig --enableshadow --passalgo=sha512
firstboot --disabled
rootpw --iscrypted !!

# Request reboot|poweroff after installation -- poweroff if packaging AMI immediately after install
poweroff
#reboot

services --disabled=NetworkManager,kdump --enabled=acpid,ntpd,sshd

############################# Disk partitioning ##############################
bootloader
zerombr
clearpart --all --initlabel
part / --fstype xfs --size 1000 --grow --label=/

############################### Packages #####################################
%packages --nobase --excludedocs
@core --nodefaults
-aic94xx-firmware*
-alsa-*
-iwl*firmware
-biosdevname
-ivtv-firmware
-NetworkManager*
-iprutils
-plymouth
net-tools
ntp
openssh
yum-plugin-priorities
yum-utils
epel-release
cloud-init
cloud-utils-growpart
dracut-config-generic
-dracut-config-rescue
%end

######## Post Install ########
%post

# Remove grub config for booting this kickstart and clean up X11 stuff in /tmp
rm -rf /boot/grub
rm -f /boot/kickstart*
rm -rf /tmp/.*-unix

# Remove firewalld; it is required to be present for install/image building.
# but we dont ship it in cloud
#yum -C -y remove firewalld --setopt="clean_requirements_on_remove=1"
yum -C -y remove linux-firmware

# setup systemd not to use graphical interface target
rm -f /etc/systemd/system/default.target
ln -s /lib/systemd/system/multi-user.target /etc/systemd/system/default.target

# remove auto virtual TTYs and reorder console entries
sed -i 's/#NAutoVTs=.*/NAutoVTs=0/' /etc/systemd/logind.conf
sed -i 's/console=tty0/console=tty0 console=ttyS0,115200n8/' /boot/grub2/grub.cfg

# Fix network config to remove UUID and mac address references
# simple eth0 config, again not hard-coded to the build hardware
cat > /etc/sysconfig/network-scripts/ifcfg-eth0 << EOF
DEVICE="eth0"
BOOTPROTO="dhcp"
ONBOOT="yes"
TYPE="Ethernet"
USERCTL="yes"
PEERDNS="yes"
IPV6INIT="no"
EOF
echo -e "NETWORKING=yes\nNOZEROCONF=yes" > /etc/sysconfig/network

# change dhcp client retry/timeouts to resolve bug #6866
echo -e "timeout 300;\nretry 60;" > /etc/dhcp/dhclient.conf

# remove ssh keys and any rules setting up network interfaces
rm -f /etc/udev/rules.d/70-persistent-*
ln -s /dev/null /etc/udev/rules.d/80-net-name-slot.rules
rm -rf /etc/ssh/*key*

# disable systemd from auto-mounting tmpfs ram disk on /tmp
systemctl mask tmp.mount

# make sure firstboot doesn't start
echo "RUN_FIRSTBOOT=NO" > /etc/sysconfig/firstboot

# set infra tag for future compatibility
echo 'genclo' > /etc/yum/vars/infra

# Fix grub and fstab to refer to LABEL instead of UUID
sed -i 's#UUID=.* / #LABEL=/                 / #' /etc/fstab
sed -i 's#root=UUID=[0-9a-f-]* #root=LABEL=/ #' /boot/grub2/grub.cfg

# Use cloud-user as cloud-init default user
sed -i 's/ name: .*/ name: cloud-user/' /etc/cloud/cloud.cfg
sed -i 's/ gecos: .*/ gecos: Cloud User/' /etc/cloud/cloud.cfg
# Clean yum and temp up a bit
yum clean all

echo "Fixing SELinux contexts."
touch /var/log/cron
touch /var/log/boot.log
mkdir -p /var/cache/yum
/usr/sbin/fixfiles -R -a restore

# Fill the remaining disk with zeros for maximum image compression
dd if=/dev/zero of=/zerofill bs=1M
rm -f /zerofill

%end
