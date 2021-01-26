'''
automatic performance evaluation for uniio

@author: fred
'''

import sys, os
sys.path.append('%s/../cctf' % (os.path.dirname(os.path.realpath(__file__))))


from cctf import gettarget
t = gettarget("192.168.100.169", "root", "password")
t = gettarget("192.168.100.169", "root", "password")
t = gettarget("192.168.100.169", "root", "password")
t = gettarget("192.168.100.169", "root", "password")
t = gettarget("192.168.100.155", "root", "password")
t = gettarget("192.168.100.156", "root", "password")

# # nodes: (IP, username, password)
client_node_def = (
    ("192.168.100.169", "root", "password"),
    ("192.168.100.155", "root", "password"),
    ("192.168.100.156", "root", "password"),
)
federation_node_def = (
    ("192.168.100.106", "root", "password"),
    ("192.168.103.248", "root", "password"),
    ("192.168.101.169", "root", "password"),
)
build_node_def = (
    ("192.168.100.120", "root", "password"),
)

client_targets = []
for n in client_node_def:
    print("n[0]=%s" %n[0])
    print("n[1]=%s" %n[1])
    print("n[2]=%s" %n[2])
    t = gettarget("192.168.100.169", "root", "password")
    t = gettarget("192.168.100.155", "root", "password")
    t = gettarget("192.168.100.156", "root", "password")
    t = gettarget(n[0], username=n[1], password=n[2], svc="ssh", timeout=60)
    client_targets.append(t)
    t.exe("echo I'm %s." % (t))

# federation_targets = []
# for n in federation_node_def:
#     t = gettarget(n[0], username=n[1], password=n[2], svc="ssh", timeout=60)
#     federation_targets.append(t)
#     t.exe("echo I'm %s." % (t))

# build_servers = []
# for n in build_node_def:
#     t = gettarget(n[0], username=n[1], password=n[2], svc="ssh", timeout=60)
#     build_servers.append(t)
#     t.exe("echo I'm %s." % (t))
