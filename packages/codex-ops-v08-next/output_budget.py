"""Share a soft presentation budget within one outbound frame, never across turns."""
TARGET_BYTES = 12000
MIN_ITEM_BYTES = 768


def fair_share(sizes, target):
    share = target / len(sizes)
    unused = sum(max(0, share - size) for size in sizes)
    oversized = sum(size > share for size in sizes)
    return share + unused / max(1, oversized)


class FrameBudget:
    def __init__(self, presenter, sizes, target=TARGET_BYTES):
        self.presenter = presenter
        self.sizes = sizes
        self.source_bytes = sum(sizes)
        self.target = target
        self.active = self.source_bytes > target and len(sizes) > 1
        self.allocation = int(fair_share(sizes, target)) if sizes else target

    def record(self, *args):
        self.presenter.record(*args)

    def render(self, text, channel='text'):
        method = getattr(self.presenter, 'render_budgeted', None)
        if not self.active or method is None:
            return self.presenter.render(text, channel)
        allocation = max(MIN_ITEM_BYTES, self.allocation)
        return method(text, channel, allocation)
