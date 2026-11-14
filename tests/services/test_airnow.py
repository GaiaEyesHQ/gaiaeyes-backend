import httpx
import pytest
from services.external import airnow

pytestmark = pytest.mark.anyio

@pytest.fixture
def anyio_backend():
    return "asyncio"

def mock_provider(monkeypatch, handler):
    client = httpx.AsyncClient
    monkeypatch.setattr(airnow, "API_KEY", "test-private-key")
    monkeypatch.setattr(airnow.httpx, "AsyncClient",
                        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs))

@pytest.mark.parametrize("coordinates", [False, True])
async def test_current_observations_preserve_contract(monkeypatch, coordinates):
    def handler(request):
        assert request.url.path == "/aq/observation/current/ziplatlong/"
        assert "distance" not in request.url.params
        assert request.url.params["API_KEY"] == "test-private-key"
        if coordinates:
            assert request.url.params["latitude"] == "30.3423"
            assert request.url.params["longitude"] == "-97.6673"
        else:
            assert request.url.params["zipCode"] == "78754"
        return httpx.Response(200, json=[
            {"nowcastAQI": 52, "aqiCategoryName": "Moderate", "parameterName": "PM2.5"},
            {"nowcastAQI": 0, "aqiCategoryName": "Good", "parameterName": "OZONE"},
            {"nowcastAQI": None}, {"nowcastAQI": -999},
        ])
    mock_provider(monkeypatch, handler)
    rows = (await airnow.current_by_latlon(30.3423, -97.6673) if coordinates
            else await airnow.current_by_zip("78754"))
    assert rows == [
        {"AQI": 52, "Category": {"Name": "Moderate"}, "ParameterName": "PM2.5"},
        {"AQI": 0, "Category": {"Name": "Good"}, "ParameterName": "O3"},
    ]

@pytest.mark.parametrize("failure", ["status", "timeout"])
async def test_errors_do_not_expose_credentials(monkeypatch, failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout(str(request.url), request=request)
        return httpx.Response(410)
    mock_provider(monkeypatch, handler)
    with pytest.raises(httpx.HTTPError) as error:
        await airnow.current_by_zip("78754")
    assert "test-private-key" not in str(error.value)
    assert "API_KEY" not in str(error.value)
    assert ("410" if failure == "status" else "ReadTimeout") in str(error.value)

@pytest.mark.parametrize("body", [b"[]", b""])
async def test_empty_response(monkeypatch, body):
    mock_provider(monkeypatch, lambda request: httpx.Response(200, content=body))
    assert await airnow.current_by_zip("78754") == []

async def test_missing_key(monkeypatch):
    monkeypatch.setattr(airnow, "API_KEY", "")
    assert await airnow.current_by_zip("78754") == []

async def test_error_envelope(monkeypatch):
    mock_provider(monkeypatch, lambda request: httpx.Response(200, json={"WebServiceError": [{"Message": "private detail"}]}))
    with pytest.raises(ValueError, match="unexpected AirNow response shape"):
        await airnow.current_by_zip("78754")

async def test_invalid_observations(monkeypatch):
    mock_provider(monkeypatch, lambda request: httpx.Response(200, json=[
        None, "bad", {"nowcastAQI": True}, {"nowcastAQI": "52"},
        {"nowcastAQI": -999}, {"nowcastAQI": 0, "parameterName": "PM2.5"},
    ]))
    assert await airnow.current_by_zip("78754") == [
        {"AQI": 0, "Category": {"Name": None}, "ParameterName": "PM2.5"},
    ]
