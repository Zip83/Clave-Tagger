# ClaveTagger

ClaveTagger is a local MP3 categorization tool for Latin DJ libraries. It reads ID3 metadata, suggests configured music categories, can analyze audio with the MAEST Discogs model, can train local classifiers from already tagged files, and can write reviewed `Grouping` / `Color` tags back to MP3 files.

This is a hobby project built for personal DJ-library cleanup. It does not guarantee correct genre classification, BPM detection, model predictions, playlist matching, or tag-writing behavior. Treat every suggestion as a draft, review important changes manually, and keep backups of music files before applying tag writes.

The app is safe by default. MP3 files are never modified unless `--apply-write` is passed in the CLI or the GUI write action is explicitly applied.

## Fresh Install

Install Python 3.12, then create a local virtual environment in the project folder:

```powershell
.\setup.bat
```

or:

```powershell
.\scripts\setup.ps1
```

The setup script creates `.venv-maest`, ensures `pip` exists, upgrades `pip`, and installs `requirements.txt`.

Manual setup is also possible:

```powershell
python -m venv .venv-maest
```

If you use `uv`, this is also fine:

```powershell
uv venv --python 3.12 .venv-maest
```

Install dependencies:

```powershell
.venv-maest\Scripts\python.exe -m pip install -r requirements.txt
```

`.venv-maest` is a local Python environment. It is recreated during setup and must not be committed to git.

The first `model`, `both`, or `all` audio analysis run downloads MAEST / Hugging Face model weights into the normal Hugging Face cache for the current Windows user. Those weights are not stored in this repository.

## Hugging Face Token Setup

Optional Hugging Face authentication can be configured with a local `.env` file:

```powershell
copy .env.example .env
notepad .env
```

Set `HF_TOKEN=...` inside `.env` when you want higher Hugging Face rate limits or need access to private/gated models. Public models usually work without a token. `.env` is ignored by git.

## Runtime Files

Runtime files are written to dedicated folders:

- `reports/`: generated CSV reports and manual overrides.
- `progress/`: MAEST progress cache JSON.
- `models/`: local learned classifier artifacts.
- `logs/`: app logs and captured decode warnings.
- `settings/`: local GUI preferences such as analysis mode, model files, presets, and output paths.

Generated files in those folders are ignored by git by default. Placeholder files and docs are kept so the folder layout exists after clone.

## Quick Start

Show CLI help:

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --help
```

Start the GUI:

```powershell
.\run_gui.bat
```

Create a metadata-only report:

```powershell
.\run_cli.bat --source "C:\Music\Salsa" --mode tags --estimate-only
.\run_cli.bat --source "C:\Music\Salsa" --mode tags
```

Create an audio report with the default MAEST model. By default this uses one 30-second analysis window:

```powershell
.\run_cli.bat --source "C:\Music\Salsa" --mode model
```

Analyze only files that do not already have `Grouping` / `TIT1` filled, while still keeping all rows in the CSV:

```powershell
.\run_cli.bat --source "C:\Music\Salsa" --mode model --only-missing-grouping
```

For slower but more stable audio analysis, average audio-model predictions across the whole song:

```powershell
.\run_cli.bat --source "C:\Music\Salsa" --mode model --model-full-track
```

Start a clean run while keeping old cache/CSV files in a timestamped backup:

```powershell
.\run_cli.bat --source "C:\Music\Salsa" --mode model --artifact-policy fresh --artifact-backup-dir backups
```

Use a different Hugging Face `audio-classification` model:

```powershell
.\run_cli.bat --source "C:\Music\Salsa" --mode model --audio-model-id "organization/model-name"
```

List known model presets:

```powershell
.\run_cli.bat --list-audio-models
```

Compare every supported audio model preset side by side:

```powershell
.\run_cli.bat --source "C:\Music\Salsa" --compare-audio-models --model-comparison-csv reports\model_comparison.csv
```

Match a label playlist such as a TIDAL/VirtualDJ playlist named `Son` against local MP3 files. The playlist supplies the category, while the local file supplies the real audio for later training:

```powershell
.\run_cli.bat --source "C:\Users\Zip\Music\DJ\Music Selection" --label-playlist "C:\Users\Zip\Documents\VirtualDJ\My Lists\Son.xml" --label-playlist-output reports\son_playlist_matches.csv
```

Only use your own trained classifier, without MAEST or any other external audio model:

```powershell
.\run_cli.bat --source "C:\Music\Salsa" --mode learned --use-classifier models\learned_light.joblib
```

Run all sources:

```powershell
.\run_cli.bat --source "C:\Music\Salsa" --mode all --use-classifier models\learned_light.joblib
```

Default outputs are:

- Main CSV: `reports/report_main.csv`
- Details CSV: `reports/report_details.csv`
- Progress cache: `progress/music_category_report_progress.json`
- Model comparison CSV: `reports/model_comparison.csv`
- Light classifier: `models/learned_light.joblib`
- Heavy classifier: `models/learned_heavy.pt`
- Log file: `logs/clavetagger.log`

## GUI

Run:

```powershell
.\run_gui.bat
```

The GUI window title is `ClaveTagger`. It supports the same main workflows as the CLI:

- Add one or more source folders.
- Add immediate subfolders from a parent folder.
- Remove selected folders or clear the folder list.
- Recursively preview MP3 files immediately after folder selection.
- Analyze with `tags`, `model`, `both`, `learned`, or `all`.
- Compare all supported audio model presets side by side.
- Estimate runtime.
- Train light or heavy classifiers.
- Evaluate predictions against an existing truth column.
- Suggest config tuning from CSV mismatch evidence.
- Dry-run or apply ID3 `Grouping` / `Color` writes.
- Edit manual corrections and save them to `reports/manual_overrides.csv`.
- Play selected tracks through the optional in-app player, with external-player fallback.

Long-running work runs outside the Tkinter main thread. The table highlights the current row, marks completed / review rows, updates `Processed X/Y`, and supports cooperative abort.

The GUI remembers analysis, training, model, output, and write-option settings in `settings/gui_settings.json` between launches. It intentionally does not remember selected source folders or loaded tracks, so reopening the app does not unexpectedly scan an old library. Dangerous write execution is still opt-in; `Apply write` is not restored as enabled.

On Windows, enable `Prevent sleep while busy` in the Analysis settings to keep the computer awake during long analysis, training, writing, or comparison runs. ClaveTagger releases that request automatically when the task finishes, fails, or is aborted.

Before long GUI actions such as Analyze, Compare Audio Models, and Train classifier, ClaveTagger checks for existing cache/CSV/model output files. You can resume from them or start fresh; fresh mode moves old files into `backups/<timestamp>/` first.

## Classification Modes

- `tags`: classify from ID3 tags, artist, title, album, genre, and filename.
- `model`: classify from the selected Hugging Face audio-classification model.
- `both`: run `tags` and `model`.
- `learned`: use a trained local classifier.
- `all`: run `tags`, `model`, and `learned`.

The default audio model is MAEST: `mtg-upf/discogs-maest-30s-pw-73e-ts`. Pass `--audio-model-id` to use another Hugging Face `audio-classification` model. The model must return labels that can be mapped through `model_labels` in `category_config.json`; otherwise the raw labels still appear in the details CSV, but category mapping may end as `Needs review`.

Pass `--model-full-track` to make the selected audio model analyze the whole song by averaging 30-second chunks. The progress cache key includes both the audio model id and full-track/clip scope, so results from different models are not reused by mistake.

The default recommendation policy is confidence-aware:

1. Manual override
2. Learned high/medium
3. Tag high/medium

In combined modes, audio-model output remains visible in the model columns but does not become the main `recommended_grouping` by itself. Use `--mode model` or an explicit `--recommendation-priority` when you want the selected audio model to drive the recommendation.

Pass `--recommendation-priority manual,learned,tags,model` or another comma-separated order when you want fixed priority instead.

Use `--artifact-policy fresh` when you want a clean run without deleting existing output. Fresh mode moves the relevant files into `backups/<timestamp>/`; default `resume` keeps using compatible cache/CSV data.

## Audio Model Presets

ClaveTagger keeps the model overview in `audio_model_catalog.json`. The rank is a practical preset order for this app, based on expected fit to Latin DJ category mapping, label usefulness, and implementation support. It is not a universal benchmark, and the real winner should still be checked with `--evaluate` against your tagged library.

The GUI Settings tab has an audio model preset picker. Supported Hugging Face `audio-classification` presets fill the `Audio model` field automatically. Future backend entries are documented so they can be implemented later, but selecting them does not make the current audio path run a different backend.

Use `--compare-audio-models` or the GUI action `Actions > Compare Audio Models` when you want a diagnostic run across every supported preset. This writes `reports/model_comparison.csv` by default and the GUI opens a separate comparison window after the run. The comparison uses the same progress cache as normal audio analysis, keyed by model id and clip/full-track scope, so already analyzed files are reused.

| Rank | Model | Status | Speed | Best use |
| ---: | --- | --- | --- | --- |
| 1 | Learned local classifier | supported | depends on backend | Best fit after training on your own tagged library. Use `--mode learned` with a trained `models/learned_light.joblib` or `models/learned_heavy.pt`. |
| 2 | MAEST Discogs 30s 129e | supported | slow | Best public preset candidate for Discogs-style music genre labels when processing time is acceptable. |
| 3 | MAEST Discogs 30s 73e teacher-student | supported | medium | Current default and the most tested preset in this project. |
| 4 | MAEST Discogs 10s 129e | supported | faster | Quicker broad scans; more stable when combined with `--model-full-track`. |
| 5 | MAEST Discogs 5s 129e | supported | fastest MAEST preset | Rough scans and experiments; likely the least stable MAEST option for subtle genre cues. |
| 6 | Custom Hugging Face audio-classification model | supported | varies | Use any compatible Hugging Face audio-classification model id, then map its labels in `category_config.json`. |
| 7 | CLAP HTSAT fused | future backend | heavy | Promising for zero-shot comparison against category names, but it needs a zero-shot audio backend first. |
| 8 | MuQ large MSD | future backend | heavy | Useful candidate for embeddings plus a learned classifier, not a direct category mapper yet. |

The supported MAEST presets are closest to the current implementation because they return Discogs-like labels that can be mapped through `model_labels` in `category_config.json`. CLAP and MuQ are intentionally listed as future backends: they are interesting candidates, but they need different inference code before ClaveTagger can use them directly.

## Category Configuration

Categories, aliases, real tag values, colors, text patterns, and MAEST label mappings live in `category_config.json`.

New styles should be added through that file. For example, `Rumba` can define `Guaguanco` / `Guaguanco`-style aliases and MAEST labels without changing Python code.

Playlist label imports use `playlist_label_patterns` from `category_config.json`. For example, a playlist named `Son` maps to `Son Cubano`, which writes `#Son_Cubano` and `#999999` when the local-file match is high-confidence and approved.

Text classification behavior is also configured there under `text_classification`:

- `use_source_folder`: whether folder names may influence text classification. The default is `false`.
- `minimum_score`: below this score the result becomes `Needs review`.
- `conflict_margin`: if the best two category scores are too close, the result becomes `Needs review`.
- `confidence_thresholds`: score thresholds for `high` and `medium`.
- `weights`: scoring weights for strong/weak genre, filename prefix, folder, and metadata text hits.

Each category can define:

- `category`: display category name.
- `grouping`: actual ID3 grouping value to write.
- `color`: actual color tag value to write.
- `aliases`: values normalized back to this category.
- `tag_patterns`: metadata / filename hints.
- `weak_tag_patterns`: hints that count only as weak evidence, useful for ambiguous words like `salsa`, `pop`, `son`, or artist names that are not always one style.
- `model_labels`: MAEST labels mapped to this category.
- `model_weight`: model score adjustment.

## CSV Reports

The main CSV is meant for review:

- `file_path`, `file_name`, `artist`, `title`, `album`, `genre`
- `id3_grouping`, `id3_grouping_normalized`
- `id3_color`, `id3_color_normalized`
- `tag_suggested_grouping`, `tag_confidence`
- `model_audio_suggested_grouping`, `model_audio_confidence`, `model_audio_bpm`
- `learned_suggested_grouping`, `learned_confidence`
- `recommended_grouping`, `recommended_source`, `recommended_confidence`
- `target_grouping`, `target_color`

The details CSV keeps helper/debug columns:

- `tag_reason`
- `model_audio_top_labels`
- `model_audio_category_scores`
- `model_audio_reason`
- `learned_reason`

## Label Playlist Matching

Use label playlist matching when a playlist name is already your truth label, such as a TIDAL or VirtualDJ playlist named `Son`. ClaveTagger does not read protected streaming audio. Instead, it matches those playlist rows to local MP3 files by strict artist/title similarity, with album/year as extra evidence. Only high-confidence, non-ambiguous matches fill `target_grouping` and `target_color`; everything else remains for review.

Supported label playlist formats:

- VirtualDJ XML / `.vdjfolder`
- M3U / M3U8
- CSV with columns such as `artist`, `title`, `album`, `year`

In the GUI, load or preview your local music folders first, then use **Actions > Match Label Playlist** or the **Match playlist** button above the track table. Choose the exported playlist file(s), then choose the playlist category/genre, for example `Son Cubano`. If you leave the category as `Infer from playlist name`, ClaveTagger uses `playlist_label_patterns` from `category_config.json`, so a playlist named `Son` maps to `Son Cubano`.

GUI matching writes `reports/playlist_label_matches.csv` by default and updates only in-memory `target_grouping` / `target_color` for high-confidence matches. It does not write MP3 tags. Review the pending rows, then use **Write Pending Tags Dry Run** and **Write Pending Tags** when ready.

Example:

```powershell
.\run_cli.bat --source "C:\Users\Zip\Music\DJ\Music Selection" --label-playlist "C:\Users\Zip\Documents\VirtualDJ\My Lists\Son.xml" --label-playlist-output reports\son_playlist_matches.csv
```

Review `reports\son_playlist_matches.csv`. Then dry-run the tag write:

```powershell
.\run_cli.bat --write-tags-from-csv reports\son_playlist_matches.csv --grouping-column target_grouping --color-column target_color
```

Apply only after review:

```powershell
.\run_cli.bat --write-tags-from-csv reports\son_playlist_matches.csv --grouping-column target_grouping --color-column target_color --only-when-empty --apply-write
```

Manual GUI corrections are saved to `reports/manual_overrides.csv` with:

```text
file_path,file_name,artist,title,manual_grouping,manual_color,note,updated_at
```

Load them in CLI with:

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --input-csv reports\report_main.csv --overrides-csv reports\manual_overrides.csv --mode tags
```

## Training

Training is explicit. It is never started by a normal analysis unless you click the GUI training action or pass `--train-classifier`.

Training skips files where normalized `Grouping` is empty.

Do not train only on one newly added category and expect the existing model to update safely. Standard classifiers need at least two categories in the same training run so they can learn boundaries between styles. To add another style later, retrain from a cumulative set: the whole tagged library, or a CSV/folder selection that includes the old tagged categories plus the new tagged category.

### Training Progress And Presets

Training reports progress in both CLI and GUI. Light training shows row/feature collection, fitting, and save phases. Heavy training shows tagged-file scanning, chunk planning, epoch/batch progress, loss, and ETA.

In the GUI, `Training source` controls what gets trained:

- `Current loaded tracks`: use the rows already shown in the table.
- `Selected folders`: reload from selected folders.
- `Input CSV`: reload from the input CSV field.

Classifier presets:

- `Light`: fast classifier from report/detail feature columns; does not read audio.
- `Heavy Fast`: 3 epochs, 8 batch size, up to 2 chunks per tagged file.
- `Heavy Balanced`: 8 epochs, 8 batch size, all tagged files and all chunks.
- `Heavy Thorough`: 15 epochs, 8 batch size, all tagged files and all chunks.

Expert values are used exactly as shown in the GUI after a preset fills them. Empty `Max files` means all tagged files. Empty `Max chunks` means the whole song split into 30-second chunks.

### Light Classifier

Create a model/details report first:

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --source "C:\Music" --mode model
```

Train:

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --input-csv reports\report_main.csv --classifier-input reports\report_details.csv --train-classifier --classifier-preset light --classifier-output models\learned_light.joblib
```

Use:

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --source "C:\Music\Salsa" --mode learned --use-classifier models\learned_light.joblib --classifier-backend light
```

### Heavy Audio Classifier

The heavy backend trains a local PyTorch audio CNN from tagged MP3 audio. It scans source folders recursively and uses full songs split into 30-second chunks.

By default ClaveTagger limits PyTorch CPU work to keep the GUI responsive during heavy training and heavy learned analysis. Override it only when needed:

```powershell
$env:CLAVETAGGER_TORCH_THREADS = "6"
```

Lower values leave more CPU for the GUI and the rest of Windows. Higher values can train faster but may make the computer feel less responsive.

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --source "C:\Music" --train-classifier --classifier-preset heavy-balanced --classifier-output models\learned_heavy.pt
```

Quick experiment:

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --source "C:\Music" --train-classifier --classifier-preset heavy-fast --classifier-output models\learned_heavy.pt
```

Use:

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --source "C:\Music\Salsa" --mode learned --use-classifier models\learned_heavy.pt --classifier-backend heavy
```

## Calibration

Calibration reads existing report CSV files, compares predictions with a truth column, writes a mismatch report, and creates a proposed config file. It does not overwrite `category_config.json`.

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --calibrate-from-csv reports\report_main.csv --truth-column id3_grouping_normalized --calibration-output category_config.tuned.json --mismatch-output reports\calibration_mismatches.csv
```

Review the tuned config before replacing the main config.

## Evaluation

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --input-csv reports\report_main.csv --evaluate --prediction-column recommended_grouping --truth-column id3_grouping_normalized
```

Evaluation prints the selected prediction column and also compares available tag/model/learned/recommended columns.

## Writing Tags

All write commands are dry-run unless `--apply-write` is passed.

Tag writing changes MP3 metadata in place. Use dry-runs first, review the planned changes, and keep your own backup when working with a valuable music library.

Dry-run `Grouping` only:

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --write-grouping-from-csv reports\report_main.csv --value-column target_grouping
```

Apply `Grouping` only:

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --write-grouping-from-csv reports\report_main.csv --value-column target_grouping --apply-write
```

Dry-run `Grouping` and `Color`:

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --write-tags-from-csv reports\report_main.csv --grouping-column target_grouping --color-column target_color
```

Apply only when empty:

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --write-tags-from-csv reports\report_main.csv --grouping-column target_grouping --color-column target_color --only-when-empty --apply-write
```

For reading, `TIT1` is treated as the `Grouping` value. `GRP1` is intentionally ignored. For multi-value `TXXX:Color` frames, the last value is treated as the current color, matching the way VirtualDJ commonly presents the active value.

`Grouping` is written to ID3 `TIT1`; old `GRP1` frames are removed during a write. `Color` is written to `TXXX:Color`.

## Audio Decode Warnings

Some MP3 files contain malformed frames or embedded trailing data. ClaveTagger captures Python warnings where possible, writes details to `logs/clavetagger.log`, and marks failed/zero-length audio as `Needs review`. The original MP3 file is left untouched.

## Tests

Run the full test suite:

```powershell
.venv-maest\Scripts\python.exe -m unittest discover -s tests -v
```

See `TESTING.md` for more examples.

## Repository Notes

Recommended app name: `ClaveTagger`

Recommended git repository name: `clave-tagger`

Do not commit local virtual environments, downloaded model caches, generated reports, logs, progress JSON, or trained model binaries unless there is an intentional release/artifact process.
