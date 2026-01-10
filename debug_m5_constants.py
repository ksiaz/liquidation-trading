from memory.m5_constants import FORBIDDEN_VALUE_PATTERNS
print(f"PATTERNS: {FORBIDDEN_VALUE_PATTERNS}")
print(f"Type: {type(FORBIDDEN_VALUE_PATTERNS)}")
print(f"STRONG_ in list? {'STRONG_' in FORBIDDEN_VALUE_PATTERNS}")

test_val = "STRONG_BUY"
upper_val = test_val.upper()
found = False
for p in FORBIDDEN_VALUE_PATTERNS:
    if p in upper_val:
        print(f"Match found: {p} in {upper_val}")
        found = True
if not found:
    print("No match found!")
