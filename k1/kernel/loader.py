# Module Loader
# Scans k1/modules/*/module.yaml
# Installs tools, prompts, agents into registries


class ModuleLoader:
    def __init__(self, modules_path, registries):
        self.modules_path = modules_path
        self.registries = registries

    async def scan_and_load(self):
        # Scan modules directory
        # Load each module.yaml
        # Install components into registries
        pass

    async def hot_reload(self):
        # Watch for changes and reload
        pass
