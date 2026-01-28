"""
Development Reasoning Tool

A meta-tool to question assumptions, track unknowns, and prevent
configuration/logic errors during development sessions.

Usage:
    from tools.dev_reasoning import Reasoner

    r = Reasoner()
    r.assume("node is writing trades")  # Track assumption
    r.verify("node is writing trades", "checked --write-trades flag")  # Verify
    r.unknown("forceOrder schema in blocks")  # Track unknowns
    r.lesson("node needs --write-trades flag for liquidation data")  # Record lesson
    r.checklist("new_integration")  # Run integration checklist
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Literal
from enum import Enum


class AssumptionStatus(Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    FALSIFIED = "falsified"


@dataclass
class Assumption:
    """An assumption made during development."""
    statement: str
    created_at: float
    status: AssumptionStatus = AssumptionStatus.UNVERIFIED
    verification_note: Optional[str] = None
    verified_at: Optional[float] = None


@dataclass
class Unknown:
    """Something we don't know but should find out."""
    question: str
    created_at: float
    resolved: bool = False
    resolution: Optional[str] = None
    resolved_at: Optional[float] = None


@dataclass
class Lesson:
    """A lesson learned from debugging/development."""
    statement: str
    created_at: float
    context: Optional[str] = None
    tags: List[str] = field(default_factory=list)


# Standard checklists for common operations
CHECKLISTS = {
    "new_integration": [
        "Is the process actually running?",
        "Are all required flags/options enabled?",
        "Is data flowing through all stages?",
        "Are there any silent failures (check logs)?",
        "Is the schema/format as expected?",
        "Is there a startup/bootstrap delay?",
        "Are file paths correct?",
        "Are permissions sufficient?",
    ],
    "data_not_flowing": [
        "Is the source producing data?",
        "Is the consumer reading from the right location?",
        "Are there format/schema mismatches?",
        "Is there a buffer/queue that's stuck?",
        "Are there any error logs?",
        "Is the polling interval correct?",
        "Is there a rate limit being hit?",
        "Did a process restart and lose state?",
    ],
    "cascade_trigger": [
        "Is proximity data available?",
        "Is liquidation data flowing?",
        "Are thresholds appropriate for market conditions?",
        "Is the state machine transitioning correctly?",
        "Are all required callbacks wired?",
        "Is the organic flow detector active?",
        "Is timestamp handling correct?",
    ],
    "node_operation": [
        "Is the node process running?",
        "Is it synced to current block?",
        "Are output flags enabled (--write-trades, etc)?",
        "Is disk space sufficient?",
        "Are file permissions correct?",
        "Is the data directory correct?",
        "Is there a bootstrap/catchup phase?",
    ],
    "memory_management": [
        "Are max_* limits configured?",
        "Are prune methods being called?",
        "Is cleanup coordinator running?",
        "Are there unbounded collections?",
        "Is memory actually growing?",
        "What's the growth rate?",
    ],
}


class Reasoner:
    """
    Development reasoning assistant.

    Tracks assumptions, unknowns, and lessons to help prevent
    configuration and logic errors during development.
    """

    def __init__(self, persist_path: Optional[Path] = None):
        """
        Initialize reasoner.

        Args:
            persist_path: Path to persist reasoning state (optional)
        """
        self._assumptions: Dict[str, Assumption] = {}
        self._unknowns: Dict[str, Unknown] = {}
        self._lessons: List[Lesson] = []
        self._persist_path = persist_path or Path(".dev_reasoning.json")

        # Load persisted state if exists
        self._load()

    # =========================================================================
    # Assumptions
    # =========================================================================

    def assume(self, statement: str) -> None:
        """
        Record an assumption.

        Call this whenever you make an assumption that should be verified.

        Example:
            r.assume("node is writing trades to node_trades/")
        """
        if statement not in self._assumptions:
            self._assumptions[statement] = Assumption(
                statement=statement,
                created_at=time.time(),
            )
            print(f"⚠️  ASSUMPTION: {statement}")
        else:
            print(f"📋 Already tracking: {statement}")

    def verify(self, statement: str, note: str) -> None:
        """
        Mark an assumption as verified.

        Example:
            r.verify("node is writing trades", "confirmed with ls -la")
        """
        if statement in self._assumptions:
            a = self._assumptions[statement]
            a.status = AssumptionStatus.VERIFIED
            a.verification_note = note
            a.verified_at = time.time()
            print(f"✅ VERIFIED: {statement}")
            print(f"   Note: {note}")
        else:
            print(f"❓ Unknown assumption: {statement}")

    def falsify(self, statement: str, note: str) -> None:
        """
        Mark an assumption as false.

        Example:
            r.falsify("node is writing trades", "--write-trades flag was missing")
        """
        if statement in self._assumptions:
            a = self._assumptions[statement]
            a.status = AssumptionStatus.FALSIFIED
            a.verification_note = note
            a.verified_at = time.time()
            print(f"❌ FALSIFIED: {statement}")
            print(f"   Note: {note}")
        else:
            # Create and immediately falsify
            self._assumptions[statement] = Assumption(
                statement=statement,
                created_at=time.time(),
                status=AssumptionStatus.FALSIFIED,
                verification_note=note,
                verified_at=time.time(),
            )
            print(f"❌ FALSIFIED (new): {statement}")
            print(f"   Note: {note}")

    def list_unverified(self) -> List[str]:
        """List all unverified assumptions."""
        unverified = [
            a.statement for a in self._assumptions.values()
            if a.status == AssumptionStatus.UNVERIFIED
        ]
        if unverified:
            print("⚠️  UNVERIFIED ASSUMPTIONS:")
            for s in unverified:
                print(f"   - {s}")
        else:
            print("✅ No unverified assumptions")
        return unverified

    # =========================================================================
    # Unknowns
    # =========================================================================

    def unknown(self, question: str) -> None:
        """
        Record something we don't know but should find out.

        Example:
            r.unknown("What is the forceOrder schema in block data?")
        """
        if question not in self._unknowns:
            self._unknowns[question] = Unknown(
                question=question,
                created_at=time.time(),
            )
            print(f"❓ UNKNOWN: {question}")
        else:
            print(f"📋 Already tracking: {question}")

    def resolve(self, question: str, answer: str) -> None:
        """
        Resolve an unknown.

        Example:
            r.resolve("forceOrder schema", "Doesn't exist - liqs come from node_trades")
        """
        if question in self._unknowns:
            u = self._unknowns[question]
            u.resolved = True
            u.resolution = answer
            u.resolved_at = time.time()
            print(f"💡 RESOLVED: {question}")
            print(f"   Answer: {answer}")
        else:
            print(f"❓ Unknown question: {question}")

    def list_unknowns(self) -> List[str]:
        """List unresolved unknowns."""
        unresolved = [
            u.question for u in self._unknowns.values()
            if not u.resolved
        ]
        if unresolved:
            print("❓ UNRESOLVED UNKNOWNS:")
            for q in unresolved:
                print(f"   - {q}")
        else:
            print("✅ No unresolved unknowns")
        return unresolved

    # =========================================================================
    # Lessons
    # =========================================================================

    def lesson(self, statement: str, context: Optional[str] = None,
               tags: Optional[List[str]] = None) -> None:
        """
        Record a lesson learned.

        Example:
            r.lesson(
                "hl-node needs --write-trades flag for liquidation data",
                context="Spent 30 min debugging missing liquidations",
                tags=["node", "configuration"]
            )
        """
        l = Lesson(
            statement=statement,
            created_at=time.time(),
            context=context,
            tags=tags or [],
        )
        self._lessons.append(l)
        print(f"📚 LESSON: {statement}")
        if context:
            print(f"   Context: {context}")
        self._save()

    def search_lessons(self, keyword: str) -> List[Lesson]:
        """Search lessons by keyword."""
        matches = []
        keyword_lower = keyword.lower()
        for l in self._lessons:
            if (keyword_lower in l.statement.lower() or
                (l.context and keyword_lower in l.context.lower()) or
                any(keyword_lower in t.lower() for t in l.tags)):
                matches.append(l)

        if matches:
            print(f"📚 LESSONS matching '{keyword}':")
            for l in matches:
                print(f"   - {l.statement}")
        else:
            print(f"No lessons matching '{keyword}'")
        return matches

    # =========================================================================
    # Checklists
    # =========================================================================

    def checklist(self, name: str) -> List[str]:
        """
        Run a standard checklist.

        Available checklists:
        - new_integration
        - data_not_flowing
        - cascade_trigger
        - node_operation
        - memory_management
        """
        if name not in CHECKLISTS:
            print(f"❌ Unknown checklist: {name}")
            print(f"   Available: {', '.join(CHECKLISTS.keys())}")
            return []

        items = CHECKLISTS[name]
        print(f"📋 CHECKLIST: {name}")
        print("-" * 40)
        for i, item in enumerate(items, 1):
            print(f"   {i}. {item}")
        print("-" * 40)
        return items

    def question(self, topic: str) -> None:
        """
        Generate probing questions for a topic.

        Example:
            r.question("liquidation detection")
        """
        print(f"🔍 QUESTIONS about '{topic}':")
        print("-" * 40)
        questions = [
            f"What are we assuming about {topic}?",
            f"How do we know {topic} is working?",
            f"What could cause {topic} to fail silently?",
            f"What configuration is required for {topic}?",
            f"Have we verified {topic} with recent data?",
            f"What are the dependencies of {topic}?",
            f"What would we see if {topic} wasn't working?",
        ]
        for q in questions:
            print(f"   • {q}")
        print("-" * 40)

    # =========================================================================
    # Status
    # =========================================================================

    def status(self) -> None:
        """Print current reasoning status."""
        unverified = sum(1 for a in self._assumptions.values()
                        if a.status == AssumptionStatus.UNVERIFIED)
        falsified = sum(1 for a in self._assumptions.values()
                       if a.status == AssumptionStatus.FALSIFIED)
        unresolved = sum(1 for u in self._unknowns.values() if not u.resolved)

        print("=" * 50)
        print("DEVELOPMENT REASONING STATUS")
        print("=" * 50)
        print(f"Assumptions: {len(self._assumptions)} total")
        if unverified:
            print(f"  ⚠️  {unverified} UNVERIFIED")
        if falsified:
            print(f"  ❌ {falsified} falsified")
        print(f"Unknowns: {len(self._unknowns)} total")
        if unresolved:
            print(f"  ❓ {unresolved} UNRESOLVED")
        print(f"Lessons: {len(self._lessons)} recorded")
        print("=" * 50)

    # =========================================================================
    # Persistence
    # =========================================================================

    def _save(self) -> None:
        """Save state to disk."""
        data = {
            "assumptions": {k: asdict(v) for k, v in self._assumptions.items()},
            "unknowns": {k: asdict(v) for k, v in self._unknowns.items()},
            "lessons": [asdict(l) for l in self._lessons],
        }
        # Convert enums
        for a in data["assumptions"].values():
            a["status"] = a["status"].value

        with open(self._persist_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _load(self) -> None:
        """Load state from disk."""
        if not self._persist_path.exists():
            return

        try:
            with open(self._persist_path, 'r') as f:
                data = json.load(f)

            for k, v in data.get("assumptions", {}).items():
                v["status"] = AssumptionStatus(v["status"])
                self._assumptions[k] = Assumption(**v)

            for k, v in data.get("unknowns", {}).items():
                self._unknowns[k] = Unknown(**v)

            for l in data.get("lessons", []):
                self._lessons.append(Lesson(**l))
        except Exception:
            pass  # Start fresh if load fails


# Singleton instance for easy access
_reasoner: Optional[Reasoner] = None

def get_reasoner() -> Reasoner:
    """Get the global reasoner instance."""
    global _reasoner
    if _reasoner is None:
        _reasoner = Reasoner(
            persist_path=Path("/media/ksiaz/D/liquidation-trading/.dev_reasoning.json")
        )
    return _reasoner


# Convenience functions
def assume(statement: str) -> None:
    get_reasoner().assume(statement)

def verify(statement: str, note: str) -> None:
    get_reasoner().verify(statement, note)

def falsify(statement: str, note: str) -> None:
    get_reasoner().falsify(statement, note)

def unknown(question: str) -> None:
    get_reasoner().unknown(question)

def resolve(question: str, answer: str) -> None:
    get_reasoner().resolve(question, answer)

def lesson(statement: str, context: Optional[str] = None,
           tags: Optional[List[str]] = None) -> None:
    get_reasoner().lesson(statement, context, tags)

def checklist(name: str) -> List[str]:
    return get_reasoner().checklist(name)

def question(topic: str) -> None:
    get_reasoner().question(topic)

def status() -> None:
    get_reasoner().status()


if __name__ == "__main__":
    # Demo
    r = get_reasoner()

    # Record what we learned today
    r.lesson(
        "hl-node needs --write-trades flag for liquidation data in node_trades/",
        context="Liquidations stuck at 1197 for 1+ hour, discovered missing flag",
        tags=["node", "configuration", "liquidations"]
    )

    r.lesson(
        "Historical validation results (759 trades) were from API mode, not node mode",
        context="Performance metrics may not transfer to node-based system",
        tags=["validation", "testing"]
    )

    r.status()
