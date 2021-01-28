#!/usr/bin/env python

'''
automatic performance evaluation for uniio

@author: fred
'''
import sys, os, json, getopt
sys.path.append('%s/../cctf' % (os.path.dirname(os.path.realpath(__file__))))
from cctf import gettarget, common

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
        * build 3 target lists: client_targets, federation_targets, build_servers
        * upload uio_scripts to all targets
        * return 3 target lists as a tuple: (client_targets, federation_targets, build_servers)
    '''
    global g_runtime_dir
    # node defs: [ (IP, username, password), ... ]
    client_node_def = g_conf["client_nodes"]
    federation_node_def = g_conf["federation_nodes"]
    build_node_def = g_conf["build_nodes"]

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

    build_servers = []
    for n in build_node_def:
        t = gettarget(n[0], username=n[1], password=n[2], svc="ssh", timeout=10)
        if t:
            build_servers.append(t)
        else:
            return None

    # upload uio_scripts to targets
    for t in client_targets + federation_targets:
        if not t.upload("%s" % (g_rootdir), g_runtime_dir):
            return None

    return (client_targets, federation_targets, build_servers)

def get_gitcmd():
    git_proxy = "ALL_PROXY="+g_conf["git_proxy"] if g_conf.has_key("git_proxy") else ""
    return "%s git" % (git_proxy) if git_proxy else "git"

def build(build_servers):
    '''
        build uniio rpms
    '''
    global g_runtime_dir
    gitcmd = get_gitcmd()
    cos = []
    for n in build_servers:
        shs = []
        for i in range(4):  # use 4 shells for parallel compilation
            sh = n.newshell()
            shs.append(sh)
        for sh in shs:
            sh.exe("export GIT_SSH_COMMAND=\"ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o IdentityFile=/root/fred/.ssh/id_rsa -o ProxyCommand='ssh -q -W %h:%p evidence.orcadt.com'\"")

        # git clone all repos in parallel
        repos = ('uniio', 'uniio-ui', 'sysmgmt', 'nasmgmt')
        i = 0
        for repo in repos:
            cmd = "[[ -e '%s/%s' ]] && { cd %s/%s && %s pull --recurse-submodules; } || { %s clone --recurse-submodules git@github.com:uniio/%s.git %s/%s; }" \
                  % (g_runtime_dir, repo, g_runtime_dir, repo, gitcmd, gitcmd, repo, g_runtime_dir, repo)
            cos.append( shs[i%4].exe(cmd, wait=False) )
            i += 1
        for co in cos:
            if not co.succ():
                return False
        sh0 = shs[0]        # shell used for uniio compilation
        sh1 = shs[1]        # shell used for sysmgmt compilation
        sh2 = shs[2]        # shell used for nasmgmt compilation
        sh3 = shs[3]        # shell used for uniio-ui compilation
        
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
                common.log("failed cmake command:\n%s" % (co.cmdline), 1)
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


if __name__ == "__main__":
    conf = handleopts()
    if not conf: exit(1)

    targets = prep_targets()
    if not targets: exit(1)

    client_targets, federation_targets, build_servers = targets
    if not build(build_servers): exit(1)