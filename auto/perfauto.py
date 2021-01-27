'''
automatic performance evaluation for uniio

@author: fred
'''
import sys, os
sys.path.append('%s/../cctf' % (os.path.dirname(os.path.realpath(__file__))))

from cctf import gettarget, common

# nodes: (IP, username, password)
client_node_def = (
    ("192.168.100.169", "root", "password"),
    ("192.168.100.155", "root", "password"),
    ("192.168.100.156", "root", "password"),
)

federation_node_def = (
    ("192.168.100.206", "root", "password"),
    ("192.168.103.248", "root", "password"),
    ("192.168.101.169", "root", "password"),
)
build_node_def = (
    ("192.168.100.120", "root", ".id_rsa"),
)

client_targets = []
for n in client_node_def:
    t = gettarget(n[0], username=n[1], password=n[2], svc="ssh", timeout=60)
    client_targets.append(t)

federation_targets = []
for n in federation_node_def:
    t = gettarget(n[0], username=n[1], password=n[2], svc="ssh", timeout=60)
    federation_targets.append(t)

build_servers = []
for n in build_node_def:
    t = gettarget(n[0], username=n[1], password=n[2], svc="ssh", timeout=10)
    build_servers.append(t)

runtime_dir = '/tmp'
cos = []
for t in client_targets + federation_targets + build_servers:
    cmd = "cd /tmp && { [[ -e uio_scripts ]] && (cd uio_scripts && ALL_PROXY=socks5://192.168.100.120:8899 git pull --recurse-submodules;) || ALL_PROXY=socks5://192.168.100.120:8899 git clone --recurse-submodules https://github.com/fred-chen/uio_scripts.git; }"
    cos.append(t.exe(cmd, wait=False))

for co in cos:
    if (not co.succ()):
        common.log("failed command: %s" % (co.cmdline))
