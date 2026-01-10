"""
Debug why percentage-based tolerance still finds 0 patterns.
Show what buckets are being created.
"""

import sys
sys.path.insert(0, 'd:/liquidation-trading')

from comprehensive_bot_detector import ComprehensiveBotDetector

# Test with the actual fill amounts we saw
fills = [
    ('BID', 1822804.52),
    ('BID', 1865278.98),
    ('BID', 1915899.49),
    ('ASK', 3078163.42),
    ('ASK', 3079043.82),  # Should match with 5% tolerance!
]

detector = ComprehensiveBotDetector(tolerance_pct=0.05)

print("=" * 80)
print("DEBUGGING PERCENTAGE-BASED BUCKETING")
print("=" * 80)

for side, amount in fills:
    bucket = detector._get_bucket(amount)
    bucket_size = amount * 0.05
    
    print(f"\n{side} fill: ${amount:,.2f}")
    print(f"  5% tolerance: ${bucket_size:,.2f}")
    print(f"  Bucket: ${bucket:,.2f}")

# The two ASK fills that should match
print("\n" + "=" * 80)
print("TESTING THE TWO SIMILAR ASK FILLS")
print("=" * 80)

amount1 = 3078163.42
amount2 = 3079043.82
diff = abs(amount2 - amount1)
diff_pct = (diff / amount1 * 100)

bucket1 = detector._get_bucket(amount1)
bucket2 = detector._get_bucket(amount2)

print(f"\nFill 1: ${amount1:,.2f} → Bucket: ${bucket1:,.2f}")
print(f"Fill 2: ${amount2:,.2f} → Bucket: ${bucket2:,.2f}")
print(f"\nDifference: ${diff:,.2f} ({diff_pct:.3f}%)")
print(f"Buckets match: {bucket1 == bucket2}")

if bucket1 != bucket2:
    print(f"\n❌ PROBLEM: Buckets don't match even though fills are {diff_pct:.3f}% apart!")
    print(f"   This is within 5% tolerance but bucketing failed.")
    
    # Show why
    bucket_size1 = amount1 * 0.05
    bucket_size2 = amount2 * 0.05
    
    print(f"\n   Fill 1 bucket size: ${bucket_size1:,.2f}")
    print(f"   Fill 2 bucket size: ${bucket_size2:,.2f}")
    print(f"   Bucket sizes differ by: ${abs(bucket_size2 - bucket_size1):,.2f}")
    
    print(f"\n   The problem: Each fill calculates its OWN bucket size!")
    print(f"   Solution: Use FIXED bucket sizes, not percentage of each fill")

print("\n" + "=" * 80)
