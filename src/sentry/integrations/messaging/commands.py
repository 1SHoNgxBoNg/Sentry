import itertools
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Generic, TypeVar


@dataclass(frozen=True, eq=True)
class CommandInput:
    cmd_value: str
    arg_values: tuple[str, ...] = ()

    def get_all_tokens(self) -> Iterable[str]:
        yield self.cmd_value
        yield from self.arg_values

    def adjust(self, slug: "CommandSlug") -> "CommandInput":
        """Remove the args that are part of a slug."""
        token_count = len(slug.tokens) - 1
        slug_part = [self.cmd_value] + list(self.arg_values)[:token_count]
        remaining_args = self.arg_values[token_count:]
        return CommandInput(" ".join(slug_part), remaining_args)


class CommandNotMatchedError(Exception):
    def __init__(self, message: str, unmatched_input: CommandInput) -> None:
        super().__init__(message)
        self.unmatched_input = unmatched_input


class CommandSlug:
    def __init__(self, text: str) -> None:
        self.tokens = tuple(token.casefold() for token in text.strip().split())

    def does_match(self, cmd_input: CommandInput) -> bool:
        if not self.tokens:
            return cmd_input.cmd_value == "" and not cmd_input.arg_values
        cmd_prefix = itertools.islice(cmd_input.get_all_tokens(), 0, len(self.tokens))
        cmd_tokens = tuple(token.casefold() for token in cmd_prefix)
        return self.tokens == cmd_tokens

    def __repr__(self):
        joined_tokens = " ".join(self.tokens)
        return f"{type(self).__name__}({joined_tokens!r})"


class MessagingIntegrationCommand:
    def __init__(self, name: str, command_text: str, aliases: Iterable[str] = ()) -> None:
        super().__init__()
        self.name = name
        self.command_slug = CommandSlug(command_text)
        self.aliases = frozenset(CommandSlug(alias) for alias in aliases)

    @staticmethod
    def _to_tokens(text: str) -> tuple[str, ...]:
        return tuple(token.casefold() for token in text.strip().split())

    def get_all_command_slugs(self) -> Iterable[CommandSlug]:
        yield self.command_slug
        yield from self.aliases


MESSAGING_INTEGRATION_COMMANDS = (
    HELP := MessagingIntegrationCommand("HELP", "help", aliases=("", "support", "docs")),
    LINK_IDENTITY := MessagingIntegrationCommand("LINK_IDENTITY", "link"),
    UNLINK_IDENTITY := MessagingIntegrationCommand("UNLINK_IDENTITY", "unlink"),
    LINK_TEAM := MessagingIntegrationCommand("LINK_TEAM", "link team"),
    UNLINK_TEAM := MessagingIntegrationCommand("UNLINK_TEAM", "unlink team"),
)

R = TypeVar("R")  # response


class MessagingIntegrationCommandDispatcher(Generic[R], ABC):
    """The set of commands handled by one messaging integration."""

    @property
    @abstractmethod
    def command_handlers(
        self,
    ) -> Iterable[tuple[MessagingIntegrationCommand, Callable[[CommandInput], R]]]:
        raise NotImplementedError

    def dispatch(self, cmd_input: CommandInput) -> R:
        candidate_handlers = [
            (slug, callback)
            for (command, callback) in self.command_handlers
            for slug in command.get_all_command_slugs()
        ]

        def parsing_order(handler: tuple[CommandSlug, Callable[[CommandInput], R]]) -> int:
            # Sort by descending length of arg tokens. If one slug is a prefix of
            # another (e.g., "link" and "link team"), we must check for the longer
            # one first.
            slug, _ = handler
            return -len(slug.tokens)

        candidate_handlers.sort(key=parsing_order)
        for (slug, callback) in candidate_handlers:
            if slug.does_match(cmd_input):
                arg_input = cmd_input.adjust(slug)
                return callback(arg_input)
        raise CommandNotMatchedError(f"{cmd_input=!r}", cmd_input)