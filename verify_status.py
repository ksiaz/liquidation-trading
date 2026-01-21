from observation import ObservationSystem
from observation.types import ObservationStatus
import time

def test_transition():
    print("Initializing ObservationSystem...")
    obs = ObservationSystem(["BTCUSDT"])
    
    print(f"Initial Status: {obs._status}")
    if obs._status != ObservationStatus.UNINITIALIZED:
        print("FAIL: Should be UNINITIALIZED")
        return

    print("Advancing time...")
    obs.advance_time(time.time())
    
    print(f"Post-Advance Status: {obs._status}")
    
    if obs._status == ObservationStatus.ACTIVE:
        print("SUCCESS: Transitioned to ACTIVE")
    else:
        print(f"FAIL: Status is {obs._status}")

if __name__ == "__main__":
    test_transition()
