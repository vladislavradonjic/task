import sys


def main() -> None:
    args = sys.argv
    for i, arg in enumerate(args):
        print(f"{i}: {arg!r}")


if __name__ == "__main__":
    main()