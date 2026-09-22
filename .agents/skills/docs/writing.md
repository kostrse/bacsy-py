# Writing the documentation

These rules keep pages written at different times, by different people or agents, reading
as one site. `SKILL.md` covers the mechanics; this file covers the words.

## Voice and shape

- Write in the second person, present tense. One idea per paragraph, usually three to five
  sentences. A page answers one question, and its first paragraph says which.
- Prefer prose over structure. A bullet list has at most six items; anything with three or
  more comparable rows is a table. Never nest lists.
- A page stays under about 1200 words, a code block under 25 lines. "Command line" and
  "BCS API tokens" in the reference and concepts may run longer, since they are looked up,
  not read.
- At most one admonition per H2 section. `!!! warning` is reserved for money and orders,
  `!!! tip` for notebook asides and shortcuts, `!!! note` for upstream quirks. Use
  `??? note "…"` for material most readers can skip.
- Tabs (`=== "Script"` / `=== "Notebook"`) show the same example in two settings; do not
  use them for unrelated content.
- Say what the code does, not what the reader will now see. No "let's", no "simply", no
  "note that", no exclamation marks.
- Headings are sentence case, short, and name the task or the thing: "Placing an order",
  "Connection caps". No "Introduction" or "Overview" headings; the first paragraph is the
  introduction.

## Terminology

The exact terms are **refresh token** and **access token**. The BCS web terminal calls the
credential it issues an "API token"; Home, Installation, Quickstart and Accounts and tokens
bridge once, on first use, as "API token (refresh token)", and then say "refresh token"
where access tokens are also in play and plain "token" where they are not. No other page
says "API token".

| Term | Meaning |
| --- | --- |
| account | a name bacsy keeps tokens under, such as `main`; never the brokerage account |
| brokerage account | the agreement at the broker that a token gives access to |
| scope | what a token may do: `read` or `write`; a write token also reads |
| the BCS web terminal | where tokens are issued and deleted |
| token endpoint | the upstream service that exchanges a refresh token for an access token |
| service | one of the API's microservices: portfolio, limits, margin, instruments, market data, orders, trades, operations |
| instrument key | a ticker and a class code together; the only way to name an instrument |
| board, class code | the trading board an instrument is quoted on and its code, such as `TQBR` |
| stream | one WebSocket connection with its subscriptions |
| event | one message a stream yields |
| `Reconnected` | the marker a stream yields after it reconnected; data may have been missed |
| state directory | the one directory where bacsy keeps the accounts file and the access-token cache |
| settlement term | `T0`, `T1`, `T2` or `T365`, the planned position |

Tokens are "issued" and "deleted" in the web terminal; bacsy "saves", "removes", "prunes"
and "verifies" them. Orders are "placed", "edited" and "cancelled". A stream is "opened"
and "closed", a subscription "added" and "removed".

## Example vocabulary

Every example uses the same names, so a reader who moves between pages recognises the
setup at once.

| Thing | Use |
| --- | --- |
| account name | `main` |
| first instrument | `("SBER", "TQBR")` |
| second instrument | `("GAZP", "TQBR")` |
| derivatives | only on pages about them, since contract codes expire |
| variables | `client`, `stream`, `event`, `quote`, `quotes`, `order`, `report`, `page`, `positions`, `position` |
| entry point | one `async def main() -> None`, run with `asyncio.run(main())` |

A script example is complete: imports, `main`, and `asyncio.run(main())` at the bottom. A
notebook example is a cell body with top-level `await` and never calls `asyncio.run`; it
sits in a `=== "Notebook"` tab or on a page that says it is for notebooks.

Every guide after Client setup opens with the sentence "Examples assume `client` is an open
`TradeApiClient`; see [Client setup](client-setup.md)." and its examples then show only the
body that uses `client`. Do not repeat client creation on those pages.

Imports: `from bacsy import ...` for anything in `bacsy.__all__`, `from bacsy.models import
...` for models. Never `import bacsy`, never `from bacsy.client import ...`. Cross references
still use the defining path, `[TradeApiClient][bacsy.client.TradeApiClient]`, whatever the
import line shows.

Output in examples is shown sparingly, as a `text` block, and is invented but plausible.
Tokens appear only in the redacted form `eyJh**********lCGA`. Never a real token, account
identifier, client code, login or captured response.

Before using any name in an example, check it exists in `src/bacsy` with the exact
signature; the example checker type-checks every Python block, and a guessed method name
fails the build.

## Fact ownership

Each fact lives on one page. Another page that needs it links there instead of restating
it, so a change in the code is a change in one place.

| Fact | Owner |
| --- | --- |
| the three factories, config defaults table, client lifetime | Guides → Client setup |
| recommended token workflows, rotation, hygiene | Guides → Accounts and tokens |
| pagination rules, history floors | Guides → Account data |
| boards and class codes, instrument keys | Guides → Instruments |
| REST market-data limits (quotes, depth, bars) | Guides → Market data |
| uncertain order outcome procedure, `client_order_id` | Guides → Orders |
| stream caps, per-connection limits, event table | Guides → Streaming |
| the four error categories, exception table | Guides → Errors and retries |
| provider selection rule, caches, state-directory contents | Concepts → Authentication |
| every upstream token fact: lifetimes, claims, endpoint, rejection order | Concepts → BCS API tokens |
| per-service budgets, retry decision table, backoff | Concepts → Rate limiting |
| data types, lenient enums, unions and fallbacks | Concepts → Models |
| connection mechanics, replay, queue | Concepts → Streams |
| layers, seams, testing recipe | Concepts → Architecture and testing |
| QUIK table and field glossary | Concepts → QUIK lineage |
| every command, option, JSON shape, exit code, status value, account-name rule | Reference → Command line |
| the three environment variables and the no-precedence rule | Reference → Environment variables |

## Links

Link the first mention of a page-owned fact and the first mention of a public object
on a page; later mentions are plain code spans. Link text is the page title or the object
name, never "here" or "this page". Relative `.md` links between pages, mkdocstrings
references for objects; both are checked by the strict build.

## Reference pages

A reference page is an intro paragraph that says what the objects are for and links the
guide, then `:::` directives under H2 headings. Every object is rendered once, on the page
of its defining module. A wrong or missing description is fixed in the docstring.

## Russian

A page not yet translated holds the placeholder from `SKILL.md`. Navigation titles in
`zensical.ru.toml` are translated when the page is added, so the two navigations always
have the same shape.
