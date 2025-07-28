from components.summarizer.base_summarizer import BaseSummarizer

class Qwen(BaseSummarizer):
   def __init__(self, model_name=..., revision=..., device="cpu"):
       # Load model
       pass

    def summarize(self, prompt: str) -> str:
        pass