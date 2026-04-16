"""Test per il modulo prompt_builder."""

from __future__ import annotations

from pathlib import Path

from computer_graphics.prompt_builder import PromptBuilder


class TestPromptBuilderBuild:
    def test_returns_dict_with_required_keys(self) -> None:
        builder = PromptBuilder(model="llama3")
        payload = builder.build("una stanza con tavolo")
        assert isinstance(payload, dict)
        assert "model" in payload
        assert "messages" in payload
        assert "stream" in payload
        assert "options" in payload

    def test_model_name_in_payload(self) -> None:
        builder = PromptBuilder(model="mistral")
        payload = builder.build("test")
        assert payload["model"] == "mistral"

    def test_stream_is_false(self) -> None:
        builder = PromptBuilder()
        payload = builder.build("test scena")
        assert payload["stream"] is False

    def test_messages_has_system_and_user(self) -> None:
        builder = PromptBuilder()
        payload = builder.build("una stanza con tavolo")
        messages = payload["messages"]
        roles = [m["role"] for m in messages]
        assert "system" in roles
        assert "user" in roles

    def test_user_message_contains_description(self) -> None:
        builder = PromptBuilder()
        description = "una cucina con frigorifero e tavolo"
        payload = builder.build(description)
        user_msg = next(m for m in payload["messages"] if m["role"] == "user")
        assert description in user_msg["content"]

    def test_system_prompt_contains_json_instruction(self) -> None:
        builder = PromptBuilder()
        payload = builder.build("test")
        system_msg = next(m for m in payload["messages"] if m["role"] == "system")
        assert "JSON" in system_msg["content"]
        assert "name" in system_msg["content"]

    def test_low_temperature_in_options(self) -> None:
        builder = PromptBuilder()
        payload = builder.build("test")
        assert payload["options"]["temperature"] <= 0.3

    def test_custom_system_prompt(self) -> None:
        custom_prompt = "Rispondi sempre con un array JSON."
        builder = PromptBuilder(system_prompt=custom_prompt)
        payload = builder.build("test")
        system_msg = next(m for m in payload["messages"] if m["role"] == "system")
        assert system_msg["content"] == custom_prompt

    def test_system_prompt_from_file(self, tmp_path: Path) -> None:
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Prompt da file di test.", encoding="utf-8")
        builder = PromptBuilder(system_prompt_file=prompt_file)
        payload = builder.build("test")
        system_msg = next(m for m in payload["messages"] if m["role"] == "system")
        assert system_msg["content"] == "Prompt da file di test."

    def test_fallback_to_default_if_file_missing(self) -> None:
        builder = PromptBuilder(system_prompt_file="/file/inesistente.txt")
        payload = builder.build("test")
        # Non deve sollevare eccezioni, usa default
        assert len(payload["messages"]) == 2
