"""Deterministic query anchors; interpretation remains with the calling model."""
import re
from workflow_validation import options, require, text, integer

FOCUSES = ('auto', 'definition', 'references', 'configuration', 'failure')
SYMBOL = re.compile(r'`([^`\n]+)`|\b([A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+|_[A-Za-z][A-Za-z0-9_]*|[a-z]+[A-Z][A-Za-z0-9]*|[A-Za-z][A-Za-z0-9_-]*\.[A-Za-z0-9_.-]+)\b')
STOP = frozenset(('where what how why does which this that from with find show code function source please '
                  'config configuration configured settings error failure implementation implemented '
                  'test tests testing tested regression spec specs the and for into about whose these those '
                  'are was were been being its has have had can could should would method defined defines '
                  'definition used uses capped caps').split())


def strings(value, label, maximum):
    require(isinstance(value, list) and len(value) <= maximum, f'{label} must contain at most {maximum} strings')
    return list(dict.fromkeys(text(item, label, 512) for item in value))


def _words(question):
    return [word for word in re.findall(r'\b[A-Za-z]{3,}\b', question) if word.lower() not in STOP][:4]


def anchors(question):
    explicit = [next(value for value in match if value) for match in SYMBOL.findall(question)]
    return list(dict.fromkeys(explicit or _words(question)))[:8]


def parse(args):
    options(args, ('question', 'anchors', 'paths', 'focus', 'maxBytes'))
    question = text(args.get('question'), 'question', 8000)
    require(len(question) <= 2000, 'question must fit 2000 characters')
    supplied = strings(args.get('anchors', []), 'anchors', 8)
    paths = strings(args.get('paths', ['.']), 'paths', 4)
    require(bool(paths), 'paths must not be empty')
    focus = args.get('focus', 'auto')
    require(focus in FOCUSES, 'Unknown investigation focus')
    return {'question': question, 'anchors': supplied or anchors(question), 'paths': paths,
            'focus': focus, 'maxBytes': integer(args, 'maxBytes', 4096, 24576, 12288)}
