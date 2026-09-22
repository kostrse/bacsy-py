# Getting help

Most questions are answered by the page that owns the topic: the guides for how to do
something, the concepts for how the library behaves, and the [Reference](../reference/client.md)
for every signature, command and exit code. The site search covers all of them. When a
page is wrong or leaves you guessing, that is a bug in the documentation and worth an
issue as much as a bug in the code.

## Questions and bugs

Open an issue on [GitHub](https://github.com/kostrse/bacsy-py/issues). A bug report says
which version of bacsy and of Python you run, what you did, what you expected and what
happened, with the error text. A feature request says what you are trying to do rather
than which method you would like to exist; bacsy is a client library only, so trading
strategies and order bots are out of scope.

!!! warning

    Remove every token, agreement id, client code, login, order number and amount before
    you paste anything. The `text` of an API error is written by the broker and may
    contain account data; a report that contains a credential is deleted, not edited.

The version is printed by `bacsy --version`, and by `bacsy.__version__` in Python.

## Questions about the API itself

The library implements the service; it does not define it. Which instruments exist, what
a board means, when a session opens, how an order is settled and what the daily limits
are, are questions for the
[official BCS Trade API documentation](https://trade-api.bcs.ru/) and for BCS support.
bacsy documents an upstream fact only where the library depends on it, such as the
[token lifetimes](../concepts/bcs-api-tokens.md) and the
[rate limits](../concepts/rate-limiting.md).

## Security problems

A vulnerability in how the library handles tokens matters more than most bugs. Report it
privately through
[GitHub's vulnerability reporting](https://github.com/kostrse/bacsy-py/security/advisories/new),
never in a public issue; the
[security policy](https://github.com/kostrse/bacsy-py/blob/main/.github/SECURITY.md) says
what to include and what to expect.

## Contributing

Fixes and improvements are welcome. The
[contributing guide](https://github.com/kostrse/bacsy-py/blob/main/.github/CONTRIBUTING.md)
describes the checks a change must pass and how AI-assisted changes are accepted. Open
an issue before starting a large change, so the design is agreed first.
