# Hot Reload Engine
# File watcher for dev mode
# Triggers module reload on changes


class HotReloadEngine:
    def __init__(self, loader):
        self.loader = loader

    async def start_watching(self):
        # Watch k1/modules/ for changes
        # Call loader.scan_and_load() on changes
        pass
