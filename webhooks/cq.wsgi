#!/usr/bin/python2.7

#import datetime
from base64 import b64encode
import ConfigParser
from cStringIO import StringIO
import fcntl
import httplib
import json
import os
import pprint
import shutil
import sqlite3
import sys
import traceback
from urlparse import parse_qs

mypath = 'var/www/webhooks'
if mypath not in sys.path:
    sys.path.append(mypath)

import lib.config
import lib.gapi

default_checks = ['pylint', 'pycodestyle', 'flake8']

if os.environ.get("HOME") is None:
    os.environ["HOME"] = "/var/www"

def debug(obj):
    sys.stderr.write(pprint.pformat(obj) + "\n")

def application(environ, start_response):
    connection = sqlite3.connect('/var/lib/webhooks/webhooks.sqlite')
    cursor = connection.cursor()
    status = '200 OK'
    output = ''

    length = int(environ.get('CONTENT_LENGTH', '0'))
    body = environ['wsgi.input'].read(length)
#   h environ['wsgi.input'] = body
    if 'HTTP_X_GITHUB_EVENT' not in environ:
        params = parse_qs(environ.get('QUERY_STRING'))
        if params.get('state') and params.get('code'):
            # registration callback
            output, responseHeaders = lib.gapi.returnRegistrationCallback(cursor, params.get('state')[0], params.get('code')[0])
        else:
            # registration form
            output, responseHeaders = lib.gapi.returnRegister(cursor)
            connection.commit()
            #output, responseHeaders = returnMessage(False, "Not a github request")
        start_response(status, responseHeaders)
        connection.commit()
        connection.close()
        return [output]
    else:
        if not lib.gapi.verifyGitHubSignature(environ, body):
            output, responseHeaders = lib.gapi.returnMessage(False, "Checksum bad")
            start_response(status, responseHeaders)
            return [output]
    request = json.loads(body)
    if environ.get("HTTP_X_GITHUB_EVENT") == "ping":
        output, responseHeaders = lib.gapi.returnMessage(True, "Test OK")
    elif environ.get("HTTP_X_GITHUB_EVENT") == "push":
        output, responseHeaders = lib.gapi.returnMessage(True, "Ignoring push")
    elif environ.get("HTTP_X_GITHUB_EVENT") == "pull_request":
        repo_id = request['repository']['id']
        pr = request['pull_request']['number']
        head_sha = request['pull_request']['head']['sha']
        localdata = list(cursor.execute('SELECT full_name, installation_id FROM repos WHERE id = ?', [repo_id]))
        for entry in localdata:
            if request['action'] not in ['opened', 'synchronize']:
                continue
            repo_name, installation_id = entry
            lib.gapi.installationID = installation_id
            for check_type in default_checks:
                cursor.execute('INSERT INTO checks (repo_id, pull, state, head_sha, type) VALUES (?, ?, ?, ?, ?)', [repo_id, pr, 'queued', head_sha, check_type])
                connection.commit()
                #rowid = cursor.lastrowid
                #github_id = lib.gapi.gitHubSetCheck(rowid, repo_name, head_sha, status='queued', check_type=check_type)
                #cursor.execute('UPDATE checks SET github_id = ? WHERE id = ?', [github_id, rowid])
                #connection.commit()
            break
        output, responseHeaders = lib.gapi.returnMessage(True, "Processed pull_request")
    elif environ.get("HTTP_X_GITHUB_EVENT") == "check_suite":
        repo_id = request['repository']['id']
        head_sha = request['check_suite']['head_sha']
        localdata = list(cursor.execute('SELECT full_name, installation_id FROM repos WHERE id = ?', [repo_id]))
        for entry in localdata:
            if request['action'] not in ['requested', 'rerequested']:
                continue
            repo_name, installation_id = entry
            lib.gapi.installationID = installation_id
            prs = list(cursor.execute('SELECT DISTINCT pull FROM checks WHERE head_sha = ?', [head_sha]))
            debug("head_sha: {}".format(head_sha))
            for line in prs:
                pr, = line
                debug("pr")
                debug(pr)
                for check_type in default_checks:
                    cursor.execute('INSERT INTO checks (repo_id, pull, state, head_sha, type) VALUES (?, ?, ?, ?, ?)', [repo_id, pr, 'queued', head_sha, check_type])
                    rowid = cursor.lastrowid
                    github_id = lib.gapi.gitHubSetCheck(rowid, repo_name, head_sha, status='queued', check_type=check_type)
                    cursor.execute('UPDATE checks SET github_id = ? WHERE id = ?', [github_id, rowid])
                    connection.commit()
            debug("B")
            break
        output, responseHeaders = lib.gapi.returnMessage(True, 'Processed check_suite')
    elif environ.get("HTTP_X_GITHUB_EVENT") == "integration_installation":
        output, responseHeaders = lib.gapi.returnMessage(True, "Ignoring integration_installation")
    elif environ.get("HTTP_X_GITHUB_EVENT") == "installation":
        if request['action'] == 'created':
            installation_id = request['installation']['id']
            app_id = request['installation']['app_id']
            cursor.execute('INSERT INTO installations (id, app_id) '
                           'VALUES(?, ?)', [installation_id, app_id])
            connection.commit()
            for repo in request['repositories']:
                repo_id = repo['id']
                full_name = repo['full_name']
                if full_name [-12:] == "PyBitmessage":
                    cursor.execute("INSERT INTO repos (id, full_name, installation_id) VALUES(?, ?, ?)",
                        [repo_id, full_name, installation_id])
                    connection.commit()
        elif request['action'] == 'deleted':
            installation_id = request['installation']['id']
            cursor.execute('DELETE FROM repos WHERE installation_id = ?',
                    [installation_id])
            cursor.execute('DELETE FROM installations WHERE id = ?',
                    [installation_id])
            connection.commit()
        output, responseHeaders = lib.gapi.returnMessage(True, 'Installation {}'.format(request['action']))
    elif environ.get("HTTP_X_GITHUB_EVENT") == "check_run":
        try:
            payload = json.loads(body)
            if payload['action'] == "rerequested":
                github_id = payload['check_run']['id']
                head_sha = payload['check_run']['head_sha']
                check_id = payload['check_run']['external_id']
                installation_id = payload['installation']['id']
                full_name = payload['repository']['full_name']
                lib.gapi.installationID = installation_id
                localdata = list(cursor.execute('SELECT repo_id, pull, head_sha, type FROM checks WHERE github_id = ?', [github_id]))
                for entry in localdata:
                    repo_id, pr, head_sha, check_type = entry
                if not repo_id:
                    raise BaseException
                cursor.execute('INSERT INTO checks (repo_id, pull, state, github_id, head_sha, type) VALUES (?, ?, ?, ?, ?, ?)', [repo_id, pr, 'queued', github_id, head_sha, check_type])
                connection.commit()
                check_id = cursor.lastrowid
                new_github_id = lib.gapi.gitHubSetCheck(check_id, full_name, head_sha, status='queued')
                cursor.execute('UPDATE checks SET github_id = ? WHERE id = ?', [new_github_id, check_id])
                connection.commit()
                output, responseHeaders = lib.gapi.returnMessage(True, "Requeued check {} as {}".format(github_id, new_github_id))
            else:
                raise BaseException
        except:
            output, responseHeaders = lib.gapi.returnMessage(False, "Not found")
    else:
        debug("Unknown command %s" % (environ.get("HTTP_X_GITHUB_EVENT")))
        output, responseHeaders = lib.gapi.returnMessage(False, "Unknown command, ignoring")
#    output = ''
#    for k, v in environ.items():
#        output += '%.40s %s\n' % (k, v)
    #responseHeaders = sendFile("ffb8c8eb-3d3b-4306-b65e-e0d1fa4f7ea0")
    start_response(status, responseHeaders)
    connection.commit()
    connection.close()
    return [output]
