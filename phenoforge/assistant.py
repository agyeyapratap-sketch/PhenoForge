"""Optional local LLM assistant through Ollama (http://localhost:11434).

Questions about the current scan are answered from its traits, metadata and processing
history, sent only to the Ollama server on this computer. Nothing is sent anywhere else.
"""

from __future__ import annotations

import json
import urllib.request

DEFAULT_URL = "http://localhost:11434"

SYSTEM = (
    "You are a plant phenotyping assistant inside a desktop analysis app. Answer from the scan "
    "summary provided. Be explicit about units, about whether the scan has a verified metric scale, "
    "and about limitations (occlusion, leaf candidates are not guaranteed biological leaves, voxel "
    "volume needs calibration against harvest data). If the summary does not contain the answer, say so."
)


def list_models(url: str = DEFAULT_URL, timeout: float = 3.0) -> list[str]:
    with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout) as r:
        return [m["name"] for m in json.loads(r.read())["models"]]


def ask(question: str, context: dict, model: str = "gemma3:4b", url: str = DEFAULT_URL, timeout: float = 300.0) -> str:
    body = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Scan summary (JSON):\n" + json.dumps(context, indent=1, default=str)[:30000]
             + "\n\nQuestion: " + question},
        ],
    }
    req = urllib.request.Request(f"{url}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]
