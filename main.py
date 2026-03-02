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
import json
import logging
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
from playwright.sync_api import sync_playwright

# Set up logging for development errors
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"
PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")


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


@app.route("/api/fetch", methods=["POST"])
def fetch_html():
    """
    Fetches the actual HTML from the input URL.
    To avoid context length limit issues, we truncate the code to 5000 characters.
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
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process"
                ]
            )
            page = browser.new_page()
            
            artifacts = []
            artifact_contents = []
            
            def handle_response(response):
                try:
                    # Collect URLs of resources that load successfully
                    if response.ok:
                        artifacts.append(response.url)
                        req_type = response.request.resource_type
                        if req_type in ["script", "stylesheet"]:
                            text = response.text()
                            if text:
                                # Truncate individual artifacts to prevent blowing up the context completely
                                artifact_contents.append(f"\n\n--- Origin: {response.url} ---\n{text[:3000]}")
                except Exception as e:
                    logger.warning(f"Could not process response for {response.url}: {e}")
            
            page.on("response", handle_response)
            
            # Navigate using networkidle to ensure JavaScript has loaded elements
            page.goto(url, wait_until="networkidle", timeout=15000)
            html_content = page.content()
            browser.close()
            
            full_data = html_content + "".join(artifact_contents)
            # Increase context size dramatically now that we append external resources
            return jsonify({"html": full_data[:40000], "artifacts": artifacts})
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
        with open(prompt_path, "r") as f:
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
            "options": {"num_ctx": 32768}
        }
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
            logger.error(f"Failed to generate feedback for {prompt_file}: {e}")
            yield f"\n\nError connecting to Ollama: {str(e)}"
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON response for {prompt_file}.")
            yield "\n\nError decoding JSON from Ollama payload."

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
        with open(prompt_path, "r") as f:
            system_prompt = f.read().strip()
    except FileNotFoundError:
        return jsonify({"error": "Summary prompt not found."}), 404

    full_prompt = f"{system_prompt}\n\n```text\n{text[:5000]}\n```"

    def generate():
        payload = {"model": model, "prompt": full_prompt, "stream": True}
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
            logger.error(f"Failed to generate summary: {e}")
            yield f"\n\nError connecting to Ollama: {str(e)}"
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON response.")
            yield "\n\nError decoding JSON from Ollama payload."

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
