import os
import requests
from subprocess import call
import tempfile

def cloneRepo(reponame):
    td = tempfile.mkdtemp()
    with open(os.devnull, 'wb') as fnull:
        call(['git', 'clone', 'https://github.com/{}'.format(reponame), td], stdout=fnull, stderr=fnull)
    os.chdir(td)
    return td

def checkoutPR(reponame, pr):
    with open(os.devnull, 'wb') as fnull:
        call(['git', 'fetch', 'origin', 'pull/{}/head:pr-{}'.format(pr, pr)], stdout=fnull, stderr=fnull)
        call(['git', 'checkout', 'pr-{}'.format(pr)], stdout=fnull, stderr=fnull)

def checkoutBase(reponame, base_branch, base_sha):
    with open(os.devnull, 'wb') as fnull:
        call(['git', 'fetch', 'origin', base_branch], stdout=fnull, stderr=fnull)
        call(['git', 'checkout', base_branch], stdout=fnull, stderr=fnull)
        call(['git', 'reset', '--hard', base_sha], stdout=fnull, stderr=fnull)

def updateLocalTranslationSource():
    return
    call(["git", "stash", "-q"])
    call(["git", "checkout", "-q", branch])
    call(["git", "pull", "-q"])
    call(["pylupdate4", "src/translations/bitmessage.pro"])

def updateLocalTranslationDestination(ts, lang):
    return
    call(["git", "pull", "--all", "-q"])
    call(["git", "stash", "-q"])
    call(["git", "checkout", "-q", branch])
    call(["git", "checkout", "-q", "-b", "translate_" + lang + "_" + str(ts)])
    call(["git", "branch", "-q", "--set-upstream-to=origin/v0.6"])

def commitTranslatedLanguage(ts, lang):
    return
    call(["lrelease-qt4", "src/translations/bitmessage.pro"])
    call(["git", "add", "src/translations/bitmessage_" + lang + ".ts", "src/translations/bitmessage_" + lang + ".qm"])
    call(["git", "commit", "-q", "-S", "-m", "Auto-updated language %s from transifex" % (lang)])
    newbranch = "translate_" + lang + "_" + str(ts)
    call(["git", "push", "-q", "translations", newbranch + ":" + newbranch])
    request = {
        "title": "Translation update " + lang,
        "body": "Auto-updated from transifex",
        "head": "PyBitmessageTranslations:" + newbranch,
        "base": branch
    }
    headers = {"Authorization": "token " + gitHubToken}
    response = requests.post("repos/Bitmessage/PyBitmessage/pulls",
        headers=headers, data=json.dumps(request))
    # TODO: save pull request number
    return response
#    print "JSON dumps request: %s" % (json.dumps(request))
#    print "Response from github for pull request: %i, %s" % (response.status_code, response.content)

def listPullRequests():
    headers = {"Authorization": "token " + gitHubToken}
    response = requests.get("https://api.github.com/repos/Bitmessage/PyBitmessage/pulls?state=open&base=%s&sort=created&direction=desc" % branch,
        headers=headers)
    pulls = []
    if response.ok:
        try:
            data = json.loads(response.content)
            for i in data:
                if i['user']['login'] != gitHubUsername:
                    continue
                if not i['head']['label'].startswith(gitHubUsername):
                    continue
#                print i['number'], i['title'], i['user']['login'], i['head']['label'], i['head']['ref']
                pulls.append({'number': i['number'], 'branch': i['head']['ref']})
        except:
            print "Exception"
            traceback.print_exc()
            pass
    else:
        print "Not ok"
    return pulls
#    print "JSON dumps request: %s" % (json.dumps(request))
#    print "Response from github for pull request: %i, %s" % (response.status_code, response.content)

def rebasePullRequest(newbranch):
#    newbranch = "translate_" + lang + "_" + str(ts)
    return
    call(["git", "pull", "--all", "-q"])
    call(["git", "stash", "-q"])
    call(["git", "checkout", "-q", newbranch])
    call(["git", "branch", "-q", "--set-upstream-to=origin/v0.6"])
    call(["git", "rebase", "-q"])
    call(["git", "commit", "-q", "--no-edit", "--amend", "-S"])
    call(["git", "push", "-q", "-f", "translations", newbranch + ":" + newbranch])
    call(["git", "checkout", "-q", branch])

def checkIfPullRequestMerged(ts, lang):
#    Get if a pull request has been merged
#    GET /repos/:owner/:repo/pulls/:number/merge
#    Response if pull request has been merged
#    Status: 204 No Content
#    Response if pull request has not been merged
#    Status: 404 Not Found
    return


