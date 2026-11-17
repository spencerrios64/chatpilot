# chatpilot

Let a local AI model operate your PC: run commands, read and write files, and (optionally) use the mouse and keyboard. One Python file, no dependencies, nothing leaves your machine.

    python chatpilot.py "find the 10 biggest files in my Downloads and list them"

## Setup (Windows)
1. Install [Python](https://python.org) and [Ollama](https://ollama.com).
2. Run \`setup.bat\`. It downloads the default model, **Qwen3-14B Abliterated** (a Heretic-decensored Qwen3-14B tuned for tool use, about 9 GB, fits a 12 GB graphics card).
3. Open a terminal in the folder you want it to work in and run the command above.

## Pick a model
Any OpenAI-compatible server works (\`--url\`), and any model name works (\`--model\`). Abliterated ("heretic") models refuse far less, which matters in an agent loop because one refusal stops the whole chain.

| Your graphics memory | Try |
|---|---|
| 12 GB | \`hf.co/RootMonsteR/Qwen3-14B-Abliterated-GGUF:Q4_K_M\` (default) |
| 6-8 GB | a smaller abliterated model, e.g. \`huihui_ai/qwen3-abliterated:8b\` |
| 24 GB+ | a 27B-35B Heretic build such as \`hf.co/Youssofal/Qwen3.6-27B-Abliterated-Heretic-Uncensored-GGUF:Q4_K_M\` |

Model names change often; check them on ollama.com or huggingface.co before pulling. Smaller models make more mistakes with multi-step work, so start with small tasks.

## Safety (read this)
An uncensored model that controls your computer can delete or change anything you can. chatpilot adds guard rails, but they are not a substitute for care:
- **Ask mode is the default.** Every action is shown and needs a yes. \`a\` approves the rest of the task; \`q\` quits.
- **\`--mode auto\`** skips the questions. Only use it in a throwaway folder or a virtual machine.
- **Always blocked, in every mode:** disk formatting, partitioning, boot config, wiping the registry hives, deleting drive roots or system folders, and similar. This is a pattern list and cannot catch everything.
- **Everything is logged** to \`chatpilot-log.jsonl\` in the folder you run it from.
- **Ctrl+C stops it** immediately.
- Back up anything you care about, and run it with \`--dir\` pointed at the folder it should work in. It is not sandboxed: commands can still reach other folders.
- It reads files and web content it finds, which can contain text that tries to steer the model. Keep ask mode on when it handles content you do not trust.

## Options
\`\`\`
--model NAME     model name (default Qwen3-14B Abliterated)
--url URL        OpenAI-compatible server (default http://localhost:11434/v1)
--mode ask|auto  confirm each action, or not
--dir FOLDER     working folder
--steps N        maximum steps per task (default 30)
--gui            also allow click, type_text and press_key (pip install pyautogui)
\`\`\`
The model cannot see the screen (text only), so mouse control is mostly useful for simple, predictable sequences.

Part of the [chathub](https://spencerrios64.github.io/chathub/) family.
