from pipeline.parse import merge_sources, parse_conversation


def test_name_colon_format():
    msgs, inferred = parse_conversation("Officer Lim: This is the police.\nVictim: What?\nOfficer Lim: You must transfer money.")
    assert not inferred and [m.sender for m in msgs] == ["Officer Lim", "Victim", "Officer Lim"]


def test_whatsapp_bracket_format_with_multiline():
    t = "[12/03/24, 3:45:12 PM] John: hello\n[12/03/24, 3:46:00 PM] Mary: line one\nline two\n[12/03/24, 3:47:00 PM] John: bye"
    msgs, inferred = parse_conversation(t)
    assert not inferred and len(msgs) == 3
    assert msgs[1].text == "line one\nline two"


def test_whatsapp_dash_format():
    msgs, inferred = parse_conversation("12/03/2024, 15:45 - Bank Officer: your account\n12/03/2024, 15:46 - Me: ok")
    assert [m.sender for m in msgs] == ["Bank Officer", "Me"]


def test_unlabeled_is_inferred():
    msgs, inferred = parse_conversation("Hi this is your daughter, my phone broke. Please send $500 urgently.")
    assert inferred and len(msgs) == 1 and msgs[0].inferred_sender


def test_single_note_line_is_not_speaker():
    msgs, inferred = parse_conversation("URGENT: your parcel is held, click here to pay fee")
    assert inferred and len(msgs) == 1


def test_urls_not_treated_as_speakers():
    msgs, inferred = parse_conversation("https://evil.com: something\nsecond line of text")
    assert inferred


def test_merge_forwards_and_paste():
    msgs, inferred = merge_sources([("Alice", "hi"), (None, "Bob: yo\nAlice: sup")])
    assert [m.sender for m in msgs] == ["Alice", "Bob", "Alice"] and [m.idx for m in msgs] == [0, 1, 2]
