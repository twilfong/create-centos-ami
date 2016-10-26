#!/bin/bash
#
# Add and/or update packages in an existing AMI, then clean-up and prep to turn into new AMI
#

# Update and install new packages
yum update -y
#yum install -y package1 package2
# If you are updating kernel you'll need to reboot after the update and do the following:
#package-cleanup --oldkernels --count=1
yum clean all

# Empty log files
for f in `find /var/log/ -type f`; do >$f; done

# Remove instance-specific stuff
sed -i '/^HOSTNAME/d' /etc/sysconfig/network
rm -rf /var/lib/cloud/instance /var/lib/cloud/instances/* /var/lib/cloud/data/*
rm -f /root/.ssh/authorized_keys /etc/sudoers.d/*cloud-init*
rm -f /home/cloud-user/.ssh/*
rm -f /etc/ssh/*key*

# Fill the remaining disk with zeros for maximum image compression
dd if=/dev/zero of=/zerofill bs=1M
rm -f /zerofill

shutdown -h now
