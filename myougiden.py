import sys
import os
import re
import sqlite3 as sql
from termcolor import *

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

def testdb():
    return os.path.isfile(PATHS['database'])

def opendb(case_sensitive=False):
    '''Open SQL database; returns (con, cur).'''

    con = sql.connect(PATHS['database'])
    cur = con.cursor()

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

        'subdue': ('yellow', None, None),

        'match': ('red', None, None)
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
        senses = [[color_regexp(reg, g) for g in glosses_list]
                  for glosses_list in senses]

    return (kanjis, readings, senses)


def format_entry_tsv(kanjis, readings, senses, search_params, color=False):
    sep_full = '；'
    sep_half = '; '

    if color:
        sep_full = fmt(sep_full, 'subdue')
        sep_half = fmt(sep_half, 'subdue')
        kanjis, readings, senses = colorize_data(kanjis, readings, senses, search_params)

    return '%s\t%s\t%s' % (
                sep_full.join(readings),
                sep_full.join(kanjis),
                "\t".join([sep_half.join(glosses_list) for glosses_list in senses])
                )

def format_entry_human(kanjis, readings, senses, search_params, color=True):
    sep_full = '；'
    sep_half = '; '

    if color:
        sep_full = fmt(sep_full, 'subdue')
        sep_half = fmt(sep_half, 'subdue')
        kanjis, readings, senses = colorize_data(kanjis, readings, senses, search_params)

    s = ''

    s += sep_full.join(readings)

    if len(kanjis) > 0:
        s += "\n"
        s += sep_full.join(kanjis)

    for sensenum, glosses_list in enumerate(senses, start=1):
        s += "\n "

        sn = str(sensenum) + '.'
        if color:
            sn = fmt(sn, 'misc')
        s += sn + ' '

        s += sep_half.join(glosses_list)

    return s


def fetch_entry(cur, ent_seq):
    '''Return tuple of lists (kanjis, readings, senses).'''

    kanjis = []
    readings = []
    senses = [] # list of list of glosses

    cur.execute('SELECT kanji FROM kanjis WHERE ent_seq = ?;', [ent_seq])
    for row in cur.fetchall():
        kanjis.append(row[0])

    cur.execute('SELECT reading FROM readings WHERE ent_seq = ?;', [ent_seq])
    for row in cur.fetchall():
        readings.append(row[0])

    sense_ids = []
    cur.execute('SELECT id FROM senses WHERE ent_seq = ?;', [ent_seq])
    for row in cur.fetchall():
        sense_ids.append(row[0])
    for sense_id in sense_ids:
        glosses = []

        cur.execute('SELECT gloss FROM glosses WHERE sense_id = ?;', [sense_id])
        for row in cur.fetchall():
            glosses.append(row[0])

        senses.append(glosses)

    return (kanjis, readings, senses)

def search_by(cur, field, query, extent='whole', regexp=False, case_sensitive=False):
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

    # print('SELECT ent_seq FROM entries %s WHERE %s.%s %s;'
    #       % (join, table, field, operator),
    #       query)

    cur.execute('''
SELECT ent_seq
FROM entries
  %s
WHERE %s.%s %s
;'''
                % (join, table, field, operator),
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

