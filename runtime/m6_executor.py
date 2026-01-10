from observation.types import ObservationSnapshot, ObservationStatus, SystemHaltedException


def execute(observation_snapshot: ObservationSnapshot) -> None:
    if observation_snapshot.status == ObservationStatus.FAILED:
        raise SystemHaltedException("Observation FAILED")
    
    if observation_snapshot.status == ObservationStatus.UNINITIALIZED:
        return
    
    return
