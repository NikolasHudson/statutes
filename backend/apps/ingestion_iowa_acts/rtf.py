"""Linear, strike-aware RTF text extraction for enrolled Iowa bills.

Why not striprtf (already a dependency): measured superlinear on the LGE
enrolled-bill files — 262 KB → 39 s, and the 1.38 MB omnibus (SF 2385, GA 90)
had to be killed after 18 minutes. This tokenizer is a single O(n) pass.

Why strike-awareness is not optional: amendatory act sections reprint the
amended Code text with deletions in ``\\strike`` runs and insertions in
``\\ul`` runs. Plain text extraction (striprtf, and the official PDFs' text
layer) silently inlines the *repealed* words into the sentence. Dropping
strike runs yields the "resulting law" text; keeping the run boundaries
yields the del/ins segments the supersession pipeline wants.

Scope: the Arbortext ``CDocsPublishRtf`` dialect the legislature publishes
(RTF 1, ANSI/cp1252). Handles the general RTF core — groups, control
words/symbols, ``\\'hh`` escapes, ``\\uN``/``\\uc`` unicode, skippable
destinations — so it degrades gracefully on other producers, but it is not a
general-purpose RTF renderer.
"""

from __future__ import annotations

from dataclasses import dataclass

# Destination groups whose content is never document text. Anything else
# introduced with {\* ...} (an *optional* destination) is skipped per spec.
_SKIP_DESTINATIONS = frozenset(
    {
        "fonttbl",
        "colortbl",
        "stylesheet",
        "info",
        "pict",
        "object",
        "header",
        "footer",
        "headerl",
        "headerr",
        "headerf",
        "footerl",
        "footerr",
        "footerf",
        "field",  # fldinst/fldrslt not used by the LGE dialect
    }
)

# Control symbols / words that emit literal characters.
_LITERALS = {
    "par": "\n",
    "line": "\n",
    "row": "\n",
    "sect": "\n",
    "page": "\n",
    "tab": "\t",
    "cell": "\t",
    "emdash": "—",
    "endash": "–",
    "lquote": "‘",
    "rquote": "’",
    "ldblquote": "“",
    "rdblquote": "”",
    "bullet": "•",
    "emspace": " ",
    "enspace": " ",
}


@dataclass(frozen=True)
class Run:
    """A maximal stretch of text with constant strike/underline state."""

    text: str
    strike: bool
    ul: bool


class _State:
    __slots__ = ("strike", "ul", "skip", "uc")

    def __init__(self, strike=False, ul=False, skip=False, uc=1):
        self.strike = strike
        self.ul = ul
        self.skip = skip
        self.uc = uc

    def copy(self) -> _State:
        return _State(self.strike, self.ul, self.skip, self.uc)


def tokenize(data: bytes) -> list[Run]:
    """One linear pass over the raw RTF bytes → text runs with formatting."""
    # RTF is 7-bit ASCII by design; high bytes only appear via \'hh which we
    # decode explicitly, so latin-1 gives a lossless char-per-byte view.
    s = data.decode("latin-1")
    n = len(s)
    i = 0

    state = _State()
    stack: list[_State] = []
    runs: list[Run] = []
    buf: list[str] = []
    buf_key = (state.strike, state.ul)
    pending_unicode_skip = 0

    def flush():
        nonlocal buf
        if buf:
            runs.append(Run("".join(buf), buf_key[0], buf_key[1]))
            buf = []

    def emit(ch: str):
        nonlocal buf_key
        if state.skip:
            return
        key = (state.strike, state.ul)
        if key != buf_key:
            flush()
            buf_key = key
        buf.append(ch)

    while i < n:
        c = s[i]

        if c == "{":
            stack.append(state)
            state = state.copy()
            i += 1
            # {\* ...}: optional destination — unknown ones are skipped.
            if s.startswith("\\*", i):
                j = i + 2
                # peek the destination control word
                k = j + 1
                while k < n and s[k].isalpha():
                    k += 1
                word = s[j + 1 : k] if j < n and s[j] == "\\" else ""
                if word not in ("ul", "strike"):  # never text-bearing anyway
                    state.skip = True
                i = j
            continue

        if c == "}":
            if stack:
                state = stack.pop()
                if (state.strike, state.ul) != buf_key:
                    flush()
                    buf_key = (state.strike, state.ul)
            i += 1
            continue

        if c == "\\":
            i += 1
            if i >= n:
                break
            c2 = s[i]

            if c2.isalpha():
                j = i
                while j < n and s[j].isalpha():
                    j += 1
                word = s[i:j]
                param = None
                k = j
                if k < n and (s[k] == "-" or s[k].isdigit()):
                    m = k + 1 if s[k] == "-" else k
                    while m < n and s[m].isdigit():
                        m += 1
                    param = int(s[k:m])
                    k = m
                if k < n and s[k] == " ":  # the delimiting space is consumed
                    k += 1
                i = k

                if word == "u" and param is not None:
                    if not state.skip:
                        emit(chr(param + 65536 if param < 0 else param))
                    pending_unicode_skip = state.uc
                    # consume the fallback chars (plain or \'hh)
                    while pending_unicode_skip > 0 and i < n:
                        if s.startswith("\\'", i):
                            i += 4
                        elif s[i] in "{}\\":
                            break
                        else:
                            i += 1
                        pending_unicode_skip -= 1
                elif word == "uc":
                    state.uc = param or 0
                elif word == "strike":
                    state.strike = param != 0
                elif word == "ul":
                    state.ul = param != 0
                elif word == "ulnone":
                    state.ul = False
                elif word in _SKIP_DESTINATIONS:
                    state.skip = True
                elif word in _LITERALS:
                    emit(_LITERALS[word])
                # every other control word is formatting we don't care about
                continue

            # control symbols
            if c2 == "'":
                hex_str = s[i + 1 : i + 3]
                i += 3
                try:
                    emit(bytes([int(hex_str, 16)]).decode("cp1252"))
                except (ValueError, UnicodeDecodeError):
                    pass
                continue
            if c2 == "~":
                emit(" ")
            elif c2 == "-":
                pass  # optional hyphen — invisible unless line-broken
            elif c2 == "_":
                emit("-")
            elif c2 in "{}\\":
                emit(c2)
            elif c2 == "\n" or c2 == "\r":
                emit("\n")
            i += 1
            continue

        # raw CR/LF in the file are NOT document text in RTF
        if c == "\r" or c == "\n":
            i += 1
            continue

        emit(c)
        i += 1

    flush()
    return runs


def resulting_text(runs: list[Run]) -> str:
    """The "resulting law" text: strike (deleted) runs dropped, underline
    (inserted) runs kept as ordinary text. NBSPs normalized to spaces."""
    return "".join(r.text for r in runs if not r.strike).replace(" ", " ")


def full_text_with_markers(runs: list[Run]) -> str:
    """Debug view: deletions wrapped in ⟪…⟫, insertions in ⟦…⟧."""
    out = []
    for r in runs:
        t = r.text.replace(" ", " ")
        if r.strike:
            out.append(f"⟪{t}⟫")
        elif r.ul:
            out.append(f"⟦{t}⟧")
        else:
            out.append(t)
    return "".join(out)
