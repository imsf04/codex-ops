"""SQLite FTS5 retrieval; uses the Python standard library, no copied vendor code.

FTS5 documentation: https://www.sqlite.org/fts5.html (SQLite public domain).
The index is request-local so TTL, policy and ownership are checked on every query.
"""
from contextlib import closing
import re
import sqlite3

from workflow_validation import require


def terms(query):
    words = list(dict.fromkeys(re.findall(r'\w+', query, re.UNICODE)))
    require(bool(words), 'query must contain a word or source identifier')
    require(len(words) <= 32, 'query supports at most 32 lexical terms')
    return ' OR '.join('"' + word.replace('"', '""') + '"' for word in words)


def ranked(rows, query, count):
    expression = terms(query)
    with closing(sqlite3.connect(':memory:')) as db:
        db.execute('CREATE VIRTUAL TABLE evidence USING fts5(content, tokenize="unicode61")')
        db.executemany('INSERT INTO evidence(rowid,content) VALUES(?,?)',
                       [(index + 1, row['text']) for index, row in enumerate(rows)])
        hits = db.execute('SELECT rowid FROM evidence WHERE evidence MATCH ? '
                          'ORDER BY bm25(evidence),rowid LIMIT ?', (expression, count)).fetchall()
    return [rows[row[0] - 1] for row in hits]


def select(rows, budget):
    selected, used = [], 0
    for row in rows:
        size = len(row['text'].encode('utf-8'))
        if used + size > budget:
            break
        selected.append(row)
        used += size
    return selected, used
