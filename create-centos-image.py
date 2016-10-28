#!/usr/bin/python
"""CentOS image from-kickstart creator

Creates a CentOS Openstack image by bootstrapping from another image. The
userdata script for the launched bootstrap image will download the installer
images from the given CentOS mirror URL, and configure grub to run a kickstart
install after reboot, using the given kickstart URL.

The kickstart config should specify the 'poweroff' option, and do any needed
cleanup in the '%post' section to make the instance suitable for a cloud image.

Once the install is done and the instance has shutdown, the console or API
can be used to create an image from the instance. This has only been tested
with CentOS kickstarts using a CentOS image for bootstrap.

Requires shade. Credentials can be set with environment variables or any other
method described at http://docs.openstack.org/developer/os-client-config/.
"""

__copyright__ = "Copyright 2014 Tim Wilfong"
__license__ = "http://www.apache.org/licenses/LICENSE-2.0"

import shade
from argparse import ArgumentParser
from getpass import getpass
from os_client_config import OpenStackConfig

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
parser = ArgumentParser(description='CentOS image from-kickstart creator')
parser.add_argument('-c', '--cloud', type=str, default=None,
                    help='Name of cloud to connect to')
parser.add_argument('-n', '--name', type=str, default='CentosImage',
                    help='Name of new image')
parser.add_argument('-b', '--bootimage', type=str, default='centos6',
                    help='Name or ID of bootstrap image')
parser.add_argument('-k', '--key', type=str, default=None,
                    help='Name of keypair to use')
parser.add_argument('-s', '--subnetid', type=str, default=None,
                    help='SubnetID in VPC. Default is to pick first one.')
parser.add_argument('-f', '--flavor', type=str, default='m1.small',
                    help='Instance flavor')
parser.add_argument('-d', '--disksize', type=int, default=None,
                    help='Disk size in GB')
parser.add_argument('-g', '--secgroup', type=str, default='default',
                    help='Name of security group')
parser.add_argument('-m', '--mirrorurl', type=str,
                    default='http://mirror.san.fastserv.com/pub/linux/centos/7/os/x86_64/',
                    help='URL for centOS mirror. Must contain images/ directory')
parser.add_argument('-u', '--ksurl', type=str,
                    default='https://raw.githubusercontent.com/twilfong/create-centos-ami/master/centos7-cloud.ks',
                    help='URL for kickstart config')
parser.add_argument('-z', '--zone', type=str, default=None,
                    help='Availability zone for instance and storage')
parser.add_argument('-N', '--network', type=str, default=None,
                    help='Name or ID of network to attach')
parser.add_argument('-T', '--timeout', type=int, default=10,
                    help='Maximum number of minutes to wait for shutdown.')
args = parser.parse_args()

userdata = ('#!/bin/sh\n' +
            '# Image and Kickstart URLs\n' +
            'vmlinuz_url=' + args.mirrorurl + 'images/pxeboot/vmlinuz\n' +
            'initrd_url=' + args.mirrorurl + 'images/pxeboot/initrd.img\n' +
            'ks_url=' + args.ksurl + '\n' +
            BOOTSTRAP_SCRIPT)

# Connect to Openstack API using config from environment or files
cfg = OpenStackConfig(pw_func=getpass)
if args.cloud:
    envauth = shade.openstack_cloud().auth
    cloud = shade.openstack_cloud(config=cfg, cloud=args.cloud, **envauth)
else:
    cloud = shade.openstack_clouds(config=cfg)[0]

# Set up argument list for create_server call
kwargs = {'security_groups': [args.secgroup], 'userdata': userdata}
if args.key: kwargs['key_name'] = args.key

# Pick a network
if args.network: kwargs['network'] = args.network
else: kwargs['network'] = cloud.list_networks()[0]['id']

# Set disk mapping if needed
if args.disksize:
    print "Creating volume for instance..."
    result = cloud.create_volume(args.disksize, timeout=60,
            image=args.bootimage, availability_zone=args.zone)
    kwargs['boot_volume'] = result.id
    kwargs['terminate_volume'] = True
    kwargs['availability_zone'] = args.zone

# launch instance
result = cloud.create_server(args.name, args.bootimage, args.flavor, **kwargs)
print "Launching instance %s" % result.id
