# Agent Instructions

This file gives project-specific guidance for future coding agents working on ClaveTagger.

## Project Purpose

ClaveTagger is a local MP3 categorization tool for Latin DJ libraries. It generates CSV reports, reads and optionally writes ID3 `Grouping` and `Color` tags, classifies tracks from metadata and audio, and can train local classifiers from already tagged libraries.

Safety matters: MP3 files must never be modified unless the user explicitly requests a write operation and `--apply-write` is used.

## Architecture

Keep responsibilities separated:

- `music_category_report.py`: thin CLI compatibility entry point only.
- `music_category/app_paths.py`: app name and default runtime paths.
- `music_category/app_logging.py`: file logging and exception logging.
- `music_category/cancel.py`: cooperative cancellation token.
- `music_category/config.py`: category configuration, aliases, normalization, `Grouping` and `Color` mapping.
- `music_category/schemas.py`: shared constants, modes, field names, and default row fields.
- `music_category/csv_io.py`: MP3 discovery, CSV reading/writing, and classifier detail merging.
- `music_category/progress.py`: progress cache and duration formatting.
- `music_category/recommendations.py`: confidence-aware recommendation selection.
- `music_category/overrides.py`: manual correction CSV read/write/apply logic.
- `music_category/calibration.py`: CSV mismatch analysis and proposed config tuning.
- `music_category/report_estimate.py`: runtime estimation.
- `music_category/id3_tags.py`: ID3 read/write helpers.
- `music_category/text_classifier.py`: metadata and filename classification.
- `music_category/audio_model.py`: MAEST audio model integration and audio-label mapping.
- `music_category/model_runner.py`: MAEST report execution and progress callbacks.
- `music_category/light_model.py`: light learned classifier implementation.
- `music_category/learning.py`: learned-classifier dispatch.
- `music_category/heavy_model.py`: heavy PyTorch audio CNN trained from tagged MP3 audio.
- `music_category/tag_writer.py`: tag write planning and application.
- `music_category/evaluation.py`: prediction evaluation.
- `music_category/cli_parser.py`: CLI argument parser.
- `music_category/cli.py`: CLI command orchestration.
- `music_category/report.py`: compatibility facade that re-exports public functions.
- `music_category/gui_services.py`: GUI-facing service layer, testable without Tkinter.
- `music_category_gui.py`: Tkinter UI only: widgets, worker thread, queue, table, logs, and playback wiring.
- `tests/`: unit tests.

When adding features, prefer adding logic to a focused module or service function. Avoid putting business logic directly into `music_category_gui.py`.

## Runtime Files

Default runtime folders are:

- `reports/`: generated CSV reports and manual overrides.
- `progress/`: MAEST progress cache JSON.
- `models/`: local learned classifiers.
- `logs/`: application logs and captured decode warnings.

Generated files in those folders are ignored by git. Commit only placeholders/docs such as `reports/.gitkeep`, `progress/.gitkeep`, `logs/.gitkeep`, and `models/README.md`.

`.venv-maest` is a local virtual environment and must not be committed. MAEST / Hugging Face model weights are downloaded into the user's normal cache on first audio-model run and must not be committed.

## Configuration

Categories and style mappings should be config-driven through `category_config.json` whenever possible.

Use config fields such as:

- `category`
- `grouping`
- `color`
- `aliases`
- `tag_patterns`
- `model_labels`
- `model_weight`
- `bpm_boosts`

Do not hardcode new styles in Python unless the behavior cannot reasonably live in config.

`Guaguanco` is configured as a signal for `Rumba`, not `Conga` or automatic `Salsa`.

## CLI Behavior

Preserve existing commands where possible. `music_category_report.py` should remain a stable entry point.

Important CLI patterns:

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --help
.venv-maest\Scripts\python.exe music_category_report.py --source "C:\Music\Salsa" --mode tags
.venv-maest\Scripts\python.exe music_category_report.py --source "C:\Music\Salsa" --mode model --output-csv reports\report_main.csv --details-csv reports\report_details.csv
.venv-maest\Scripts\python.exe music_category_report.py --source "C:\Music" --train-classifier --classifier-backend heavy --classifier-output models\learned_heavy.pt
```

Windows helper scripts are available:

```powershell
.\setup.bat
.\run_gui.bat
.\run_cli.bat --help
.\test.bat
```

Training must remain explicit through `--train-classifier`. Normal analysis must not start training implicitly.

Write modes must remain dry-run unless `--apply-write` is present.

## GUI Behavior

The GUI must stay responsive. Long-running work should run outside the Tkinter main thread and communicate back through the queue.

Keep the GUI thin:

- Build widgets in `music_category_gui.py`.
- Put workflow logic in `music_category/gui_services.py`.
- Keep tag writing, report generation, training, calibration, and evaluation outside widget callbacks when possible.

When adding GUI features, add unit-testable service logic first, then wire it into the UI.

The GUI should remain aligned with CLI workflows: estimate, analyze, train, evaluate, calibrate, dry-run writes, apply writes, folder preview, manual overrides, and progress/abort behavior.

## Learned Classifiers

Two learned classifier backends exist:

- `light`: scikit-learn classifier over MAEST scores, top labels, BPM, and config-derived features.
- `heavy`: PyTorch audio CNN trained directly from tagged MP3 audio.

Heavy training uses whole tracks by splitting each file into 30-second windows. Inference also uses whole-track windowing and averages probabilities across windows.

Do not make heavy training run automatically during report generation.

Do not treat training as incremental single-class fine-tuning. The supported workflow is cumulative retraining from tagged files. If a new style is added, train with examples of previous categories plus the new category so the classifier keeps a useful decision boundary.

## Testing

Use Python's built-in `unittest`.

Run all tests:

```powershell
.venv-maest\Scripts\python.exe -m unittest discover -s tests -v
```

See `TESTING.md` for more examples.

Unit tests should be fast and avoid:

- downloading or running MAEST
- full heavy training
- requiring real MP3 files
- opening Tkinter windows

Use mocks for slow or external behavior. Put GUI workflow tests against `music_category/gui_services.py`, not the live Tkinter app.

## Safety Rules

- Never write MP3 tags unless explicitly requested.
- Keep write operations dry-run by default.
- If testing ID3 writes, use copied files only.
- Do not delete user music files.
- Avoid destructive filesystem commands.
- Keep generated reports and scratch files in the project workspace unless the user gives a specific output path.

## Code Style

- Keep modules small and responsibility-focused.
- Prefer plain functions and dataclasses unless a class adds real state or behavior.
- Keep compatibility imports in `music_category_report.py` working for the GUI and existing scripts.
- Use config-driven behavior for style/category additions.
- Add tests for new classification rules, recommendation changes, write planning, calibration, overrides, and service workflows.
- Avoid long-running operations in unit tests.

## Documentation

Update documentation when changing user-facing behavior:

- `README.md`: general project usage.
- `TESTING.md`: testing commands and strategy.
- `AGENTS.md`: guidance for future agents.

For new CLI switches, update `README.md` and make sure `--help` remains clear.
