from load_u2 import dec, num


def test_num_preserves_null():
    assert num(None) is None


def test_dec_preserves_null():
    assert dec(None, 2) is None
