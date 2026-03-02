import unittest
from unittest.mock import patch, MagicMock
from main import app, get_available_models


class TestApp(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    @patch("main.requests.get")
    def test_get_available_models_success(self, mock_get):
        # Mocking Ollama's local response locally
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "models": [{"name": "llama3:latest"}, {"name": "mistral"}]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        models = get_available_models()
        self.assertEqual(models, ["llama3:latest", "mistral"])

    @patch("main.requests.get")
    def test_get_available_models_failure(self, mock_get):
        import requests

        mock_get.side_effect = requests.exceptions.RequestException("Connection error")

        models = get_available_models()
        self.assertIsNone(models)

    @patch("main.get_available_models")
    def test_api_models_endpoint(self, mock_get_models):
        mock_get_models.return_value = ["modelA", "modelB"]
        response = self.client.get("/api/models")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"models": ["modelA", "modelB"]})

    def test_api_fetch_no_payload(self):
        response = self.client.post("/api/fetch")
        self.assertEqual(
            response.status_code, 415
        )  # Because of application/json missing

    def test_api_fetch_no_url(self):
        response = self.client.post("/api/fetch", json={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json["error"],
            (
                "No JSON payload provided."
                if response.json.get("error") == "No JSON payload provided."
                else "No URL provided."
            ),
        )

    @patch("main.sync_playwright")
    def test_api_fetch_success(self, mock_playwright):
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_page.content.return_value = "<html><body>Target Page</body></html>"

        mock_browser.new_page.return_value = mock_page
        mock_p.chromium.launch.return_value = mock_browser

        # mock context manager
        mock_playwright.return_value.__enter__.return_value = mock_p

        response = self.client.post("/api/fetch", json={"url": "example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Target Page", response.json["html"])
        self.assertIn("artifacts", response.json)
        mock_page.goto.assert_called_with(
            "https://example.com",
            wait_until="networkidle",
            timeout=15000,
        )

    def test_api_evaluate_missing_payload(self):
        response = self.client.post("/api/evaluate", json={"model": "dummy"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "model or prompt_file missing.")

    @patch("main.requests.post")
    def test_api_evaluate_success_stream(self, mock_post):
        # We need a dummy prompt txt to exist as we check it, or we patch the open builtin
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b'{"response": "Analysis part 1 "}',
            b'{"response": "part 2."}',
            b'{"done": true}',
        ]
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        # Mock opening a file directly to bypass physical prompt files dependency in the test env
        with patch(
            "builtins.open", unittest.mock.mock_open(read_data="Mock Prompt Text")
        ):
            response = self.client.post(
                "/api/evaluate",
                json={
                    "model": "test-model",
                    "prompt_file": "usability.txt",
                    "html": "<p>Test</p>",
                },
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_data(as_text=True)
            self.assertEqual(data, "Analysis part 1 part 2.")

    @patch("main.requests.post")
    def test_api_summarize_success_stream(self, mock_post):
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b'{"response": "| Category | Value |\\n"}',
            b'{"response": "|---|---|"}',
            b'{"done": true}',
        ]
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with patch(
            "builtins.open", unittest.mock.mock_open(read_data="Summarize this:")
        ):
            response = self.client.post(
                "/api/summarize",
                json={"model": "test-model", "text": "Very long text output"},
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_data(as_text=True)
            self.assertIn("Category", data)


if __name__ == "__main__":
    unittest.main()
