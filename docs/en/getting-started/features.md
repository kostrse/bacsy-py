# Features

bacsy is a client, not a framework: it gives a Python program typed, paced, authenticated
access to the BCS Trade API and stays out of the way of whatever the program does with
the data. These are the things it does for you that a hand-written wrapper around
`httpx2` would not.

<div class="grid cards" markdown>

-   :lucide-check-check:{ .lg .middle } **Complete and current**

    ---

    Every current REST endpoint and stream of the API, and none of the deprecated ones.

    [:lucide-arrow-right: Account data](../guides/account-data.md)

-   :lucide-braces:{ .lg .middle } **Typed end to end**

    ---

    Pydantic models for every request and response, `Decimal` for every price and
    quantity, and a public interface that passes strict type checking.

    [:lucide-arrow-right: Models](../concepts/models.md)

-   :lucide-key-round:{ .lg .middle } **Tokens managed for you**

    ---

    The `bacsy` command saves, verifies and prunes refresh tokens. The client exchanges
    them for access tokens, caches those, and always presents the least-privileged token
    that can do the job.

    [:lucide-arrow-right: Accounts and tokens](../guides/accounts-and-tokens.md)

-   :lucide-gauge:{ .lg .middle } **Rate limits and retries built in**

    ---

    Requests are paced per API service to the published limits. Transient failures are
    retried with backoff; an order is never sent twice.

    [:lucide-arrow-right: Rate limiting](../concepts/rate-limiting.md)

-   :lucide-radio:{ .lg .middle } **Streams that come back**

    ---

    A dropped WebSocket reconnects, replays its subscriptions and hands you a
    `Reconnected` marker, so your code knows when data may have been missed.

    [:lucide-arrow-right: Streaming](../guides/streaming.md)

-   :lucide-shield-check:{ .lg .middle } **Survives API changes**

    ---

    An unknown field, enum value or instrument kind never raises. Your program keeps
    running when the API grows.

    [:lucide-arrow-right: Models](../concepts/models.md)

-   :lucide-notebook-pen:{ .lg .middle } **Notebook friendly**

    ---

    Top-level `await` in a cell, one line from a response to a DataFrame, and access
    tokens shared across kernel restarts.

    [:lucide-arrow-right: Notebooks](../guides/notebooks.md)

-   :lucide-flask-conical:{ .lg .middle } **Testable**

    ---

    Every seam is a protocol. Inject a mock transport for REST and a fake connector for
    streams, and test your strategy without a network.

    [:lucide-arrow-right: Architecture and testing](../concepts/architecture-and-testing.md)

</div>

## What it leaves to you

bacsy carries no trading strategies, no order-management logic and no market model. It
does not decide when to trade, it does not persist your orders or your data, and it does
not wrap the upstream documentation: the
[official BCS Trade API documentation](https://trade-api.bcs.ru/) remains the reference
for the service's rules, limits and instrument universe. What it guarantees is that every
call you make is typed, paced within the API's limits, authenticated with the least
privileged token you hold, and retried only when retrying is safe.

Ready to try it? The [Quickstart](quickstart.md) installs the package and gets you to your
first quote.
