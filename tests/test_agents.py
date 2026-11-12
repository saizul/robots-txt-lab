import pytest

from robots_txt_lab.agents import agent_profile, crawler_token, is_valid_token, product_token


@pytest.mark.parametrize(
    ("value", "token"),
    [
        ("Googlebot", "googlebot"),
        ("googlebot/1.2", "googlebot"),
        ("googlebot*", "googlebot"),
        ("  Googlebot-News ", "googlebot-news"),
        ("*", "*"),
        ("* ", "*"),
        ("*bot", ""),
        ("* comment", "*"),
        ("Storebot-Google", "storebot-google"),
        ("my_bot", "my_bot"),
        ("/bad", ""),
        ("", ""),
    ],
)
def test_product_token(value, token):
    assert product_token(value) == token


def test_is_valid_token():
    assert is_valid_token("Googlebot-Image")
    assert is_valid_token("*")
    assert not is_valid_token("Googlebot/2.1")
    assert not is_valid_token("bot 2")


@pytest.mark.parametrize(
    ("ua", "token"),
    [
        ("Googlebot", "googlebot"),
        ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "googlebot"),
        ("Googlebot-Image/1.0", "googlebot-image"),
        (
            "Mozilla/5.0 (Linux; Android 8.0; Pixel 2 Build/OPD3.170816.012; Storebot-Google/1.0) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "storebot-google",
        ),
        ("Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)", "bingbot"),
        ("Mozilla/5.0 (compatible; ExampleBot/0.1; https://www.example.com/bot.html)", "examplebot"),
        ("*", "*"),
    ],
)
def test_crawler_token(ua, token):
    assert crawler_token(ua) == token


def test_google_profile_fallbacks():
    p = agent_profile("Googlebot-Image")
    assert p.tokens == ("googlebot-image", "googlebot")
    assert p.use_global
    assert agent_profile("Storebot-Google").tokens == ("storebot-google",)


def test_google_profile_global_ignored_for_adsbot():
    assert agent_profile("AdsBot-Google").use_global is False
    assert agent_profile("Mediapartners-Google").use_global is False


def test_rfc_profile_has_no_special_cases():
    p = agent_profile("Googlebot-Image", "rfc")
    assert p.tokens == ("googlebot-image",)
    assert agent_profile("AdsBot-Google", "rfc").use_global
