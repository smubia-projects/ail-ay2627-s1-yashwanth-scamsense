from pipeline.redact import redact_text, Redactor


def test_nric_and_fin():
    r = redact_text("My IC is S1234567D and FIN G7654321K ok")
    assert "S1234567D" not in r.text and "G7654321K" not in r.text
    assert "[NRIC_1]" in r.text and "[NRIC_2]" in r.text


def test_sg_phone_formats():
    for raw in ["91234567", "+65 9123 4567", "9123-4567", "+6591234567", "6123 4567", "81234567"]:
        r = redact_text(f"call me on {raw} now")
        assert "[PHONE_1]" in r.text, raw
        assert raw not in r.text


def test_same_number_same_placeholder():
    r = Redactor()
    out = r.redact("call 91234567") + " | " + r.redact("whatsapp +65 9123 4567 or 98765432")
    assert out.count("[PHONE_1]") == 2 and "[PHONE_2]" in out


def test_international_phone():
    r = redact_text("WhatsApp me at +44 7911 123456")
    assert "7911" not in r.text and "[PHONE_" in r.text


def test_email():
    r = redact_text("send to john.tan+bank@gmail.com asap")
    assert "gmail" not in r.text and "[EMAIL_1]" in r.text


def test_card_luhn_valid_only():
    r = redact_text("card 4111 1111 1111 1111 exp 12/27")
    assert "4111" not in r.text and "[CARD_1]" in r.text
    r2 = redact_text("order ref 1234 5678 9012 3456")  # fails Luhn -> not a card (may be treated as account)
    assert "[CARD_" not in r2.text


def test_bank_account_numbers():
    for raw in ["123-456-789-0", "0123456789", "012-34567-8", "123456789012"]:
        r = redact_text(f"transfer to account {raw} please")
        assert raw not in r.text, raw
        assert "[ACCOUNT_1]" in r.text


def test_otp_code_redacted():
    r = redact_text("Your OTP is 483920. Do not share.")
    assert "483920" not in r.text and "[OTP_1]" in r.text


def test_urls_survive_untouched():
    url = "https://dbs-secure.example.xyz/login?id=1234567890123"
    r = redact_text(f"Click {url} now")
    assert url in r.text


def test_dates_and_amounts_not_redacted():
    t = "On 12/03/2024 at 3:45 PM you paid $1,250.50 for 3 items"
    assert redact_text(t).text == t


def test_counts():
    r = redact_text("S1234567D and 91234567 and a@b.com")
    assert r.counts == {"NRIC": 1, "PHONE": 1, "EMAIL": 1}


def test_no_raw_pii_left_in_mixed_text():
    t = ("Officer Lim here. Your NRIC T0123456A is linked to account 123-456-789-0. Call +65 8123 4567 or "
         "email lim@police-sg.com. Card 5500 0000 0000 0004.")
    out = redact_text(t).text
    for raw in ["T0123456A", "123-456-789-0", "8123 4567", "lim@police-sg.com", "5500 0000 0000 0004"]:
        assert raw not in out
