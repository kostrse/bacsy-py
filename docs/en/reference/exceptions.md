# Exceptions

Every error derives from `BacsyError` and belongs to one of four categories, named for what
the caller does next: `TransportError`, `ConfigurationError`, `AuthError` and `ApiError`.
An error that came from an HTTP response carries it as `response`, and `transient` says
whether the same call may succeed later without a change on the caller's side. A bad
argument to a library call raises `ValueError`, as in the standard library.
[Errors and retries](../guides/errors-and-retries.md) shows how to handle them.

::: bacsy.exceptions
