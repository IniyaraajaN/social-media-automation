"""Analyze one social post with a local Ollama model and return structured JSON."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "examples" / "post_input.json"
DEFAULT_PROMPT = ROOT / "prompts" / "social_post_analysis.txt"
DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
REQUIRED_METRICS = ("reach", "likes", "comments", "shares", "saves")

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "performance_summary": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
        "caption_options": {"type": "array", "items": {"type": "string"}},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["performance_summary", "caption_options", "hashtags"],
    "additionalProperties": False,
}


class InputValidationError(ValueError):
    """Raised when the input JSON does not match the expected post shape."""


class AnalysisAPIError(RuntimeError):
    """Raised when the model request fails or returns unusable output."""


def _request_local_model(messages: list[dict[str, str]], model: str, client: Any | None) -> str:
    try:
        if client is not None:
            response = client.chat(
                model=model,
                messages=messages,
                format="json",
                stream=False,
                options={"temperature": 0.5},
            )
        else:
            base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL).strip().rstrip("/")
            request_body = json.dumps(
                {
                    "model": model,
                    "messages": messages,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.5},
                }
            ).encode("utf-8")
            request = urllib.request.Request(
                f"{base_url}/api/chat",
                data=request_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=300) as http_response:
                response = json.loads(http_response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        if exc.code == 404 and "model" in detail.lower():
            raise AnalysisAPIError(
                f"Ollama does not have model '{model}'. Download it with: ollama pull {model}"
            ) from exc
        raise AnalysisAPIError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AnalysisAPIError(
            "Cannot connect to Ollama at localhost:11434. Start the Ollama app, then try again."
        ) from exc
    except Exception as exc:
        raise AnalysisAPIError(f"The local model request failed ({type(exc).__name__}): {exc}") from exc

    if isinstance(response, dict):
        output_text = response.get("message", {}).get("content")
    else:
        message = getattr(response, "message", None)
        output_text = getattr(message, "content", None)
    if not isinstance(output_text, str) or not output_text.strip():
        raise AnalysisAPIError("The local model returned no JSON output. Try running the example again.")
    return output_text


def load_local_env(env_path: Path = ROOT / ".env") -> None:
    """Load simple KEY=VALUE entries without replacing existing environment values."""
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key in {"OLLAMA_BASE_URL", "OLLAMA_MODEL"}:
            os.environ.setdefault(key, value)


def validate_input(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputValidationError("Input must be a JSON object.")

    caption = payload.get("caption")
    if not isinstance(caption, str) or not caption.strip():
        raise InputValidationError("'caption' must be a non-empty string.")
    if len(caption) > 2200:
        raise InputValidationError("'caption' must be 2,200 characters or fewer.")

    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        raise InputValidationError("'metrics' must be a JSON object.")

    missing = [key for key in REQUIRED_METRICS if key not in metrics]
    if missing:
        raise InputValidationError("Missing metric(s): " + ", ".join(missing) + ".")

    normalized_metrics: dict[str, Any] = {}
    for key in REQUIRED_METRICS:
        value = metrics[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise InputValidationError(f"Metric '{key}' must be a non-negative integer.")
        if value < 0:
            raise InputValidationError(f"Metric '{key}' must be a non-negative integer.")
        normalized_metrics[key] = value

    post_type = payload.get("post_type")
    if post_type is not None:
        if not isinstance(post_type, str) or not post_type.strip():
            raise InputValidationError("'post_type' must be a non-empty string when provided.")
        normalized_post_type: str | None = post_type.strip()
    else:
        normalized_post_type = None

    normalized: dict[str, Any] = {
        "caption": caption.strip(),
        "metrics": normalized_metrics,
    }
    if normalized_post_type is not None:
        normalized["post_type"] = normalized_post_type
    return normalized


def validate_output(payload: Any, verified_stats: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AnalysisAPIError("The model response was not a JSON object.")
    required = {"performance_summary", "caption_options", "hashtags"}
    if set(payload) != required:
        raise AnalysisAPIError("The model response did not contain the required JSON fields.")

    summary_parts = payload["performance_summary"]
    if (
        not isinstance(summary_parts, list)
        or len(summary_parts) != 2
        or any(not isinstance(item, str) or not item.strip() for item in summary_parts)
    ):
        raise AnalysisAPIError("The performance summary must contain exactly two non-empty sentence strings.")
    for item in summary_parts:
        sentence_count = len(re.findall(r"[.!?](?:[\"')\]]*)?(?:\s|$)", item.strip()))
        if sentence_count > 1:
            raise AnalysisAPIError("Each performance summary item must contain only one sentence.")
    normalized_parts = [item.strip() for item in summary_parts]
    normalized_parts = [part if part[-1] in ".!?" else part + "." for part in normalized_parts]
    summary = " ".join(normalized_parts)

    compact_summary = re.sub(r"(?<=\d),(?=\d)", "", summary)
    reach = verified_stats["reach"]
    interactions = verified_stats["interactions"]
    if not re.search(rf"(?<!\d){reach}(?!\d)", compact_summary):
        raise AnalysisAPIError(f"The summary must state the verified reach of {reach:,}.")
    if not re.search(rf"(?<!\d){interactions}(?!\d)", compact_summary):
        raise AnalysisAPIError(f"The summary must state the verified {interactions:,} interactions.")
    if verified_stats["engagement_rate_percent"] is None:
        if "cannot be calculated" not in summary.casefold():
            raise AnalysisAPIError("The summary must say engagement rate cannot be calculated when reach is zero.")
    else:
        rate_label = f"{verified_stats['engagement_rate_percent']:.1f}%"
        if rate_label not in compact_summary:
            raise AnalysisAPIError(f"The summary must use the verified engagement rate of {rate_label}.")

    captions = payload["caption_options"]
    if (
        not isinstance(captions, list)
        or len(captions) != 2
        or any(not isinstance(item, str) or not item.strip() for item in captions)
    ):
        raise AnalysisAPIError("The model response must contain exactly two non-empty caption options.")
    normalized_captions = [re.sub(r"[\W_]+", "", item.casefold()) for item in captions]
    if normalized_captions[0] == normalized_captions[1]:
        raise AnalysisAPIError("The two caption options must be distinct, not duplicates.")

    hashtags = payload["hashtags"]
    if (
        not isinstance(hashtags, list)
        or len(hashtags) != 3
        or any(not isinstance(tag, str) or not re.fullmatch(r"#\S+", tag.strip()) for tag in hashtags)
    ):
        raise AnalysisAPIError("The model response must contain exactly three hashtags, each starting with #.")

    return {
        "performance_summary": summary,
        "caption_options": [item.strip() for item in captions],
        "hashtags": [tag.strip() for tag in hashtags],
    }


def factual_summary_parts(post: dict[str, Any]) -> list[str]:
    """Return a two-sentence fallback using only application-calculated metrics."""
    metrics = post["metrics"]
    reach = metrics["reach"]
    interactions = sum(metrics[key] for key in ("likes", "comments", "shares", "saves"))
    if reach == 0:
        return [
            f"The post received {interactions:,} interactions across likes, comments, shares, and saves.",
            "An engagement rate cannot be calculated because reach is zero.",
        ]
    engagement_rate = interactions / reach * 100
    return [
        f"The post reached {reach:,} accounts and received {interactions:,} interactions.",
        f"Its engagement rate was {engagement_rate:.1f}%.",
    ]


def analyze_post(
    payload: Any,
    *,
    client: Any | None = None,
    prompt_path: Path = DEFAULT_PROMPT,
    model: str | None = None,
) -> dict[str, Any]:
    post = validate_input(payload)
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise AnalysisAPIError("The prompt file is empty.")

    load_local_env()
    chosen_model = (model or os.getenv("OLLAMA_MODEL") or DEFAULT_MODEL).strip()
    if not chosen_model:
        raise AnalysisAPIError("OLLAMA_MODEL cannot be empty.")

    metrics = post["metrics"]
    total_interactions = sum(metrics[key] for key in ("likes", "comments", "shares", "saves"))
    verified_stats = {
        "reach": metrics["reach"],
        "interactions": total_interactions,
        "engagement_rate_percent": (total_interactions / metrics["reach"] * 100) if metrics["reach"] else None,
    }
    request_payload = {"post": post, "verified_statistics": verified_stats}
    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": "Analyze this post JSON and return only a JSON object matching this structure: "
            + json.dumps(OUTPUT_SCHEMA, ensure_ascii=False)
            + "\nPost data and statistics calculated by the application (use these figures exactly):\n"
            + json.dumps(request_payload, ensure_ascii=False),
        },
    ]

    for attempt in range(3):
        output_text = _request_local_model(messages, chosen_model, client)
        try:
            output = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise AnalysisAPIError("The model response was not valid JSON.") from exc
        try:
            return validate_output(output, verified_stats)
        except AnalysisAPIError as exc:
            if "summary" in str(exc).casefold():
                output["performance_summary"] = factual_summary_parts(post)
                return validate_output(output, verified_stats)
            if attempt < 2:
                messages.extend(
                    [
                        {"role": "assistant", "content": output_text},
                        {
                            "role": "user",
                            "content": f"The previous JSON failed validation: {exc} "
                            "Return a corrected JSON object. performance_summary must be an array of exactly "
                            "two strings, one complete sentence per string, and use the verified statistics "
                            "from the original input exactly; do not "
                            "invent audience reactions, causes, benchmarks, or trends. caption_options must be "
                            "an array of exactly two distinct non-empty strings. hashtags must be an array of "
                            "exactly three strings, each starting with # and containing no spaces. Preserve the "
                            "required field names and do not add text outside JSON.",
                        },
                    ]
                )
                continue
            raise
    raise AnalysisAPIError("The local model could not produce valid output after two correction attempts.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze one social post using a local Ollama model.")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT, help="JSON file with caption and metrics.")
    parser.add_argument("--output", type=Path, help="Optional path to write the result JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        error = f"Cannot read input JSON file: {exc}"
        sys.stderr.write(json.dumps({"error": error}, ensure_ascii=False) + "\n")
        return 2

    try:
        result = analyze_post(payload)
    except InputValidationError as exc:
        sys.stderr.write(json.dumps({"error": f"Invalid input: {exc}"}, ensure_ascii=False) + "\n")
        return 2
    except AnalysisAPIError as exc:
        sys.stderr.write(json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n")
        return 2

    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            sys.stderr.write(json.dumps({"error": f"Cannot write output JSON file: {exc}"}, ensure_ascii=False) + "\n")
            return 2
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
