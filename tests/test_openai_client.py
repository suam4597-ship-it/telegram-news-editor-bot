from app.llm.client import extract_output_text


def test_extract_output_text_from_responses_payload() -> None:
    payload = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "{\"ok\":true}"},
                ],
            }
        ]
    }
    assert extract_output_text(payload) == '{"ok":true}'

