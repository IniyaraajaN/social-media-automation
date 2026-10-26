# Bi-weekly Instagram reporting automation

This project contains both parts of the take-home assignment.

## Part 1 - Bi-weekly social reporting

The reporting pipeline:

1. Loads a fictional Instagram post dataset.
2. Stores normalized post metrics in SQLite.
3. Calculates engagement rate, top posts, and change against the preceding 14-day period.
4. Uses the local Ollama model to suggest two caption options and three hashtags for the top post, then creates a one-page PDF report with those ideas.
5. Can be scheduled every two weeks with Windows Task Scheduler.

> The included dataset is simulated. This version does not connect to Instagram or represent real account performance. The timestamps are relative to the report date so the scheduled demo remains populated over time. If Ollama is unavailable, the PDF is still generated and notes that local AI suggestions could not be added.

## Requirements

- Python 3.10 or newer
- `pip`

## Setup

From this project folder in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks virtual-environment activation, run the commands with `python -m pip` directly or use a new PowerShell session with your usual local script policy.

## Run once

```powershell
python -m src.report
```

The program writes:

- `data/reporting.sqlite3` - stored demo posts
- `output/pdf/biweekly_report.pdf` - one-page report
- `output/report_preview.png` - screenshot preview of the report

To create a report for a fixed date:

```powershell
python -m src.report --as-of 2026-10-25
```

## Metric definitions

- Post interactions = likes + comments + shares + saves.
- Post engagement rate = post interactions / post reach × 100.
- Period engagement rate = period interactions / period reach × 100.
- Top 3 posts are ranked by each post's engagement rate.
- The current period is the latest 14 complete days; the previous period is the 14 days immediately before it.
- Total metrics show percent change. Engagement rate shows the difference in percentage points.

## Schedule every two weeks on Windows

After installing the dependency, run this once from PowerShell in the project folder:

```powershell
.\setup_biweekly_task.ps1
```

This registers a task for every other Monday at 9:00 AM local time. The computer must be awake for the report to run. To remove the scheduled task later:

Ollama must be running at report time for the AI ideas to appear. If it is stopped, the report still completes without those suggestions.

```powershell
Unregister-ScheduledTask -TaskName "Social Media Biweekly Demo Report" -Confirm:$false
```

## Project layout

```text
data/mock_posts.json      Fictional input dataset
src/report.py             Ingestion, SQLite storage, calculations, PDF generation
setup_biweekly_task.ps1   Windows Task Scheduler setup
output/                   Generated report output
examples/                  Example AI input JSON
prompts/                   Separate AI prompt
src/ai_analyzer.py         Part 2 local Ollama post analysis CLI
src/web_app.py             Local dashboard web server
web/index.html             Frontend for metrics, Ollama ideas, and PDF preview
tests/test_ai_analyzer.py  Three offline test cases
```

The included Part 1 dataset is simulated. The live Instagram API can be added as a separate data-source adapter after Meta developer access is available.

## Part 2 - Local AI post analysis

The feature accepts one JSON file with a caption and post metrics, then returns JSON containing a 2-3 sentence client summary, two local-AI caption options, and three hashtags. The application calculates verified statistics and checks that the model's summary uses those figures accurately; if the local model gets a figure wrong, the script uses a factual two-sentence fallback. The prompt is kept separately in `prompts/social_post_analysis.txt`.

### Local model setup

Part 2 uses Ollama on this computer, so it does not call the OpenAI API or need an API key. Install and open the Ollama app, then download the local model if it is not already installed:

```powershell
ollama pull qwen2.5:3b
```

The default model is `qwen2.5:3b`. The `.env.example` file documents optional `OLLAMA_BASE_URL` and `OLLAMA_MODEL` settings; copy it to `.env` only if you need to change those defaults. Ollama serves its local chat API at `http://localhost:11434`.

### Run the analyzer

Make sure Ollama is running, then run the example from PowerShell:

```powershell
.\.venv\Scripts\python.exe -m src.ai_analyzer
```

This uses `examples/post_input.json` and prints the result JSON to the terminal. To use a different input file or save the result:

```powershell
.\.venv\Scripts\python.exe -m src.ai_analyzer path\to\post.json --output output\post_analysis.json
```

Input metrics must contain non-negative integer values for `reach`, `likes`, `comments`, `shares`, and `saves`. The caption and metrics are sent only to the local Ollama server on this computer when using the default local setup.

### Test cases

Three offline test cases are included in `tests/test_ai_analyzer.py`: valid analysis output, invalid/missing metrics, and a local model connection failure. They use a fake client and do not call Ollama. Run them with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Local dashboard frontend

Start the local web dashboard from this project folder:

```powershell
.\.venv\Scripts\python.exe -m src.web_app
```

Open `http://127.0.0.1:8765` in your browser. The page shows the current demo metrics and top posts, can request local Ollama ideas, and can generate/open the PDF report. It binds to localhost and uses the mock dataset; it is not a public website or an Instagram account connection. Press `Ctrl+C` in the terminal to stop it.
