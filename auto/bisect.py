#!/usr/bin/env python

'''
a script automatically finds out which commit causes the performance regression

@author: fred
'''

import sys, os, getopt, json, uuid, datetime, time
sys.path.append('%s/../cctf' % (os.path.dirname(os.path.realpath(__file__))))
from cctf import gettarget, me

g_conf = None
g_conf_file = ""
g_runtime_dir = '/tmp'
g_c1, g_c2 = "",""
g_narrow = 3
g_kiops = 300
g_results = []
g_op = "bisect"  # bisect or daily
g_repeats = 1

def usage(errmsg=""):
    if(errmsg != ""):
        sys.stderr.write("\nERROR: %s\n\n" % errmsg)
    just = len("usage: %s" % (os.path.basename(sys.argv[0])))
    print("usage: %s  [ -c|--config configfile.json ] [ -r repeats ] commit1 commit2" % (os.path.basename(sys.argv[0])))
    print("%s  [ -m|--method bisect ] [ -k kiops ] [ --narrow num_commits ] " % (' '.rjust(just)))
    print("%s  [ -m|--method everyn ] [ --narrow num_commits ] " % (' '.rjust(just)))
    print("%s  [ -m|--method daily  ] [ --narrow num_days ] " % (' '.rjust(just)))
    print("")
    print("a script automatically finds out which commit causes the performance regression.")
    print("")
    print("options:")
    print("  -c, --config : config file path.")
    print("  -r           : repeat test for 'repeats' times.")
    print("  -m bisect    : checkout middle commits and run bisect perf test against it.")
    print("  -m everyn    : checkout every n commits and run bisect perf test against it.")
    print("  -m daily     : checkout the last commit in every num_days and run perf test everytime.")
    print("    -k         : use with '-m bisect', the K IOPS number for bisect comparison.")
    print("    --narrow   : use with '-m bisect', '-m daily' and '-m every'. ")
    print("                  for bisect: stop when remaining commits are less than num_commits.")
    print("                  for every : checkout every num_commits commits.")
    print("                  for daily : checkout the last commits in every num_days.")
    print("")
    print("arguments:")
    print("  commit1, commit2 : start and end commits for test. start from the latest commit of the branch in config file if only one of them is specified.")
    print("")
    exit(1)

def handleopts():
    global g_conf, g_conf_file, g_runtime_dir, g_c1, g_c2, g_narrow, g_kiops, g_op, g_repeats

    conf_file = "%s/auto.json" % (os.path.dirname(os.path.realpath(__file__)))
    try:
        options, args = getopt.gnu_getopt(sys.argv[1:], "hc:k:m:r:", ["help", "configfile=", "narrow=", "method="])
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
        if(o in ('-r', '')):
            g_repeats = int(a)
        if(o in ('-m', '--method')):
            g_op = a

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
    clst = sh.exe("cd {0}/{1} && {2} --no-pager log --pretty=format:'%h{3}%ci{3}%an{3}%s'".format(g_runtime_dir, repo, gitcmd, "|^||IMAFANCYSPLITTER||^|"), log=False).getlist()
    clist = []
    for c in clst:
        clist.append(c.split("|^||IMAFANCYSPLITTER||^|"))
    return clist

def get_iops(logpath):
    iops, iops_str = None, None
    rt, path_results, err = me.exe("tail -100 {log} | grep 'log location' | awk '{{print $3}}'".format(log=logpath))
    rt, iops_str    , err = me.exe("tail -100 {log} | grep 'Total: IOPS:' | awk '{{print $3}}' ".format(log=logpath))
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
    global g_results

    top_commit = clist[0][0]; bottom_commit = clist[len(clist)-1][0]
    print ("\n\nbisect: top_commit=%s, bottom_commit=%s, num_commits=%d, compare_iops=%d, narrow_down=%d" % (top_commit, bottom_commit, len(clist), g_kiops*1000, g_narrow))
    if not clist or len(clist) <= narrow:
        return []
    if not runlast:
        idx = len(clist) / 2
    else:
        idx = len(clist) - 1  # run the last commit for the first round
    result = run_commit(clist[idx])
    iops = result[1]
    if iops > 0:
        if iops > comp_iops:  # goto left half in the list (for later commits)
            lst = clist[:idx]
        else:                 # goto right half in the list (for earlier commits)
            lst = clist[idx+1:]
    else:   # can't get iops for this round, retry with the closest commits
        lst = clist[:-1]
    g_results.append(result)
    if runlast:
        lst = clist
    result = bisect(lst, comp_iops, narrow, runlast=False)
    return result

def daily(clist, days):
    """test commit every 'days' days

    Args:
        clist (list): the commit list: [ [hash, committer date, author name, desc], ...  ]
        days (int): every n days
    """
    global g_results

    daily_commits = {}  # { date : [ commit1, commit2 ] }
    for c in clist:
        date_str = c[1].split(" ")[0]
        hash     = c[0]
        if daily_commits.has_key(date_str):
            daily_commits[date_str].append(hash)
        else:
            daily_commits[date_str] = [ hash ]
    # choosing hashes
    hashes = []   # [ [hash, date], [hash, date], ... ]
    lasthash = clist[len(clist)-1][0]
    prev_date = None
    for d in reversed(sorted(daily_commits)):
        date_obj = datetime.datetime.strptime(d, '%Y-%m-%d')
        hash = daily_commits[d][0]
        if not prev_date or abs((prev_date - date_obj).days) >= days:
            prev_date = date_obj
            hashes.append([hash, date_obj])          # choose the latest commit hash of that day
        else:
            if hash == lasthash:
                hashes.append([lasthash, date_obj])  # choose the last hash in clist anyway
    for i in range(len(hashes)):
        date_strs = [ "%s(%d-%.2d-%.2d)" % (hash[0], hash[1].year, hash[1].month, hash[1].day) for hash in hashes[i:] ]
        hash = hashes[i][0]
        for commit in clist:
            if commit[0] == hash: break
        print ("\n\ndaily (every %d days): %s" % (days, " ".join(date_strs)))
        result = run_commit(commit)
        g_results.append(result)
    
    print_summary(g_results, clist)
    return g_results

def everyn(clist, num_commits):
    """test commit every 'num_commits' num_commits

    Args:
        clist (list): the commit list: [ [hash, committer date, author name, desc], ...  ]
        num_commits (int): every n commits
    """
    global g_results

    # choosing commits
    indices = range(0, len(clist), num_commits)
    if indices[len(indices)-1] != len(clist) - 1:
        indices.append(len(clist) - 1)
    
    commits = []
    for idx in indices:
        commits.append(clist[idx])
    idx = 0
    for idx in range(len(commits)):
        commit = commits[idx]
        commit_hash_strs = [ "%s" % (c[0]) for c in commits[idx:] ]
        print ("\n\neveryn (every %d commits): %s" % (num_commits, " ".join(commit_hash_strs)))
        result = run_commit(commit)
        g_results.append(result)
    print_summary(g_results, clist)
    return g_results

def print_summary(results, clist):
    print ("\nSummary:")
    print ("-"*80)
    if not results:
        print ("no results.")
    for result in results:
        print ("commit: %s iops: %d" % (result[0], result[1]))
    max_iops     = None
    maxiops_hash = ""
    min_iops     = None
    miniops_hash = ""
    for i in range(len(results)):
        hash = results[i][0]
        iops = results[i][1]
        if max_iops is None: max_iops = iops
        if min_iops is None: min_iops = iops
        if iops >= max_iops:
            max_iops     = iops
            maxiops_hash = hash
        if iops <= min_iops:
            min_iops     = iops
            miniops_hash = hash
    max_commit, min_commit = None, None
    for c in clist:
        hash = c[0]
        if hash == maxiops_hash:
            max_commit = c
        if hash == miniops_hash:
            min_commit = c
    print ("\n")
    if max_iops:
        print ("maximum iops: %d commit: %s" % (max_iops, "|".join(max_commit)))
    if min_iops:
        print ("minimum iops: %d commit: %s" % (min_iops, "|".join(min_commit)))

def run_commit(commit):
    """run a single perf test on the given hash

    Args:
        commit (str): a git commit: [hash, committer date, author name, desc]
    """
    path_perfauto = "{0}/perfauto.py".format(os.path.dirname(os.path.realpath(__file__)))
    hash = commit[0]
    logpath = "{0}.{1}.out".format(hash, str(uuid.uuid1()))

    print ("-" * 80)
    sys.stdout.write ( "testing {0} log: {1}\n".format( "|".join(commit), logpath ) ); sys.stdout.flush()

    cmd   = "{0} -c {1} -u --ref={2} -p --fill 600 --fullmap --uioonly > {3} ".format(path_perfauto, g_conf_file, hash, logpath)
    iops  = None; path = None
    start = time.time()
    succ  = me.succ(cmd)
    dur   = time.time() - start
    if not succ:  # execution fail
        sys.stdout.write( "FAIL!! {0} log: {1}\nREALTIME: {2:.0f} seconds.\n".format( "|".join(commit), logpath, dur) )
    else:
        iops, iops_str, path = get_iops(logpath)
        sys.stdout.write( "IOPS: {2} ref: {0} log: {1}\nREALTIME: {3:.0f} seconds.\n".format( "|".join(commit), logpath, iops_str, dur) )
    if path and os.path.exists(path):
        me.exe("mv {0} {1}/".format(logpath, path))
    if iops:
        result = [ hash, iops ]
    else:   # can't get iops for this round, retry with the closest commits
        result = [ hash, 0 ]
    print ("-" * 80)
    print ("")
    
    return result

if __name__ == "__main__":
    if not handleopts(): exit(1)

    build_server = get_build_server()
    clist = get_clist(build_server)  # [ [hash, committer date, author name, desc], ...  ]
    clist = sorted(clist, key=lambda l: l[1], reverse=True)
    if not g_c2:    # no second commit specified, use top commit by default
        g_c2 = clist[0][0]
    # print ("="*40+"clist start (%d)" % (len(clist))+"="*40)
    # for c in clist:
    #     print (c)
    # print ("="*40+"clist end (%d)" % (len(clist))+"="*40)
    # print ("g_c1=%s, g_c2=%s" % (g_c1, g_c2))
    # find commit indices
    idx1, idx2 = -1, -1
    for i in range(len(clist)):
        hash = clist[i][0]
        if g_c1 == hash:
            idx1 = i
        if g_c2 == hash:
            idx2 = i
    # print ("idx1=%d, idx2=%d" % (idx1, idx2))
    if idx1 == -1 or idx2 == -1:
        print ("can not find '%s' or '%s' in git commit history!" % (g_c1, g_c2))
        exit(1)
    if idx1 > idx2:
        min, max = idx2, idx1
    else:
        min, max = idx1, idx2
    clist = clist[min:max+1]
    print ("="*40+" clist start (%d) " % (len(clist))+"="*40)
    for c in clist:
        print (c)
    print ("="*40+" clist end   (%d) " % (len(clist))+"="*40)
    # print ("min=%d, max=%d" % (min, max))
    # exit(1)

    if g_op == "bisect":
        print("Performing 'bisect' performance test.")
        bisect(clist, g_kiops * 1000, g_narrow, runlast=True) # [ [hash, iops], ... ]
        print_summary(g_results, clist)
        g_results.reverse()
        c1 = ""; c2 = ""
        for r in g_results:
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
    elif g_op == "daily":  # daily
        print("Performing 'daily' performance test at the last commits of every %d days. repeats: %d." % (g_narrow, g_repeats))
        for i in range(g_repeats):
            print ("ROUND %d" % i)
            daily(clist, g_narrow)
    elif g_op == "everyn":
        print("Performing 'every_%d_commits' performance test. repeats: %d." % (g_narrow, g_repeats))
        for i in range(g_repeats):
            print ("ROUND %d" % i)
            everyn(clist, g_narrow)
    else:
        usage("method '%s' is not supported." % (g_op))


