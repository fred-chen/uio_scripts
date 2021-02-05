#!/usr/bin/env python

'''
a script automatically finds out which commit causes the performance regression

@author: fred
'''

import sys, os, getopt, json, uuid
sys.path.append('%s/../cctf' % (os.path.dirname(os.path.realpath(__file__))))
from cctf import gettarget, me

g_conf = None
g_conf_file = ""
g_runtime_dir = '/tmp'
g_c1, g_c2 = "",""
g_narrow = 3
g_kiops = 300

def usage(errmsg=""):
    if(errmsg != ""):
        sys.stderr.write("\nERROR: %s\n" % errmsg)
    print("usage: %s  [ -c|--config configfile.json ] [ --narrow num_commits ] [ -k kiops ] commit1 commit2" % (os.path.basename(sys.argv[0])))
    exit(1)

def handleopts():
    global g_conf, g_conf_file, g_runtime_dir, g_c1, g_c2, g_narrow, g_kiops

    conf_file = "%s/auto.json" % (os.path.dirname(os.path.realpath(__file__)))
    try:
        options, args = getopt.gnu_getopt(sys.argv[1:], "hc:k:", ["help", "configfile=", "narrow="])
    except getopt.GetoptError as err:
        usage(err)
    for o, a in options:
        if(o in ('-h', '--help')): 
            usage()
        if(o in ('-c', '--config')):
            conf_file = a
        if(o in ('', '--narrow')):
            g_narrow = int(a)
        if(o in ('-k', '')):
            g_kiops = int(a)
    f = open(conf_file)
    if not f:
        print("can not open configuration file '%s'." % conf_file)
        return None
    jstr = f.read()
    if not jstr: 
        print("can not read configuration file '%s'." % conf_file)
        return None
    g_conf = json.loads(jstr)
    if not g_conf:
        print("can not parse configuration file '%s'." % conf_file)
        return None
    g_runtime_dir = g_conf["runtime_dir"] if g_conf.has_key("runtime_dir") else g_runtime_dir
    g_conf_file = conf_file
    i=-1
    for i in range(len(args)):
        if i == 0:
            g_c1 = args[0]
        elif i == 1:
            g_c2 = args[1]
    if i >= 2:
        usage("too many commits were specified.")
    if i == -1:
        usage("at least one commit must be specified.")
    return True

def get_build_server():
    build_node_def = g_conf["build_server"]  # [IP, username, password, git_ssh_identifyfile]

    build_server = None
    build_server = gettarget(build_node_def[0], username=build_node_def[1], password=build_node_def[2], svc="ssh", timeout=60)
    if not build_server:
        build_server = None

    return build_server

def get_gitcmd():
    git_proxy = "ALL_PROXY="+g_conf["build_server_git_proxy"] if g_conf.has_key("build_server_git_proxy") else ""
    return "%s git" % (git_proxy) if git_proxy else "git"

def get_clist(build_server):
    a,b,c,git_ssh_identityfile = g_conf["build_server"]  # [IP, username, password, git_ssh_identityfile]
    sh = build_server.newshell()
    sh.exe("cd /tmp")
    sh.exe("export GIT_SSH_COMMAND=\"ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o IdentityFile=%s -o ProxyCommand='ssh -q -W %%h:%%p evidence.orcadt.com'\"" % (git_ssh_identityfile))
    
    # git clone uniio repo
    gitcmd = get_gitcmd()
    repo = "uniio"
    checkout = g_conf["%s_checkout"%(repo)] if g_conf.has_key("%s_checkout"%(repo)) else "default"
    cmd = "[[ -e '%s/%s' ]] && { cd %s/%s && git fetch; } || { %s clone --recurse-submodules git@github.com:uniio/%s.git %s/%s; }" \
            % (g_runtime_dir, repo, g_runtime_dir, repo, gitcmd, repo, g_runtime_dir, repo)
    if not sh.exe(cmd).succ(): return None
    
    if checkout != "default": # checkout desired branch or tag or commit
        cmd = "cd %s/%s && %s checkout %s" % (g_runtime_dir, repo, gitcmd, checkout)
        sh.exe(cmd)
    cmd = "cd %s/%s && %s pull --no-edit || true" % (g_runtime_dir, repo, gitcmd)
    sh.exe(cmd)
    clst = sh.exe("cd %s/%s && %s log --pretty=format:'%%h|%%ci|%%an|%%s'" % (g_runtime_dir, repo, gitcmd), log=False).getlist()
    clist = []
    for c in clst:
        clist.append(c.split("|"))
    return clist

def get_iops(logpath):
    iops, iops_str = None, None
    uiodir = "{0}/..".format(os.path.dirname(os.path.realpath(__file__)))
    path_showfio = "{0}/client/showfio.sh".format(uiodir)
    rt, path_results, err = me.exe("tail {log} | grep 'log location' | awk '{{print $3}}'".format(log=logpath))
    if path_results:
        cmd = "{showfio} $(ls {path}/fio_output/[^fill]*) | grep 'Total: IOPS:' | awk '{{print $3}}' ".format(showfio=path_showfio, path=path_results)
        rt, iops_str, stderr = me.exe(cmd)
        iops = int(iops_str.split("@")[0]) if iops_str else None
    return iops, iops_str, path_results

def bisect(clist, comp_iops, narrow=3, runlast=False):
    '''
          every run it will checkout the ** MIDDLE ** commit in the list
          then build and replace, then run the test
          arguments:
            clist: [ (hash, committer date, author name, desc), ... ]
            narrow: recurse perf test until the commits in list is narrowed down to a given number, default 4 commits.
          return: [ [hash, iops], ... ]
            hash: the commit it chose to run
            iops: the total iops number corresponds to commit_info
    '''
    path_perfauto = "{0}/perfauto.py".format(os.path.dirname(os.path.realpath(__file__)))

    results = []
    if not clist or len(clist) <= narrow: 
        return results
    if not runlast:
        idx = len(clist) / 2
    else:
        idx = len(clist) - 1  # run the last commit for the first round
    hash = clist[idx][0]
    logpath = "{0}.{1}.out".format(hash, str(uuid.uuid1()))
    sys.stdout.write( "testing {0} log: {1}".format( "|".join(clist[idx]), logpath ) ); sys.stdout.flush()

    cmd = "{0} -c {1} -u --ref={2} -p --fill 600 --fullmap > {3} ".format(path_perfauto, g_conf_file, hash, logpath)
    iops = None; path = None
    succ = me.succ(cmd)
    if not succ:  # execution fail
        sys.stdout.write( "\r" + "FAIL!! {0} log: {1}\n".format( "|".join(clist[idx]), logpath ) )
    else:
        iops, iops_str, path = get_iops(logpath)
        sys.stdout.write( "\r" + "IOPS: {2} ref: {0} log: {1}\n".format( "|".join(clist[idx]), logpath, iops_str ) )
        if os.path.exists(path):
            me.exe("mv {0} {1}/".format(logpath, path))
    if iops:
        results.append([ hash, iops ])
        if iops > comp_iops:  # goto left half in the list (for later commits)
            lst = clist[:idx]
        else:                 # goto right half in the list (for earlier commits)
            lst = clist[idx+1:]
    else:   # can't get iops for this round, retry with the closest commits
        results.append([ hash, -1 ])
        lst = clist[:-1]
    return results.append(bisect(lst, comp_iops, narrow, runlast=False))
    
if __name__ == "__main__":
    if not handleopts(): exit(1)

    build_server = get_build_server()
    clist = get_clist(build_server)  # [ [hash, committer date, author name, desc], ...  ]
    if not g_c2:    # no second commit specified, use top commit by default
        g_c2 = clist[0][0]

    # find commit indices
    idx1, idx2 = -1, -1
    for i in range(len(clist)):
        hash = clist[i][0]
        if g_c1 == hash or g_c2 == hash:
            if idx1 == -1:  # idx1 not set yet
                idx1 = i
            else:
                idx2 = i
                break
    if idx1 > idx2:
        min, max = idx2, idx1
    else:
        min, max = idx1, idx2
    clist = clist[min:max+1]
    top_commit = clist[0][0]; bottom_commit = clist[max-min][0]

    print ("bisect: top_commit=%s, bottom_commit=%s, num_commits=%d, compare_iops=%d, narrow_down=%d" % (top_commit, bottom_commit, len(clist), g_kiops*1000, g_narrow))
    print ("-" * 80)
    results = bisect(clist, g_kiops * 1000, g_narrow, runlast=True) # [ [hash, iops], ... ]
    results.reverse()
    c1 = ""; c2 = ""
    for r in results:
        hash = r[0]
        iops = r[1]
        if iops > g_kiops*1000:
            if not c1: c1 = hash  # the most recent commit that achieves performance goal
        else:
            if not c2: c2 = hash  # the most recent commit that fails performance goal
    for i in range(len(clist)):
        hash = clist[i][0]
        if hash == c1:
            idx1 = i
        if hash == c2:
            idx2 = i
    if idx1 > idx2:
        min, max = idx2, idx1
    else:
        min, max = idx1, idx2

    clist = clist[min:max+1]
    print ("the problematic commit might be in:")
    for c in clist:
        print ("|".join(c))
        


