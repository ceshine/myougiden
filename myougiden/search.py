import re
from myougiden import texttools as tt

def search_by(cur, field, query, lang='eng', extent='whole', regexp=False, case_sensitive=False, frequent=False):
    '''Main search function.  Return list of ent_seqs.

    Field in ('kanji', 'reading', 'gloss').
    Extent in ('whole', 'beginning', 'word', 'partial').
    '''

    if regexp:
        operator = 'REGEXP ?'

        if extent == 'whole':
            query = '^' + query + '$'
        elif extent == 'beginning':
            query = '^' + query
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

            if extent == 'beginning':
                query = query + '%'
            elif extent == 'partial':
                query = '%' + query + '%'

    if field == 'kanji':
        table = 'kanjis'
        join = 'JOIN kanjis ON entries.ent_seq = kanjis.ent_seq'
    elif field == 'reading':
        table = 'readings'
        join = 'JOIN readings ON entries.ent_seq = readings.ent_seq'
    elif field == 'gloss':
        table = 'glosses'
        join = '''JOIN glosses ON entries.ent_seq = glosses.ent_seq'''

    if field == 'gloss':
        where_extra = "AND glosses.lang = '%s'" % lang
    else:
        where_extra = ''
    if frequent:
        where_extra += 'AND entries.frequent = 1'


    cur.execute('''
SELECT DISTINCT entries.ent_seq
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


def guess(cur, conditions):
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

def matched_regexp(search_params):
    '''Return a regexp that reflects what the search_params matched.

    Used to color the result, with the params returned by guess_search().
    '''

    # TODO: there's some duplication between this logic and search_by()

    reg = search_params['query']
    if not search_params['regexp']:
        reg = re.escape(reg)

    if search_params['extent'] == 'whole':
        reg = '^' + reg + '$'
    elif search_params['extent'] == 'beginning':
        reg = '^' + reg
    elif search_params['extent'] == 'word':
        reg = r'\b' + reg + r'\b'

    if search_params['case_sensitive']:
        reg = tt.get_regexp(reg, 0)
    else:
        reg = tt.get_regexp(reg, re.I)

    return reg

