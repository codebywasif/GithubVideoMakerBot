import soundfile as sf
try:
    from voxcpm import VoxCPM
except ImportError:
    VoxCPM = None

class VoxCPM_TTS:
    """
    A Text-to-Speech engine that uses the local openbmb/VoxCPM2 model.
    """

    def __init__(self):
        self.max_chars = 1000
        if VoxCPM is None:
            raise RuntimeError("VoxCPM library is not installed. Please run `pip install voxcpm soundfile`")
            
        print("Loading VoxCPM model (this may take a minute or two on first run if it needs to download weights)...")
        # Load the pre-trained VoxCPM2 model
        self.model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)

    def run(self, text, filepath, random_voice: bool = False):
        """
        Convert the provided text to speech using VoxCPM and save it.
        """
        try:
            # We add a generic prompt design for a professional voice.
            # VoxCPM uses text descriptions in parentheses for voice design.
            prompt = f"(a clear professional male voice) {text}"
            
            wav = self.model.generate(
                text=prompt,
                cfg_value=2.0,           
                inference_timesteps=10   
            )

            # Save the output audio
            sf.write(filepath, wav, self.model.tts_model.sample_rate)
            
        except Exception as e:
            raise RuntimeError(f"Failed to generate audio with VoxCPM TTS: {str(e)}")
