TARGET_MODULE = "common.utils.util"


def test_is_sshable_returns_false(get_handler):
    subject = get_handler(TARGET_MODULE)

    assert subject.is_sshable("127.0.0.1", "username", "password") is False
    assert subject.is_sshable("www.google.com", "username", "password") is False
