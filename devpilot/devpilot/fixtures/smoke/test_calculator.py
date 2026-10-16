from calculator import add


def test_positive():
    assert add(2, 3) == 5

def test_negative():
    assert add(-7, 2) == -5
