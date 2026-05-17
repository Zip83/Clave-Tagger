import os
from pathlib import Path
import time
from collections import Counter

from . import app_logging, audio_decode, audio_model, config
from .light_model import truth_category

HEAVY_MODEL_KIND = "heavy-audio-cnn"
N_MELS = 64
HOP_LENGTH = 512
TARGET_FRAMES = 938
CHUNK_DURATION = 30.0
CHUNK_STRIDE = 30.0
TORCH_THREADS_ENV = "CLAVETAGGER_TORCH_THREADS"


def preferred_torch_threads(cpu_count=None, env_value=None):
    """Pick a conservative PyTorch CPU thread count so the GUI remains responsive."""
    if env_value is None:
        env_value = os.environ.get(TORCH_THREADS_ENV, "")
    try:
        configured = int(str(env_value).strip()) if str(env_value).strip() else 0
    except ValueError:
        configured = 0
    if configured > 0:
        return configured

    available = cpu_count if cpu_count is not None else (os.cpu_count() or 2)
    return max(1, min(4, available - 1))


def configure_torch_runtime(torch_module):
    """Configure torch runtime."""
    thread_count = preferred_torch_threads()
    try:
        torch_module.set_num_threads(thread_count)
    except Exception:
        pass
    try:
        torch_module.set_num_interop_threads(1)
    except Exception:
        pass
    return thread_count


def waveform_to_log_mel(audio, sample_rate=audio_model.SAMPLE_RATE, n_mels=N_MELS, target_frames=TARGET_FRAMES):
    """Waveform to log mel."""
    import librosa
    import numpy as np
    import torch

    mel = librosa.feature.melspectrogram(
        y=audio,
        sr=sample_rate,
        n_mels=n_mels,
        hop_length=HOP_LENGTH,
        power=2.0,
    )
    log_mel = librosa.power_to_db(mel, ref=np.max)
    log_mel = (log_mel - float(log_mel.mean())) / (float(log_mel.std()) + 1e-6)

    if log_mel.shape[1] < target_frames:
        pad_width = target_frames - log_mel.shape[1]
        log_mel = np.pad(log_mel, ((0, 0), (0, pad_width)), mode="constant")
    elif log_mel.shape[1] > target_frames:
        log_mel = log_mel[:, :target_frames]

    return torch.tensor(log_mel, dtype=torch.float32).unsqueeze(0)


def load_file_tensor(file_path, clip_offset=0.0, clip_duration=CHUNK_DURATION):
    """Load file tensor."""
    (audio, _sample_rate), _caught, _stderr_output = audio_decode.load_audio(
        file_path,
        sample_rate=audio_model.SAMPLE_RATE,
        mono=True,
        offset=clip_offset,
        duration=clip_duration,
    )
    return waveform_to_log_mel(audio)


def safe_load_file_tensor(file_path, clip_offset=0.0, clip_duration=CHUNK_DURATION):
    """Safe load file tensor."""
    try:
        return load_file_tensor(file_path, clip_offset=clip_offset, clip_duration=clip_duration)
    except Exception as error:
        app_logging.log_exception(f"Skipping undecodable heavy training chunk {file_path} at {clip_offset}s", error)
        return None


def chunk_starts_for_file(file_path, chunk_duration=CHUNK_DURATION, chunk_stride=CHUNK_STRIDE):
    """Chunk starts for file."""
    duration, _caught, _stderr_output = audio_decode.get_duration(file_path)
    if duration <= chunk_duration:
        return [0.0]

    starts = []
    current = 0.0
    while current + 1.0 < duration:
        starts.append(round(current, 3))
        current += chunk_stride

    last_start = max(0.0, duration - chunk_duration)
    if starts[-1] < last_start:
        starts.append(round(last_start, 3))
    return starts


class AudioCnn:
    """AudioCnn."""
    @staticmethod
    def create(num_classes):
        """Create the requested value."""
        import torch.nn as nn

        return nn.Sequential(
            nn.Conv2d(1, 16, kernel_size=3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)),
            nn.Flatten(),
            nn.Linear(64, num_classes),
        )


def collect_labeled_audio_rows(rows, truth_column="id3_grouping_normalized", limit=None, progress_callback=None, cancel_token=None):
    """Collect labeled audio rows."""
    samples = []
    skipped_no_truth = 0
    skipped_missing_file = 0
    total = len(rows)
    for index, row in enumerate(rows, start=1):
        if cancel_token:
            cancel_token.throw_if_cancelled()
        if progress_callback:
            progress_callback(
                {
                    "event": "training_scan_file_start",
                    "backend": "heavy",
                    "row": row,
                    "status": "current",
                    "after_status": "done",
                    "processed": index - 1,
                    "total": total,
                    "message": f"Heavy training scan {index}/{total}: {row.get('file_name') or row.get('file_path') or 'track'}",
                }
            )
        label = truth_category(row, truth_column)
        if not label:
            skipped_no_truth += 1
            if progress_callback:
                progress_callback(
                    {
                        "event": "training_scan_file",
                        "backend": "heavy",
                        "row": row,
                        "status": "needs_review",
                        "processed": index,
                        "total": total,
                        "message": f"Heavy training scan {index}/{total}: skipped empty Grouping",
                    }
                )
            continue
        file_path = row.get("file_path", "")
        if not file_path or not Path(file_path).exists():
            skipped_missing_file += 1
            if progress_callback:
                progress_callback(
                    {
                        "event": "training_scan_file",
                        "backend": "heavy",
                        "row": row,
                        "status": "error",
                        "processed": index,
                        "total": total,
                        "message": f"Heavy training scan {index}/{total}: missing file",
                    }
                )
            continue
        samples.append((row, label))
        if progress_callback:
            progress_callback(
                {
                    "event": "training_scan_file",
                    "backend": "heavy",
                    "row": row,
                    "status": "done",
                    "processed": index,
                    "total": total,
                    "message": f"Heavy training scan {index}/{total}: collected {label}",
                }
            )
        if limit and len(samples) >= limit:
            break
    return samples, skipped_no_truth, skipped_missing_file


def expand_samples_to_chunks(samples, max_chunks_per_file=None, progress_callback=None, cancel_token=None):
    """Expand samples to chunks."""
    expanded = []
    total = len(samples)
    for index, (row, label) in enumerate(samples, start=1):
        if cancel_token:
            cancel_token.throw_if_cancelled()
        if progress_callback:
            progress_callback(
                {
                    "event": "training_chunks_file_start",
                    "backend": "heavy",
                    "row": row,
                    "status": "current",
                    "after_status": "done",
                    "processed": index - 1,
                    "total": total,
                    "message": f"Heavy training chunks {index}/{total}: {row.get('file_name') or row.get('file_path') or 'track'}",
                }
            )
        starts = chunk_starts_for_file(row["file_path"])
        if max_chunks_per_file:
            starts = starts[:max_chunks_per_file]
        for start in starts:
            expanded.append((row, label, start))
        if progress_callback:
            progress_callback(
                {
                    "event": "training_chunks_file",
                    "backend": "heavy",
                    "row": row,
                    "status": "done",
                    "processed": index,
                    "total": total,
                    "chunks": len(expanded),
                    "message": f"Heavy training chunks {index}/{total}: total chunks={len(expanded)}",
                }
            )
    return expanded


class AudioDataset:
    """AudioDataset."""
    def __init__(self, chunk_samples, label_to_index, cancel_token=None):
        """Initialize this object."""
        self.chunk_samples = chunk_samples
        self.label_to_index = label_to_index
        self.cancel_token = cancel_token

    def __len__(self):
        """Len."""
        return len(self.chunk_samples)

    def __getitem__(self, index):
        """Getitem."""
        import torch

        if self.cancel_token:
            self.cancel_token.throw_if_cancelled()
        row, label, start = self.chunk_samples[index]
        tensor = safe_load_file_tensor(row["file_path"], clip_offset=start)
        if self.cancel_token:
            self.cancel_token.throw_if_cancelled()
        if tensor is None:
            return None
        return tensor, torch.tensor(self.label_to_index[label], dtype=torch.long)


def collate_valid_training_batch(batch):
    """Collate valid training batch."""
    import torch

    valid = [item for item in batch if item is not None]
    if not valid:
        return None, None
    tensors, labels = zip(*valid)
    return torch.stack(list(tensors)), torch.stack(list(labels))


def train_heavy_classifier(
    rows,
    output_path,
    truth_column="id3_grouping_normalized",
    epochs=8,
    batch_size=8,
    learning_rate=1e-3,
    limit=None,
    max_chunks_per_file=None,
    progress_callback=None,
    cancel_token=None,
):
    """Train heavy classifier."""
    if cancel_token:
        cancel_token.throw_if_cancelled()
    if progress_callback:
        progress_callback(
            {
                "event": "training_setup_start",
                "backend": "heavy",
                "processed": 0,
                "total": 1,
                "message": "Training heavy classifier: loading PyTorch...",
            }
        )
    import torch
    torch_threads = configure_torch_runtime(torch)
    if cancel_token:
        cancel_token.throw_if_cancelled()
    from torch.utils.data import DataLoader, WeightedRandomSampler
    if cancel_token:
        cancel_token.throw_if_cancelled()

    if progress_callback:
        progress_callback(
            {
                "event": "training_start",
                "backend": "heavy",
                "processed": 0,
                "total": len(rows),
                "message": f"Training heavy classifier: scanning {len(rows)} rows (PyTorch CPU threads={torch_threads})",
            }
        )
    samples, skipped_no_truth, skipped_missing_file = collect_labeled_audio_rows(
        rows,
        truth_column,
        limit,
        progress_callback=progress_callback,
        cancel_token=cancel_token,
    )
    if cancel_token:
        cancel_token.throw_if_cancelled()
    labels = sorted({label for _row, label in samples})
    if len(samples) < 2 or len(labels) < 2:
        raise ValueError(
            "Heavy classifier training needs at least two existing audio files from at least two tagged categories. "
            "To add another style later, retrain from the whole tagged library so the model keeps examples "
            "of previous categories while learning the new one."
        )

    if progress_callback:
        progress_callback(
            {
                "event": "training_chunks_start",
                "backend": "heavy",
                "processed": 0,
                "total": len(samples),
                "message": f"Planning heavy training chunks for {len(samples)} tagged files",
            }
        )
    chunk_samples = expand_samples_to_chunks(
        samples,
        max_chunks_per_file,
        progress_callback=progress_callback,
        cancel_token=cancel_token,
    )
    if cancel_token:
        cancel_token.throw_if_cancelled()
    if len(chunk_samples) < 2:
        raise ValueError("Heavy classifier training did not find enough audio chunks.")

    if progress_callback:
        progress_callback(
            {
                "event": "training_setup_model",
                "backend": "heavy",
                "processed": 0,
                "total": 1,
                "message": f"Training heavy classifier: preparing dataset/model for {len(chunk_samples)} chunks...",
            }
        )
    if cancel_token:
        cancel_token.throw_if_cancelled()
    label_to_index = {label: index for index, label in enumerate(labels)}
    chunk_label_counts = Counter(label for _row, label, _start in chunk_samples)
    class_weights = [
        (len(chunk_samples) / max(1, len(labels) * chunk_label_counts[label])) ** 0.5
        for label in labels
    ]
    sample_weights = [1.0 / max(1, chunk_label_counts[label]) for _row, label, _start in chunk_samples]
    if cancel_token:
        cancel_token.throw_if_cancelled()
    dataset = AudioDataset(chunk_samples, label_to_index, cancel_token=cancel_token)
    sampler = WeightedRandomSampler(sample_weights, num_samples=len(sample_weights), replacement=True)
    loader = DataLoader(dataset, batch_size=batch_size, sampler=sampler, collate_fn=collate_valid_training_batch)
    if cancel_token:
        cancel_token.throw_if_cancelled()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if progress_callback:
        progress_callback(
            {
                "event": "training_setup_model",
                "backend": "heavy",
                "processed": 1,
                "total": 1,
                "message": f"Training heavy classifier: initializing model on {device}...",
            }
        )
    if cancel_token:
        cancel_token.throw_if_cancelled()
    model = AudioCnn.create(len(labels)).to(device)
    if cancel_token:
        cancel_token.throw_if_cancelled()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    criterion = torch.nn.CrossEntropyLoss(weight=torch.tensor(class_weights, dtype=torch.float32, device=device))
    if cancel_token:
        cancel_token.throw_if_cancelled()

    model.train()
    last_loss = 0.0
    total_batches = len(loader)
    training_started = time.time()
    for epoch in range(1, epochs + 1):
        if cancel_token:
            cancel_token.throw_if_cancelled()
        total_loss = 0.0
        seen = 0
        for batch_index, (batch_x, batch_y) in enumerate(loader, start=1):
            if cancel_token:
                cancel_token.throw_if_cancelled()
            if batch_x is None:
                if progress_callback:
                    completed_batches = (epoch - 1) * total_batches + batch_index
                    progress_callback(
                        {
                            "event": "training_batch_skipped",
                            "backend": "heavy",
                            "epoch": epoch,
                            "epochs": epochs,
                            "batch": batch_index,
                            "batches": total_batches,
                            "processed": completed_batches,
                            "total": max(1, epochs * total_batches),
                            "message": f"Training heavy | epoch {epoch}/{epochs} | batch {batch_index}/{total_batches} skipped undecodable audio",
                        }
                    )
                continue
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            if cancel_token:
                cancel_token.throw_if_cancelled()
            optimizer.zero_grad()
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            if cancel_token:
                cancel_token.throw_if_cancelled()
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item()) * len(batch_x)
            seen += len(batch_x)
            if progress_callback:
                completed_batches = (epoch - 1) * total_batches + batch_index
                all_batches = max(1, epochs * total_batches)
                elapsed = time.time() - training_started
                eta = (elapsed / completed_batches) * (all_batches - completed_batches) if completed_batches else 0.0
                progress_callback(
                    {
                        "event": "training_batch_done",
                        "backend": "heavy",
                        "epoch": epoch,
                        "epochs": epochs,
                        "batch": batch_index,
                        "batches": total_batches,
                        "processed": completed_batches,
                        "total": all_batches,
                        "loss": float(loss.item()),
                        "eta_seconds": eta,
                        "message": (
                            f"Training heavy | epoch {epoch}/{epochs} | batch {batch_index}/{total_batches} "
                            f"| loss={float(loss.item()):.4f}"
                        ),
                    }
                )
        last_loss = total_loss / max(1, seen)
        if progress_callback:
            progress_callback(
                {
                    "event": "heavy_epoch_done",
                    "backend": "heavy",
                    "epoch": epoch,
                    "epochs": epochs,
                    "processed": epoch,
                    "total": epochs,
                    "loss": last_loss,
                    "message": f"Heavy classifier epoch {epoch}/{epochs}, loss={last_loss:.4f}",
                }
            )

    payload = {
        "kind": HEAVY_MODEL_KIND,
        "model_state_dict": model.cpu().state_dict(),
        "labels": labels,
        "settings": {
            "n_mels": N_MELS,
            "target_frames": TARGET_FRAMES,
            "sample_rate": audio_model.SAMPLE_RATE,
            "chunk_duration": CHUNK_DURATION,
            "chunk_stride": CHUNK_STRIDE,
        },
        "trained_rows": len(samples),
        "trained_chunks": len(chunk_samples),
        "label_counts": {label: sum(1 for _row, sample_label in samples if sample_label == label) for label in labels},
        "chunk_label_counts": dict(chunk_label_counts),
        "class_weights": {label: float(class_weights[index]) for index, label in enumerate(labels)},
        "skipped_no_truth": skipped_no_truth,
        "skipped_missing_file": skipped_missing_file,
        "skipped_no_features": 0,
        "loss": last_loss,
        "config_categories": [item.get("category", "") for item in config.category_items()],
    }
    if cancel_token:
        cancel_token.throw_if_cancelled()
    if progress_callback:
        progress_callback(
            {
                "event": "training_save_start",
                "backend": "heavy",
                "processed": epochs,
                "total": epochs,
                "message": f"Saving heavy classifier to {output_path}",
            }
        )
    torch.save(payload, output_path)
    if progress_callback:
        progress_callback(
            {
                "event": "training_done",
                "backend": "heavy",
                "processed": epochs,
                "total": epochs,
                "message": f"Heavy classifier trained: rows={len(samples)}, chunks={len(chunk_samples)}, labels={len(labels)}",
            }
        )
    return payload


def run_heavy_analysis(rows, classifier_path, progress_callback=None, cancel_token=None):
    """Run heavy analysis."""
    if cancel_token:
        cancel_token.throw_if_cancelled()
    if progress_callback:
        progress_callback(
            {
                "event": "learned_setup_start",
                "processed": 0,
                "pending": len(rows),
                "message": "Loading heavy learned classifier...",
            }
        )
    import torch
    torch_threads = configure_torch_runtime(torch)
    if cancel_token:
        cancel_token.throw_if_cancelled()
    if progress_callback:
        progress_callback(
            {
                "event": "learned_setup_progress",
                "processed": 0,
                "pending": len(rows),
                "message": f"Heavy learned classifier: PyTorch CPU threads={torch_threads}",
            }
        )

    payload = torch.load(classifier_path, map_location="cpu")
    if cancel_token:
        cancel_token.throw_if_cancelled()
    labels = payload["labels"]
    model = AudioCnn.create(len(labels))
    model.load_state_dict(payload["model_state_dict"])
    model.eval()
    if cancel_token:
        cancel_token.throw_if_cancelled()
    total = len(rows)

    with torch.no_grad():
        for index, row in enumerate(rows, start=1):
            if cancel_token:
                cancel_token.throw_if_cancelled()
            if progress_callback:
                progress_callback(
                    {
                        "event": "learned_file_start",
                        "row": row,
                        "processed": index - 1,
                        "pending": total,
                        "total": total,
                        "message": f"Classifying {row.get('file_name', '')} ({index}/{total})",
                    }
                )
            try:
                chunk_probabilities = []
                for start in chunk_starts_for_file(row["file_path"]):
                    tensor = load_file_tensor(row["file_path"], clip_offset=start).unsqueeze(0)
                    chunk_probabilities.append(torch.softmax(model(tensor), dim=1)[0])
                probabilities = torch.stack(chunk_probabilities).mean(dim=0)
                best_index = int(torch.argmax(probabilities).item())
                probability = float(probabilities[best_index].item())
                category = labels[best_index]
                confidence = "high" if probability >= 0.70 else "medium" if probability >= 0.50 else "low" if probability >= 0.35 else "review"
                if confidence == "review":
                    category = "Needs review"
                result = {
                    "learned_suggested_grouping": category,
                    "learned_confidence": confidence,
                    "learned_reason": f"Heavy audio CNN probability={probability:.3f}; labels={', '.join(labels)}",
                }
            except Exception as error:
                result = {
                    "learned_suggested_grouping": "Needs review",
                    "learned_confidence": "review",
                    "learned_reason": f"Heavy audio CNN error: {error}",
                }
            row.update(result)
            if progress_callback:
                progress_callback(
                    {
                        "event": "learned_file_done",
                        "row": row,
                        "processed": index,
                        "pending": total,
                        "total": total,
                        "message": f"{row.get('file_name', '')} -> {result['learned_suggested_grouping']} ({result['learned_confidence']})",
                    }
                )
