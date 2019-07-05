from hashlib import sha1
import hmac
import json
import jwt
from random import choice
import requests
from string import ascii_lowercase
import sys
import time

import lib.config

# GitHub APP
private_key = open(lib.config.c.get('cq', 'privkey')).read()
gitHubSecret = lib.config.c.get('cq', 'githubsecret')
gitHubAppID = lib.config.c.getint('cq', 'appid')

gitHubAuthToken = None
gitHubAuthTokenExpiration = 0
installationID = None

def randString():
    return ''.join(choice(ascii_lowercase) for i in range(64))

def ISO8601Time():
    zone = time.strftime('%z')
    zone = '{}:{}'.format(zone[:3], zone[3:])
    return time.strftime("%Y-%m-%dT%H:%M:%S") + zone

def verifyGitHubSignature (environ, payload_body):
    signature = 'sha1=' + hmac.new(gitHubSecret, payload_body, sha1).hexdigest()
    try:
        if signature != environ.get('HTTP_X_HUB_SIGNATURE'):
            return False
        return True
    except:
        return False

def returnMessage(status = False, message = "Unimplemented"):
    output = json.dumps({"status": "OK" if status else "FAIL", "message": message})
    return [output, [('Content-type', 'text/plain'),
        ('Content-Length', str(len(output)))
    ]]

def returnRegister(cursor):
    output = u""
    state = randString()
    cursor.execute("INSERT INTO oauth_pending(state) VALUES(?)", [state])
    with open('/var/www/html/register.html') as f:
        output = f.read().format(gitHubClientID, state)
    return [output, [('Content-type', 'text/html'),
        ('Content-Length', str(len(output)))
    ]]

def returnRegistrationCallback(cursor, state, code):
    output = u""
    cursor.execute("DELETE FROM oauth_pending WHERE state = ?", [state])
    if not cursor.rowcount:
        # no such state
        output = 'Naughty'
    else:
        payload = {'client_id': gitHubClientID,
                   'client_secret': gitHubClientSecret,
                   'code': code,
                   'state': state}
        headers = {'Content-Type': 'application/json',
                   'Accept': 'application/json'}
        response = requests.post("https://github.com/login/oauth/access_token",
                                headers=headers, data=json.dumps(payload))
        token = json.loads(response.content)['access_token']
        cursor.execute("INSERT INTO oauth(code, state, access_token) VALUES(?, ?, ?)", [code, state, token])
        output = 'OK'
    return [output, [('Content-type', 'text/plain'),
        ('Content-Length', str(len(output)))
    ]]

def getJWT():
    payload = {'iat': int(time.time()),
               'exp': int(time.time()) + 600,
               'iss': gitHubAppID}
    return jwt.encode(payload, private_key, algorithm='RS256')

def getHeaders():
    if gitHubAuthToken:
        return {'Authorization': 'token {}'.format(gitHubAuthToken),
                'Accept': 'application/vnd.github.antiope-preview+json'}
    else:
        return {'Authorization': 'Bearer {}'.format(getJWT()),
                'Accept': 'application/vnd.github.machine-man-preview+json'}

def gitHubAuth():
    global gitHubAuthToken, gitHubAuthTokenExpires
    if gitHubAuthToken and gitHubAuthTokenExpires > time.time():
        return
    gitHubAuthToken = None
    gitHubAuthTokenExpires = time.time()
    response = requests.post('https://api.github.com/app/installations/{}/access_tokens'.format(installationID), headers=getHeaders(), data="")
    if response.ok:
        try:
            data = json.loads(response.content)
            gitHubAuthToken = data['token']
        except:
            raise BaseException("json problem")
    else:
        raise BaseException("response error: {}".format(response.content))

def gitHubPost(url, payload):
    gitHubAuth()
    response = requests.post('https://api.github.com/{}'.format(url), headers=getHeaders(), data=json.dumps(payload))
    if response.ok:
        try:
            data = json.loads(response.content)
        except:
            pass
    else:
        raise BaseException("response error: {}".format(response.content))
    return data

def gitHubPatch(url, payload):
    gitHubAuth()
    response = requests.patch('https://api.github.com/{}'.format(url), headers=getHeaders(), data=json.dumps(payload))
    if response.ok:
        try:
            data = json.loads(response.content)
        except:
            pass
    else:
        raise BaseException("response error: {}".format(response.content))
    return data
    
def gitHubGet(url):
    gitHubAuth()
    response = requests.get('https://api.github.com/{}'.format(url), headers=getHeaders())
    if response.ok:
        try:
            data = json.loads(response.content)
        except:
            pass
    else:
        raise BaseException(response.content)
    return data

def gitHubSetCheck(check_id, repo_name, head_sha, github_id=None, status='queued', annotations=None, conclusion=None, summary=None, check_type='pylint'):
    payload = {'name': 'Code Quality - {}'.format(check_type),
               'head_sha': str(head_sha),
               'external_id': str(check_id),
               'status': status
              }
    if status == 'in_progress':
        payload['output'] = {'title': 'Code quality check running',
                             'summary': summary if summary else 'Check in progress'}
        #payload['started_at'] = ISO8601Time()
    elif status == 'completed':
        payload['completed_at'] = ISO8601Time()
        payload['output'] = {'title': 'Code quality check completed',
                             'summary': summary if summary else 'Check completed'}
        if conclusion:
            payload['conclusion'] = conclusion
        elif annotations:
            payload['conclusion'] = 'failure'
        else:
            payload['conclusion'] = 'success'
    if github_id:
        if annotations:
            chunk = []
            for a in annotations:
                chunk.append(a)
                if len(chunk) == 50:
                    payload['output']['annotations'] = chunk
                    result = gitHubPatch('repos/{}/check-runs/{}'.format(repo_name, github_id), payload)
                    chunk = []
            if chunk:
                payload['output']['annotations'] = chunk
                result = gitHubPatch('repos/{}/check-runs/{}'.format(repo_name, github_id), payload)
        else:
            result = gitHubPatch('repos/{}/check-runs/{}'.format(repo_name, github_id), payload)
    else:
        result = gitHubPost('repos/{}/check-runs'.format(repo_name), payload)
    return result['id']
