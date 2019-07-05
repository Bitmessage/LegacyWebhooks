import re
import requests

REGEXDIFF1 = re.compile('^diff ')
REGEXDIFF2 = re.compile('^--- a/(.+)$')
REGEXDIFF3 = re.compile('^\+\+\+ b/(.+)$')
REGEXDIFF4 = re.compile('^\@\@ -(\d+),(\d+) \+(\d+),(\d+)')
REGEXDIFF5 = re.compile('^rename from (.+)$')
REGEXDIFF6 = re.compile('^rename to (.+)$')

def diff_content(url):
    response = requests.get(url)
    if not response.ok:
        return None
    return response.content

def diff_lines(content):
    retval = {}
    fname = None
    for line in content.splitlines():
        x = re.match(REGEXDIFF2, line)
        if x:
            fname = x.group(1)
            if fname not in retval:
                retval[fname] = []
            continue
        x = re.match(REGEXDIFF3, line)
        if x:
            fname = x.group(1)
            if fname not in retval:
                retval[fname] = []
            continue
        x = re.match(REGEXDIFF4, line)
        if x:
            f, l = x.group(3, 4)
            f = int(f)
            l = int(l)
            t = f + l - 1
            retval[fname].append([f, t])
    return retval

def renames(content):
    retval = {}
    renameFrom = None
    for line in content.splitlines():
        x = re.match(REGEXDIFF5, line)
        if x:
            renameFrom = x.group(1)
            continue
        x = re.match(REGEXDIFF6, line)
        if x:
            retval[renameFrom] = x.group(1)
            continue
    return retval

if __name__ == '__main__':
    import pprint
    pprint.pprint(diff_lines('https://github.com/Bitmessage/PyBitmessage/pull/1346.diff'))
