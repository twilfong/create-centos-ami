#!/usr/bin/python
"""CentOS AMI from-kickstart creator

Creates a CentOS AMI by bootstrapping the install from an amazon linux AMI.
The userdata script for the launched bootstrap AMI will download the installer
images from the given CentOS mirror URL, and configure grub to run a kickstart
install after reboot, using the given kickstart URL.

The kickstart config should specify the 'poweroff' option, and do any needed
cleanup in the '%post' section to make the image suitable for an AMI.

Once the install is done and the instance has shutdown, the console or EC2 API
can be used to create an image from the instance. This has only been tested
with CentOS kickstarts using an amazon linux HVM-EBS AMI for bootstrap.

Requires boto. Credentials can be set with environment variables or any other
boto method, including keyrings defined in ~/.boto.
"""

__copyright__ = "Copyright 2014 Tim Wilfong"
__license__ = "http://www.apache.org/licenses/LICENSE-2.0"

import sys, time
from argparse import ArgumentParser
from boto.ec2 import blockdevicemapping, connect_to_region, networkinterface
from boto import vpc

BOOTSTRAP_SCRIPT = '''
mkdir -p /boot/
curl $vmlinuz_url > /boot/kickstart-vmlinuz
curl $initrd_url > /boot/kickstart-initrd.img

# Setup boot
cat << EOF > /boot/grub/menu.lst
default 0
timeout 0
title Kernel
    root (hd0,0)
    kernel /boot/kickstart-vmlinuz ks=$ks_url console=ttyS0 xen_pv_hvm=enable
    initrd /boot/kickstart-initrd.img
EOF

# Restart
reboot
'''

# Parse command line arguments
parser = ArgumentParser(description='CentOS AMI from-kickstart creator')
parser.add_argument('-r', '--region', type=str, default='us-west-2',
                    help='AWS region')
parser.add_argument('-b', '--bootami', type=str,
                    default='amzn-ami-minimal-hvm-20*x86_64-ebs',
                    help='Name of bootstrap AMI')
parser.add_argument('-k', '--key', type=str, default=None,
                    help='Name of keypair to use')
parser.add_argument('-s', '--subnetid', type=str, default=None,
                    help='SubnetID in VPC. Default is to pick first one.')
parser.add_argument('-t', '--type', type=str, default='t2.medium',
                    help='Instance type')
parser.add_argument('-d', '--disksize', type=int, default=None,
                    help='Disk size in GB')
parser.add_argument('-g', '--secgroup', type=str, default='default',
                    help='Name of security group')
parser.add_argument('-m', '--mirrorurl', type=str,
                    default='http://mirror.san.fastserv.com/pub/linux/centos/6/os/x86_64/',
                    help='URL for centOS mirror. Must contain images/ directory')
parser.add_argument('-u', '--ksurl', type=str,
                    default='https://raw.githubusercontent.com/twilfong/create-centos-ami/master/centos6-cloud.ks',
                    help='URL for kickstart config')
parser.add_argument('--novpc', action='store_true',
                    default=False, help='Do not use VPC even if available.')
parser.add_argument('--timeout', type=int, default=10,
                    help='Maximum number of minutes to wait for shutdown.')
args = parser.parse_args()

userdata = ('#!/bin/sh\n' +
            '# Image and Kickstart URLs\n' +
            'vmlinuz_url=' + args.mirrorurl + 'images/pxeboot/vmlinuz\n' +
            'initrd_url=' + args.mirrorurl + 'images/pxeboot/initrd.img\n' +
            'ks_url=' + args.ksurl + '\n' +
            BOOTSTRAP_SCRIPT)

# Connect to EC2 endpoint for region
conn = connect_to_region(args.region)

# Choose first AMI ID that matches the given bootami name pattern
try: id = conn.get_all_images(filters={'name': args.bootami})[0].id
except IndexError: sys.exit('ERROR: No matching AMIs found!')

# Connect to the given SubnetID or get a list of subnets in this region
if args.novpc:
    subnets = None
else:
    subnets = vpc.connect_to_region(args.region).get_all_subnets(args.subnetid)

# Use a VPC if we can, unless told not to. Use first subnet in list.
if subnets:
    grpfilt = {'group-name': args.secgroup, 'vpc_id': subnets[0].vpc_id}
    subnetid = subnets[0].id
    # Find the security group id from the name
    group = conn.get_all_security_groups(filters=grpfilt)[0].id
    # associate the instance with a VPC and give it a puclic IP address
    interface = networkinterface.NetworkInterfaceSpecification(
            subnet_id=subnetid, groups=[group],
            associate_public_ip_address=True)
    interfaces = networkinterface.NetworkInterfaceCollection(interface)
    groups = None
else:
    interfaces = None
    groups = [args.secgroup]

# Set disk mapping if needed
if args.disksize:
    dev_xvda = blockdevicemapping.BlockDeviceType(delete_on_termination=True)
    dev_xvda.size = args.disksize
    device_map = blockdevicemapping.BlockDeviceMapping()
    device_map['/dev/xvda'] = dev_xvda
else:
    device_map = None

# launch instance
res = conn.run_instances(id, key_name=args.key, instance_type=args.type,
        network_interfaces=interfaces, user_data=userdata,
        security_groups=groups, block_device_map=device_map)

instance = res.instances[0]
print "Launching instance %s" % instance.id

# Poll and print instance state until stopped or timeout is reached
state = None
sys.stdout.write("Instance state:")
for i in range(args.timeout * 10):
    pstate = state
    state = conn.get_only_instances(instance.id)[0].state
    if pstate != state: sys.stdout.write('\n    %s ' % state)
    sys.stdout.flush()
    if state == 'stopped':
        # Eventualy create the image from the stopped instance here?
        print
        break
    else:
        time.sleep(6)
        sys.stdout.write('.')

