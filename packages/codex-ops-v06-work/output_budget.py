"""Share a soft presentation budget within one outbound frame, never across turns."""
TARGET_BYTES = 12000
MIN_ITEM_BYTES = 768


class FrameBudget:
    def __init__(self, presenter, sizes, target=TARGET_BYTES):
        self.presenter = presenter
        self.sizes = sizes
        self.source_bytes = sum(sizes)
        self.target = target
        self.active = self.source_bytes > target and len(sizes) > 1

    def record(self, *args):
        self.presenter.record(*args)

    def render(self, text, channel='text'):
        method = getattr(self.presenter, 'render_budgeted', None)
        if not self.active or method is None:
            return self.presenter.render(text, channel)
        allocation = max(MIN_ITEM_BYTES, int(self.target * len(text.encode()) / self.source_bytes))
        return method(text, channel, allocation)
