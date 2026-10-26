# Loom walkthrough: what to show and say

Target length: about 3 minutes 45 seconds. Keep the dashboard, terminal, project folder, and report ready before recording. The webcam is optional; make sure your microphone works.

## Before recording

- Open the dashboard at `http://127.0.0.1:8765/` and confirm it shows the demo data and Ollama status.
- Keep a PowerShell window open in the project folder.
- Have `examples/post_input.json`, `prompts/social_post_analysis.txt`, `README.md`, and `output/pdf/biweekly_report.pdf` ready to open.
- Do not show `.env`, credentials, or account settings. The dataset is fictional; say that clearly.

## 0:00-0:25 — Introduce the project

**Show:** Start on the dashboard's top section, with the project title and the demo-data notice visible.

**Say:**

> This take-home has two parts: a scheduled social reporting pipeline and a small local AI feature. I built both in Python. This demo uses fictional Instagram-style data, which the assignment allows, so it is not connected to a real Instagram account.

## 0:25-1:35 — Part 1: scheduled report

**Show, in this order:**

1. Dashboard metric cards and reporting-period comparison.
2. The top-three posts table; point out the interaction and engagement-rate values.
3. Click **Get Ollama ideas** and briefly show the ideas, then click **Generate PDF report**.
4. Scroll to the PDF preview or click **Open PDF**. Point out the two periods, ranked posts, and AI ideas section.
5. If time allows, show Windows Task Scheduler → **Task Scheduler Library** → `Social Media Biweekly Demo Report`, including its every-other-Monday trigger.

**Say:**

> The report pipeline loads post dates, types, reach, likes, comments, shares, and saves from `data/mock_posts.json`. It stores the posts in SQLite, calculates interaction and engagement figures, compares two completed 14-day periods, ranks the top three posts, and creates a one-page PDF. Windows Task Scheduler is set to run it every other Monday. The report still completes if Ollama is unavailable; it then notes that AI ideas could not be added.

## 1:35-2:45 — Part 2: local AI analysis

**Show, in this order:**

1. Open `examples/post_input.json` and point out the caption and five metrics.
2. Open `prompts/social_post_analysis.txt` to show the prompt is kept separately.
3. In PowerShell, run:

```powershell
.\.venv\Scripts\python.exe -m src.ai_analyzer
```

4. Show the returned JSON with the performance summary, two captions, and three hashtags.

**Say:**

> Part 2 accepts one post as JSON. The separate prompt guides Ollama, which runs on this computer, to suggest two caption options and three hashtags. The program checks the response and verifies its summary against figures calculated from the input. If the model gets the arithmetic wrong, the program uses a factual fallback so the reported numbers stay correct.

Do not describe mock data as live Instagram data or the fallback summary as model-written.

## 2:45-3:25 — Reliability and code

**Show, in this order:**

1. In PowerShell, run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

2. Show the passing test results.
3. Briefly show `README.md`'s setup/run instructions and the local dashboard instructions.

**Say:**

> There are three offline tests for valid output, bad input, and a model failure. I ran them successfully. The README explains setup and run steps. The frontend is a local dashboard for viewing metrics, requesting ideas, and opening the report.

## 3:25-3:45 — Close

**Show:** Return to the dashboard or the project README.

**Say:**

> The current version demonstrates the complete workflow with mock data and a local model. A live account source could replace the mock input after Meta developer access is available.
