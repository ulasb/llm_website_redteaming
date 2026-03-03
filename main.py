"""
This code was created and published by Ulaş Bardak.
It is licensed under the Mozilla Public License 2.0 (MPL 2.0).
This means that you can use, modify, and distribute this code,
but any modifications to these files must also be made available
under the MPL 2.0.

This script runs a Flask server that evaluates a provided URL using an Ollama model
for usability, performance, best practices, and security vulnerabilities.
"""

import os
import asyncio
import json
import logging
import uuid
from typing import List, Optional
import requests
from flask import (
    Flask,
    request,
    render_template,
    jsonify,
    Response,
    stream_with_context,
)
from browser_use import Browser

# Set up logging for development errors
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"
PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
SCREENSHOTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "screenshots"
)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# Magic string constants parsed for operations:
TOTAL_CONTENT_TRUNCATION_LIMIT = 40000


def get_available_models() -> Optional[List[str]]:
    """
    Fetches the list of available models from the local Ollama instance.

    Returns
    -------
    Optional[List[str]]
        A list of model names or None if an error occurred.
    """
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        response.raise_for_status()
        data = response.json()
        models = [model.get("name") for model in data.get("models", [])]
        return [m for m in models if m is not None]
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch models from Ollama: {e}")
        return None


def stream_ollama_response(payload: dict, error_context: str):
    """Refactored internal helper to securely push payload generation loops cleanly without overlapping context"""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if line:
                chunk = json.loads(line)
                if "response" in chunk:
                    yield chunk["response"]
                if chunk.get("done"):
                    break
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to generate feedback for {error_context}: {e}")
        yield f"\n\nError connecting to Ollama: {str(e)}"
    except json.JSONDecodeError:
        logger.error(f"Failed to decode JSON response for {error_context}.")
        yield "\n\nError decoding JSON from Ollama payload."


@app.route("/")
def index():
    """Serves the main frontend application."""
    return render_template("index.html")


@app.route("/api/models")
def models():
    """Returns the available Ollama models in JSON format."""
    models_list = get_available_models()
    if models_list is None:
        return jsonify({"models": [], "error": "Could not fetch models"}), 500
    return jsonify({"models": models_list})


async def fetch_page_with_agent(url: str) -> dict:
    """
    Uses browser-use's Browser to load a page, capture its rendered HTML,
    and take a screenshot.
    """
    browser = Browser(headless=True)
    await browser.start()
    try:
        await browser.navigate_to(url)
        page = await browser.get_current_page()
        html_content = await page.evaluate(
            "() => document.documentElement.outerHTML"
        )
        screenshot_bytes = await browser.take_screenshot()
        filename = f"{uuid.uuid4().hex}.png"
        filepath = os.path.join(SCREENSHOTS_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(screenshot_bytes)
        return {
            "html": html_content[:TOTAL_CONTENT_TRUNCATION_LIMIT],
            "screenshot": filename,
        }
    finally:
        await browser.stop()


@app.route("/api/fetch", methods=["POST"])
def fetch_html():
    """
    Fetches the rendered HTML and a screenshot from the input URL using browser-use.
    To avoid context length limit issues, we truncate the content to 40000 characters.
    """
    data = request.json
    if not data:
        return jsonify({"error": "No JSON payload provided."}), 400

    url = data.get("url")
    if not url:
        return jsonify({"error": "No URL provided."}), 400

    if not url.startswith("http"):
        url = "https://" + url

    try:
        result = asyncio.run(fetch_page_with_agent(url))
        return jsonify(result)
    except Exception as e:
        logger.error(f"Failed to load URL {url}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/evaluate", methods=["POST"])
def evaluate():
    """
    Evaluates the HTML against a specific prompt text from the prompts directory
    using local Ollama inference. This streams the text back to the frontend.
    """
    data = request.json
    if not data:
        return jsonify({"error": "No JSON payload provided."}), 400

    model = data.get("model")
    prompt_file = data.get("prompt_file")
    html_content = data.get("html", "")

    if not model or not prompt_file:
        return jsonify({"error": "model or prompt_file missing."}), 400

    prompt_path = os.path.join(PROMPTS_DIR, prompt_file)
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read().strip()
    except FileNotFoundError:
        return jsonify({"error": f"Prompt file {prompt_file} not found."}), 404

    full_prompt = f"{system_prompt}\n\n```html\n{html_content}\n```"

    def generate():
        # Add options to drastically increase the LLM Context Window to ingest all files
        payload = {
            "model": model,
            "prompt": full_prompt,
            "stream": True,
            "options": {"num_ctx": 32768},
        }
        yield from stream_ollama_response(payload, prompt_file)

    return Response(stream_with_context(generate()), content_type="text/plain")


@app.route("/api/summarize", methods=["POST"])
def summarize():
    """
    Summarizes the generated evaluation.
    """
    data = request.json
    if not data:
        return jsonify({"error": "No JSON payload provided."}), 400

    model = data.get("model")
    text = data.get("text", "")

    if not model:
        return jsonify({"error": "model missing."}), 400

    prompt_path = os.path.join(PROMPTS_DIR, "summary.txt")
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read().strip()
    except FileNotFoundError:
        return jsonify({"error": "Summary prompt not found."}), 404

    full_prompt = (
        f"{system_prompt}\n\n```text\n{text[:TOTAL_CONTENT_TRUNCATION_LIMIT]}\n```"
    )

    def generate():
        payload = {"model": model, "prompt": full_prompt, "stream": True}
        yield from stream_ollama_response(payload, "summary.txt")

    return Response(stream_with_context(generate()), content_type="text/plain")


def main() -> int:
    """
    Entrypoint which launches the development Flask server across port 5000.
    """
    logger.info("Starting Flask application across 127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
