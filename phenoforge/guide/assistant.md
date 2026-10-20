# Local AI assistant

The **Assistant** tab lets you ask questions about the current scan in plain language, for
example "Which plant is tallest?" or "Is the leaf area reliable?". It uses a language model
that runs on your own computer through the free program **Ollama**. Nothing leaves your
computer.

The assistant is optional. Everything else in PhenoForge works without it.

## Set up Ollama (once)

1. Download and install Ollama from ollama.com.
2. Open a terminal (PowerShell) and download a model, for example:

   ```
   ollama pull gemma3:4b
   ```

   This is a few GB. Smaller models are faster but less reliable; larger models need more
   memory.
3. Ollama runs in the background after installation.

On university-managed PCs you may need IT to install Ollama.

## Ask a question

1. Open a scan and click **Run analysis** on the [3D analysis](3d-analysis.md) tab. The
   assistant can only answer from results that exist.
2. Open the **Assistant** tab.
3. **Server** is `http://localhost:11434` (Ollama on this computer). Leave it unless Ollama
   runs elsewhere.
4. Click **List models** to fill the **Model** list with the models you have downloaded, and
   choose one. The default is `gemma3:4b`. You can also type a model name.
5. Type your question in the box at the bottom and press Enter or click **Ask**.

The answer appears in the chat area. A first answer can take from a few seconds to a few
minutes, depending on the model and your computer.

## What the assistant sees

With each question PhenoForge sends Ollama a summary of:

- the scan name and whether it is metric,
- all the analysis results (traits, plants, leaves, heads, objects, package details),
- the processing history (what was done to the scan),
- the library metadata, if the scan was opened from the library.

The assistant is told to state units, to say whether the scale is verified, to mention
limits (hidden leaves, leaf candidates, uncalibrated volume), and to say so when the summary
does not contain the answer.

## Use it with care

Language models can be wrong, and can sound confident when they are wrong. Use the
assistant to explore and to explain, and check any number it gives against the result
tables.

If you see "Ollama not reachable at http://localhost:11434", Ollama is not running or not
installed. Start Ollama, then click **List models** again.
