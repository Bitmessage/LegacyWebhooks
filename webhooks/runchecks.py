#!/usr/bin/python2.7

import fcntl
import os
from shutil import rmtree
import sqlite3
import sys

try:
    lockfile = open('/tmp/runchecks.lock', 'a')
    fcntl.lockf(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    #print "runchecks locked, exiting"
    sys.exit()

mypath = 'var/www/webhooks'
if mypath not in sys.path:
    sys.path.append(mypath)

import lib.checks
import lib.diff
import lib.gapi
import lib.git

def handle_exception(exc_type, exc_value, exc_traceback):
    cursor.execute("UPDATE checks SET state = 'queued' WHERE id = ?", [check_id])
    connection.commit()
    pass

def file_list():
    queue = []
    for root, dirs, files in os.walk('.'):
        root = root[2:]
        if root == '.git':
            continue
        for f in files:
            if root:
                f = os.path.join(root, f)
            queue.append(f)
    return queue

connection = sqlite3.connect('/var/lib/webhooks/webhooks.sqlite', timeout=600)
cursor = connection.cursor()

checks = list(cursor.execute("SELECT id, repo_id, pull, head_sha, github_id, type FROM checks WHERE state = 'queued'"))

for check in checks:
    check_id, repo_id, pr, head_sha, github_id, check_type = check
    result = list(cursor.execute("SELECT full_name, installation_id FROM repos WHERE id = ?", [repo_id]))
    if not result:
        cursor.execute("UPDATE checks SET state = 'unregistered' WHERE id = ?", [check_id])
        connection.commit()
        continue
    for r in result:
        full_name, installation_id = r
        lib.gapi.installationID = installation_id
    try:
        pullinfo = lib.gapi.gitHubGet('repos/{}/pulls/{}'.format(full_name, pr))
    except BaseException:
        continue
    if not head_sha:
        head_sha = pullinfo['head']['sha']
    github_id = lib.gapi.gitHubSetCheck(check_id, full_name, head_sha, github_id, 'in_progress')
    cursor.execute("UPDATE checks SET state = 'pending', github_id = ?, head_sha= ? WHERE id = ?", [github_id, head_sha, check_id])
    connection.commit()
    td = lib.git.cloneRepo(full_name)
    base_branch, base_sha = pullinfo['base']['ref'], pullinfo['base']['sha']
    diff = pullinfo['diff_url']
    diff_content = lib.diff.diff_content(diff)
    diff_lines = lib.diff.diff_lines(diff_content)
    renames = lib.diff.renames(diff_content)
    lib.git.checkoutBase(full_name, base_branch, base_sha)
    old_annotations = lib.checks.check(check_type, file_list(), renames)
    lib.git.checkoutPR(full_name, pr)
    new_annotations = lib.checks.check(check_type, file_list())
    new_annotations.set_diff(diff_lines)
    conclusion, summary, annotations = lib.checks.compareAnnotations(old_annotations, new_annotations, check_type)
    print "PR {}/{}: {}".format(pr, check_type, summary)
    lib.gapi.gitHubSetCheck(check_id, full_name, head_sha,
                            github_id, status='in_progress',
                            check_type=check_type,
                            annotations=lib.checks.annotationsMutate(annotations))
    lib.gapi.gitHubSetCheck(check_id, full_name, head_sha,
                            github_id, 'completed',
                            check_type=check_type,
                            conclusion='success' if len(annotations) == 0 else 'failure',
                                summary=summary)
    os.chdir("/var/www")
    #import pprint
    #sys.stderr.write(pprint.pformat(annotations) + "\n")
    rmtree(td)
    cursor.execute("UPDATE checks SET state = 'completed' WHERE id = ?", [check_id])
    connection.commit()
    lib.gapi.installationID = None
    lib.gapi.gitHubAuthToken = None

connection.close()
