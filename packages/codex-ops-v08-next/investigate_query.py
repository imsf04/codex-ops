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


def _words(question, maximum=4):
    return [word for word in re.findall(r'\b[A-Za-z]{3,}\b', question) if word.lower() not in STOP][:maximum]


def _cjk(question):
    runs = re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff]+', question[:512])
    grams = [run[index:index + 2] for run in runs for index in range(len(run) - 1)]
    return list(dict.fromkeys(grams))[:32]


def _secondary(question, primary):
    candidates = _words(SYMBOL.sub(' ', question), 12) + _cjk(question)
    known = {word.casefold() for word in primary}
    return list(dict.fromkeys(word for word in candidates if word.casefold() not in known))


def _selection(question, supplied):
    if supplied:
        return supplied, [], 'explicit'
    primary = anchors(question)
    secondary = _secondary(question, primary)
    if primary:
        return primary, secondary, 'inferred'
    return secondary, [], 'inferred'


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
    primary, secondary, origin = _selection(question, supplied)
    return {'question': question, 'anchors': primary, 'secondaryAnchors': secondary, 'anchorOrigin': origin, 'paths': paths,
            'focus': focus, 'maxBytes': integer(args, 'maxBytes', 4096, 24576, 12288)}


def search_args(query, path, expanded=False):
    bounds = (8, 16, 12, 4) if expanded else (2, 3, 8, 3)
    return {'path': path, 'pattern': '|'.join(re.escape(item) for item in query['anchors']),
            'before': bounds[0], 'after': bounds[1], 'maxMatches': bounds[2], 'maxFiles': bounds[3]}
