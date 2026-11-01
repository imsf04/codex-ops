"""Show matched context inside a fused-search receipt without another retrieval."""
from record_preview import preview as records
from reducers import encode, small


def _context(value, budget):
    selected = records(value, budget)
    if selected is not None:
        return selected
    return small(value)


def preview(value, budget=3500):
    search = value.get('search', {})
    result = {'kind': 'search-context', 'status': value.get('status'),
              'matchedTotal': search.get('matchedTotal'), 'searchComplete': search.get('scanComplete'),
              'selectedMatches': value.get('selectedMatches'), 'omittedMatches': value.get('omittedMatches'),
              'snapshotConsistency': value.get('snapshotConsistency'),
              'contextPath': '/context', 'matchesPath': '/matches', 'checksPath': '/matchChecks'}
    for remaining in (budget - 650, budget // 2, 512):
        result['context'] = _context(value.get('context', {}), remaining)
        if len(encode(result).encode()) <= budget:
            return result
    result.pop('context')
    return {**result, 'clipped': True}


def capture(store, value, operation):
    receipt = store.capture(value)
    if operation == 'search' and receipt.get('kind') == 'reference':
        receipt['preview'] = preview(value)
    return receipt
