#!/usr/bin/python2.7

#import datetime
from base64 import b64encode
from cStringIO import StringIO
import fcntl
from hashlib import sha1
import hmac
import httplib
import json
import os
import pprint
import requests
import shutil
from subprocess import call, Popen
import sys
import tempfile
import time
import traceback
from urlparse import parse_qs

# for hook
gitHubSecret = "SANITISED"

# for API calls
gitHubUsername = "PyBitmessageDevOps"
gitHubToken = ""
branch = "v0.6"
lock = None

sys.exit()

os.chdir("/usr/src/PyBitmessage")
if os.environ.get("HOME") is None:
    os.environ["HOME"] = "/var/www"

def debug(obj):
    sys.stderr.write(pprint.pformat(obj) + "\n")

def verifyGitHubSignature (environ, payload_body):
    signature = 'sha1=' + hmac.new(gitHubSecret, payload_body, sha1).hexdigest()
    try:
        if signature != environ.get('HTTP_X_HUB_SIGNATURE'):
            return False
        return True
    except:
        return False

def verifyTransifexSignature (environ, payload_body):
    signature = b64encode(hmac.new(transifexSecret, payload_body, sha1).digest())
    try:
        debug(signature)
        if signature != environ.get('HTTP_X_TX_SIGNATURE'):
            return False
        return True
    except:
        return False

def returnMessage(status = False, message = "Unimplemented"):
    output = json.dumps({"status": "OK" if status else "FAIL", "message": message})
    return [output, [('Content-type', 'text/plain'),
        ('Content-Length', str(len(output)))
    ]]

def updateLocalTranslationSource():
    call(["git", "stash", "-q"])
    call(["git", "checkout", "-q", branch])
    call(["git", "pull", "-q"])
    call(["pylupdate4", "src/translations/bitmessage.pro"])

def uploadTranslationSource():
    headers = {"Authorization": "Basic " + b64encode(transifexUsername + ":" + transifexPassword)}
    response = requests.put("https://www.transifex.com/api/2/project/pybitmessage/resource/pybitmessage/content/",
        headers=headers, files={'bitmessage_en.ts': open("src/translations/bitmessage_en.ts", "rb")})
    return response

def updateLocalTranslationDestination(ts, lang):
    call(["git", "pull", "--all", "-q"])
    call(["git", "stash", "-q"])
    call(["git", "checkout", "-q", branch])
    call(["git", "checkout", "-q", "-b", "translate_" + lang + "_" + str(ts)])
    call(["git", "branch", "-q", "--set-upstream-to=origin/v0.6"])

def downloadTranslatedLanguage(ts, lang):
    headers = {"Authorization": "Basic " + b64encode(transifexUsername + ":" + transifexPassword)}
    resname = "pybitmessage_" + lang + ".ts"
    fname = "bitmessage_" + lang.lower() + ".ts"
    with open("src/translations/" + fname, "wt") as handle:
        response = requests.get("https://www.transifex.com/api/2/project/pybitmessage/resource/pybitmessage/translation/" + lang + "/",
            headers=headers)
        if response.ok:
            content = json.loads(response.content)["content"]
            handle.write(content.encode("utf-8"))
#        print "Response from github for pull request: %i, %s" % (response.status_code, response.content)
    return response

def commitTranslatedLanguage(ts, lang):
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
    response = requests.post("https://api.github.com/repos/Bitmessage/PyBitmessage/pulls",
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

def deleteBranch(ts, lang):
    newbranch = "translate_" + lang + "_" + str(ts)
    call(["git", "branch", "-q", "-D", newbranch])
    # TODO: delete remote branch

def lockWait():
    global lockFile, lock
    lock = open(lockFile, "wb")
    fcntl.lockf(lock, fcntl.LOCK_EX)

def unlock():
    global lockFile, lock
    fcntl.lockf(lock, fcntl.LOCK_UN)
    if os.path.isfile(lockFile):
        os.unlink(lockFile)

def application(environ, start_response):
    status = '200 OK'
    output = ''

    lockWait()
    length = int(environ.get('CONTENT_LENGTH', '0'))
    body = environ['wsgi.input'].read(length)
#   h environ['wsgi.input'] = body

    if environ.get("HTTP_X_GITHUB_EVENT") == "ping":
        if not verifyGitHubSignature(environ, body):
            output, responseHeaders = returnMessage(False, "Checksum bad")
            start_response(status, responseHeaders)
            unlock()
            return [output]
        output, responseHeaders = returnMessage(True, "Test OK")
    elif environ.get("HTTP_X_GITHUB_EVENT") == "push":
        if not verifyGitHubSignature(environ, body):
            output, responseHeaders = returnMessage(False, "Checksum bad")
            start_response(status, responseHeaders)
            unlock()
            return [output]
        try:
            payload = json.loads(body)
            if payload['ref'] != "refs/heads/" + branch:
                unlock()
                raise Exception
            updateLocalTranslationSource()
            response = uploadTranslationSource()
            output, responseHeaders = returnMessage(True, "Processed: %i, %s:" % (response.status_code, response.content))
        except:
            output, responseHeaders = returnMessage(True, "Not processing")
    elif "Transifex" in environ.get("HTTP_USER_AGENT"):
#        debug(environ)
#        debug(body)
        if not verifyTransifexSignature(environ, body):
            debug ("Verify Transifex Signature fail, but fuck them")
        else:
            debug ("Verify Transifex Signature ok")
#            output, responseHeaders = returnMessage(False, "Checksum bad")
#            start_response(status, responseHeaders)
#            unlock()
#            return [output]
        try:
#            debug(body)
            payload = parse_qs(body)
#            debug(payload)
            if 'pybitmessage' in payload['project'] and 'pybitmessage' in payload['resource']:
                if 'translated' in payload and '100' in payload['translated']:
                    ts = int(time.time())
                    updateLocalTranslationDestination(ts, payload['language'][0].lower())
                    downloadTranslatedLanguage(ts, payload['language'][0])
                    response = commitTranslatedLanguage(ts, payload['language'][0].lower())
                    if response.ok:
                        output, responseHeaders = returnMessage(True, "Processed.")
                    else:
                        output, responseHeaders = returnMessage(False, "Error: %i." % (response.status_code))
                else:
                    output, responseHeaders = returnMessage(False, "Nothing to do")
            else:
                output, responseHeaders = returnMessage(False, "Nothing to do")
        except:
            output, responseHeaders = returnMessage(True, "Not processing")
    else:
        debug("Unknown command %s" % (environ.get("HTTP_X_GITHUB_EVENT")))
        output, responseHeaders = returnMessage(True, "Unknown command, ignoring")
#    output = ''
#    for k, v in environ.items():
#        output += '%.40s %s\n' % (k, v)
    #responseHeaders = sendFile("ffb8c8eb-3d3b-4306-b65e-e0d1fa4f7ea0")
    start_response(status, responseHeaders)
    unlock()
    return [output]

if __name__ == "__main__":
    lockWait()
    if len(sys.argv) < 2:
        unlock()
        sys.exit()
    if sys.argv[1] == "commit":
        updateLocalTranslationSource(tempdir)
        response = uploadTranslationSource(tempdir)
        print "Uploaded to transifex: %i, %s" % (response.status_code, response.content)
    elif sys.argv[1] == "translated":
        if len(sys.argv) < 3:
            unlock()
            sys.exit()
        lang = sys.argv[2]
        print "Cloning repo"
        ts = int(time.time())
        updateLocalTranslationDestination(ts, lang.lower())
        print "Downloading translated file"
        downloadTranslatedLanguage(ts, lang)
        print "Creating pull request"
        response = commitTranslatedLanguage(ts, lang.lower())
        print "Pull request sent"
    elif sys.argv[1] == "rebase":
        for pull in listPullRequests():
            rebasePullRequest(pull['branch'])
            print "Rebased %s" % (pull['number'])
            break
    unlock()
