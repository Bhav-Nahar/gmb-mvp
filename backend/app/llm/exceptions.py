class LLMProviderError(Exception):
    def __init__(self, message: str = "AI service temporarily unavailable"):
        self.message = message
        super().__init__(self.message)
