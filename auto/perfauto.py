#!/usr/bin/env python

'''
automatic performance evaluation for uniio

@author: fred
'''
import sys, os, json, getopt, subprocess
sys.path.append('%s/../cctf' % (os.path.dirname(os.path.realpath(__file__))))
from cctf import gettarget, common, me

g_curdir = os.path.abspath(os.getcwd())
g_conf = {}
g_rootdir = os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), os.pardir))
g_runtime_dir = '/tmp'
g_script_dir = g_runtime_dir + "/uio_scripts"

def usage(errmsg=""):
    if(errmsg != ""):
        sys.stderr.write("\nERROR: %s\n" % errmsg)
    print("usage: %s [ -c|--config configfile.json ]" % (os.path.basename(sys.argv[0])))
    exit(1)

def handleopts():
    global g_conf
    conf_file = "%s/auto.json" % (os.path.dirname(os.path.realpath(__file__)))
    try:
        options, args = getopt.gnu_getopt(sys.argv[1:], "hc:", ["help", "configfile="])
    except getopt.GetoptError as err:
        usage(err)
    for o, a in options:
        if(o in ('-h', '--help')): 
            usage()
        if(o in ('-c', '--config')):
            conf_file = a
    
    # load configuration file
    f = open(conf_file)
    if not f:
        common.log("can not open configuration file '%s'." % conf_file, 1)
        return None
    jstr = f.read()
    if not jstr: 
        common.log("can not read configuration file '%s'." % conf_file, 1)
        return None
    conf = json.loads(jstr)
    if not conf:
        common.log("can not parse configuration file '%s'." % conf_file, 1)
        return None
    g_conf = conf
    return conf

def prep_targets():
    '''
        * build 3 target lists: client_targets, federation_targets, build_server
        * upload uio_scripts to all targets
        * return 3 target lists as a tuple: (client_targets, federation_targets, build_server)
    '''
    global g_runtime_dir
    # node defs: [ (IP, username, password), ... ]
    client_node_def = g_conf["client_nodes"]
    federation_node_def = g_conf["federation_nodes"]
    build_node_def = g_conf["build_server"]  # [IP, username, password, git_ssh_identifyfile]

    client_targets = []
    for n in client_node_def:
        t = gettarget(n[0], username=n[1], password=n[2], svc="ssh", timeout=60)
        if t:
            client_targets.append(t)
        else:
            return None

    federation_targets = []
    for n in federation_node_def:
        t = gettarget(n[0], username=n[1], password=n[2], svc="ssh", timeout=60)
        if t:
            federation_targets.append(t)
        else:
            return None

    build_server = None
    build_server = gettarget(build_node_def[0], username=build_node_def[1], password=build_node_def[2], svc="ssh", timeout=60)
    if not build_server:
        return None

    # upload uio_scripts to targets
    for t in client_targets + federation_targets:
        if not t.upload("%s" % (g_rootdir), g_runtime_dir):
            return None

    return (client_targets, federation_targets, build_server)

def get_gitcmd():
    git_proxy = "ALL_PROXY="+g_conf["git_proxy"] if g_conf.has_key("git_proxy") else ""
    return "%s git" % (git_proxy) if git_proxy else "git"

def build(build_server):
    '''
        build uniio rpms
    '''
    global g_runtime_dir
    gitcmd = get_gitcmd()
    a,b,c,git_ssh_identityfile = g_conf["build_server"]  # [IP, username, password, git_ssh_identityfile]
    print (git_ssh_identityfile)
    cos = []
    shs = []
    for i in range(4):  # use 4 shells for parallel compilation
        sh = build_server.newshell()
        if not sh: 
            return False
        shs.append(sh)
    for sh in shs:
        sh.exe("cd /tmp")
        sh.exe("export GIT_SSH_COMMAND=\"ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o IdentityFile=%s -o ProxyCommand='ssh -q -W %%h:%%p evidence.orcadt.com'\"" % (git_ssh_identityfile))
    # git clone all repos in parallel
    # repos = ('uniio', 'uniio-ui', 'sysmgmt', 'nasmgmt')
    repos = ('uniio', 'uniio-ui', 'nasmgmt')
    i = 0
    for repo in repos:
        cmd = "[[ -e '%s/%s' ]] && { cd %s/%s && %s pull --recurse-submodules; } || { %s clone --recurse-submodules git@github.com:uniio/%s.git %s/%s; }" \
                % (g_runtime_dir, repo, g_runtime_dir, repo, gitcmd, gitcmd, repo, g_runtime_dir, repo)
        cos.append( shs[i%4].exe(cmd, wait=False) )
        i += 1
    for co in cos:
        if not co.succ():
            common.log("failed git command: '%s'" % (co.cmdline), 1)
            return False

    sh0 = shs[0]
    sh1 = shs[1]
    sh2 = shs[2]
    sh3 = shs[3]
    # cmake repos
    cos = []
    co = sh0.exe("cd %s/%s && rm -rf build && mkdir build && cd build && cmake3 -DCMAKE_BUILD_TYPE=Release .." % (g_runtime_dir, "uniio"), wait=False)
    cos.append(co)
    co = sh1.exe("cd %s/%s && rm -rf build && mkdir build && cd build && cmake3 -DCMAKE_BUILD_TYPE=Release .." % (g_runtime_dir, "sysmgmt"), wait=False)
    cos.append(co)
    co = sh2.exe("cd %s/%s && rm -rf build && mkdir build && cd build && cmake3 -DCMAKE_BUILD_TYPE=Release .." % (g_runtime_dir, "nasmgmt"), wait=False)
    cos.append(co)
    co = sh3.exe("cd %s/%s && rm -rf build_debug && mkdir build_debug && cd build_debug && cmake3 .." % (g_runtime_dir, "uniio-ui"), wait=False)
    cos.append(co)
    for co in cos:
        if not co.succ():
            common.log("failed cmake command: '%s'" % (co.cmdline), 1)
            return False

    # make repos
    cos = []
    co = sh0.exe("cd %s/%s/build && make -j20 package" % (g_runtime_dir, "uniio"), wait=False)
    cos.append(co)
    co = sh1.exe("cd %s/%s/build && make -j20 package" % (g_runtime_dir, "sysmgmt"), wait=False)
    cos.append(co)
    co = sh2.exe("cd %s/%s/build && make -j20 package" % (g_runtime_dir, "nasmgmt"), wait=False)
    cos.append(co)
    co = sh3.exe("cd %s/%s/build_debug && make -j20 package" % (g_runtime_dir, "uniio-ui"), wait=False)
    cos.append(co)
    for co in cos:
        if not co.succ():
            common.log("failed make command: '%s'" % (co.cmdline), 1)
            return False
    return True

def init_cluster(client_targets, federation_targets, build_server):
    # download from build server and upload rpm packages to federation nodes:
    me.call("rm -rf /tmp/rpms && mkdir /tmp/rpms", shell=True)
    if not build_server.download("/tmp/rpms/", "%s/uniio/build/object-array-*.rpm" % (g_runtime_dir)):                    # download uniio rpms
        return False
    if not build_server.download("/tmp/rpms/", "%s/nasmgmt/build/object-array-nasmgmt-*.rpm" % (g_runtime_dir)):          # download nasmgmt rpms
        return False
    if not build_server.download("/tmp/rpms/", "%s/sysmgmt/build/object-array-sysmgmt-*.rpm" % (g_runtime_dir)):          # download sysmgmt rpms
        return False
    if not build_server.download("/tmp/rpms/", "%s/uniio-ui/build_debug/object-array-uniio-ui-*.rpm" % (g_runtime_dir)):  # download uniio-ui rpms
        return False

    for t in federation_targets:
        t.exe("mkdir -p /tmp/rpms")
        if not t.upload("/tmp/rpms/*.rpm", "/tmp/rpms/"):
            return False
    
    # shutdown cluster and replace rpms
    cos = []
    for t in federation_targets:
        cmd  = "%s/uio_scripts/server/init_cluster.sh -f --replace=/tmp/rpms" % (g_runtime_dir)
        cos.append(t.exe(cmd, wait=False))
    for co in cos:
        if not co.succ():
            common.log("failed when shutting down uniio.")
            return False

    # init backend and restart uniio
    cos = []
    for t in federation_targets:
        cmd  = "%s/uio_scripts/server/init_cluster.sh -i" % (g_runtime_dir)
        cos.append(t.exe(cmd, wait=False))
    for co in cos:
        if not co.succ():
            common.log("failed when initializing uniio.")
            return False

    if not push_topology(federation_targets):
        return False
    
    return True

def push_topology(federation_targets):
    # pushing topology
    t = federation_targets[0]
    if not t.exe("cioctl topology %s" % (g_conf["topology"])).succ():
        return False
    if not t.exe("cioctl portal --management_ip %s --iscsi_ip %s" % (g_conf["management_ip"], g_conf["iscsi_ip"])).succ():
        return False
    return True

def create_luns(client_targets, federation_targets):
    # get client iscsi initiator iqns for mapping
    iqns = {}  # { address : iqn }
    for t in client_targets:
        iqns[t.address] = t.exe("awk -F'=' '{print \$2}' /etc/iscsi/initiatorname.iscsi").stdout.strip()
    
    t = federation_targets[0]
    # create luns
    for i in range(g_conf["num_luns"]):
        if not t.exe("cioctl create lun%d %dG" % (i, g_conf["lunsize_G"])).succ():
            return False
        if not t.exe("cioctl iscsi target create --name tgt-%d" % (i)).succ():
            return False
    
    # create initiator groups
    for address in iqns.keys():
        iqn = iqns[address]
        addr = address.replace(".", "-")
        if not t.exe("cioctl iscsi initiator create --name i%s --iqn %s" % (addr, iqn)).succ():
            return False
        if not t.exe("cioctl iscsi initiatorgroup create --name ig%s --initiators i%s" % (addr, addr)).succ():
            return False

    # create mappings: luns are evenly mapped to clients
    num_igs = len(iqns); luns_per_client = g_conf["num_luns"] / len(iqns)
    for i in range(g_conf["num_luns"]):
        address = iqns.keys()[(i/luns_per_client)%num_igs]
        addr = address.replace(".", "-"); igroup = "ig%s" % (addr)
        if not t.exe("cioctl iscsi mapping create --blockdevice lun%d --target tgt-%d --initiatorgroup %s" % (i, i, igroup)).succ():
            return False
    return True

def clear_luns(federation_targets):
    cos = []
    t = federation_targets[0]
    mappings = t.exe("cioctl iscsi mapping list | grep iqn | awk '{print \$2}'").getlist()
    for mapping in mappings:
        if not t.exe("cioctl iscsi mapping delete --ignore_session_check --blockdevice %s --yes-i-really-really-mean-it" % (mapping)).succ():
            return False
    targets = t.exe("cioctl iscsi target list | grep iqn | awk '{print \$2}'").getlist()
    for tgt in targets:
        if not t.exe(" cioctl iscsi target delete --name %s --yes-i-really-really-mean-it" % (tgt)).succ():
            return False
    snapshots = t.exe("cioctl snapshot list | grep GiB | awk '{print \$2}'").getlist()
    for snap in snapshots:
        if not t.exe("cioctl detach %s" % (snap)).succ():
            return False
    luns = t.exe("cioctl list | grep GB | awk '{print \$2}' | grep -v '^-'").getlist()
    for lun in luns:
        if not t.exe("cioctl delete %s" % (lun)).succ():
            return False
    igs = t.exe("cioctl iscsi initiatorgroup list | grep -E '.+-[0-9]+-' | awk '{print \$2}'").getlist()
    for ig in igs:
        if not t.exe("cioctl iscsi initiatorgroup delete --name %s --yes-i-really-really-mean-it" % (ig)).succ():
            return False
    initiators = t.exe("cioctl iscsi initiator list | grep -E '.+-[0-9]+-' | awk '{print \$2}'").getlist()
    for it in initiators:
        if not t.exe("cioctl iscsi initiator delete --name %s --yes-i-really-really-mean-it" % (it)).succ():
            return False
    return True


def iscsi_out(client_targets):
    cos = []
    iscsi_ip = g_conf["iscsi_ip"]
    
    # logout all iscsi session and delete discovery db
    for t in client_targets:
        cos.append(t.exe("iscsiadm -m node --logout", wait=False))
        cos.append(t.exe("iscsiadm -m session -u", wait=False))
        cos.append(t.exe("iscsiadm -m discoverydb -t sendtargets -p %s:3260 -o delete" % (iscsi_ip), wait=False))
    for co in cos:
        co.wait()
    return True

def iscsi_in(client_targets):
    cos = []
    iscsi_ip = g_conf["iscsi_ip"]

    # login iscsi session
    for t in client_targets:
        cos.append(t.exe("iscsiadm -m discovery -t st -p %s" % (iscsi_ip), wait=False))
        cos.append(t.exe("iscsiadm -m node --login -p %s" % (iscsi_ip), wait=False))
    for co in cos:
        co.wait()
    return True

def fio_server(client_targets):
    cos = []

    # login iscsi session
    for t in client_targets:
        cos.append(t.exe("killall -9 fio || true", wait=False))
        cos.append(t.exe("fio --server --daemonize=/tmp/fio.pid", wait=False))
    for co in cos:
        if not co.succ():
            common.log("failed restarting fio server.")
            return False    
    return True

if __name__ == "__main__":
    conf = handleopts()
    if not conf: exit(1)

    targets = prep_targets()
    if not targets: exit(1)

    client_targets, federation_targets, build_server = targets
    # if not build(build_server): exit(1)

    # if not init_cluster(*targets): exit(1)

    # push_topology(federation_targets)
    # create_luns(client_targets, federation_targets)
    # iscsi_out(client_targets)
    # iscsi_in(client_targets)
    # clear_luns(federation_targets)
    fio_server(client_targets)
