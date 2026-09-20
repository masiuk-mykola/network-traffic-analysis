import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from capture_api.domain.base import Scalar
from capture_api.domain.models import (
    FilterAll,
    FilterAny,
    FilterCond,
    FilterNode,
    FilterNot,
    FilterOp,
)
from capture_api.errors import DomainError
from capture_api.search.compile import FilterError, validate_condition
from capture_api.world.catalog import FIELD_DEFS_BY_NAME

BARE_TOKEN = re.compile(r"[A-Za-z0-9_.:*?/\\-]+")
PUNCTUATION: tuple[str, ...] = ("!=", ">=", "<=", "(", ")", ",", "=", "~")
KEYWORDS: frozenset[str] = frozenset({"and", "or", "not", "in", "cidr", "between", "has"})
RANGE = ".."

SYMBOL_OPS: Mapping[str, FilterOp] = {
    "=": "eq",
    "!=": "eq",
    "~": "glob",
    ">=": "gte",
    "<=": "lte",
}
"""Infix symbols and the operator they mean (``!=`` is wrapped in ``not`` afterwards)."""

type TokenKind = Literal["bare", "string", "punct", "end"]


class LqlError(Exception):
    def __init__(self, detail: str, pos: int, end: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.pos = pos
        self.end = end

    def as_domain_error(self) -> DomainError:
        return DomainError(
            422, "lql_syntax", self.detail, extra={"ctx": {"pos": self.pos, "end": self.end}}
        )


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    text: str
    pos: int
    end: int
    value: str = ""

    @property
    def keyword(self) -> str | None:
        folded = self.text.casefold()
        return folded if self.kind == "bare" and folded in KEYWORDS else None


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if char == '"':
            token = _quoted(source, index)
            tokens.append(token)
            index = token.end
            continue
        punct = next((p for p in PUNCTUATION if source.startswith(p, index)), None)
        if punct is not None:
            tokens.append(Token("punct", punct, index, index + len(punct), punct))
            index += len(punct)
            continue
        match = BARE_TOKEN.match(source, index)
        if match is None:
            raise LqlError(f"Unexpected character {char!r}.", index, index + 1)
        tokens.append(Token("bare", match.group(), index, match.end(), match.group()))
        index = match.end()
    tokens.append(Token("end", "", length, length))
    return tokens


def _quoted(source: str, start: int) -> Token:
    parts: list[str] = []
    index = start + 1
    while index < len(source):
        char = source[index]
        if char == "\\" and index + 1 < len(source):
            parts.append(source[index + 1])
            index += 2
            continue
        if char == '"':
            text = source[start : index + 1]
            return Token("string", text, start, index + 1, "".join(parts))
        parts.append(char)
        index += 1
    raise LqlError("Unterminated string.", start, len(source))


class Parser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.tokens = tokenize(source)
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def advance(self) -> Token:
        token = self.tokens[self.index]
        if token.kind != "end":
            self.index += 1
        return token

    def accept_keyword(self, keyword: str) -> bool:
        if self.current.keyword == keyword:
            self.advance()
            return True
        return False

    def expect_punct(self, text: str) -> Token:
        token = self.current
        if token.kind != "punct" or token.text != text:
            raise LqlError(f"Expected '{text}'.", token.pos, max(token.end, token.pos + 1))
        return self.advance()

    def parse(self) -> FilterNode:
        if self.tokens[0].kind == "end":
            return FilterAll(all=[])
        node = self.parse_or()
        if self.current.kind != "end":
            token = self.current
            raise LqlError(f"Unexpected {token.text!r}.", token.pos, max(token.end, token.pos + 1))
        return node

    def parse_or(self) -> FilterNode:
        options = [self.parse_and()]
        while self.accept_keyword("or"):
            options.append(self.parse_and())
        return options[0] if len(options) == 1 else FilterAny(any=options)

    def parse_and(self) -> FilterNode:
        parts = [self.parse_unary()]
        while True:
            if self.accept_keyword("and"):
                parts.append(self.parse_unary())
                continue
            if not self._starts_unary():
                break
            parts.append(self.parse_unary())
        return parts[0] if len(parts) == 1 else FilterAll(all=parts)

    def _starts_unary(self) -> bool:
        token = self.current
        if token.kind == "end":
            return False
        if token.kind == "punct":
            return token.text == "("
        return token.keyword in (None, "not", "has")

    def parse_unary(self) -> FilterNode:
        token = self.current
        if token.keyword == "not":
            self.advance()
            return FilterNot(not_=self.parse_unary())
        if token.kind == "punct" and token.text == "(":
            self.advance()
            node = self.parse_or()
            self.expect_punct(")")
            return node
        if token.keyword == "has":
            self.advance()
            name = self._field()
            return self._condition(name, "exists", [], name.pos, name.end)
        return self.parse_condition()

    def _field(self) -> Token:
        token = self.current
        if token.kind != "bare" or token.keyword is not None:
            raise LqlError("Expected a field name.", token.pos, max(token.end, token.pos + 1))
        return self.advance()

    def parse_condition(self) -> FilterNode:
        name = self._field()
        token = self.current
        if token.kind == "punct" and token.text in SYMBOL_OPS:
            self.advance()
            value = self._value()
            node = self._condition(name, SYMBOL_OPS[token.text], [value.value], name.pos, value.end)
            return FilterNot(not_=node) if token.text == "!=" else node
        keyword = token.keyword
        if keyword == "in":
            self.advance()
            return self._parse_in(name)
        if keyword == "cidr":
            self.advance()
            value = self._value()
            return self._condition(name, "cidr", [value.value], name.pos, value.end)
        if keyword == "between":
            self.advance()
            return self._parse_between(name)
        raise LqlError(
            f"Expected an operator after '{name.text}'.",
            token.pos,
            max(token.end, token.pos + 1),
        )

    def _value(self) -> Token:
        token = self.current
        if token.kind not in ("bare", "string"):
            raise LqlError("Expected a value.", token.pos, max(token.end, token.pos + 1))
        return self.advance()

    def _parse_in(self, name: Token) -> FilterNode:
        self.expect_punct("(")
        values = [self._value()]
        while self.current.kind == "punct" and self.current.text == ",":
            self.advance()
            values.append(self._value())
        closing = self.expect_punct(")")
        return self._condition(name, "in", [token.value for token in values], name.pos, closing.end)

    def _parse_between(self, name: Token) -> FilterNode:
        first = self._value()
        text = first.value
        if RANGE in text:
            low, _, rest = text.partition(RANGE)
            if not low:
                raise LqlError("Expected a lower bound.", first.pos, first.end)
            if rest:
                return self._condition(name, "between", [low, rest], name.pos, first.end)
            high = self._value()
            return self._condition(name, "between", [low, high.value], name.pos, high.end)
        separator = self.current
        if separator.kind != "bare" or not separator.text.startswith(RANGE):
            raise LqlError(
                "Expected '..' between the bounds.",
                separator.pos,
                max(separator.end, separator.pos + 1),
            )
        self.advance()
        tail = separator.text[len(RANGE) :]
        if tail:
            return self._condition(name, "between", [text, tail], name.pos, separator.end)
        high = self._value()
        return self._condition(name, "between", [text, high.value], name.pos, high.end)

    def _condition(
        self, name: Token, op: FilterOp, values: Sequence[str], pos: int, end: int
    ) -> FilterCond:
        field = name.text if name.text in FIELD_DEFS_BY_NAME else name.text.casefold()
        try:
            if op == "exists":
                cond = FilterCond(field=field, op=op)
            elif op in ("in", "between"):
                cond = FilterCond(field=field, op=op, values=list(values))
            else:
                cond = FilterCond(field=field, op=op, value=values[0])
            validate_condition(cond)
        except FilterError as exc:
            raise LqlError(exc.detail, pos, end) from exc
        except ValueError as exc:
            raise LqlError(str(exc).removeprefix("Value error, "), pos, end) from exc
        return cond


def _needs_quotes(value: str) -> bool:
    return value == "" or BARE_TOKEN.fullmatch(value) is None or value.casefold() in KEYWORDS


def quote(value: Scalar) -> str:
    text = str(value)
    if not _needs_quotes(text):
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _print_condition(cond: FilterCond) -> str:
    values = cond.values or ([] if cond.value is None else [cond.value])
    if cond.op == "exists":
        return f"has {cond.field}"
    if cond.op == "in":
        return f"{cond.field} in ({', '.join(quote(item) for item in values)})"
    if cond.op == "between":
        low, high = values[0], values[1]
        return f"{cond.field} between {quote(low)} .. {quote(high)}"
    symbols: dict[str, str] = {"eq": "=", "glob": "~", "gte": ">=", "lte": "<=", "cidr": "cidr"}
    return f"{cond.field} {symbols[cond.op]} {quote(values[0])}"


def normalize(node: FilterNode) -> str:
    if isinstance(node, FilterAll):
        if not node.all:
            return ""
        return " and ".join(_wrap_in_and(child) for child in node.all)
    if isinstance(node, FilterAny):
        return " or ".join(normalize(child) for child in node.any)
    if isinstance(node, FilterNot):
        return f"not ({normalize(node.not_)})"
    return _print_condition(node)


def _wrap_in_and(node: FilterNode) -> str:
    text = normalize(node)
    return f"({text})" if isinstance(node, FilterAny) else text


def parse(source: str) -> tuple[FilterNode, str]:
    node = Parser(source).parse()
    return node, normalize(node)
