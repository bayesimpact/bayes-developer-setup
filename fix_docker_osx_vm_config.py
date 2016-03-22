#!/usr/bin/python
'''Ensures that docker-machine creates VMs with good DNS settings.

This has so far only been an issue for using our private Docker registries,
where the Docker daemon strangely uses a local DNS IP (192.168.2.1) and fails
to find our docker registry when looked up (e.g. at docker.bayesimpact.org).
This script sets the VM to use Google's DNS servers, alleviating the issue.
'''

import sys

path = sys.argv[1]
settings = '["8.8.8.8", "8.8.4.4"]'

contents = None
with open(path) as f:
    contents = f.read().splitlines()

fixed = False
for i, line in enumerate(contents):
    if line.strip().startswith('"Dns"') and "null" in line:
        contents[i] = line.replace("null", settings)
        print "Changing default docker-machine DNS settings to:"
        print contents[i]
        fixed = True

if not fixed:
    print "Nothing to fix."

with open(path, 'w') as f:
    for line in contents:
        print >>f, line
