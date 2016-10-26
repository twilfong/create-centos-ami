create-centos-ami
=================

Python script and example files for creating a new CentOS 6 or 7 AMI from a kickstart file.

Example use:

```
mirror_url=http://mirror.san.fastserv.com/pub/linux/centos/7/os/x86_64/
ks_url=https://raw.githubusercontent.com/twilfong/create-centos-ami/master/centos7-ami.ks
./create-centos-ami.py -r us-west-2 -t m4.large -m $mirror_url -u $ks_url
```
