from uuid import uuid4
import pytest
from pydantic import ValidationError
from services.migraine.time_correction import TimeCorrectionIn


def request(**fields):
    return {'request_id':str(uuid4()),'expected_revision':1,'expected_canonical_updated_at':'2026-01-01T00:00:00Z',**fields}

@pytest.mark.parametrize('utc,wall,offset,valid',[
 ('2026-11-01T06:30:00Z','2026-11-01T01:30:00',-300,True),
 ('2026-11-01T07:30:00Z','2026-11-01T01:30:00',-360,True),
 ('2026-11-01T06:30:00Z','2026-11-01T01:30:00',-360,False),
 ('2026-03-08T08:30:00Z','2026-03-08T02:30:00',-360,False),
 ('2026-03-08T08:30:00Z','2026-03-08T03:30:00',-300,True),
])
def test_strict_gap_fold_offset(utc,wall,offset,valid):
    value=request(start={'utc':utc,'original_time':wall,'timezone_name':'America/Chicago','utc_offset_minutes':offset})
    if valid: assert TimeCorrectionIn.model_validate(value).start.original_time==wall
    else:
        with pytest.raises(ValidationError): TimeCorrectionIn.model_validate(value)

@pytest.mark.parametrize('fields',[{}, {'start':None},{'state':None},{'end':{'utc':'2026-01-01T00:00:00Z'}},{'unexpected':1}])
def test_retain_clear_and_invalid_shapes(fields):
    with pytest.raises(ValidationError): TimeCorrectionIn.model_validate(request(**fields))
    assert 'start' not in TimeCorrectionIn.model_validate(request(end=None)).canonical_request()
    assert TimeCorrectionIn.model_validate(request(end=None)).canonical_request()['end'] is None
