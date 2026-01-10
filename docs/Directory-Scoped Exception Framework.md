

No other file name is valid.

---

## 4. Exception Declaration Format

Each exception declaration MUST be explicit and structured.

### 4.1 Required Structure

```md
# Semantic Exception Declaration

## Directory
observation/ingestion/

## Allowed Leak Classes
- Derived Data (Class 1.4)
- Naming-Implied Semantics (Class 1.9)

## Explicitly Allowed Constructs
- Counters
- Rolling aggregates
- Internal normalization
- Internal naming containing interpretive terms

## Explicitly Forbidden (Even Here)
- External exposure
- Snapshot fields
- Logs
- Mandates
- Execution influence

## Justification
This directory performs raw data ingestion and normalization.
All semantics remain strictly internal and are discarded before boundary crossing.

## Audit Notes
Any export from this directory must be raw or nullified.

Missing sections invalidate the exception.
5. Allowed Exception Classes (Closed Set)

Only the following semantic leak classes may ever be exception-eligible:

    1.4 Derived Data Leaks

    1.9 Naming-Implied Semantics

All other classes are never exceptionable.

Notably forbidden even with exceptions:

    Interpretive meaning

    Predictive meaning

    Evaluative judgement

    Causal attribution

    Temporal interpretation

    Cross-layer semantics

6. Boundary Reinforcement Rule

An exception never propagates across boundaries.

Specifically:

    Importing a module from an exception directory does not import the exception

    Returned values lose exception protection immediately

    Any public API crossing a boundary is treated as external speech

Violations are constitutional failures.
7. Observation Layer Special Case
7.1 Permitted Exception

observation/ingestion/ MAY declare exceptions for:

    Counters

    Aggregations

    Internal state

    Internal interpretive naming

7.2 Absolute Prohibitions

Even within observation ingestion:

    No semantic fields may appear in ObservationSnapshot

    No interpretive names may appear in public types

    No derived metrics may cross into governance

    No inference may survive snapshot construction

8. Execution & Mandate Layers

No directory under execution/, arbitration/, or mandate emission
may ever declare a semantic exception.

This is absolute.

Rationale:
Execution must operate only on constitutionally clean inputs.
9. Auditability Requirements
9.1 Static Audit

Every exception must be:

    Discoverable by file search

    Parsed by CI

    Explicitly reviewed

9.2 Diff Sensitivity

Any change to:

    .semantic_exceptions.md

    Directory structure

    Boundary interfaces

Triggers mandatory review.
10. Violation Conditions

The following constitute hard violations:

    Semantic construct present without exception declaration

    Exception declaration missing required fields

    Exception applied to non-eligible leak class

    Semantic construct escaping directory scope

    Exception used to justify external exposure

11. Revocation Rule

Exceptions are revocable at any time.

Upon revocation:

    All code must be brought into compliance

    No grandfathering exists

12. Completeness Statement

This framework is:

    Minimal

    Exhaustive

    Non-overlapping

    Mechanically enforceable

No other exception mechanism is permitted.
13. Constitutional Lock

Any modification to:

    Eligible leak classes

    Scope unit

    Boundary rules

    Declaration format

Requires constitutional amendment.

END OF DOCUMENT