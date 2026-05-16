# Testing

ClaveTagger uses Python's built-in `unittest` framework. No extra test runner is required.

## Run All Tests

From the project root:

```powershell
.venv-maest\Scripts\python.exe -m unittest discover -s tests -v
```

or on Windows:

```powershell
.\test.bat
```

## Run One Test File

```powershell
.venv-maest\Scripts\python.exe -m unittest tests.test_config -v
.venv-maest\Scripts\python.exe -m unittest tests.test_classification -v
.venv-maest\Scripts\python.exe -m unittest tests.test_learning -v
.venv-maest\Scripts\python.exe -m unittest tests.test_heavy_model -v
.venv-maest\Scripts\python.exe -m unittest tests.test_gui_services -v
.venv-maest\Scripts\python.exe -m unittest tests.test_hardening -v
```

## Run One Test Case

```powershell
.venv-maest\Scripts\python.exe -m unittest tests.test_classification.ClassificationTests.test_text_classifier_maps_guaguanco_to_rumba -v
```

## What The Unit Tests Cover

- Category config loading, aliases, `Grouping`, and `Color` mapping.
- Text classification rules such as `Guaguanco -> Rumba`.
- MAEST label mapping rules without running the actual MAEST model.
- Confidence-aware recommendation policy and manual override priority.
- Light learned-classifier feature parsing.
- Heavy classifier dispatch and whole-track chunk planning.
- GUI service workflow logic without opening Tkinter windows.
- Runtime path defaults, `.gitignore` hygiene, calibration output, and decode-error handling.
- Native decoder stderr capture so malformed MP3 messages go to the log instead of flooding the console.

## What The Unit Tests Intentionally Avoid

The unit tests do not run long audio inference or full heavy training. Those are integration/manual workflows because they can take a long time and depend on local audio files, hardware, and model downloads.

Useful manual checks:

```powershell
.venv-maest\Scripts\python.exe music_category_report.py --source "C:\Music\Salsa" --mode tags --estimate-only
.venv-maest\Scripts\python.exe music_category_report.py --source "C:\Music\Salsa" --mode model --output-csv reports\report_main.csv --details-csv reports\report_details.csv
.venv-maest\Scripts\python.exe music_category_report.py --source "C:\Music" --train-classifier --classifier-backend heavy --classifier-output models\learned_heavy.pt --heavy-max-files 20 --heavy-max-chunks-per-file 2
.venv-maest\Scripts\python.exe music_category_report.py --calibrate-from-csv reports\report_main.csv --calibration-output category_config.tuned.json
```
