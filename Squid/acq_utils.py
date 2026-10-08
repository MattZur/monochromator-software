import numpy as np

def create_angle_array(
    angle_start: float | None = None,
    angle_stop: float | None = None,
    angle_step: float | None = None,
    fine_ranges: list[tuple[float, float, float]] | None = None,
    include_coarse: bool = True,
) -> np.ndarray:
    """
    Sorted array of scan angles wihtout duplication.

    A coarse sweep (angle_start -> angle_stop inclusive, spacing angle_step) is
    combined with any number of fine ranges given as (start, stop, step).
    Set include_coarse = False to scan only the fine ranges.
    """
    segments = list(fine_ranges or [])
    if include_coarse:
        if None in (angle_start, angle_stop, angle_step):
            raise ValueError(
                "angle_start, angle_stop and angle_step are required when include_coarse = True")
        segments.insert(0, (angle_start, angle_stop, angle_step))
    if not segments:
        raise ValueError("No angles to scan: enable include_coarse or give fine_ranges.")

    angles = np.concatenate([np.arange(a, b + s / 2, s) for a, b, s in segments])
    return np.unique(np.round(angles, 10))