"""Librosa feature extraction for local audio classifiers."""


def _safe_summary(features, name, values):
    """Add mean and standard deviation values for a feature matrix.

    Args:
        features: Mutable feature dictionary receiving numeric values.
        name: Stable feature name prefix.
        values: NumPy array-like values returned by Librosa.
    """
    import numpy as np

    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return
    features[f"audio_feature:{name}:mean"] = float(np.nanmean(array))
    features[f"audio_feature:{name}:std"] = float(np.nanstd(array))


def extract_audio_features(audio, sample_rate):
    """Extract rhythm, timbre, and percussion features without BPM.

    Args:
        audio: Mono waveform samples.
        sample_rate: Sample rate used by the waveform.

    Returns:
        Dictionary of stable numeric feature names to float values.

    Raises:
        ValueError: If the waveform is empty or too short for useful analysis.
    """
    import librosa
    import numpy as np

    audio = np.asarray(audio, dtype=float)
    if audio.size < 1024:
        raise ValueError("audio is too short for feature extraction")

    features = {}
    harmonic, percussive = librosa.effects.hpss(audio)
    harmonic_energy = float(np.mean(np.abs(harmonic))) + 1e-9
    percussive_energy = float(np.mean(np.abs(percussive)))
    features["audio_feature:percussive_ratio"] = percussive_energy / harmonic_energy
    features["audio_feature:rms_mean"] = float(np.mean(librosa.feature.rms(y=audio)))
    features["audio_feature:zero_crossing_rate_mean"] = float(np.mean(librosa.feature.zero_crossing_rate(y=audio)))

    mfcc = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=13)
    for index, row in enumerate(mfcc, start=1):
        _safe_summary(features, f"mfcc_{index:02d}", row)

    _safe_summary(features, "spectral_centroid", librosa.feature.spectral_centroid(y=audio, sr=sample_rate))
    _safe_summary(features, "spectral_bandwidth", librosa.feature.spectral_bandwidth(y=audio, sr=sample_rate))
    _safe_summary(features, "spectral_rolloff", librosa.feature.spectral_rolloff(y=audio, sr=sample_rate))
    _safe_summary(features, "spectral_contrast", librosa.feature.spectral_contrast(y=audio, sr=sample_rate))
    _safe_summary(features, "chroma", librosa.feature.chroma_stft(y=harmonic, sr=sample_rate))

    onset_envelope = librosa.onset.onset_strength(y=percussive, sr=sample_rate)
    _safe_summary(features, "onset_strength", onset_envelope)
    if onset_envelope.size:
        rhythmic_autocorrelation = librosa.feature.tempogram(onset_envelope=onset_envelope, sr=sample_rate)
        _safe_summary(features, "rhythmic_autocorrelation", rhythmic_autocorrelation)

    return {key: round(float(value), 6) for key, value in sorted(features.items())}


def serialize_audio_features(features):
    """Serialize audio features for details CSV storage.

    Args:
        features: Mapping returned by :func:`extract_audio_features`.

    Returns:
        Semicolon-separated ``name=value`` string.
    """
    return "; ".join(f"{key}={value:.6f}" for key, value in sorted((features or {}).items()))


def parse_audio_features(value):
    """Parse serialized audio feature values from a details CSV row.

    Args:
        value: Semicolon-separated ``name=value`` feature string.

    Returns:
        Dictionary of feature names to numeric values.
    """
    features = {}
    for part in (value or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, raw_value = part.rsplit("=", 1)
        try:
            features[name.strip()] = float(raw_value)
        except ValueError:
            continue
    return features
