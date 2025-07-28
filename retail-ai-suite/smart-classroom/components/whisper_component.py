from components.pipeline_comoponent import PipelineComponent
from components.asr.openvino.whisper import Whisper

class WhisperASRComponent(PipelineComponent):
    def __init__(self, whisper_model="openai/whisper-small", device="cpu"):
        pass


    def process(self, audio_path):
        pass