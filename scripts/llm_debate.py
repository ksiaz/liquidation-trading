#!/usr/bin/env python3
"""
LLM Debate: Claude vs GPT for code review OR design discussions.

Usage (code review):
    python scripts/llm_debate.py <file> [--rounds 5] [--topic "security"]
    python scripts/llm_debate.py runtime/risk/monitor.py --topic "edge cases"

Usage (design debate):
    python scripts/llm_debate.py --design "How should we handle partial fills in the execution engine?"
    python scripts/llm_debate.py --design "Should we use event sourcing or state snapshots for position tracking?"
    python scripts/llm_debate.py --design-file design_problem.md --context runtime/execution/
"""

import argparse
import sys
from pathlib import Path

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import openai
except ImportError:
    openai = None


SYSTEM_PROMPT_CODE = """You are a senior engineer in a code review debate.
- Be direct and specific about issues
- Reference line numbers when relevant
- If you agree with a point, say so briefly and move on
- Focus on issues that could cause bugs, security problems, or maintenance pain
- When you've reached agreement on all major points, say "CONSENSUS REACHED"
"""

SYSTEM_PROMPT_DESIGN = """You are a senior engineer debating a design decision.
- Propose concrete solutions, not vague suggestions
- Discuss tradeoffs explicitly (complexity vs flexibility, performance vs maintainability)
- Challenge assumptions and ask clarifying questions
- If you disagree, explain WHY with specific scenarios
- Consider: failure modes, edge cases, future extensibility, operational complexity
- When you've converged on a recommended approach, say "CONSENSUS REACHED" and state the recommendation
"""


def get_claude_response(client, history: list[dict], system_prompt: str) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=system_prompt,
        messages=history,
    )
    return response.content[0].text


def get_gpt_response(client, history: list[dict], system_prompt: str) -> str:
    messages = [{"role": "system", "content": system_prompt}] + history
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1500,
        messages=messages,
    )
    return response.choices[0].message.content


def print_response(name: str, text: str, round_num: int):
    color = "\033[94m" if name == "CLAUDE" else "\033[93m"
    reset = "\033[0m"
    print(f"\n{color}{'='*60}")
    print(f"{name} (round {round_num})")
    print(f"{'='*60}{reset}")
    print(text)


def run_debate(
    initial_prompt: str,
    system_prompt: str,
    max_rounds: int = 5,
    first_speaker: str = "claude"
) -> dict:
    """Run a debate between Claude and GPT."""

    if anthropic is None:
        print("ERROR: anthropic package not installed. Run: pip install anthropic")
        sys.exit(1)
    if openai is None:
        print("ERROR: openai package not installed. Run: pip install openai")
        sys.exit(1)

    claude_client = anthropic.Anthropic()
    gpt_client = openai.OpenAI()

    history = []
    history.append({"role": "user", "content": initial_prompt})

    # First speaker
    if first_speaker == "claude":
        resp = get_claude_response(claude_client, history, system_prompt)
        speaker = "CLAUDE"
    else:
        resp = get_gpt_response(gpt_client, history, system_prompt)
        speaker = "GPT"

    history.append({"role": "assistant", "content": resp})
    print_response(speaker, resp, 1)

    if "CONSENSUS REACHED" in resp:
        return {"rounds": 1, "history": history, "consensus": True}

    for round_num in range(2, max_rounds + 1):
        # Alternate speakers
        if speaker == "CLAUDE":
            next_speaker = "GPT"
            get_response = lambda h: get_gpt_response(gpt_client, h, system_prompt)
        else:
            next_speaker = "CLAUDE"
            get_response = lambda h: get_claude_response(claude_client, h, system_prompt)

        prompt = f"""The other engineer said:

{history[-1]['content']}

Do you agree? Disagree? What would you add or challenge?
If you've reached agreement on the key points, say "CONSENSUS REACHED" and summarize."""

        history.append({"role": "user", "content": prompt})
        resp = get_response(history)
        history.append({"role": "assistant", "content": resp})
        print_response(next_speaker, resp, round_num)
        speaker = next_speaker

        if "CONSENSUS REACHED" in resp:
            return {"rounds": round_num, "history": history, "consensus": True}

    return {"rounds": max_rounds, "history": history, "consensus": False}


def debate(code: str, topic: str = "bugs and issues", max_rounds: int = 5) -> dict:
    """Run a code review debate."""
    initial_prompt = f"""Review this code for {topic}. Be specific about what you find.

```
{code}
```

List the issues you see, ordered by severity."""

    return run_debate(initial_prompt, SYSTEM_PROMPT_CODE, max_rounds)


def design_debate(
    problem: str,
    context: str = "",
    constraints: str = "",
    max_rounds: int = 5
) -> dict:
    """Run a design/architecture debate."""

    initial_prompt = f"""DESIGN PROBLEM:
{problem}
"""
    if context:
        initial_prompt += f"""
CONTEXT (existing code/architecture):
```
{context}
```
"""
    if constraints:
        initial_prompt += f"""
CONSTRAINTS:
{constraints}
"""

    initial_prompt += """
Propose a solution. Be specific about:
1. The approach and why
2. Key tradeoffs you're accepting
3. What could go wrong"""

    return run_debate(initial_prompt, SYSTEM_PROMPT_DESIGN, max_rounds)


def summarize_debate(history: list[dict]) -> str:
    """Ask Claude to summarize the final consensus."""
    if anthropic is None:
        return "Cannot summarize: anthropic not installed"

    client = anthropic.Anthropic()

    debate_text = "\n\n".join(
        f"{'CLAUDE' if i % 2 == 1 else 'GPT'}: {msg['content']}"
        for i, msg in enumerate(history)
        if msg['role'] == 'assistant'
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"""Summarize the agreed-upon issues from this code review debate.
List only the points both reviewers agreed on.

DEBATE:
{debate_text}

AGREED ISSUES (bullet points):"""
        }]
    )
    return response.content[0].text


def load_context_files(context_path: str) -> str:
    """Load context from a file or directory."""
    path = Path(context_path)
    if path.is_file():
        return f"# {path.name}\n{path.read_text()}"

    if path.is_dir():
        parts = []
        for f in sorted(path.rglob("*.py"))[:10]:  # Limit to 10 files
            try:
                content = f.read_text()
                if len(content) < 5000:  # Skip huge files
                    parts.append(f"# {f.relative_to(path)}\n{content}")
            except Exception:
                pass
        return "\n\n".join(parts)

    return ""


def main():
    parser = argparse.ArgumentParser(
        description="LLM Debate: Claude vs GPT for code review or design discussions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Code review
  python scripts/llm_debate.py runtime/risk/monitor.py --topic "race conditions"

  # Design debate
  python scripts/llm_debate.py --design "Should position state be event-sourced or snapshot-based?"

  # Design with context
  python scripts/llm_debate.py --design "How should we handle partial fills?" --context runtime/execution/

  # Design from file
  python scripts/llm_debate.py --design-file docs/DESIGN_QUESTION.md
"""
    )

    # Mode selection
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("input", nargs="?", help="File path for code review (or '-' for stdin)")
    mode.add_argument("--design", "-d", metavar="QUESTION",
                      help="Design question to debate")
    mode.add_argument("--design-file", metavar="FILE",
                      help="File containing design question")

    # Common options
    parser.add_argument("--rounds", "-r", type=int, default=5, help="Max debate rounds")
    parser.add_argument("--summarize", "-s", action="store_true",
                        help="Print summary of agreed points at end")

    # Code review options
    parser.add_argument("--topic", "-t", default="bugs, edge cases, and issues",
                        help="Focus area for code review")

    # Design options
    parser.add_argument("--context", "-c", metavar="PATH",
                        help="File or directory with relevant code context for design debate")
    parser.add_argument("--constraints", metavar="TEXT",
                        help="Constraints to consider (e.g., 'must be backwards compatible')")

    args = parser.parse_args()

    # Determine mode and run
    if args.design:
        # Design debate mode
        context = load_context_files(args.context) if args.context else ""

        print(f"\n\033[1mDESIGN DEBATE\033[0m")
        print(f"Question: {args.design}")
        if args.context:
            print(f"Context from: {args.context}")
        if args.constraints:
            print(f"Constraints: {args.constraints}")
        print(f"Max rounds: {args.rounds}")

        result = design_debate(
            problem=args.design,
            context=context,
            constraints=args.constraints or "",
            max_rounds=args.rounds
        )

    elif args.design_file:
        # Design debate from file
        path = Path(args.design_file)
        if not path.exists():
            print(f"ERROR: File not found: {args.design_file}")
            sys.exit(1)

        problem = path.read_text()
        context = load_context_files(args.context) if args.context else ""

        print(f"\n\033[1mDESIGN DEBATE\033[0m")
        print(f"Question from: {args.design_file}")
        print(f"Max rounds: {args.rounds}")

        result = design_debate(
            problem=problem,
            context=context,
            constraints=args.constraints or "",
            max_rounds=args.rounds
        )

    elif args.input:
        # Code review mode
        if args.input == "-":
            code = sys.stdin.read()
        else:
            path = Path(args.input)
            if not path.exists():
                print(f"ERROR: File not found: {args.input}")
                sys.exit(1)
            code = path.read_text()

        print(f"\n\033[1mCODE REVIEW DEBATE\033[0m")
        print(f"File: {args.input}")
        print(f"Topic: {args.topic}")
        print(f"Max rounds: {args.rounds}")

        result = debate(code, topic=args.topic, max_rounds=args.rounds)

    else:
        parser.print_help()
        sys.exit(1)

    # Results
    print(f"\n\033[1m{'='*60}")
    print(f"DEBATE COMPLETE")
    print(f"{'='*60}\033[0m")
    print(f"Rounds: {result['rounds']}")
    print(f"Consensus: {'Yes' if result['consensus'] else 'No (hit max rounds)'}")

    if args.summarize:
        print(f"\n\033[1mSUMMARY OF AGREED POINTS:\033[0m")
        print(summarize_debate(result['history']))


if __name__ == "__main__":
    main()
