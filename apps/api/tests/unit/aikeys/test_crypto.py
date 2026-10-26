import uuid

import pytest

from app.aikeys.crypto import KeyBox, KeyBoxError, Sealed, generate_master_key, parse_master_keys

WS_A, WS_B = uuid.uuid4(), uuid.uuid4()
SECRET = "not-a-real-key-for-tests"


def box(*versions: int) -> KeyBox:
    return KeyBox.from_setting(",".join(generate_master_key(v) for v in versions))


def test_ac10_round_trip_and_ciphertext_hides_the_key() -> None:
    keybox = box(1)

    sealed = keybox.seal(WS_A, SECRET)

    assert SECRET.encode() not in sealed.ciphertext
    assert len(sealed.nonce) == 12
    assert keybox.open(WS_A, sealed) == SECRET


def test_same_key_encrypts_differently_each_time() -> None:
    keybox = box(1)

    assert keybox.seal(WS_A, SECRET).ciphertext != keybox.seal(WS_A, SECRET).ciphertext


def test_ac10_ciphertext_moved_to_another_workspace_fails() -> None:
    keybox = box(1)

    with pytest.raises(KeyBoxError):
        keybox.open(WS_B, keybox.seal(WS_A, SECRET))


def test_ac10_tampered_ciphertext_fails() -> None:
    keybox = box(1)
    sealed = keybox.seal(WS_A, SECRET)
    flipped = bytes([sealed.ciphertext[0] ^ 1]) + sealed.ciphertext[1:]

    with pytest.raises(KeyBoxError):
        keybox.open(WS_A, Sealed(flipped, sealed.nonce, sealed.key_version))


def test_ac10_wrong_master_key_fails() -> None:
    sealed = box(1).seal(WS_A, SECRET)

    with pytest.raises(KeyBoxError):
        box(1).open(WS_A, sealed)


def test_rotation_new_version_encrypts_old_still_decrypts() -> None:
    v1 = generate_master_key(1)
    old_box = KeyBox.from_setting(v1)
    sealed_v1 = old_box.seal(WS_A, SECRET)

    rotated = KeyBox.from_setting(f"{v1},{generate_master_key(2)}")

    assert rotated.open(WS_A, sealed_v1) == SECRET
    assert rotated.seal(WS_A, SECRET).key_version == 2
    with pytest.raises(KeyBoxError):
        rotated.open(WS_A, Sealed(sealed_v1.ciphertext, sealed_v1.nonce, 7))


@pytest.mark.parametrize("value", ["", "v1", "v1:" + "A" * 10, "key:abc", "v1:!!!"])
def test_bad_master_key_settings_rejected(value: str) -> None:
    with pytest.raises(ValueError, match=r"BYOK|32 bytes|base64|no keys"):
        parse_master_keys(value)
