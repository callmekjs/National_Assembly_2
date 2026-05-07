from __future__ import annotations

from . import parser, normalizer, chunker

def main():
    parser.main()
    normalizer.main()
    chunker.main()
    print("[pipeline] completed: parser -> normalizer -> chunker")

if __name__ == "__main__":
    main()
