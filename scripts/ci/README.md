# Constitutional Compliance CI System

This directory contains the enforcement infrastructure for the Constitutional Execution System.

## Architecture

```
scripts/ci/
├── load_schema.py                   # Schema loading utility
├── check_forbidden_imports.py       # R001, R002
├── verify_state_machine.py          # R003
├── verify_arbitration_priority.py   # R004
├── check_new_modules.py             # R005
├── check_frozen_components.py       # R006
├── verify_invariant_coverage.py     # R007
├── check_epistemic_exposure.py      # R008
├── check_m5_query_params.py         # R009
├── check_mandate_types.py           # R010
├── check_dependency_drift.py        # R011
├── check_primitive_computation.py   # R012
├── check_exit_supremacy.py          # R013
├── check_failed_state_terminal.py   # R014
├── check_doc_correspondence.py      # R015 (warning)
├── check_case_sensitivity.py        # R016 (warning)
├── check_timestamp_units.py         # R017
├── scan_forbidden_vocabulary.py     # Vocabulary enforcement
├── validate_schema_completeness.py  # Schema validation
├── verify_modules_exist.py          # Module existence check
├── check_dependency_graph.py        # Cycle detection
└── README.md                        # This file
```

## Quick Start

### Local Testing

```bash
# Test schema loading
python3 scripts/ci/load_schema.py SYSTEM_MAP_SCHEMA.yaml

# Run specific rule
python3 scripts/ci/check_forbidden_imports.py \
  --schema SYSTEM_MAP_SCHEMA.yaml \
  --scan runtime/ \
  --forbidden observation/internal/ memory/m2_ \
  --fail-on-violation

# Test all validators
for script in scripts/ci/check_*.py scripts/ci/verify_*.py; do
  echo "Testing $script..."
  python3 "$script" --help
done
```

### Install Pre-Commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Test on all files
pre-commit run --all-files
```

## Rule Summary

### Blocking Rules (Exit 1)

- **R001**: Forbidden imports (execution → observation)
- **R002**: Observation imports execution
- **R003**: State machine transition table changed
- **R004**: Arbitration priority order changed
- **R005**: New module not registered in schema
- **R006**: Frozen component modified without override
- **R007**: Invariant without enforcement point
- **R008**: Evaluative field in ObservationSnapshot
- **R009**: Forbidden M5 query parameter
- **R010**: Unregistered mandate type
- **R011**: Undeclared dependency
- **R012**: Primitive computation via M5 query
- **R013**: EXIT not checked first
- **R014**: FAILED state has exit transition
- **R017**: Timestamp units incorrect

### Warning Rules (Exit 0)

- **R015**: Doc-code correspondence missing
- **R016**: Case sensitivity handling incomplete

## CI Pipeline

Runs automatically on:
- Pull requests to main/master
- Direct pushes to main/master

See `.github/workflows/constitutional_compliance.yml`

## Troubleshooting

### "Frozen component modified"
Add `OVERRIDE: CODE_FREEZE` to commit message with evidence reference.

### "Forbidden import detected"
Check `forbidden_edges` in schema. Update schema if new dependency required.

### "State machine modified"
State machines are constitutionally frozen. Requires architectural amendment.

### "Schema validation failed"
Ensure schema updated in same commit as code changes.

## Adding New Rules

1. Create validator script following naming convention
2. Add to `CI_VALIDATION_RULES` in schema
3. Add to GitHub Actions workflow
4. Add to pre-commit config
5. Test locally before pushing

## Emergency Override

Only use in production emergencies with:
1. Commit message: `EMERGENCY OVERRIDE: [reason]`
2. Two architect approvals
3. Logged evidence
4. Post-merge audit within 24h

## Contact

For CI issues:
- Review: `SYSTEM_ARCHITECTURE_MAP.md`
- Review: `SYSTEM_MAP_SCHEMA.yaml`
- Consult: System architect
