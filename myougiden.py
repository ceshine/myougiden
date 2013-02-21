import errno
import sys
import os
import re
import sqlite3 as sql
from termcolor import *
from glob import glob

DBVERSION = '5'

PATHS = {}

PATHS['pkgprefix'] = os.path.realpath(os.path.dirname(__file__))
PATHS['vardir'] = os.path.join(PATHS['pkgprefix'], 'var')
PATHS['database'] = os.path.join(PATHS['vardir'], 'jmdict.sqlite')
PATHS['jmdict_url'] = 'http://ftp.monash.edu.au/pub/nihongo/JMdict_e.gz'

# extracted from edict "reading" fields. TODO: cross-check with Unicode
edict_kana='・？ヽヾゝゞー〜ぁあぃいうぇえおかがきぎくぐけげこごさざしじすずせぜそぞただちっつづてでとどなにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろわゐゑをんァアィイゥウェエォオカガキギクグケゲコゴサザシジスズセゼソゾタダチヂッツヅテデトドナニヌネノハバパヒビピフブプヘベペホボポマミムメモャヤュユョヨラリルレロヮワヰヱヲンヴヶ'
edict_kana_regexp=re.compile("^[%s]*$" % edict_kana)
def is_kana(string):
    return re.match(edict_kana_regexp, string) is not None

def has_alpha(string):
    return re.search('[a-z]', string, re.I) is not None

def has_regexp_special(string):
    '''True if string has characters of regular expressions.'''
    special = re.compile('[%s]' % re.escape(r'.^$*+?{}()[]\|'))
    return special.search(string)


# from http://stackoverflow.com/questions/600268/mkdir-p-functionality-in-python
# convenience function because python < 3.2 has no exist_ok
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise

regexp_store = {}
def get_regexp(pattern, flags):
    '''Return a compiled regexp from persistent store; make one if needed.

    We use this helper function so that the SQL hooks don't have to
    compile the same regexp at every query.

    Flags are not part of the hash; i.e. this function doesn't work
    for the same pattern with different flags.
    '''

    if pattern in regexp_store.keys():
        return regexp_store[pattern]
    else:
        comp = re.compile(pattern, re.U | flags)
        regexp_store[pattern] = comp
        return comp


def regexp_sensitive(pattern, field):
    '''SQL hook function for case-sensitive regexp matching.'''
    reg = get_regexp(pattern, 0)
    return reg.search(field) is not None

def regexp_insensitive(pattern, field):
    '''SQL hook function for case-insensitive regexp matching.'''
    reg = get_regexp(pattern, re.I)
    return reg.search(field) is not None

def match_word_sensitive(word, field):
    '''SQL hook function for whole-word, case-sensitive, non-regexp matching.'''
    reg = get_regexp(r'\b' + re.escape(word) + r'\b', 0)
    return reg.search(field) is not None

def match_word_insensitive(word, field):
    '''SQL hook function for whole-word, case-sensitive, non-regexp matching.'''
    reg = get_regexp(r'\b' + re.escape(word) + r'\b', re.I)
    return reg.search(field) is not None


class Sense():
    '''Attributes:
    - glosses: a list of glosses.
    - pos: part-of-speech.
    - id: database ID.
    '''

    def __init__(self, id=None, pos=None, glosses=None):
        self.id = id
        self.glosses = glosses or list()
        self.pos = pos

class DatabaseAccessError(Exception):
    '''Generic error accessing database.'''
    pass

class DatabaseMissing(DatabaseAccessError):
    '''Database not found.'''
    pass
class DatabaseWrongVersion(DatabaseAccessError):
    '''Database is of wrong version.'''
    pass
class DatabaseUpdating(DatabaseAccessError):
    '''Database is currently updating.'''
    pass
class DatabaseStaleUpdates(DatabaseAccessError):
    '''Temporary files left, updating process aborted anormally.'''
    pass

def opendb(case_sensitive=False):
    '''Test and open SQL database; returns (con, cur).

    Raises DatabaseAccessError subclass if database can't be used for any
    reason.'''

    temps = glob(PATHS['database'] + '.new.*')
    if temps:
        for temp in temps:
            m = re.match(PATHS['database'] + '.new.([0-9]*)',
                         temp)
            pid = int(m.group(1))
            try:
                os.getpgid(pid)
            except OSError:
                raise DatabaseStaleUpdates('updatedb-myougiden was interrupted; please run again')
        raise DatabaseUpdating('updatedb-myougiden is running, please wait a while :)')

    if not os.path.isfile(PATHS['database']):
        raise DatabaseMissing('Could not find ' + PATHS['database'])

    try:
        con = sql.connect(PATHS['database'])
        cur = con.cursor()
    except sql.OperationalError as e:
        raise DatabaseAccessError(str(e))

    try:
        cur.execute('SELECT dbversion FROM versions;')
        dbversion = cur.fetchone()[0]
    except sql.OperationalError:
        raise DatabaseAccessError("Couldn't read database to check version")

    if dbversion != DBVERSION:
        raise DatabaseWrongVersion('Incorrect database version: %s' % dbversion)

    if case_sensitive:
        con.create_function('regexp', 2, regexp_sensitive)
        con.create_function('match', 2, match_word_sensitive)
        cur.execute('PRAGMA case_sensitive_like = 1;')
    else:
        con.create_function('regexp', 2, regexp_insensitive)
        con.create_function('match', 2, match_word_insensitive)
        cur.execute('PRAGMA case_sensitive_like = 0;')

    return con, cur


# style : args
# *args as for colored()
FORMATTING={
        # color problems:
        # - japanese bitmap fonts are kinda crummy in bold
        # - non-bold gray doesn't even show in my dark xterm
        # - green/red is the most common color blindness
        # - it's very hard to impossible to detect if bg is dark or light
        # - cyan is better for dark bg, blue for light

        'reading': ('magenta', None, None),

        'kanji': ('cyan', None, None),

        # default
        # 'gloss':

        'misc': ('green', None, None),
        'highlight': ('green', None, ['bold']),

        'subdue': ('yellow', None, None),

        'match': ('red', None, None),

}

def fmt(string, style):
    return colored(string, *(FORMATTING[style]))

def color_regexp(reg_obj, longstring, base_style=None):
    '''Search regexp in longstring; return longstring with match colored.'''

    m = reg_obj.search(longstring)
    if not m:
        return longstring
    else:
        head = longstring[:m.start()]
        tail = longstring[m.end():]
        if base_style:
            head = fmt(head, base_style)
            tail = fmt(tail, base_style)
        return head + fmt(m.group(), 'match') + tail


def colorize_data(kanjis, readings, senses, search_params):
    '''Colorize matched data according to search parameters.

    search_params: A dictionary of arguments like those of search_by().
    '''

    # TODO: there's some duplication between this logic and search_by()

    # regexp to match whatever the query matched
    reg = search_params['query']
    if not search_params['regexp']:
        reg = re.escape(reg)

    if search_params['extent'] == 'whole':
        reg = '^' + reg + '$'
    elif search_params['extent'] == 'word':
        reg = r'\b' + reg + r'\b'

    if search_params['case_sensitive']:
        reg = get_regexp(reg, 0)
    else:
        reg = get_regexp(reg, re.I)


    if search_params['field'] == 'reading':
        readings = [color_regexp(reg, r, 'reading') for r in readings]
        kanjis = [fmt(k, 'kanji') for k in kanjis]
    elif search_params['field'] == 'kanji':
        readings = [fmt(k, 'reading') for k in readings]
        kanjis = [color_regexp(reg, k, 'kanji') for k in kanjis]
    elif search_params['field'] == 'gloss':
        readings = [fmt(k, 'reading') for k in readings]
        kanjis = [fmt(k, 'kanji') for k in kanjis]

        for sense in senses:
            sense.glosses = [color_regexp(reg, g) for g in sense.glosses]

    for sense in senses:
        if sense.pos:
            sense.pos = fmt(sense.pos, 'subdue')

    return (kanjis, readings, senses)

# this thing really needs to be better thought of
def format_entry_tsv(kanjis, readings, senses, is_frequent, search_params, color=False):
    # as of 2012-02-21, no reading or kanji field uses full-width semicolon
    sep_full = '；'

    # as of 2012-02-21, only one entry uses '|' .
    # and it's "C|NET", which should be "CNET" anyway.
    sep_half = '|'

    # escape separator
    for sense in senses:
        for idx, gloss in enumerate(sense.glosses):
            # I am unreasonably proud of this solution.
            sense.glosses[idx] = sense.glosses[idx].replace(sep_half, '¦')

    if is_frequent:
        freqmark = '(P)'

    if color:
        sep_full = fmt(sep_full, 'subdue')
        sep_half = fmt(sep_half, 'subdue')
        if is_frequent:
            freqmark = fmt(freqmark, 'highlight')
        kanjis, readings, senses = colorize_data(kanjis, readings, senses, search_params)

    s = ''

    s += "%s\t%s" % (sep_full.join(readings), sep_full.join(kanjis))
    for sense in senses:
        if sense.pos:
            pos = ' ' + sense.pos + ' '
        else:
            pos = ''
        s += "\t%s%s" % (pos, sep_half.join(sense.glosses))

    if is_frequent:
        s += ' '  + freqmark

    return s

def format_entry_human(kanjis, readings, senses, is_frequent, search_params, color=True):
    sep_full = '；'
    sep_half = '; '

    if is_frequent:
        freqmark = '※'

    if color:
        sep_full = fmt(sep_full, 'subdue')
        sep_half = fmt(sep_half, 'subdue')

        if is_frequent:
            freqmark = fmt(freqmark, 'highlight')
        kanjis, readings, senses = colorize_data(kanjis, readings, senses, search_params)

    s = ''

    if is_frequent:
        s += freqmark + ' ' + sep_full.join(readings)
    else:
        s += sep_full.join(readings)

    if len(kanjis) > 0:
        s += "\n"
        s += sep_full.join(kanjis)

    for sensenum, sense in enumerate(senses, start=1):
        sn = str(sensenum) + '.'
        if color:
            sn = fmt(sn, 'misc')

        if sense.pos:
            s += "\n%s %s %s" % (sn, sense.pos, sep_half.join(sense.glosses))
        else:
            s += "\n%s %s" % (sn, sep_half.join(sense.glosses))

    return s


def fetch_entry(cur, ent_seq):
    '''Return tuple of (kanjis, readings, senses, is_frequent).'''

    kanjis = [] # list of strings
    readings = [] # list of strings
    senses = [] # list of Sense objects

    cur.execute('SELECT frequent FROM entries WHERE ent_seq = ?;', [ent_seq])
    if cur.fetchone()[0] == 1:
        is_frequent = True
    else:
        is_frequent = False

    cur.execute('SELECT kanji FROM kanjis WHERE ent_seq = ?;', [ent_seq])
    for row in cur.fetchall():
        kanjis.append(row[0])

    cur.execute('SELECT reading FROM readings WHERE ent_seq = ?;', [ent_seq])
    for row in cur.fetchall():
        readings.append(row[0])

    senses = []
    cur.execute('SELECT id, pos FROM senses WHERE ent_seq = ?;', [ent_seq])
    for row in cur.fetchall():
        if row[1]:
            pos = '(%s)' % row[1]
        else:
            pos = None

        sense = Sense(id=row[0], pos=pos)

        cur.execute('SELECT gloss FROM glosses WHERE sense_id = ?;', [sense.id])
        for row in cur.fetchall():
            sense.glosses.append(row[0])

        senses.append(sense)

    return (kanjis, readings, senses, is_frequent)

def search_by(cur, field, query, extent='whole', regexp=False, case_sensitive=False, frequent=False):
    '''Main search function.  Return list of ent_seqs.

    Field in ('kanji', 'reading', 'gloss').
    '''

    if regexp:
        operator = 'REGEXP ?'

        if extent == 'whole':
            query = '^' + query + '$'
        elif extent == 'word':
            query = r'\b' + query + r'\b'

    else:
        if extent == 'word':
            # we custom-implemented match() to whole-word search.
            #
            # it uses regexps internally though (but the user query is
            # escaped).
            operator = 'MATCH ?'

        else:
            # LIKE gives us case-insensitiveness implemented in the
            # database, so we usen it even for whole-field matching.
            #
            # "\" seems to be the least common character in EDICT.
            operator = r"LIKE ? ESCAPE '\'"

            # my editor doesn't like raw strings
            # query = query.replace(r'\', r'\\')
            query = query.replace('\\', '\\\\')

            query = query.replace('%', r'\%')
            query = query.replace('_', r'\_')

            if extent == 'partial':
                query = '%' + query + '%'

    if field == 'kanji':
        table = 'kanjis'
        join = 'NATURAL JOIN kanjis'
    elif field == 'reading':
        table = 'readings'
        join = 'NATURAL JOIN readings'
    elif field == 'gloss':
        table = 'glosses'
        join = 'NATURAL JOIN senses JOIN glosses ON senses.id = glosses.sense_id'

    where_extra = ''
    if frequent:
        where_extra += 'AND frequent = 1'

    cur.execute('''
SELECT ent_seq
FROM entries
  %s
WHERE %s.%s %s
%s
;'''
                % (join, table, field, operator, where_extra),
                [query])

    res = []
    for row in cur.fetchall():
        res.append(row[0])
    return res


def guess_search(cur, conditions):
    '''Try many searches; stop at first successful.

    conditions -- list of dictionaries.

    Each dictionary in *conditions is a set of keyword arguments for
    search_by() (including the mandatory arguments!).

    guess_search will try all in order, and choose the first one with
    >0 results.

    Return value: 2-tuple (condition, entries) where:
     - condition is the chosen search condition
     - entries is a list of entries (see search_by() )
    '''

    for condition in conditions:
        res = search_by(cur, **condition)
        if len(res) > 0:
            return (condition, res)
    return (None, [])

def short_expansion(cur, abbrev):
    cur.execute(''' SELECT short_expansion FROM abbreviations WHERE abbrev = ? ;''', [abbrev])
    row = cur.fetchone()
    if row:
        return row[0]
    else:
        return None

def abbrev_line(cur, abbrev, color=True):
    exp = short_expansion(cur, abbrev)
    if color:
        abbrev = fmt(abbrev, 'subdue')
    return "%s\t%s" % (abbrev, exp)

def abbrevs_table(cur, color=True):
    cur.execute('''
    SELECT abbrev
    FROM abbreviations
    ORDER BY abbrev
    ;''')

    abbrevs=[]
    for row in cur.fetchall():
        abbrevs.append(row[0])
    return "\n".join([abbrev_line(cur, abbrev, color) for abbrev in abbrevs])
