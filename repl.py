"""Interactive llang shell.

Type a program and press Enter on a blank line to run it. Definitions persist
between submissions. Use :help for commands.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from llang import LangError, Lexer, Parser, Interpreter  # noqa: E402

HELP = """llang interactive shell
  type code, then press Enter on a blank line to run it
  :help    show this message
  :clear   reset all definitions
  :quit    leave the shell
  Ctrl-C / Ctrl-D also leave
"""


def main() -> None:
    interpreter = Interpreter()
    buffer: list[str] = []
    print("llang — type :help for help")

    while True:
        try:
            prompt = "llang> " if not buffer else "    ... "
            line = input(prompt)
        except (KeyboardInterrupt, EOFError):
            print()
            break

        stripped = line.strip()
        if not buffer and stripped.startswith(":"):
            if stripped in (":quit", ":q"):
                break
            if stripped == ":help":
                print(HELP, end="")
                continue
            if stripped == ":clear":
                interpreter = Interpreter()
                print("definitions cleared")
                continue
            print(f"unknown command: {stripped}")
            continue

        if stripped == "" and buffer:
            source = "\n".join(buffer)
            buffer = []
            try:
                program = Parser(Lexer(source).tokenize()).parse_program()
                interpreter.run(program)
            except LangError as exc:
                print(f"ERROR: {exc.render()}")
            continue

        buffer.append(line)


if __name__ == "__main__":
    main()
