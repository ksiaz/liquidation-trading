#!/usr/bin/env python3
"""
MCP Server: Consult LLMs (Gemini/Llama) from Claude Code sessions.

The LLM gets full codebase access with progressive disclosure tools.
Claude (the session) debates directly with the LLM's responses.

Setup:
1. pip install mcp google-generativeai groq
2. Get API keys:
   - Gemini: console.cloud.google.com (or AI Studio)
   - Groq: console.groq.com (free tier)
3. Add to ~/.claude/settings.json:
   {
     "mcpServers": {
       "llama": {
         "type": "stdio",
         "command": "/path/to/.venv-mcp/bin/python",
         "args": ["/path/to/scripts/mcp_debate_server.py"],
         "env": {
           "GEMINI_API_KEY": "AIza...",
           "GROQ_API_KEY": "gsk_..."
         }
       }
     }
   }
4. Restart Claude Code

The server will use Gemini by default, falling back to Groq/Llama if Gemini fails.

Usage (from Claude's perspective):
- consult_llama: Get a second opinion (LLM can explore codebase)
- continue_debate: Send your response, get counter-response
"""

import json
import os
import sys
import subprocess
import re
import ast
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("ERROR: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Try to import Gemini
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    genai = None
    GEMINI_AVAILABLE = False

# Try to import Groq (fallback)
try:
    from groq import Groq
except ImportError:
    Groq = None


# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent

# Debate history (persists across tool calls in same session)
debate_history: list[dict] = []

# Context budget system - cost per tool type (approximate output tokens)
TOOL_COSTS = {
    "explore_directory": 15,   # Cheap - just structure
    "get_file_outline": 25,    # Medium - classes/functions
    "glob": 10,                # Cheap - just paths
    "grep": 40,                # Medium - matches with context
    "read_file": 100,          # Expensive - actual content
    "find_references": 50,     # Medium - grep-like
    "run_command": 30,         # Variable
    "get_git_context": 30,     # Variable
}
DEFAULT_CONTEXT_BUDGET = 500  # Total budget in "tokens"


# ============================================================================
# GPT Tool Definitions (mirrors Claude's capabilities)
# ============================================================================

GPT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "explore_directory",
            "description": "Get directory structure overview. START HERE when exploring unfamiliar areas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (e.g., 'runtime/risk', '.')"},
                    "depth": {"type": "integer", "description": "Recursion depth (default: 2, max: 4)", "default": 2}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_outline",
            "description": "Get file structure WITHOUT full content. Shows classes, functions, imports.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to project root"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search for pattern across files. Returns matching lines with context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search"},
                    "path": {"type": "string", "description": "Directory to search (default: '.')", "default": "."},
                    "file_pattern": {"type": "string", "description": "Glob filter (default: '*.py')", "default": "*.py"},
                    "context_lines": {"type": "integer", "description": "Context lines (default: 2)", "default": 2}
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files matching a pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern (e.g., '**/*_test.py')"}
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents. Use get_file_outline first for large files. Supports line ranges.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "start_line": {"type": "integer", "description": "Start line (1-indexed)"},
                    "end_line": {"type": "integer", "description": "End line"},
                    "symbol": {"type": "string", "description": "Read specific function/class by name"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_references",
            "description": "Find all references to a symbol across the codebase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Symbol name to find"},
                    "definition_only": {"type": "boolean", "description": "Only show definition", "default": False}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run safe read-only commands (git log/diff/status, pip list, pytest --collect-only).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run (must be read-only)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_git_context",
            "description": "Get git info: log, diff, blame, status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["log", "diff", "blame", "status"]},
                    "path": {"type": "string", "description": "File path for blame, scope for log/diff"},
                    "count": {"type": "integer", "description": "Commits for log (default: 10)", "default": 10}
                },
                "required": ["action"]
            }
        }
    }
]


# ============================================================================
# Tool Execution
# ============================================================================

SAFE_COMMANDS = ["git status", "git log", "git diff", "git show", "git blame", "git branch",
                 "python -c", "python3 -c", "pytest --collect-only", "pip list", "pip show",
                 "ls", "cat", "head", "tail", "wc", "find", "grep", "rg", "tree", "file"]

FORBIDDEN = [r"rm\s", r"mv\s", r"cp\s", r">\s", r">>\s", r"sudo", r"pip install",
             r"git push", r"git commit", r"git reset", r"git checkout"]


def is_safe_command(cmd: str) -> tuple[bool, str]:
    for pattern in FORBIDDEN:
        if re.search(pattern, cmd.lower()):
            return False, f"Forbidden: {pattern}"
    for prefix in SAFE_COMMANDS:
        if cmd.lower().startswith(prefix):
            return True, ""
    return False, "Not in safe list"


def extract_python_symbols(content: str) -> dict:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {"error": "Parse error"}

    symbols = {"imports": [], "classes": [], "functions": [], "constants": []}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            symbols["imports"].extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            symbols["imports"].extend(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            symbols["classes"].append({"name": node.name, "line": node.lineno, "methods": methods})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols["functions"].append({"name": node.name, "line": node.lineno,
                                         "args": [a.arg for a in node.args.args]})
    return symbols


def find_symbol_lines(content: str, symbol: str) -> Optional[tuple[int, int]]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == symbol:
                end = max((getattr(n, 'lineno', node.lineno) for n in ast.walk(node)), default=node.lineno)
                return (node.lineno, end)
    return None


def execute_tool(name: str, args: dict) -> str:
    try:
        if name == "explore_directory":
            path = PROJECT_ROOT / args.get("path", ".")
            if not path.exists() or not path.is_dir():
                return f"Error: Not a directory: {args.get('path')}"

            depth = min(args.get("depth", 2), 4)

            def tree(p: Path, d: int, prefix: str = "") -> list[str]:
                if d > depth:
                    return []
                lines = []
                try:
                    items = sorted([i for i in p.iterdir() if not i.name.startswith('.')],
                                   key=lambda x: (x.is_file(), x.name.lower()))[:25]
                except PermissionError:
                    return [f"{prefix}[denied]"]

                for i, item in enumerate(items):
                    last = i == len(items) - 1
                    conn = "└── " if last else "├── "
                    if item.is_dir():
                        lines.append(f"{prefix}{conn}{item.name}/")
                        lines.extend(tree(item, d + 1, prefix + ("    " if last else "│   ")))
                    else:
                        sz = item.stat().st_size
                        lines.append(f"{prefix}{conn}{item.name} ({sz//1024}kb)" if sz > 1024 else f"{prefix}{conn}{item.name}")
                return lines

            return f"📁 {args.get('path', '.')}/\n" + '\n'.join(tree(path, 1)[:80])

        elif name == "get_file_outline":
            path = PROJECT_ROOT / args["path"]
            if not path.exists():
                return f"Error: Not found: {args['path']}"

            content = path.read_text()
            if path.suffix != ".py":
                lines = content.splitlines()
                return f"# {args['path']} ({len(lines)} lines)\n" + '\n'.join(lines[:15])

            syms = extract_python_symbols(content)
            if "error" in syms:
                return syms["error"]

            out = [f"# {args['path']} ({len(content.splitlines())} lines)"]
            if syms["classes"]:
                out.append("\n## Classes")
                for c in syms["classes"]:
                    out.append(f"  class {c['name']} (line {c['line']})")
                    for m in c["methods"][:8]:
                        out.append(f"    .{m}()")
            if syms["functions"]:
                out.append("\n## Functions")
                for f in syms["functions"][:15]:
                    out.append(f"  def {f['name']}({', '.join(f['args'][:3])}) (line {f['line']})")
            return '\n'.join(out)

        elif name == "grep":
            cmd = ["rg", "--line-number", f"--context={args.get('context_lines', 2)}",
                   "--max-count=25", "--glob", args.get("file_pattern", "*.py"),
                   args["pattern"], args.get("path", ".")]
            result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10)
            return result.stdout.strip()[:4000] or f"No matches for: {args['pattern']}"

        elif name == "glob":
            matches = sorted(PROJECT_ROOT.glob(args["pattern"]),
                           key=lambda p: p.stat().st_mtime, reverse=True)[:40]
            return '\n'.join(str(m.relative_to(PROJECT_ROOT)) for m in matches) or "No matches"

        elif name == "read_file":
            path = PROJECT_ROOT / args["path"]
            if not path.exists():
                return f"Error: Not found: {args['path']}"

            content = path.read_text()
            lines = content.splitlines()

            if args.get("symbol"):
                rng = find_symbol_lines(content, args["symbol"])
                if rng:
                    args["start_line"], args["end_line"] = rng[0], rng[1] + 3
                else:
                    return f"Symbol '{args['symbol']}' not found"

            start = args.get("start_line", 1) - 1
            end = min(args.get("end_line", len(lines)), start + 150)

            selected = lines[max(0, start):end]
            numbered = [f"{start+i+1:4d} | {line}" for i, line in enumerate(selected)]
            return f"# {args['path']} (lines {start+1}-{end})\n\n" + '\n'.join(numbered)

        elif name == "find_references":
            pattern = f"\\b{args['symbol']}\\b"
            if args.get("definition_only"):
                pattern = f"(def |class ){args['symbol']}"
            cmd = ["rg", "--line-number", "--context=1", "--max-count=20",
                   "--glob", "*.py", "-e", pattern, "."]
            result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10)
            return result.stdout.strip()[:3000] or f"No references for: {args['symbol']}"

        elif name == "run_command":
            safe, reason = is_safe_command(args["command"])
            if not safe:
                return f"Blocked: {reason}"
            result = subprocess.run(args["command"], shell=True, cwd=PROJECT_ROOT,
                                    capture_output=True, text=True, timeout=15)
            return (result.stdout + result.stderr)[:3000] or "(no output)"

        elif name == "get_git_context":
            action = args["action"]
            path = args.get("path", "")
            if action == "log":
                cmd = f"git log --oneline -n {min(args.get('count', 10), 20)}"
            elif action == "diff":
                cmd = f"git diff -- {path}" if path else "git diff"
            elif action == "blame":
                if not path:
                    return "blame requires path"
                cmd = f"git blame {path} | head -50"
            elif action == "status":
                cmd = "git status --short"
            else:
                return f"Unknown action: {action}"

            result = subprocess.run(cmd, shell=True, cwd=PROJECT_ROOT,
                                    capture_output=True, text=True, timeout=10)
            return result.stdout.strip()[:3000] or "(no output)"

        return f"Unknown tool: {name}"

    except subprocess.TimeoutExpired:
        return "Timeout"
    except Exception as e:
        return f"Error: {e}"


# ============================================================================
# GPT Interaction
# ============================================================================

SYSTEM_PROMPT = """You are a technical expert in a debate with Claude (Anthropic).
Be direct, specific, and willing to disagree.

You have tools to explore the codebase. Use PROGRESSIVE DISCLOSURE:
1. explore_directory() - start broad
2. get_file_outline() - understand structure before reading
3. grep() - find relevant code
4. read_file() with symbol= or line ranges - read surgically

DON'T dump entire files. DO target specific functions.

IMPORTANT: Use the provided tools via the API's native function calling mechanism.
Do NOT write function calls as text like <function=...> - just call the tools directly.

When you've formed your opinion:
- State your position clearly
- Reference specific code/lines when relevant
- If you agree with Claude, say so and add what you'd emphasize
- If you disagree, explain why with evidence from the codebase"""

# Model configuration
GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"

# Track which backend is active
active_backend = "none"


def _convert_tools_for_gemini():
    """Convert OpenAI-style tools to Gemini format."""
    gemini_tools = []
    for tool in GPT_TOOLS:
        func = tool["function"]
        gemini_tools.append({
            "name": func["name"],
            "description": func["description"],
            "parameters": func["parameters"]
        })
    return gemini_tools


def prefetch_hint_files(hint_files: list[str]) -> str:
    """
    Pre-fetch outlines for hint files and inject into context.
    This ensures the LLM sees the important files BEFORE it starts exploring.
    """
    if not hint_files:
        return ""

    sections = ["## Pre-loaded File Outlines (from hint_files)\n"]
    sections.append("These files were specified as important. Review them FIRST.\n")

    for file_path in hint_files:
        outline = execute_tool("get_file_outline", {"path": file_path})
        if not outline.startswith("Error:"):
            sections.append(f"### {file_path}\n```\n{outline}\n```\n")
        else:
            sections.append(f"### {file_path}\n(Could not load: {outline})\n")

    return "\n".join(sections)


class ContextBudget:
    """Track context budget across tool calls."""

    def __init__(self, budget: int = DEFAULT_CONTEXT_BUDGET):
        self.budget = budget
        self.spent = 0
        self.tools_used = []

    def can_afford(self, tool_name: str) -> bool:
        cost = TOOL_COSTS.get(tool_name, 50)
        return (self.spent + cost) <= self.budget

    def spend(self, tool_name: str, args: dict):
        cost = TOOL_COSTS.get(tool_name, 50)
        self.spent += cost
        self.tools_used.append({"tool": tool_name, "args": args, "cost": cost})

    def remaining(self) -> int:
        return self.budget - self.spent

    def summary(self) -> str:
        return f"Budget: {self.spent}/{self.budget} tokens used"


def call_gemini(prompt: str, allow_tools: bool = True, context_budget: int = DEFAULT_CONTEXT_BUDGET) -> tuple[str, list]:
    """Call Gemini with context-budget-aware tool use. Returns (response, tools_used)."""
    global active_backend

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not GEMINI_AVAILABLE:
        return "ERROR: Gemini not available", []

    genai.configure(api_key=api_key)

    # Convert tools to Gemini format
    gemini_tools = _convert_tools_for_gemini() if allow_tools else None

    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
        tools=gemini_tools if gemini_tools else None
    )

    chat = model.start_chat()
    budget = ContextBudget(context_budget)

    # Initial message
    response = chat.send_message(prompt)

    max_iterations = 30  # Safety limit
    for _ in range(max_iterations):
        # Check for function calls
        if response.candidates[0].content.parts:
            has_function_call = False
            function_responses = []

            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    has_function_call = True
                    fc = part.function_call
                    tool_name = fc.name
                    tool_args = dict(fc.args) if fc.args else {}

                    # Check budget before executing
                    if not budget.can_afford(tool_name):
                        result = f"Budget exhausted ({budget.summary()}). Provide your answer with current information."
                    else:
                        result = execute_tool(tool_name, tool_args)
                        budget.spend(tool_name, tool_args)

                    function_responses.append(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=tool_name,
                                response={"result": result}
                            )
                        )
                    )

            if has_function_call and function_responses:
                # Send function results back
                response = chat.send_message(function_responses)
            else:
                # No more function calls, extract text
                break
        else:
            break

    # Extract final text response
    text_response = ""
    for part in response.candidates[0].content.parts:
        if hasattr(part, 'text') and part.text:
            text_response += part.text

    active_backend = "gemini"
    return text_response or "(no response)", budget.tools_used


def _parse_text_tool_calls(content: str) -> list[tuple[str, dict]]:
    """Parse text-based function calls that Llama sometimes outputs.

    Handles formats like:
    - <function=name{"arg": "val"}</function>
    - <function=name>{"arg": "val"}</function>
    """
    if not content:
        return []

    calls = []
    # Pattern 1: <function=name{"args"}>
    pattern1 = r'<function=(\w+)(\{[^}]+\})(?:</function>)?'
    # Pattern 2: <function=name>{"args"}</function>
    pattern2 = r'<function=(\w+)>(\{[^}]+\})</function>'

    for pattern in [pattern1, pattern2]:
        for match in re.finditer(pattern, content):
            func_name = match.group(1)
            try:
                args = json.loads(match.group(2))
                calls.append((func_name, args))
            except json.JSONDecodeError:
                pass

    return calls


def call_groq(prompt: str, allow_tools: bool = True, context_budget: int = DEFAULT_CONTEXT_BUDGET) -> tuple[str, list]:
    """Call Llama via Groq with context-budget-aware tool use. Returns (response, tools_used)."""
    global active_backend

    if Groq is None:
        return "ERROR: groq not installed. Run: pip install groq", []

    client = Groq()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    budget = ContextBudget(context_budget)

    max_iterations = 30  # Safety limit
    for _ in range(max_iterations):
        kwargs = {"model": GROQ_MODEL, "max_tokens": 2000, "messages": messages}
        if allow_tools and budget.remaining() > 0:
            kwargs["tools"] = GPT_TOOLS
            kwargs["tool_choice"] = "auto"

        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        if msg.tool_calls and allow_tools:
            messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]})
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                tool_args = json.loads(tc.function.arguments)

                # Check budget before executing
                if not budget.can_afford(tool_name):
                    result = f"Budget exhausted ({budget.summary()}). Provide your answer with current information."
                else:
                    result = execute_tool(tool_name, tool_args)
                    budget.spend(tool_name, tool_args)

                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
        else:
            # Check for text-based tool calls (Llama sometimes outputs these)
            text_calls = _parse_text_tool_calls(msg.content or "")
            if text_calls and allow_tools and budget.remaining() > 0:
                # Execute parsed text-based calls
                messages.append({"role": "assistant", "content": msg.content})
                for tool_name, tool_args in text_calls:
                    if not budget.can_afford(tool_name):
                        result = f"Budget exhausted ({budget.summary()}). Provide your answer now."
                    else:
                        result = execute_tool(tool_name, tool_args)
                        budget.spend(tool_name, tool_args)
                    # Append as user message with tool result (workaround since no tool_call_id)
                    messages.append({"role": "user", "content": f"Tool result for {tool_name}({tool_args}):\n{result}"})
            else:
                active_backend = "groq"
                return msg.content or "", budget.tools_used

    active_backend = "groq"
    return msg.content or f"(iterations exhausted, {budget.summary()})", budget.tools_used


def call_llm(prompt: str, allow_tools: bool = True, context_budget: int = DEFAULT_CONTEXT_BUDGET) -> tuple[str, list, str]:
    """Call LLM with automatic fallback and context budget. Returns (response, tools_used, backend_name)."""

    # Try Gemini first if available
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if GEMINI_AVAILABLE and gemini_key:
        try:
            response, tools = call_gemini(prompt, allow_tools, context_budget)
            if not response.startswith("ERROR:"):
                return response, tools, "Gemini"
        except Exception as e:
            pass  # Fall through to Groq

    # Fallback to Groq
    groq_key = os.environ.get("GROQ_API_KEY")
    if Groq is not None and groq_key:
        try:
            response, tools = call_groq(prompt, allow_tools, context_budget)
            return response, tools, "Llama (Groq)"
        except Exception as e:
            return f"ERROR: Both backends failed. Groq error: {e}", [], "none"

    return "ERROR: No LLM backend available. Set GEMINI_API_KEY or GROQ_API_KEY.", [], "none"


# ============================================================================
# MCP Server
# ============================================================================

server = Server("llama-consult")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="consult_llama",
            description="""Ask Llama (via Groq) for a second opinion. Llama can explore the codebase independently.

Use when:
- You're uncertain about a design decision
- You want to verify your understanding
- You're choosing between approaches
- You want an independent code review

Llama will use progressive disclosure to explore the codebase before responding.
Start a new debate or continue an existing one.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question or topic to discuss"
                    },
                    "context": {
                        "type": "string",
                        "description": "Background context (code snippets, constraints, etc.)"
                    },
                    "my_position": {
                        "type": "string",
                        "description": "Your current thinking (optional - GPT will respond to this)"
                    },
                    "hint_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Suggest files for GPT to examine"
                    },
                    "continue_debate": {
                        "type": "boolean",
                        "description": "Continue from previous exchange (default: false)",
                        "default": False
                    }
                },
                "required": ["question"]
            }
        ),
        Tool(
            name="clear_debate",
            description="Clear debate history to start fresh.",
            inputSchema={"type": "object", "properties": {}}
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    global debate_history

    if name == "clear_debate":
        debate_history = []
        return [TextContent(type="text", text="Debate history cleared.")]

    if name != "consult_llama":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    question = arguments["question"]
    context = arguments.get("context", "")
    my_position = arguments.get("my_position", "")
    hint_files = arguments.get("hint_files", [])
    continue_debate = arguments.get("continue_debate", False)

    # Pre-fetch hint files to inject their outlines directly into context
    hint_context = prefetch_hint_files(hint_files) if hint_files else ""

    # Build prompt
    if continue_debate and debate_history:
        history_text = "\n\n".join([
            f"**{h['role']}:** {h['content']}" for h in debate_history[-6:]  # Last 3 exchanges
        ])
        prompt = f"""Continuing debate...

Previous exchange:
{history_text}

Claude now says:
{my_position if my_position else question}

Your response:"""
    else:
        debate_history = []  # Fresh start
        prompt = f"""Question: {question}
"""
        if context:
            prompt += f"""
Context:
{context}
"""
        # Inject pre-fetched hint file outlines BEFORE asking LLM to explore
        if hint_context:
            prompt += f"""
{hint_context}

IMPORTANT: The files above were pre-loaded because they are directly relevant to the question.
Start your analysis from these files. Only explore other files if needed.
"""
        if my_position:
            prompt += f"""
Claude's position:
{my_position}

Do you agree or disagree? Reference the pre-loaded files above, then respond:"""
        else:
            prompt += """
Analyze the pre-loaded files above, explore further if needed, then give your assessment:"""

    # Call LLM (Gemini with Groq fallback)
    response, tools_used, backend = call_llm(prompt)

    # Update history
    if my_position:
        debate_history.append({"role": "Claude", "content": my_position})
    debate_history.append({"role": backend, "content": response})

    # Format output
    output = [f"## {backend}'s Response\n"]

    if tools_used:
        output.append("**Explored:**")
        for t in tools_used:
            args_str = ", ".join(f"{k}={repr(v)}" for k, v in list(t["args"].items())[:2])
            output.append(f"- `{t['tool']}({args_str})`")
        output.append("")

    output.append(response)
    output.append(f"\n---\n*Backend: {backend} | Turns: {len(debate_history)}. Use `continue_debate: true` to respond.*")

    return [TextContent(type="text", text="\n".join(output))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
