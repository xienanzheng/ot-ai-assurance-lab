import pytest
from pydantic import ValidationError

from shared.models import ActuatorCommand, ControlProposal, SetpointChanges


def test_actuator_percent_is_bounded():
    with pytest.raises(ValidationError):
        ActuatorCommand(high_lift_pump_speed_pct=101)


def test_proposal_confidence_is_bounded():
    with pytest.raises(ValidationError):
        ControlProposal(
            changes=SetpointChanges(),
            expected_effect="No change",
            confidence=1.2,
            explanation="Invalid confidence",
        )


def test_malformed_model_output_is_rejected():
    with pytest.raises(ValidationError):
        ControlProposal.model_validate_json('{"changes": "open pump"}')

