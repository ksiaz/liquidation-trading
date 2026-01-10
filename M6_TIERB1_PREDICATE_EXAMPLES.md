Below is a formal, certification-safe set of M6 predicate examples for Tier B-1, written to serve as governance documentation + coding reference.
No strategy logic, no interpretation, no numeric comparison, no thresholds.

Tier B-1 — M6 Predicate Examples

Scope: Structural Absence Primitives
Authority: Tier B Canon v1.0, M6 Mandate Template v1.0
Status: VALID EXEMPLARS (Non-Exhaustive)

0. Governing Constraints (Restated)

All predicates below obey M6 admissibility rules:

✔ Allowed operations

EXISTS

EQUALS

IN_CATEGORY

✘ Forbidden

Numeric comparison (>, <, >=)

Thresholds

Aggregation

Temporal reasoning

Interpretation (e.g., "significant", "dangerous", "important")

Predicates only check structure and presence, never meaning.

1. Primitive Reference Table (Tier B-1)
Primitive	ID	Output Fields
Structural Absence Duration	B1.1	absence_duration, observation_window, absence_ratio
Traversal Void Span	B1.2	max_void_duration, void_intervals
Event Non-Occurrence Counter	B1.3	expected_count, observed_count, non_occurrence_count
2. Predicate Pattern 1 — Absence Exists
Purpose

Check that any measurable absence was computed.

Admissible Use Case

"Was absence observed at all?"

{
  "requires": [
    {
      "operation": "EXISTS",
      "fact_key": "B1.1.absence_duration"
    }
  ],
  "forbids": []
}


✔ Legal
✘ Does not imply failure, suppression, or intent.

3. Predicate Pattern 2 — Absence Ratio Categorization
Purpose

Use externally categorized absence ratios (no numeric logic inside M6).

Preconditions

Upstream system classifies absence_ratio_category ∈
{"NONE", "PARTIAL", "FULL"}

Predicate
{
  "requires": [
    {
      "operation": "EQUALS",
      "fact_key": "B1.1.absence_ratio_category",
      "expected_value": "PARTIAL"
    }
  ],
  "forbids": []
}


✔ Legal
✔ Category comparison only
✘ No numeric thresholds inside M6

4. Predicate Pattern 3 — Void Interval Presence
Purpose

Check whether any traversal void exists.

{
  "requires": [
    {
      "operation": "EXISTS",
      "fact_key": "B1.2.max_void_duration"
    }
  ],
  "forbids": []
}


✔ Legal
✘ Does not imply inactivity, buildup, or intent

5. Predicate Pattern 4 — Void Classification Membership
Purpose

Check membership in a predefined void class set.

Preconditions

Upstream categorization yields void_class ∈
{"NONE", "SINGLE", "MULTIPLE"}

{
  "requires": [
    {
      "operation": "IN_CATEGORY",
      "fact_key": "B1.2.void_class",
      "category_set": ["SINGLE", "MULTIPLE"]
    }
  ],
  "forbids": []
}


✔ Legal
✔ Structural classification only
✘ No duration comparison

6. Predicate Pattern 5 — Event Non-Occurrence Exists
Purpose

Detect that at least one expected event did not occur.

{
  "requires": [
    {
      "operation": "EXISTS",
      "fact_key": "B1.3.non_occurrence_count"
    }
  ],
  "forbids": []
}


✔ Legal
✘ Does not imply failure, missed opportunity, or error

7. Predicate Pattern 6 — Exact Non-Occurrence Count (Categorical)
Preconditions

Upstream mapping:

Count	Category
0	NONE
1	SINGLE
>1	MULTIPLE
Predicate
{
  "requires": [
    {
      "operation": "EQUALS",
      "fact_key": "B1.3.non_occurrence_class",
      "expected_value": "MULTIPLE"
    }
  ],
  "forbids": []
}


✔ Legal
✔ Exact category equality
✘ No numeric reasoning

8. Predicate Pattern 7 — Combined Absence Conditions (AND)
Purpose

Gate on multiple independent absence facts.

{
  "requires": [
    {
      "operation": "EXISTS",
      "fact_key": "B1.1.absence_duration"
    },
    {
      "operation": "EXISTS",
      "fact_key": "B1.2.max_void_duration"
    }
  ],
  "forbids": []
}


✔ Legal
✔ Pure conjunction
✘ No weighting or priority

9. Predicate Pattern 8 — Absence vs Presence Exclusivity
Purpose

Require absence while forbidding presence facts.

{
  "requires": [
    {
      "operation": "EXISTS",
      "fact_key": "B1.1.absence_duration"
    }
  ],
  "forbids": [
    {
      "operation": "EXISTS",
      "fact_key": "A6.penetration_depth"
    }
  ]
}


✔ Legal
✔ Structural exclusivity
✘ No interpretation of why

10. Explicitly Invalid Predicate Examples (Rejected by M6)
❌ Numeric comparison (forbidden)
{
  "operation": "GREATER_THAN",
  "fact_key": "B1.1.absence_duration",
  "expected_value": 300
}

❌ Threshold logic (forbidden)
{
  "operation": "EQUALS",
  "fact_key": "B1.2.max_void_duration",
  "expected_value": ">100"
}

❌ Semantic inference (forbidden)
{
  "operation": "EQUALS",
  "fact_key": "B1.3.non_occurrence_count",
  "expected_value": "CRITICAL"
}

11. Design Guarantee

These examples prove:

Tier B-1 primitives are fully usable inside M6

Absence can gate permissions without interpretation

Expressive power comes from composition, not thresholds

Strategy logic is not required for governance validity

12. Recommended Next Freeze Point

At this stage, it is safe to declare:

Tier B-1 × M6 expressiveness = COMPLETE

No further predicates are required to validate absence usage.
