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

MIRROR_URL = 'http://mirror.san.fastserv.com/pub/linux/centos/6/os/x86_64/'
KICKSTART_URL = ('https://raw.githubusercontent.com/twilfong'
                 '/create-centos-ami/master/centos6-cloud.ks')


class Error(Exception):
    """Exceptions that should just print a message and exit"""
    pass


def create_parser(args=None):
    """Return ArgumentParser for list of args or command line (if none.)"""
    parser = ArgumentParser(description='CentOS AMI from-kickstart creator')
    parser.add_argument('-r', '--region', type=str, default='us-west-2',
                        help='AWS region')
    parser.add_argument('-b', '--bootami', type=str,
                        default='amzn-ami-minimal-hvm-20*x86_64-ebs',
                        help='Name or pattern of bootstrap AMI')
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
    parser.add_argument('-n', '--name', type=str, default=None,
                        help='Name for the created AMI')
    parser.add_argument('-m', '--mirrorurl', type=str, default=MIRROR_URL,
                        help='CentOS mirror URL containing images/ dir')
    parser.add_argument('-u', '--ksurl', type=str, default=KICKSTART_URL,
                        help='URL for kickstart config')
    parser.add_argument('--novpc', action='store_true', default=False,
                        help='Do not use VPC even if available.')
    parser.add_argument('--timeout', type=int, default=10,
                        help='Maximum number of minutes to wait for shutdown.')
    return parser.parse_args()


def create_userdata(mirrorurl, ksurl, bootstrap=BOOTSTRAP_SCRIPT):
    """Create userdata from mirror and kickstart urls and bootstrap script."""
    header = ['#!/bin/sh',
              '# Image and Kickstart URLs',
              'vmlinuz_url=' + mirrorurl + 'images/pxeboot/vmlinuz',
              'initrd_url=' + mirrorurl + 'images/pxeboot/initrd.img',
              'ks_url=' + ksurl]
    return '\n'.join(header) + bootstrap


def launch_instance(args):
    """Connect to AWS and launch instance using args from create_parser"""

    # Connect to EC2 endpoint for region
    conn = connect_to_region(args.region)

    # Choose first image ID that matches the given AMI name pattern
    try: id = conn.get_all_images(filters={'name': args.bootami})[0].id
    except IndexError: raise Error('ERROR: No matching AMIs found!')

    # Connect to the given SubnetID or get a list of subnets in this region
    if args.novpc:
        subnets = None
    else:
        c = vpc.connect_to_region(args.region)
        subnets = c.get_all_subnets(args.subnetid)

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
    return res.instances[0]


def wait_for_shutdown(instance, timeout, output=sys.stdout):
    """Print instance state until it is stopped. Raise Error on timeout."""
    state = None
    output.write("Instance state:")
    end = time.time() + 60 * timeout
    while time.time() < end:
        pstate = state
        state = instance.update()
        if pstate != state: output.write('\n    %s ' % state)
        output.flush()
        if state == 'stopped':
            output.write('\n')
            return
        else:
            time.sleep(5)
            output.write('.')
    output.write('\n')
    raise Error('Instance has not shutdown after %s minutes.' % timeout)


if __name__ == "__main__":
    args = create_parser()
    userdata = create_userdata(args.mirrorurl, args.ksurl)

    try:
        instance = launch_instance(args)
        print "Launching instance %s" % instance.id
    except Error, e:
        sys.exit(e)

    try:
        wait_for_shutdown(instance, args.timeout)
    except Error, e:
        if raw_input('%s Terminate it? (y/N) ' % e).lower() in ['y', 'yes']:
            print "Terminating instance %s." % instance.id
            instance.terminate()
        sys.exit('Exiting')

    # Instance is stopped. Create AMI.
    # Default name is the base filename from the kickstart URL
    name = args.name or args.ksurl.split('/')[-1].split('.')[0]
    id = instance.create_image(name)
    print "Creating AMI %s with name %s from instance %s" % (name,
                                                             id, instance.id)

    # Need to terminate instance once AMI is created
    # Should go through another polling loop. But for now, wait then kill.
    time.sleep(50)
    print "Terminating instance %s." % instance.id
    instance.terminate()
