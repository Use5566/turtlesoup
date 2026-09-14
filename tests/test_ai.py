import pytest
from backend.ai import Gemini, AIError, PAIRS, display


@pytest.mark.parametrize('kind', list(PAIRS))
def test_exact_whitelist(kind):
    assert display('yes', kind) == PAIRS[kind][0]
    assert display('no', kind) == PAIRS[kind][1]
    assert display('irrelevant', kind) == '無關'


class Response:
    status_code = 200
    def __init__(self, data): self.data = data
    def json(self): return self.data


def response(text):
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': text}]}}],
            'usageMetadata': {'totalTokenCount': 22}}


@pytest.mark.parametrize('text', ['{"decision":"yes","reason":"secret"}', '{"decision":"maybe"}', '是，因為湯底是…', '[]'])
def test_nonconforming_output_rejected(settings, monkeypatch, text):
    settings.gemini_api_key = 'test-only'
    monkeypatch.setattr('httpx.post', lambda *a, **k: Response(response(text)))
    with pytest.raises(AIError) as e:
        Gemini(settings).judge({'surface': 's', 'solution': 'secret'}, 'question', 'is', [])
    assert e.value.code == 'invalid_output'


def test_no_key_never_sends_network(settings, monkeypatch):
    def forbidden(*a, **k): pytest.fail('unexpected network')
    monkeypatch.setattr('httpx.post', forbidden)
    with pytest.raises(AIError) as e:
        Gemini(settings).judge({}, 'question', 'is', [])
    assert e.value.code == 'not_configured'


def test_payload_schema_and_usage(settings, monkeypatch):
    settings.gemini_api_key = 'test-only'
    def post(url, **kwargs):
        assert url.endswith('gemini-3.5-flash-lite:generateContent')
        assert 'test-only' not in url
        assert kwargs['json']['generationConfig']['responseMimeType'] == 'application/json'
        assert kwargs['headers']['x-goog-api-key'] == 'test-only'
        return Response(response('{"decision":"no"}'))
    monkeypatch.setattr('httpx.post', post)
    data = Gemini(settings).judge({'surface': 's', 'solution': 'private'}, 'q', 'is', [])
    assert data.decision == 'no' and data.usage['totalTokenCount'] == 22
