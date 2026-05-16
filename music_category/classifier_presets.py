PRESETS = {
    "light": {
        "label": "Light",
        "backend": "light",
        "description": "Fast classifier from report/details feature columns. It does not read audio.",
    },
    "heavy-fast": {
        "label": "Heavy Fast",
        "backend": "heavy",
        "epochs": 3,
        "batch_size": 8,
        "learning_rate": 0.001,
        "max_files": None,
        "max_chunks_per_file": 2,
        "description": "Quick audio training sample. Uses up to 2 chunks per tagged file.",
    },
    "heavy-balanced": {
        "label": "Heavy Balanced",
        "backend": "heavy",
        "epochs": 8,
        "batch_size": 8,
        "learning_rate": 0.001,
        "max_files": None,
        "max_chunks_per_file": None,
        "description": "Default heavy audio training. Uses all tagged files and all chunks.",
    },
    "heavy-thorough": {
        "label": "Heavy Thorough",
        "backend": "heavy",
        "epochs": 15,
        "batch_size": 8,
        "learning_rate": 0.001,
        "max_files": None,
        "max_chunks_per_file": None,
        "description": "Longer heavy audio training. Slower, but may fit better with enough tagged data.",
    },
}


def choices():
    return list(PRESETS)


def label_for(name):
    return PRESETS.get(name, {}).get("label", name)


def name_for_label(label):
    for name, preset in PRESETS.items():
        if preset["label"] == label:
            return name
    return label


def labels():
    return [preset["label"] for preset in PRESETS.values()]


def get(name):
    return PRESETS.get(name_for_label(name), PRESETS["light"])


def apply_to_namespace(args):
    name = getattr(args, "classifier_preset", "") or ""
    if not name:
        return
    preset = get(name)
    args.classifier_backend = preset["backend"]
    if preset["backend"] == "heavy":
        args.heavy_epochs = preset["epochs"]
        args.heavy_batch_size = preset["batch_size"]
        args.heavy_learning_rate = preset["learning_rate"]
        args.heavy_max_files = preset["max_files"]
        args.heavy_max_chunks_per_file = preset["max_chunks_per_file"]
