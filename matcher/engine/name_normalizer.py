
import re
import unicodedata

# Common first-name variants
FIRST_NAME_VARIANTS = {
    "mo": "mohamed",
    "mohammed": "mohamed",
    "muhammad": "mohamed",
    "muhammed": "mohamed",
    "mohammad": "mohamed",
    "alex": "alexander",
    "tony": "anthony",
    "mike": "michael",
    "mikey": "michael",
    "tom": "thomas",
    "johnny": "john",
    "jon": "john",
}

# For compound surnames: "van der", "de la", "el", "al", "abu", etc.
COMPOUND_SURNAME_PREFIXES = {
    "van", "der", "de", "la", "del", "di", "da", "dos", "el", "al", "abu"
}


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", text)


def squeeze_repeats(text: str) -> str:
    # shrink "aaaa" -> "aa" (but keep up to two)
    return re.sub(r"(.)\1{2,}", r"\1\1", text)


def basic_clean(text: str) -> str:
    text = text.strip().lower()
    # remove punctuation
    text = re.sub(r"[\.,;:!\?\-_/\\]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_component(text: str, enable_compound: bool = True) -> str:
    if not text:
        return ""
    t = text.strip()
    t = strip_accents(t)
    t = squeeze_repeats(t)
    t = basic_clean(t)
    if not t:
        return ""

    if enable_compound:
        parts = t.split()
        if len(parts) > 1:
            new_parts = []
            i = 0
            while i < len(parts):
                p = parts[i]
                if p in COMPOUND_SURNAME_PREFIXES and i + 1 < len(parts):
                    new_parts.append(p + " " + parts[i + 1])
                    i += 2
                else:
                    new_parts.append(p)
                    i += 1
            t = " ".join(new_parts)
    return t


def canonical_first_name(first: str) -> str:
    if not first:
        return ""
    f = basic_clean(strip_accents(first))
    return FIRST_NAME_VARIANTS.get(f, f)


def soundex_code(name: str) -> str:
    """Simple Soundex-style phonetic code."""
    if not name:
        return ""
    name = basic_clean(strip_accents(name))
    if not name:
        return ""

    first_letter = name[0].upper()

    mapping = {
        "bfpv": "1",
        "cgjkqsxz": "2",
        "dt": "3",
        "l": "4",
        "mn": "5",
        "r": "6",
    }

    def code(ch: str) -> str:
        for letters, digit in mapping.items():
            if ch in letters:
                return digit
        return ""

    digits = [code(ch) for ch in name[1:] if ch.isalpha()]

    filtered = []
    prev = ""
    for d in digits:
        if d and d != prev:
            filtered.append(d)
        prev = d

    code_str = first_letter + "".join(filtered)
    return (code_str + "000")[:4]
