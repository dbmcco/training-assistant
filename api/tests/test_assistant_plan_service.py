from src.services.assistant_plan import DayTemplate, _build_workout_prescription


def test_endurance_run_prescription_has_pace_and_distance():
    template = DayTemplate(
        discipline="run",
        workout_type="endurance_run",
        duration_min=55,
        description="placeholder",
    )

    prescription = _build_workout_prescription(
        template=template,
        phase="build",
        week_index=0,
    )

    assert prescription.target_distance_meters is not None
    assert prescription.target_distance_meters > 5000
    assert prescription.target_hr_zone == 2
    assert "Session Plan:" in prescription.description
    assert "9:00-9:30/mi" in prescription.description
    assert len(prescription.workout_steps) >= 4


def test_swim_prescription_has_yard_pacing():
    template = DayTemplate(
        discipline="swim",
        workout_type="endurance_builder",
        duration_min=50,
        description="placeholder",
    )

    prescription = _build_workout_prescription(
        template=template,
        phase="build",
        week_index=0,
    )

    assert prescription.target_distance_meters is not None
    assert prescription.target_distance_meters > 1500
    assert "2:05/100yd" in prescription.description
    assert any("100 yd" in step.get("notes", "") for step in prescription.workout_steps)


def test_strength_prescription_has_bodyweight_circuit():
    template = DayTemplate(
        discipline="strength",
        workout_type="mobility_strength",
        duration_min=35,
        description="placeholder",
    )

    prescription = _build_workout_prescription(
        template=template,
        phase="build",
        week_index=0,
    )

    assert "Circuit A" in prescription.description
    assert "squat x12" in prescription.description
    assert prescription.target_distance_meters is None
    assert prescription.target_hr_zone is None
    assert len(prescription.workout_steps) >= 4
