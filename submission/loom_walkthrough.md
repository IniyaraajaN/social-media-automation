# 3-5 minute walkthrough script

## Before recording

- Start Ollama and confirm the local model is available.
- Start the dashboard with `.\.venv\Scripts\python.exe -m src.web_app` and open `http://127.0.0.1:8765`.
- Have the latest PDF, `output/pdf/biweekly_report.pdf`, ready to show.
- Do not show `.env`, credentials, or account settings.

## Suggested narration

### 0:00-0:25 - Introduce the project

"This take-home has two parts: a scheduled social reporting pipeline and a small local AI feature. I built both in Python. This demo uses fictional Instagram-style data, which the assignment allows, so it is not connected to a real Instagram account."

### 0:25-1:35 - Walk through Part 1

"The report pipeline loads post dates, types, reach, likes, comments, shares, and saves from `data/mock_posts.json`. It stores the posts in SQLite, calculates interaction and engagement figures, compares two completed 14-day periods, ranks the top three posts, and creates a one-page PDF. Windows Task Scheduler is set to run it every other Monday."

Show the dashboard cards and top-three table, then open the PDF. Point out the period comparison, ranked posts, and local AI ideas section. Explain that the report still completes if Ollama is unavailable; the AI ideas are then omitted with a status message.

### 1:35-2:45 - Walk through Part 2

"Part 2 accepts one post as JSON. The separate prompt guides Ollama, which runs on this computer, to suggest two caption options and three hashtags. The program checks the response and verifies its summary against interaction and engagement figures calculated from the input. If the model gets the arithmetic wrong, it uses a factual fallback so the reported numbers stay correct."

Show `examples/post_input.json`, then run:

```powershell
.\.venv\Scripts\python.exe -m src.ai_analyzer
```

Briefly show the JSON output. Do not describe the mock data as live Instagram data or the fallback summary as model-written.

### 2:45-3:25 - Reliability and code

"There are three offline tests for valid output, bad input, and a model failure. I ran them successfully. The README explains setup and run steps. The frontend is a local dashboard for viewing the metrics, requesting ideas, and opening the report."

If time allows, show the passing test output and the separate prompt file `prompts/social_post_analysis.txt`.

### 3:25-3:45 - Close

"The current version demonstrates the complete workflow with mock data and a local model. A live account source could replace the mock input after Meta developer access is available."
