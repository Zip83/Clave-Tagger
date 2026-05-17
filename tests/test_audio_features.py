import unittest

import numpy as np

from music_category import audio_features


class AudioFeatureTests(unittest.TestCase):
    def test_extract_audio_features_returns_numeric_values_without_bpm(self):
        """Feature extraction should describe timbre/rhythm without tempo fields."""
        sample_rate = 16000
        seconds = 2
        t = np.linspace(0, seconds, sample_rate * seconds, endpoint=False)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)

        features = audio_features.extract_audio_features(audio, sample_rate)

        self.assertIn("audio_feature:mfcc_01:mean", features)
        self.assertIn("audio_feature:percussive_ratio", features)
        self.assertTrue(all(isinstance(value, float) for value in features.values()))
        self.assertFalse(any("bpm" in key.lower() or "tempo" in key.lower() for key in features))

    def test_extract_audio_features_rejects_too_short_audio(self):
        """Very short decode results should become review rows upstream."""
        with self.assertRaises(ValueError):
            audio_features.extract_audio_features(np.zeros(100), 16000)


if __name__ == "__main__":
    unittest.main()
