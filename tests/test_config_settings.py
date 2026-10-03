from config.settings import Settings


def test_gemini_key_alias_is_accepted():
    settings = Settings.model_validate({
        "llm_provider": "gemini",
        "GEMINI_API_KEY": "test-key",
    })

    assert settings.google_api_key == "test-key"
