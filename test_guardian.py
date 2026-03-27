"""Tests for guardian.py — JSON extraction and diff collection."""

from guardian import extract_json


# --- JSON extraction ---

# Verifies: extract_json parses a raw JSON object from plain text
def test_extract_json_raw():
    text = 'Some text before {"complete": true, "summary": "all done"} some text after'
    result = extract_json(text)
    assert result == {"complete": True, "summary": "all done"}


# Verifies: extract_json parses JSON from a markdown code block
def test_extract_json_code_block():
    text = """Here are my findings:

```json
{"confident": false, "gaps": ["missing dedup test"]}
```

I will fix these now."""
    result = extract_json(text)
    assert result == {"confident": False, "gaps": ["missing dedup test"]}


# Verifies: extract_json prefers code block JSON over raw JSON when both are present
def test_extract_json_prefers_code_block():
    text = """Some {"noise": true} before

```json
{"confident": true}
```"""
    result = extract_json(text)
    assert result == {"confident": True}


# Verifies: extract_json returns None when no valid JSON is found
def test_extract_json_no_json():
    result = extract_json("No JSON here at all")
    assert result is None


# Verifies: extract_json returns None for malformed JSON rather than raising
def test_extract_json_malformed():
    result = extract_json('{"broken": }')
    assert result is None


# Verifies: extract_json handles the complete:true response from Phase 2
def test_extract_json_phase2_complete():
    text = '```json\n{"complete": true, "summary": "Added 12 tests covering all integration paths"}\n```'
    result = extract_json(text)
    assert result["complete"] is True
    assert "integration" in result["summary"]


# Verifies: extract_json handles the complete:false response with remaining work list
def test_extract_json_phase2_incomplete():
    text = '{"complete": false, "remaining": ["error path for handlePush", "geofence boundary test"]}'
    result = extract_json(text)
    assert result["complete"] is False
    assert len(result["remaining"]) == 2


# Verifies: extract_json handles the confident:true response from Phase 3
def test_extract_json_phase3_confident():
    text = '```json\n{"confident": true}\n```'
    result = extract_json(text)
    assert result["confident"] is True


# Verifies: extract_json handles the confident:false response with gaps list from Phase 3
def test_extract_json_phase3_gaps():
    text = """I found some remaining issues:

```json
{"confident": false, "gaps": ["no test for email dedup flow", "mock DB not verified"]}
```"""
    result = extract_json(text)
    assert result["confident"] is False
    assert len(result["gaps"]) == 2


# Verifies: extract_json handles the mismatches response from comment validation gate
def test_extract_json_comment_validation():
    text = '{"mismatches": ["test.ts:42 — comment claims dedup but assertion only checks toBeDefined"]}'
    result = extract_json(text)
    assert len(result["mismatches"]) == 1
