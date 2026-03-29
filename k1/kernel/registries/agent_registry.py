# Agent Registry
# YAML agent templates


class AgentRegistry:
    def __init__(self):
        self.templates = {}

    def register_template(self, template_name, template_yaml):
        self.templates[template_name] = template_yaml

    def get_template(self, template_name):
        return self.templates.get(template_name)
