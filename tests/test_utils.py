from app.routes.urls import generate_short_code, is_valid_url

def test_generate_short_code_length():
    code = generate_short_code()
    assert len(code) == 6

def test_generate_short_code_randomness():
    code1 = generate_short_code()
    code2 = generate_short_code()
    assert code1 != code2

def test_is_valid_url():
    # Valid Cases
    assert is_valid_url("https://example.com") is True
    assert is_valid_url("http://example.org/path?q=1") is True
    
    # Invalid Cases
    assert is_valid_url("example.com") is False
    assert is_valid_url("htt:/example") is False
    assert is_valid_url("not-a-url") is False