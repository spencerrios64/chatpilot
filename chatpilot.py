#!/usr/bin/env python3
"""chatpilot - let a local AI model operate your PC (shell, files, optional mouse/keyboard).

    python chatpilot.py "clean up my Downloads folder by file type"
    python chatpilot.py                      # interactive: type tasks one after another
    python chatpilot.py --mode auto "..."    # no per-action prompts (catastrophic commands stay blocked)

Needs only Python 3.8+ and a local OpenAI-compatible server (Ollama, LM Studio, llama.cpp).
Everything the model does is logged to chatpilot-log.jsonl. Press Ctrl+C at any time to stop.
"""
import argparse, json, os, platform, re, subprocess, sys, time, urllib.request, urllib.error

DEFAULT_MODEL = "hf.co/RootMonsteR/Qwen3-14B-Abliterated-GGUF:Q4_K_M"
DEFAULT_URL = "http://localhost:11434/v1"
LOG = "chatpilot-log.jsonl"
MAX_OUT = 4000

# Commands that are never run, in any mode: they wipe disks, system files or boot config.
BLOCK = [
    r"\bformat\s+[a-z]:", r"\bdiskpart\b", r"\bbcdedit\b", r"\bcipher\s+/w", r"\bmkfs(\.\w+)?\b",
    r"\bdd\b[^\n]*\bof=/dev/", r"rm\s+(-\w+\s+)*-\w*[rf]\w*\s+(/|~|\*|/\*|\$HOME)\s*($|;|&|\|)",
    r"(del|erase)\s+[^\n]*(/s)[^\n]*\b[a-z]:\\\s*($|\s)", r"(rd|rmdir)\s+(/s\s*)?(/q\s*)?[a-z]:\\\s*($|\s)",
    r"remove-item\s+[^\n]*-recurse[^\n]*\b[a-z]:\\\s*($|\s|')", r"reg\s+delete\s+hk(lm|cr)\b",
    r":\(\)\s*\{", r"remove-item[^\n]*c:\\windows", r"(del|rd|rmdir|rm)\b[^\n]*c:\\windows",
    r"\b(sfc|dism)\b[^\n]*(/remove|/cleanup)", r"\bwipefs\b", r"\bshred\b[^\n]*/dev/",
]

TOOLS = """Tools (call exactly one per turn):
- shell    {"command": "...", "timeout": 60}     run a command in the shell, returns output
- read_file  {"path": "..."}                     read a text file
- write_file {"path": "...", "content": "..."}   create or overwrite a text file
- list_dir   {"path": "."}                       list a folder
- done       {"summary": "..."}                  finish the task and report to the user"""
GUI_TOOLS = """- click      {"x": 100, "y": 200, "button": "left"}   click the screen
- type_text  {"text": "..."}                     type on the keyboard
- press_key  {"keys": "ctrl+s"}                  press a key or combination"""


def system_prompt(workdir, gui):
    return (
        "You are an autonomous agent operating the user's computer to complete their task.\n"
        "OS: %s. Working folder: %s. Shell: %s.\n\n%s\n%s\n\n"
        "Reply with ONE JSON object and nothing else, like:\n"
        '{"thought": "short reasoning", "tool": "shell", "args": {"command": "dir"}}\n'
        "After each tool call you will get its result. Work step by step, check your results, "
        "and when the task is complete call done. Keep commands non-interactive."
        % (platform.platform(), workdir,
           "cmd.exe (use powershell -Command for PowerShell)" if os.name == "nt" else "sh",
           TOOLS, GUI_TOOLS if gui else "")
    )


def log(entry):
    entry["t"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def chat(url, model, key, messages):
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.3, "stream": False}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/chat/completions", body,
                                 {"Content-Type": "application/json", **({"Authorization": "Bearer " + key} if key else {})})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["choices"][0]["message"]["content"] or ""


def parse_action(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc: esc = False
                elif c == "\\": esc = True
                elif c == '"': in_str = False
            elif c == '"': in_str = True
            elif c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                        if isinstance(obj, dict) and "tool" in obj:
                            return obj
                    except ValueError:
                        pass
                    break
        start = text.find("{", start + 1)
    return None


def blocked(cmd):
    low = cmd.lower()
    return any(re.search(p, low) for p in BLOCK)


def clip(s):
    s = s if isinstance(s, str) else str(s)
    return s if len(s) <= MAX_OUT else s[:MAX_OUT // 2] + "\n...[%d chars cut]...\n" % (len(s) - MAX_OUT) + s[-MAX_OUT // 2:]


def describe(tool, args):
    if tool == "shell": return "RUN   " + str(args.get("command", ""))
    if tool == "write_file": return "WRITE %s (%d chars)" % (args.get("path"), len(str(args.get("content", ""))))
    return "%s %s" % (tool.upper(), json.dumps(args, ensure_ascii=False)[:200])


def run_tool(tool, args, workdir, gui):
    try:
        if tool == "shell":
            cmd = str(args.get("command", ""))
            if blocked(cmd):
                return "BLOCKED: this command matches the catastrophic-command blocklist and will not be run."
            p = subprocess.run(cmd, shell=True, cwd=workdir, capture_output=True, text=True, errors="replace",
                               timeout=float(args.get("timeout", 60)))
            return clip("exit code %d\n%s%s" % (p.returncode, p.stdout, ("\n[stderr]\n" + p.stderr) if p.stderr else ""))
        if tool == "read_file":
            with open(os.path.join(workdir, str(args["path"])), encoding="utf-8", errors="replace") as f:
                return clip(f.read())
        if tool == "write_file":
            path = os.path.join(workdir, str(args["path"]))
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(str(args.get("content", "")))
            return "wrote %s" % path
        if tool == "list_dir":
            p = os.path.join(workdir, str(args.get("path", ".")))
            return clip("\n".join(("[dir] " if os.path.isdir(os.path.join(p, n)) else "      ") + n for n in sorted(os.listdir(p))))
        if gui and tool in ("click", "type_text", "press_key"):
            import pyautogui
            if tool == "click": pyautogui.click(int(args["x"]), int(args["y"]), button=args.get("button", "left"))
            elif tool == "type_text": pyautogui.write(str(args["text"]), interval=0.02)
            else: pyautogui.hotkey(*str(args["keys"]).lower().replace(" ", "").split("+"))
            return "ok"
        return "Unknown tool '%s'." % tool
    except subprocess.TimeoutExpired:
        return "Command timed out."
    except Exception as e:  # report to the model so it can adapt
        return "Error: %s: %s" % (type(e).__name__, e)


def agent(task, a, workdir, gui):
    msgs = [{"role": "system", "content": system_prompt(workdir, gui)}, {"role": "user", "content": task}]
    log({"task": task, "model": a.model, "mode": a.mode})
    approve_all = a.mode == "auto"
    bad = 0
    for step in range(1, a.steps + 1):
        try:
            reply = chat(a.url, a.model, a.key, msgs)
        except (urllib.error.URLError, OSError) as e:
            print("Cannot reach the model server at %s (%s). Is Ollama running?" % (a.url, e)); return
        act = parse_action(reply)
        if not act:
            bad += 1
            if bad > 3: print("The model keeps replying without a valid action. Stopping."); return
            msgs += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": 'Reply with ONE JSON object: {"thought": "...", "tool": "...", "args": {...}}'}]
            continue
        bad = 0
        tool, args = str(act.get("tool")), act.get("args") or {}
        if act.get("thought"): print("\n[%d] %s" % (step, act["thought"]))
        if tool == "done":
            print("\nDONE: " + str(args.get("summary", ""))); log({"done": args}); return
        print("    " + describe(tool, args))
        if not approve_all:
            ans = input("    run it? [y]es / [n]o / [a]ll from now / [q]uit > ").strip().lower()
            if ans == "q": print("Stopped."); return
            if ans == "a": approve_all = True
            elif ans != "y":
                result = "The user declined this action. Choose another approach or call done."
                msgs += [{"role": "assistant", "content": reply}, {"role": "user", "content": "Tool result:\n" + result}]
                log({"step": step, "tool": tool, "args": args, "declined": True}); continue
        result = run_tool(tool, args, workdir, gui)
        print("    -> " + result[:300].replace("\n", "\n       "))
        log({"step": step, "tool": tool, "args": args, "result": result[:2000]})
        msgs += [{"role": "assistant", "content": reply}, {"role": "user", "content": "Tool result:\n" + result}]
    print("Reached the step limit (%d). Run again to continue." % a.steps)


def main():
    ap = argparse.ArgumentParser(description="Let a local AI model operate your PC.")
    ap.add_argument("task", nargs="*", help="what you want done (omit for interactive mode)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--url", default=DEFAULT_URL, help="OpenAI-compatible base URL")
    ap.add_argument("--key", default=os.environ.get("OPENAI_API_KEY", ""))
    ap.add_argument("--mode", choices=["ask", "auto"], default="ask", help="ask = confirm each action (default)")
    ap.add_argument("--dir", default=os.getcwd(), help="working folder (default: current folder)")
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--gui", action="store_true", help="also allow mouse/keyboard control (needs: pip install pyautogui)")
    a = ap.parse_args()
    workdir = os.path.abspath(a.dir)
    if a.gui:
        try: import pyautogui  # noqa: F401
        except ImportError: print("--gui needs pyautogui:  pip install pyautogui"); return 1
    print("chatpilot | model: %s | mode: %s | folder: %s\nCtrl+C stops it. Actions are logged to %s" % (a.model, a.mode, workdir, LOG))
    try:
        if a.task: agent(" ".join(a.task), a, workdir, a.gui)
        else:
            while True:
                t = input("\ntask (blank to quit) > ").strip()
                if not t: break
                agent(t, a, workdir, a.gui)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
