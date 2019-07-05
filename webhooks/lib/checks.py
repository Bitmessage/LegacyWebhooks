import copy
import re
import subprocess

JOBS=4
REGEXPYLINT = re.compile('^([^:]+):([0-9]+): \[([A-Z][0-9]+)\(([a-z0-9-]+)\), ([^ ]+)\] (.+)$')
REGEXPYCODESTYLE = re.compile('^([^:]+):([0-9]+):[0-9]+: ([A-Z][0-9]+) (.+)$')
REGEXFLAKE8 = re.compile('^([^:]+):([0-9]+):[0-9]+: ([A-Z][0-9]+) (.+)$')

class Annotations(object):
    error_cleaner = [
                [re.compile('^(.*) \(\d+/\d+\)$'), r'\1'],
                [re.compile('^(.*) \(line \d+\)$'), r'\1']
            ]

    def __init__(self, renames=None):
        self._data = {}
        self._diff = {}
        self._renames = renames if renames else {}

    def __len__(self):
        c = 0
        for v1 in self._data.values():
            for v2 in v1.values():
                c += len(v2)
        return c

    @staticmethod
    def _clean_error(error):
        retval = error
        for i in Annotations.error_cleaner:
            retval = re.sub(i[0], i[1], retval)
        return retval

    @staticmethod
    def _compare_diff(a, b):
        if a['in_diff'] != b['in_diff']:
            return a['in_diff'] - b['in_diff']
        return a['line'] - b['line']

    def __setitem__(self, key, value):
        if key['fname'] in self._renames:
            key['fname'] = self._renames[key['fname']]
        if key['fname'] not in self._data:
            self._data[key['fname']] = {}
        error = Annotations._clean_error(key['error'])
        if error not in self._data[key['fname']]:
            self._data[key['fname']][error] = []
        key['in_diff'] = False
        self._data[key['fname']][error].append(key)

    def __getitem__(self, key):
        if key['fname'] not in self._data:
            raise KeyError
        error = Annotations._clean_error(key['error'])
        if error not in self._data[key['fname']]:
            raise KeyError
        for v in self._data[key['fname']][error]:
            if key['line'] == v['line']:
                return v
        raise IndexError

    def __delitem__(self, key):
        if key['fname'] not in self._data:
            raise KeyError
        error = Annotations._clean_error(key['error'])
        if error not in self._data[key['fname']]:
            raise KeyError
        for v in self._data[key['fname']][error]:
            #if key['line'] == v['line']:
            # first item
            break
        else:
            raise IndexError
        self._data[key['fname']][error].remove(v)

    def __contains__(self, key):
        if key['fname'] not in self._data:
            return False
        error = Annotations._clean_error(key['error'])
        if error not in self._data[key['fname']]:
            return False
        # at least one record left
        if not self._data[key['fname']][error]:
            return False
        return True

    def __iter__(self):
        return AnnotationsIterator(copy.deepcopy(self._data))

    def set_diff(self, diff):
        for f, lines in diff.iteritems():
            if not f in self._data:
                continue
            for e in self._data[f]:
                for l1 in range(0, len(self._data[f][e])):
                    l2 = self._data[f][e][l1]['line']
                    for line in lines:
                        if l2 >= line[0] and l2 <= line[1]:
                            self._data[f][e][l1]['in_diff'] = True
                self._data[f][e].sort(cmp=Annotations._compare_diff)


class AnnotationsIterator(object):
    def __init__(self, annotations):
        self._annotations = annotations
        self._fname = None
        self._fname_iter = 0
        self._message = None
        self._message_iter = 0
        self._internal_iter = -1
        self._fnames = []
        self._messages = []

    def __iter__(self):
        return self

    def _iter_fname(self):
        self._fname = None
        while not self._fname:
            if not self._fnames:
                self._fnames = self._annotations.keys()
                self._fname_iter = 0
            if len(self._fnames) > self._fname_iter:
                self._fname = self._fnames[self._fname_iter]
                self._fname_iter += 1
            else:
                raise StopIteration

    def _iter_message(self):
        self._message = None
        while not self._message:
            if not self._messages:
                try:
                    self._messages = self._annotations[self._fname].keys()
                except KeyError:
                    self._iter_fname()
                    continue
                self._message_iter = 0
            if len(self._messages) > self._message_iter:
                self._message = self._messages[self._message_iter]
                self._message_iter += 1
            else:
                self._messages = []
                self._iter_fname()

    def _iter_record(self):
        record = None
        while not record:
            if self._internal_iter == -1:
                try:
                    self._annotations[self._fname][self._message]
                except KeyError:
                    self._iter_message()
                    continue
                self._internal_iter = 0
            self._internal_iter += 1
            try:
                return self._annotations[self._fname][self._message][self._internal_iter - 1]
            except IndexError:
                self._internal_iter = -1
                self._iter_message()

    def next(self):
        return self._iter_record()


def annotationsMutate(annotations):
    retval = []
    for v in annotations:
        if 'codeword' in v:
            title = '{} / {}'.format(v['codenum'], v['codeword'])
        else:
            title = v['codenum']
        retval.append({'path': v['fname'],
                       'annotation_level': v['level'],
                       'start_line': v['line'],
                       'end_line': v['line'],
                       'title': title,
                       'message': v['error']
                      }
                     )
    return retval

def compareAnnotations(old, new, check_type='pylint'):
    remaining = 0
    for a in new:
        if a in old:
            del old[a]
            del new[a]
            remaining += 1

    summary = '{} check complete: {} fixed, {} new, {} remaining'.format(check_type, len(old), len(new), remaining)

    return 'failure' if len(new) > 0 else 'success', summary, new

def checkPyLint(fnames, renames=None):
    retval = Annotations(renames)
    try:
        cmd = ['firejail',
               '--net=none',
               '--overlay-tmpfs',
               'pylint',
               '--rcfile=setup.cfg',
               '--persistent=n',
               '--output-format=parseable',
               '--jobs={}'.format(JOBS),
               '--reports=n']
        # filter only .py files
        cmd.extend([x for x in fnames if x[-3:] == '.py'])
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        for line in e.output.splitlines():
            if line == "":
                break
            if chr(7) in line:
                _, line = line.split(chr(7))
            x = re.match(REGEXPYLINT, line)
            if not x:
                continue
            fname, line, codenum, codeword, function, error = x.group(1, 2, 3, 4, 5, 6)
            if codenum[0] == 'W':
                annotation_level = 'warning'
            elif codenum[0] == 'E':
                annotation_level = 'failure'
            else:
                annotation_level = 'notice'
            retval[{
                    'fname': fname,
                    'level': annotation_level,
                    'line': int(line),
                    'codenum': codenum,
                    'codeword': codeword,
                    'error': error,
                    'function': function
                   }
                  ] = True
    return retval

def checkPyCodestyle(fnames, renames=None):
    retval = Annotations(renames)
    try:
        cmd = ['firejail',
               '--net=none',
               '--overlay-tmpfs',
               'python', '-m', 'pycodestyle',
               '--config=setup.cfg']
        # filter only .py files
        cmd.extend([x for x in fnames if x[-3:] == '.py'])
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        for line in e.output.splitlines():
            if line == "":
                break
            if chr(7) in line:
                _, line = line.split(chr(7))
            x = re.match(REGEXPYCODESTYLE, line)
            if not x:
                continue
            fname, line, codenum, error = x.group(1, 2, 3, 4)
            if codenum[0] == 'W':
                annotation_level = 'warning'
            elif codenum[0] == 'E':
                annotation_level = 'failure'
            else:
                annotation_level = 'notice'
            if fname == 'src/bitmessagemain.py' and codenum == 'E402':
                continue
            retval[{
                    'fname': fname,
                    'level': annotation_level,
                    'line': int(line),
                    'codenum': codenum,
                    'error': error,
                   }
                  ] = True
    return retval

def checkFlake8(fnames, renames=None):
    retval = Annotations(renames)
    try:
        cmd = ['firejail',
               '--net=none',
               '--overlay-tmpfs',
               'python', '-m', 'flake8',
               '--config=setup.cfg']
        # filter only .py files
        cmd.extend([x for x in fnames if x[-3:] == '.py'])
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        for line in e.output.splitlines():
            if line == "":
                break
            if chr(7) in line:
                _, line = line.split(chr(7))
            x = re.match(REGEXFLAKE8, line)
            if not x:
                continue
            fname, line, codenum, error = x.group(1, 2, 3, 4)
            if codenum[0] == 'W':
                annotation_level = 'warning'
            elif codenum[0] == 'E':
                annotation_level = 'failure'
            else:
                annotation_level = 'notice'
            if fname == 'src/bitmessagemain.py' and codenum == 'E402':
                continue
            retval[{
                    'fname': fname,
                    'level': annotation_level,
                    'line': int(line),
                    'codenum': codenum,
                    'error': error,
                   }
                  ] = True
    return retval

def check(check_type='pylint', fnames=[], renames=None):
    if check_type == 'pylint':
        return checkPyLint(fnames, renames)
    elif check_type == 'pycodestyle':
         return checkPyCodestyle(fnames, renames)
    elif check_type == 'flake8':
        return checkFlake8(fnames, renames)
    else:
        return Annotations()
