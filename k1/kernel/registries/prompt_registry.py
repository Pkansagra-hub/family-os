# Prompt Registry
# Markdown prompt assets


class PromptRegistry:
    def __init__(self):
        self.prompts = {}

    def register_prompt(self, prompt_name, content):
        self.prompts[prompt_name] = content

    def get_prompt(self, prompt_name):
        return self.prompts.get(prompt_name)
