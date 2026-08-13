"""Generate the scrypt hash for the reviewer demo password.

    python -m scripts.hash_demo_password

Prompts (hidden input), prints the hash to paste into DEMO_LOGIN_PASSWORD_HASH.
The plaintext is never written to a file, a log, or the database — only this
hash is stored, and it cannot be reversed.
"""
import getpass
import sys

from app.api.auth_demo import hash_password


def main() -> int:
    pw = getpass.getpass("Reviewer password: ")
    if len(pw) < 8:
        print("Use at least 8 characters — this account will be reachable from the "
              "public internet while App Review is running.", file=sys.stderr)
        return 1
    if pw != getpass.getpass("Confirm: "):
        print("Passwords did not match.", file=sys.stderr)
        return 1

    print("\nAdd these to your production environment:\n")
    print("DEMO_LOGIN_ENABLED=true")
    print("DEMO_LOGIN_EMAIL=<the email you gave Meta>")
    print(f"DEMO_LOGIN_PASSWORD_HASH={hash_password(pw)}")
    print("\nTurn DEMO_LOGIN_ENABLED back to false once App Review is complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
