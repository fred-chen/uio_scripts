#!/usr/bin/env python

'''
automatic performance evaluation for uniio

@author: fred
'''
import sys, os, json, getopt, random, re, time
sys.path.append('%s/../cctf' % (os.path.dirname(os.path.realpath(__file__))))
from cctf import gettarget, common, me

g_curdir = os.path.abspath(os.getcwd())
g_conf = None
g_rootdir = os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), os.pardir))
g_runtime_dir = '/tmp'
g_force = False
g_shutdown_only = False
g_boot_only = False
g_update = False
g_binonly = None
g_init = False
g_perftest = False
g_fullmap = False
g_cpudata = False
g_fill = 0
g_createluns = 0
g_delluns_only = False

def usage(errmsg=""):
    if(errmsg != ""):
        sys.stderr.write("\nERROR: %s\n" % errmsg)
    just = len("usage: %s" % (os.path.basename(sys.argv[0])))
    print("usage: %s [ -c|--config configfile.json ]" % (os.path.basename(sys.argv[0])))
    print("%s [ -f|--force ] [ -s|--shutdown ]" % (' '.rjust(just)))
    print("%s [ -b|--boot ]" % (' '.rjust(just)))
    print("%s [ -u|--update ] [ --binonly (binpath|conf|tag|branch|commit) ]" % (' '.rjust(just)))
    print("%s [ -i|--init ]" % (' '.rjust(just)))
    print("%s [ -p|--perftest ] [ --cpudata ] [ --fill sec ]" % (' '.rjust(just)))
    print("%s [ --createluns num ] [ --fullmap ] [ --deleteluns ]" % (' '.rjust(just)))
    print(
        "\n" "Coordinate UniIO nodes, build server and fio clients for performance test." "\n" 
        "\n" 
        "options:" "\n"
        "  -c, --config:      config file path (.json)" "\n"
        "  -f, --force:       force stop uniio node (kill cio_array)" "\n"
        "  -s, --shutdown:    gracefully stop uniio nodes" "\n"
        "  -b, --boot:        start uniio nodes" "\n"
        "  -u, --update:      update uniio build" "\n"
        "      --binonly:     use along with '-u', only update cio_array binary." "\n"
        "  -i, --init:        reinit uniio federation" "\n"
        "  -p, --perftest:    run perftest" "\n"
        "      --cpudata:     use along with '-p', collect cpu data as svg files while performance test is running" "\n"
        "      --fill:        use along with '-p', fill the luns with pure write workload for a given time in seconds" "\n"
        "  --createluns:      create a given number of luns" "\n"
        "     --fullmap:      use along with '--createluns', all clients see all luns ( clients see different luns if not specified )" "\n"
        "  --deleteluns:      delete all existing luns" "\n"
        )
    exit(1)

def handleopts():
    global g_conf, g_runtime_dir, g_force, g_shutdown_only, g_boot_only, g_update, g_init, g_perftest, g_binonly, g_fullmap, g_cpudata, g_fill, g_createluns, g_delluns_only
    conf_file = "%s/auto.json" % (os.path.dirname(os.path.realpath(__file__)))
    try:
        options, args = getopt.gnu_getopt(sys.argv[1:], "hc:fsbuipd", ["help", "configfile=","force","shutdown","boot","update","init","perftest", "binonly=", "fullmap", "cpudata", "fill=", "createluns=","deleteluns"])
    except getopt.GetoptError as err:
        usage(err)
    for o, a in options:
        if(o in ('-h', '--help')): 
            usage()
        if(o in ('-c', '--config')):
            conf_file = a
        if(o in ('-f', '--force')):
            g_force = True
        if(o in ('-s', '--shutdown')):
            g_shutdown_only = True
        if(o in ('-b', '--boot')):
            g_boot_only = True
        if(o in ('-u', '--update')):
            g_update = True
        if(o in ('', '--binonly')):
            g_binonly = a
        if(o in ('-i', '--init')):
            g_init = True
        if(o in ('-p', '--perftest')):
            g_perftest = True
        if(o in ('', '--fullmap')):
            g_fullmap = True
        if(o in ('', '--cpudata')):
            g_cpudata = True
        if(o in ('', '--fill')):
            g_fill = int(a)
        if(o in ('', '--createluns')):
            g_createluns = int(a)
        if(o in ('', '--deleteluns')):
            g_delluns_only = True
     
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
    g_runtime_dir = conf["runtime_dir"]
    if g_binonly and (g_binonly != 'conf'):
        conf["uniio_checkout"] = g_binonly   # a git commit to checkout
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
            client_targets = []

    federation_targets = []
    for n in federation_node_def:
        t = gettarget(n[0], username=n[1], password=n[2], svc="ssh", timeout=60)
        if t:
            federation_targets.append(t)
        else:
            federation_targets = []

    build_server = None
    build_server = gettarget(build_node_def[0], username=build_node_def[1], password=build_node_def[2], svc="ssh", timeout=60)
    if not build_server:
        build_server = None

    # upload uio_scripts to targets
    for t in client_targets + federation_targets:
        if not t.exe("mkdir -p %s" % (g_runtime_dir)):
            return None
        if not t.upload("%s" % (g_rootdir), g_runtime_dir):
            return None

    return (client_targets, federation_targets, build_server)

def get_gitcmd():
    git_proxy = "ALL_PROXY="+g_conf["build_server_git_proxy"] if g_conf.has_key("build_server_git_proxy") else ""
    return "%s git" % (git_proxy) if git_proxy else "git"

def build(build_server):
    '''
        pull the latest uniio repos (uniio, sysmgmt, nasmgmt, uniio-ui) from github on build server
        build on server
    '''

    global g_runtime_dir
    gitcmd = get_gitcmd()
    a,b,c,git_ssh_identityfile = g_conf["build_server"]  # [IP, username, password, git_ssh_identityfile]
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
    repos = ('uniio', 'uniio-ui', 'sysmgmt', 'nasmgmt')
    i = 0
    for repo in repos:
        checkout = g_conf["%s_checkout"%(repo)] if g_conf.has_key("%s_checkout"%(repo)) else "default"
        cmd = "[[ -e '%s/%s' ]] && { cd %s/%s && git fetch; } || { %s clone --recurse-submodules git@github.com:uniio/%s.git %s/%s; }" \
                % (g_runtime_dir, repo, g_runtime_dir, repo, gitcmd, repo, g_runtime_dir, repo)
        cos.append( shs[i%4].exe(cmd, wait=False) )
        if checkout != "default": # checkout desired branch or tag or commit
            cmd = "cd %s/%s && %s checkout %s" % (g_runtime_dir, repo, gitcmd, checkout)
            cos.append( shs[i%4].exe(cmd, wait=False) )
        cmd = "cd %s/%s && %s pull --no-edit || true" % (g_runtime_dir, repo, gitcmd)
        cos.append( shs[i%4].exe(cmd, wait=False) )
        cmd = "cd %s/%s && %s log --pretty=format:'%%h|%%ci|%%an|%%s' | head -8 || true" % (g_runtime_dir, repo, gitcmd)
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
    co = sh0.exe("cd %s/%s && mkdir -p build && cd build && cmake3 -DCMAKE_BUILD_TYPE=Release .." % (g_runtime_dir, "uniio"), wait=False)
    cos.append(co)
    co = sh1.exe("cd %s/%s && mkdir -p build && cd build && cmake3 -DCMAKE_BUILD_TYPE=Release .." % (g_runtime_dir, "sysmgmt"), wait=False)
    cos.append(co)
    co = sh2.exe("cd %s/%s && mkdir -p build && cd build && cmake3 -DCMAKE_BUILD_TYPE=Release .." % (g_runtime_dir, "nasmgmt"), wait=False)
    cos.append(co)
    co = sh3.exe("cd %s/%s && mkdir -p build_debug && cd build_debug && cmake3 .." % (g_runtime_dir, "uniio-ui"), wait=False)
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

def build_bin(build_server):
    '''
        pull the latest uniio repo from github on build server
        build cio_array and cio_array.sym on server
    '''

    global g_runtime_dir
    gitcmd = get_gitcmd()
    a,b,c,git_ssh_identityfile = g_conf["build_server"]  # [IP, username, password, git_ssh_identityfile]
    sh = build_server.newshell()
    sh.exe("cd /tmp")
    sh.exe("export GIT_SSH_COMMAND=\"ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o IdentityFile=%s -o ProxyCommand='ssh -q -W %%h:%%p evidence.orcadt.com'\"" % (git_ssh_identityfile))
    
    # git clone uniio repo
    repo = "uniio"
    checkout = g_conf["%s_checkout"%(repo)] if g_conf.has_key("%s_checkout"%(repo)) else "default"
    cmd = "[[ -e '%s/%s' ]] && { cd %s/%s && git fetch; } || { %s clone --recurse-submodules git@github.com:uniio/%s.git %s/%s; }" \
            % (g_runtime_dir, repo, g_runtime_dir, repo, gitcmd, repo, g_runtime_dir, repo)
    if not sh.exe(cmd).succ(): return False

    if checkout != "default": # checkout desired branch or tag or commit
        cmd = "cd %s/%s && %s checkout %s" % (g_runtime_dir, repo, gitcmd, checkout)
        if not sh.exe(cmd).succ(): return False

    cmd = "cd %s/%s && %s pull --no-edit || true" % (g_runtime_dir, repo, gitcmd)
    if not sh.exe(cmd).succ(): return False
    cmd = "cd %s/%s && %s log --pretty=format:'%%h|%%ci|%%an|%%s' | head -8 || true" % (g_runtime_dir, repo, gitcmd)
    if not sh.exe(cmd).succ(): return False

    # cmake repos
    if not sh.exe("cd %s/%s && mkdir -p build && cd build && cmake3 -DCMAKE_BUILD_TYPE=Release .." % (g_runtime_dir, repo)).succ():
        return False

    # make repos
    if not sh.exe("cd %s/%s/build && make -j20 cio_array cio_array.sym" % (g_runtime_dir, repo)).succ():
        return False
    return True

def cio_running(federation_target):
    '''
        return positive number if cio_array and objmgr-fab are both running
        else 0
    '''
    return fab_running() and array_running()
    
def fab_running(federation_target):
    '''
        return positive number if fabric manager is running
        else 0
    '''
    return federation_target.exe("ps -ef|grep fabric-manager.jar|grep -v grep|wc -l").getint()

def array_running(federation_target):
    '''
        return positive number if cio_array is running
        else 0
    '''
    return federation_target.exe("pgrep -nx cio_array|wc -l").getint()

def detach_luns(federation_targets):
    t = None
    for n in federation_targets:
        if fab_running(n):
            t = n
            break
    if not t:
        common.log("fabric manager is not running on all federation nodes.", 1)
        return False
    luns = t.exe("cioctl list | grep GB | awk '{print \$2}' | grep -v '^-'").getlist()
    for lun in luns:
        if not t.exe("cioctl detach --ignore_session_check %s" % (lun)).succ():
            return False
    snaps = t.exe("cioctl snapshot list | grep GiB | awk '{print \$2}'").getlist()
    for snap in snaps:
        if not t.exe("cioctl detach --ignore_session_check %s" % (snap)).succ():
            return False
    return True

def attach_luns(federation_targets):
    t = None
    for n in federation_targets:
        if fab_running(n):
            t = n
            break
    if not t:
        common.log("fabric manager is not running on all federation nodes.", 1)
        return False
    luns = t.exe("cioctl list | grep GB | awk '{print \$2}' | grep -v '^-'").getlist()
    for lun in luns:
        if not t.exe("cioctl attach %s" % (lun)).succ():
            return False
    snaps = t.exe("cioctl snapshot list | grep GiB | awk '{print \$2}'").getlist()
    for snap in snaps:
        if not t.exe("cioctl attach %s" % (snap)).succ():
            return False
    return True

def shutdown_cluster(federation_targets, force=True):
    # shutdown cluster
    cos = []
    for t in federation_targets:
        if not (array_running(t) or fab_running(t)):
            continue
        cmd  = "%s/uio_scripts/server/init_cluster.sh %s -s" % (g_runtime_dir, "-f" if force else "")
        cos.append(t.exe(cmd, wait=False))
    for co in cos:
        if not co.succ():
            common.log("failed when shutting down uniio.")
            return False
    return True

def replace_rpm(federation_targets, build_server, force=True):
    '''
        build the latest uniio on build_server and replace rpms on federation nodes
    '''
    if not build_server:
        common.log("failed replace rpms. build server is None.", 1)
        return False
    if not federation_targets:
        common.log("failed replace rpms. uniio servers are None.", 1)
        return False
    if not build(build_server):
        return False

    # download from build server and upload rpm packages to federation nodes:
    me.exe("rm -rf /tmp/rpms && mkdir /tmp/rpms")
    if not build_server.download("/tmp/rpms/", "%s/uniio/build/object-array-*.rpm" % (g_runtime_dir)):                    # download uniio rpms
        return False
    if not build_server.download("/tmp/rpms/", "%s/nasmgmt/build/object-array-nasmgmt-*.rpm" % (g_runtime_dir)):          # download nasmgmt rpms
        return False
    if not build_server.download("/tmp/rpms/", "%s/sysmgmt/build/object-array-sysmgmt-*.rpm" % (g_runtime_dir)):          # download sysmgmt rpms
        return False
    if not build_server.download("/tmp/rpms/", "%s/uniio-ui/build_debug/object-array-uniio-ui-*.rpm" % (g_runtime_dir)):  # download uniio-ui rpms
        return False

    for t in federation_targets:
        t.exe("rm -rf /tmp/rpms && mkdir -p /tmp/rpms")
        if not t.upload("/tmp/rpms/*.rpm", "/tmp/rpms/"):
            return False

    cos = []
    for t in federation_targets:
        cmd  = "%s/uio_scripts/server/init_cluster.sh %s --replace=/tmp/rpms" % (g_runtime_dir, '-f' if force else "")
        cos.append(t.exe(cmd, wait=False))
    for co in cos:
        if not co.succ():
            common.log("failed when replacing uniio packages.")
            return False
    return True


def replace_bin(federation_targets, build_server, force=True):
    '''
        if the g_binonly is a local file, simply upload the file and replace '/opt/uniio/sbin/cio_array'
        if the g_binonly is not a local file, build the latest cio_array, cio_array.sym on build_server and replace binaries on federation nodes
    '''
    if not federation_targets:
        common.log("failed replace rpms. uniio servers are None.", 1)
        return False

    if me.is_path_executable(g_binonly): # use a local binary file to update the federation
        for t in federation_targets:
            if not t.upload(g_binonly, "/opt/uniio/sbin/cio_array"):
                return False
    else:
        if not build_server:
            common.log("failed replace rpms. build server is None.", 1)
            return False
        if not build_bin(build_server):  # build and upload
            return False
        # download from build server and upload rpm packages to federation nodes:
        if not build_server.download("/tmp/", "%s/uniio/build/cio_array" % (g_runtime_dir)):  # download cio_array cio_array.sym
            return False
        if not build_server.download("/tmp/", "%s/uniio/build/cio_array.sym" % (g_runtime_dir)):  # download cio_array cio_array.sym
            return False
        for t in federation_targets:
            if not t.upload("/tmp/cio_array", "/opt/uniio/sbin/"):
                return False
            if not t.upload("/tmp/cio_array.sym", "/opt/uniio/sbin/"):
                return False
    return True

def init_cluster(federation_targets, force=True):
    if not federation_targets:
        common.log("federation nodes are None.")
        return False
    if not shutdown_cluster(federation_targets, force):
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
    for t in federation_targets: # give time for fabricmanager to be ready for accepting topology
        if not t.wait_alive(8080, 120):
            common.log("fabricmanager is not starting after 120s. port: 8080")
            return False
    if not push_topology(federation_targets):
        return False
    return True

def boot_cluster(federation_targets):
    # start objmgr and objmgr-fab on all uniio nodes
    cos = []
    for t in federation_targets:
        cmd  = "%s/uio_scripts/server/init_cluster.sh -b" % (g_runtime_dir)
        cos.append(t.exe(cmd, wait=False))
    for co in cos:
        if not co.succ():
            common.log("failed when starting uniio.")
            return False
    return True

def update_cluster(federation_targets, build_server, force=True):
    if not shutdown_cluster(federation_targets, force):
        return False
    if g_binonly:
        if not replace_bin(federation_targets, build_server, g_force):
            return False
    else:
        if not replace_rpm(federation_targets, build_server, g_force):
            return False
    if not init_cluster(federation_targets):
        return False
    return True

def push_topology(federation_targets):
    t = None
    for n in federation_targets:
        if fab_running(n):
            t = n
            break
    if not t:
        common.log("fabric manager is not running on federation nodes.", 1)
        return False
    # pushing topology
    if not t.exe("cioctl topology %s" % (g_conf["topology"])).succ():
        return False
    if not t.exe("cioctl portal --management_ip %s --iscsi_ip %s" % (g_conf["management_ip"], g_conf["iscsi_ip"])).succ():
        return False
    return True

def create_luns(client_targets, federation_targets, numluns=0):
    # get client iscsi initiator iqns for mapping
    iqns = {}  # { address : iqn }
    for t in client_targets:
        iqns[t.address] = t.exe("awk -F'=' '{print \$2}' /etc/iscsi/initiatorname.iscsi").stdout.strip()
    
    t = None
    for n in federation_targets:
        if fab_running(n):
            t = n
            break
    if not t:
        common.log("fabric manager is not running on all federation nodes.", 1)
        return False    
    
    # create luns
    num_luns = numluns if numluns else g_conf["num_luns"] if g_conf.has_key("num_luns") else 18
    for i in range(num_luns):
        if not t.exe("cioctl create lun%d %dG" % (i, g_conf["lunsize_G"])).succ():
            return False
        if not t.exe("cioctl iscsi target create --name tgt-%d" % (i)).succ():
            return False
    
    # create initiator groups
    inames = []
    for address in iqns.keys():
        iqn = iqns[address]
        addr = address.replace(".", "-")
        iname = "i%s" % (addr); inames.append(iname)
        if not t.exe("cioctl iscsi initiator create --name %s --iqn %s" % (iname, iqn)).succ():
            return False
        if not t.exe("cioctl iscsi initiatorgroup create --name ig%s --initiators i%s" % (addr, addr)).succ():
            return False
    if g_fullmap:
        if not t.exe("cioctl iscsi initiatorgroup create --name igall --initiators %s" % (','.join(inames))).succ():
            return False

    # create mappings: luns are evenly mapped to clients
    num_igs = len(iqns); luns_per_client = num_luns / len(iqns)
    for i in range(num_luns):
        address = iqns.keys()[(i/luns_per_client)%num_igs]
        addr = address.replace(".", "-"); igroup = 'igall' if g_fullmap else "ig%s" % (addr)
        if not t.exe("cioctl iscsi mapping create --blockdevice lun%d --target tgt-%d --initiatorgroup %s" % (i, i, igroup)).succ():
            return False
    return True

def clear_luns(client_targets, federation_targets):
    iscsi_ip = g_conf["iscsi_ip"]
    cos = []
    for t in client_targets:
        cos.append(t.exe("iscsiadm -m node --logout", wait=False))
        cos.append(t.exe("iscsiadm -m session -u", wait=False))
        cos.append(t.exe("iscsiadm -m discoverydb -t sendtargets -p %s:3260 -o delete" % (iscsi_ip), wait=False))
    for co in cos:
        co.wait()

    t = None
    for n in federation_targets:
        if fab_running(n):
            t = n
            break
    if not t:
        common.log("fabric manager is not running on all federation nodes.", 1)
        return False    
    
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
    for co in cos:
        if not co.succ():
            return False
    for t in client_targets:
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

def fio_build_job_contents(client_target, fill=0):
    """
        generate fio job file contents for 'runfio.sh' for a given client
        return: jobdesc, fio_job_content
            jobdesc: string to summarize the job ( may be used as prefix of job filename  )
            fio_job_content: content string for the fio job definition file
    """
    fio_job_content  = "[global]"
    fio_job_content += "\n" "write_bw_log=xxx"   # later xxx will be replaced by runfio.sh
    fio_job_content += "\n" "write_lat_log=xxx"  # later xxx will be replaced by runfio.sh
    fio_job_content += "\n" "write_iops_log=xxx" # later xxx will be replaced by runfio.sh
    fio_job_content += "\n" "log_avg_msec=10000" 
    fio_job_content += "\n" "ioengine=libaio" 
    fio_job_content += "\n" "direct=1" 
    fio_job_content += "\n" "sync=1" 
    fio_job_content += "\n" "bs=4k"
    dist = g_conf["fio_random_distribution"] if g_conf.has_key("fio_random_distribution") else "random"
    fio_job_content += "\n" "random_distribution=%s" % (dist)
    
    duprate = g_conf["fio_dedupe_percentage"] if g_conf.has_key("fio_dedupe_percentage") else 80
    if fill: duprate = 0
    if duprate != 0:
        fio_job_content += "\n" "dedupe_percentage=%d" % (duprate) 
    else:   # no deduplicable data, small changes to every fio buffer
        fio_job_content += "\n" "scramble_buffers=1"
    
    comprate = g_conf["fio_buffer_compress_percentage"] if g_conf.has_key("fio_buffer_compress_percentage") else 60
    if fill: comprate = 0
    if comprate != 0:
        fio_job_content += "\n" "buffer_compress_percentage=%d" % (comprate)
    else:   # no compressible data, refill every fio buffer
        fio_job_content += "\n" "refill_buffers=1"
    
    fio_job_content += "\n" "group_reporting=1"
    
    runtime = g_conf["fio_runtime"] if g_conf.has_key("fio_runtime") else 60
    if fill: runtime = fill
    fio_job_content += "\n" "runtime=%d" % (runtime) 
    fio_job_content += "\n" "time_based=1" 
    fio_job_content += "\n" "ramp_time=%d " % (g_conf["fio_ramp_time"] if g_conf.has_key("fio_ramp_time") else 60)

    # numjobs and iodepth may be replaced by 'runfio.sh'
    njobs = g_conf["fio_numjobs"] if g_conf.has_key("fio_numjobs") else 1
    fio_job_content += "\n" "numjobs=%d" % (njobs) 
    qdepth = g_conf["fio_iodepth"] if g_conf.has_key("fio_iodepth") else 3
    fio_job_content += "\n" "iodepth=%d" % (qdepth)
    fio_job_content += "\n" ""

    rw = g_conf["fio_rw"] if g_conf.has_key("fio_rw") else "randrw"
    nj_str = g_conf["runfio_jobs"] if g_conf.has_key("runfio_jobs") else str(njobs)
    qd_str = g_conf["runfio_qdepth"] if g_conf.has_key("runfio_qdepth") else str(qdepth)
    jobdesc = "%s.qd%s.njobs%s.%ddup.%dcomp.%s_dist.%dsec" % \
              (rw, re.sub(',| ', '-', qd_str.strip()), re.sub(',| ', '-', nj_str.strip()), duprate, comprate, dist, runtime)
    if fill: rw = "write"

    # get UNIIO iscsi luns on client
    cmd = "lsblk -p -o name,vendor | grep UNIIO | awk '{print \$1}'"
    uio_devs = client_target.exe(cmd).getlist()
    if not uio_devs:  # no uniio iscsi devices on this client
        common.log("no uniio iscsi devices on this client: %s" % (client_target.address), 1)
        return None, None

    for dev in uio_devs:
        fio_job_content += "\n" ""
        if rw[:6] == "sepjob":  # no constraint for read and write, will define separate jobs for read and write
            if rw[7:] == "rw":  # separated jobs for sequential read and write
                fio_job_content += "\n" "[%s_read]" % (dev)
                fio_job_content += "\n" "rw=read"
                fio_job_content += "\n" "filename=%s" % (dev)
                fio_job_content += "\n" "[%s_write]" % (dev)
                fio_job_content += "\n" "rw=write"
                fio_job_content += "\n" "filename=%s" % (dev)
            else:  # separated jobs for random read and write
                fio_job_content += "\n" "[%s_read]" % (dev)
                fio_job_content += "\n" "rw=randread"
                fio_job_content += "\n" "filename=%s" % (dev)
                fio_job_content += "\n" "[%s_write]" % (dev)
                fio_job_content += "\n" "rw=randwrite"
                fio_job_content += "\n" "filename=%s" % (dev)
        else:   # actual fio supported rw types
            fio_job_content += "\n" "[%s]" % (dev)
            fio_job_content += "\n" "filename=%s" % (dev)
            fio_job_content += "\n" "rw=%s" % (rw)
            if rw.strip().find('rw') >= 0:  # mixed read/write
                fio_job_content += "\n" "rwmixread=%d" % (g_conf["fio_rwmixread"] if g_conf.has_key("fio_rwmixread") else 80) 
                fio_job_content += "\n" "rwmixwrite=%d" % (g_conf["fio_rwmixwrite"] if g_conf.has_key("fio_rwmixwrite") else 20) 

    return jobdesc, fio_job_content


def fio_gen_jobs(client_targets, fill=0):
    """
        generate fio job files for 'runfio.sh' then upload to clients
        return: jobdesc, fio_job_dir
            jobdesc: the string that summarize the fio job
            fio_job_dir: directory that contains fio job files on client servers
    """
    jobdesc = None; jobfile_names = []
    # write fio job files for each client
    for t in client_targets:
        jobdesc, fio_filljob_content = fio_build_job_contents(t, fill)
        jobdesc, fio_jobfile_content = fio_build_job_contents(t)

        jobfile_name = "%s_%s.fio" % (jobdesc, t.address)
        f = open(jobfile_name, "w"); f.write(fio_jobfile_content); f.close()
        jobfile_names.append(jobfile_name)

        jobfile_name = "fill%d_%s_%s.fio" % (fill, jobdesc, t.address)
        f = open(jobfile_name, "w"); f.write(fio_filljob_content); f.close()
        jobfile_names.append(jobfile_name)
    
    # upload fio job files to all clients
    fio_job_dir = g_runtime_dir + "/fiorun/%s" % (jobdesc)
    for t in client_targets:
        t.exe( "mkdir -p %s" % (fio_job_dir) )
        for jobfile_name in jobfile_names:
            if not t.upload( jobfile_name, fio_job_dir ):
                return None, None
    for jobfile_name in jobfile_names:
        me.exe("rm -f %s" % (jobfile_name))
    return jobdesc, fio_job_dir

def fio_run(client_targets, fill=0):
    '''
        run fio job on one of the client nodes
        fill: a number
              fill luns for a given duration in seconds before performing the performance test
        return: (jobdesc, fio_job_dir, cmdobj, fio_driver)
            cmdobjs: command objs that traces the fio jobs
            fio_driver: the target that fio runs on
    '''
    if not fio_server(client_targets): return None, None, None, None
    if not iscsi_out(client_targets): return None, None, None, None
    if not iscsi_in(client_targets): return None, None, None, None

    jobdesc, fio_job_dir = fio_gen_jobs(client_targets, fill)
    if not jobdesc:
        return None, None, None, None

    # choose one of the clients as the fio driver
    idx = random.randrange(1,1024) % len(client_targets)
    fio_driver = client_targets[idx]

    # run 'client/runfio.sh' on the fio driver node
    sh_fio = fio_driver.newshell()
    if not sh_fio.exe("cd %s" % (fio_job_dir)):
        return None, None, None, None
    clients=""
    for t in client_targets:
        clients += "%s," % (t.address)  # the tailing ',' will be handled by 'runfio.sh'
    njobs = g_conf["fio_numjobs"] if g_conf.has_key("fio_numjobs") else 1
    qdepth = g_conf["fio_iodepth"] if g_conf.has_key("fio_iodepth") else 3
    nj_str = g_conf["runfio_jobs"] if g_conf.has_key("runfio_jobs") else str(njobs)
    qd_str = g_conf["runfio_qdepth"] if g_conf.has_key("runfio_qdepth") else str(qdepth)
    runtime_str = g_conf["fio_runtime"] if g_conf.has_key("fio_runtime") else "60"
    cos = []
    if fill:
        cmd = "%s/uio_scripts/client/runfio.sh --jobs 4 --qdepth 128 --clients %s --profiledir %s -t %s %s | tee %s/fiorunning.log" % (g_runtime_dir, clients, fio_job_dir, fill, "fill%d_%s" % (fill, jobdesc), g_runtime_dir)
        if not sh_fio.exe(cmd).succ():
            return None, None, None, None
    cmd = "%s/uio_scripts/client/runfio.sh --jobs '%s' --qdepth '%s' --clients %s --profiledir %s -t %s %s | tee %s/fiorunning.log" % (g_runtime_dir, nj_str, qd_str, clients, fio_job_dir, runtime_str, jobdesc, g_runtime_dir)
    cos.append(sh_fio.exe(cmd, wait=False))
    common.log("long task running on '%s': %s" % (fio_driver, cmd))

    return (jobdesc, fio_job_dir, cos, fio_driver)

def counter_log(jobdesc, federation_targets):
    '''
        start logging counter values using 'server/counters.sh' on federation nodes
        collect cpu data into flame graphs every 1 hour ( if applicable )
        return: counter_log_dir, counter_log_path, cmdobjs
            counter_log_dir:  the directory that contains counter logs and svg files
            counter_log_path: counter log location on each node
            cmdobj: the command objects tracking the counters.sh command
    '''

    # numjobs and iodepth may be replaced by 'runfio.sh'
    njobs = g_conf["fio_numjobs"] if g_conf.has_key("fio_numjobs") else 1
    qdepth = g_conf["fio_iodepth"] if g_conf.has_key("fio_iodepth") else 3
    nj_str = g_conf["runfio_jobs"] if g_conf.has_key("runfio_jobs") else str(njobs)
    qd_str = g_conf["runfio_qdepth"] if g_conf.has_key("runfio_qdepth") else str(qdepth)
    nj_str = re.sub('\s+', ',', nj_str.strip())
    qd_str = re.sub('\s+', ',', qd_str.strip())
    runtime = g_conf["fio_runtime"] if g_conf.has_key("fio_runtime") else 60

    dur = len(nj_str.split(',')) * len(qd_str.split(',')) * runtime
    cmdobjs = []

    # collect counter logs
    counter_log_dir = "%s/counter_logs" % (g_runtime_dir)
    counter_log_path = "%s/%s.%ddur.log" % (counter_log_dir,jobdesc, dur)
    for t in federation_targets:
        t.exe("mkdir -p %s" % (counter_log_dir))
        sh = t.newshell()
        if not sh:
            return None, None, None
        cmd = "%s/uio_scripts/server/counters.sh %d > %s" % (g_runtime_dir, dur, counter_log_path)
        cmdobjs.append(sh.exe(cmd, wait=False))
        common.log("long task running on '%s': %s" % (t, cmd))
    
    if g_cpudata:
        # collect cpu data with 'server/collect_cpu.sh' for one time at start
        # if duration is more than 1 hour, proceed cpu data collection every hour
        every = 3600
        num_collects = dur / every + 1
        for t in federation_targets:
            sh = t.newshell()   # get a new shell for cpu collection, so no serilization with the counter shell
            if not sh:
                return None, None, None
            # stacking commands in the same shell, it will serialize all commands
            cmdobjs.append(sh.exe("cd %s" % (counter_log_dir), wait=False))
            for elapse in [ every * i for i in range(num_collects) ]:
                prefix = "when%ds.%s" % (elapse, jobdesc)
                cmdobjs.append(sh.exe("sleep %d" % (elapse if elapse == 0 else every), wait=False))
                cmd = "%s/uio_scripts/server/collect_cpu.sh cio_array -w %s -t 30" % (g_runtime_dir, prefix)
                cmdobjs.append(sh.exe(cmd, wait=False))
                cmd = "%s/uio_scripts/server/collect_cpu.sh -w %s -t 30" % (g_runtime_dir, prefix)
                cmdobjs.append(sh.exe(cmd, wait=False))

    return counter_log_dir, counter_log_path, cmdobjs

def perf_test(client_targets, federation_targets, fill=0):
    '''
        run performance test.
        start fio workload from clients,
        collect counter logs at the same time,
        fill: fill the luns first, for a given time
        return when all jobs are done.
    '''
    status_str = ""
    jobdesc, fio_job_dir, fio_cos, fio_driver = fio_run(client_targets, fill)
    if not fio_cos:
        return False
    counter_log_dir, counter_log_path, counter_cos = counter_log(jobdesc, federation_targets)

    # wait for jobs to end
    fio_fail = None
    for fio_co in fio_cos:
        if not fio_co.succ():
            fio_fail = fio_co
    if fio_fail: status_str += ".FIO_FAIL_on_%s" % (fio_driver.address)
    counter_fail = None
    for co in counter_cos:
        if not co.succ():
            counter_fail = co
    if counter_fail: status_str += ".COUNTER_FAIL_on_%s" % (counter_fail.shell.t.address)

    # download fio logs from fio driver node
    localtime = time.localtime()
    date_str = "%d-%02d-%02d" % (localtime.tm_year, localtime.tm_mon, localtime.tm_mday)
    time_str = "%02d.%02d.%02d" % (localtime.tm_hour, localtime.tm_min, localtime.tm_sec)
    logdir = "./perflogs/%s/%s.%s_%s%s" % (date_str, jobdesc, date_str, time_str, status_str)
    me.exe("rm -rf %s" % (logdir))
    me.exe("mkdir -p %s" % (logdir))
    if not fio_driver.download(logdir, "%s/*" % (fio_job_dir)):
        return False
    # download counter logs and cpu data svg files from federation nodes
    for t in federation_targets:
        counterdir = "%s/counter_%s" % (logdir, t.address)
        svgdir = "%s/cpudata_%s" % (logdir, t.address)
        me.exe("mkdir -p %s" % (counterdir))
        if g_cpudata: me.exe("mkdir -p %s" % (svgdir))
        if not t.download(counterdir, counter_log_path):
            return False
        if g_cpudata and not t.download(svgdir, counter_log_dir+"/*%s*.svg" % (jobdesc)):
            return False
    json.dump(g_conf, open("%s/settings.json" % (logdir), 'w'), indent=2)  # dump a copy of config file to the logdir
    common.log("DONE EEPERFTEST.\n%s\nlog location: %s" % ("-"*60, os.path.join(os.getcwd(), logdir)))
    return True

if __name__ == "__main__":
    conf = handleopts()
    if not conf: exit(1)

    client_targets, federation_targets, build_server = prep_targets()
    if not client_targets or not federation_targets or not build_server: exit(1)

    if g_delluns_only:
        if not clear_luns(client_targets, federation_targets): exit(1)

    if g_shutdown_only:
        if not shutdown_cluster(federation_targets, force=g_force): exit(1)
    
    if g_boot_only:
        if not boot_cluster(federation_targets): exit(1)
    
    if g_update:
        if not update_cluster(federation_targets, build_server, force=True): exit(1)
    
    if g_init:
        if not init_cluster(federation_targets, force=True): exit(1)
    
    if g_createluns:
        if not create_luns(client_targets, federation_targets, g_createluns): exit(1)
        
    if g_perftest:
        if (g_init or g_update) and (not g_createluns):
            if not create_luns(client_targets, federation_targets, 0): exit(1)
        if not perf_test(client_targets, federation_targets, g_fill): exit(1)
    
    common.log("DONE.")
    exit(0)
