# Will Native MT5 make money?

You asked me to look through this and advise. Short answer: **yes, but not from
the code, and not at the scale the category tempts people to imagine.**

The code is the giveaway. The business, if there is one, is the hosted bridge
and the risk-compliance layer.

## The one-line version

Sell **drawdown protection to funded prop-firm traders**, delivered as a hosted
Windows bridge so it works from a Mac. Realistic ceiling is a $60k–150k/year
business inside two years. That is a good small business and a bad venture bet.

## What is actually scarce here

Three things, in descending order of how much someone will pay for them.

### 1. The Windows problem (highest willingness to pay, lowest defensibility)

The `MetaTrader5` Python package ships **Windows wheels only**. Every Mac and
Linux trader who wants this has to run a Windows VM, a Wine setup, or a VPS.
That is a genuine, universally-hated chore.

A hosted bridge — "connect your MT5 account in two minutes, works from any
machine" — is a real product with an obvious price tag. It is also the part
someone else can copy in a weekend, so it earns money without protecting it.

**Price:** $15–29/month. **Cost:** a small Windows VPS per user, roughly
$8–12/month at retail, less in bulk. Margin is thin until you multiplex.

### 2. Prop-firm rule compliance (the actual wedge)

This is where I would put the effort.

Funded traders at FTMO, MyForexFunds, Topstep and the rest operate under hard
rules: a daily loss limit, a maximum total drawdown, sometimes a per-position
cap. Breach one by a hundred dollars and a $100k account is gone. There is no
appeal.

The safety layer already built — risk ceilings, volume caps, position-count
caps, forced previews — is 60% of a product that says *"this account cannot
breach your firm's rules, because the tool physically refuses."*

That is worth far more than $19/month to someone protecting a $100k funded
account, and it converts a commodity API wrapper into something with a reason to
exist. It needs:

- A per-firm rule profile (daily loss %, total drawdown %, news-trading windows).
- A running daily-loss tracker that hard-blocks orders once the day's budget is
  spent — the single feature the whole product should be named after.
- A compliance report the trader can screenshot.

**Price:** $29–49/month. This audience is used to paying for tools, has money at
stake, and churns *less* than ordinary retail because the account is a job.

### 3. Selling to the firms instead of the traders

Prop firms and small brokers would rather their funded traders not blow up —
it costs them payout capital and support load. A white-labelled version, sold
per-firm, is a $2k–10k/month contract rather than a $29/month one.

Long sales cycle, real compliance review, and you need the retail version
working first as proof. But it is where the money actually is, and it is worth
building the retail product in a shape that can be white-labelled later.

## What will not make money

I want to be direct about these, because they are where this category usually
dies.

- **Selling the MCP server itself.** Several open-source MT5 MCP servers already
  exist on GitHub. Code is not a moat here. Give it away; it is marketing.
- **Selling alpha.** Any promise that the model picks profitable trades is false
  and will destroy the business the first month a customer loses money. This
  project sells *workflow and safety*, never edge. The README and the skill both
  say so deliberately — keep it that way.
- **Generic "AI trading assistant" positioning.** That market is saturated with
  scams, so honest products in it inherit the suspicion. The narrow
  "your funded account cannot breach its drawdown rule" pitch dodges that
  entirely.
- **Auto-trading on customers' behalf.** The moment you take discretion over
  someone else's money you are in regulated territory — investment advice or
  managed accounts, depending on jurisdiction. The current design (the user
  operates the tool, the user confirms each live order) sits on the safe side of
  that line. Crossing it turns a software business into a licensing problem.

## The honest risks

**Retail trading tools have brutal churn.** The median retail trader stops
trading within a year, frequently because they lost the account. You are selling
into a population that partially self-destructs. Prop-firm traders churn less,
which is another reason to aim there.

**Broker fragmentation is a support tax.** Every broker renames instruments
(`XAUUSD.m`, `EURUSD_i`), sets different filling modes, and has its own quirks.
The adapter handles the common cases; the long tail is support tickets forever.

**Reputational blast radius.** One bug that places a wrong order and you are the
tool that cost someone their funded account. That is why the safety layer went
in first rather than as a later feature, and why every write path is
tested. Keep that discipline — it is the product.

**You are one MetaQuotes decision from a rewrite.** The Python API is not a
committed public contract.

## Numbers, plainly

At $29/month with prop-firm positioning:

| Subscribers | ARR | What it takes |
| --- | --- | --- |
| 50 | $17k | A few good posts in prop-trading communities |
| 200 | $70k | Sustained content, a free tier that works, ~12 months |
| 500 | $174k | Real marketing spend, affiliates, or one firm partnership |

Add one white-label firm contract at $4k/month and the picture changes more
than a hundred retail subscribers would.

I do not think this becomes a venture-scale company. I do think it can become a
$100k-ish ARR product for one or two people inside two years, and the
white-label path is the only route to more.

## What I would do next, in order

1. **Ship the daily-loss guard.** Track realised + floating P/L against a daily
   budget and hard-block orders when it is spent. This is the feature the
   product should be named after, and it is maybe two days of work on the
   existing `Guard`.
2. **Add prop-firm rule profiles.** FTMO and Topstep first — they have the most
   traders and the most published rules.
3. **Publish the open-source version** and list it in a plugin directory (this
   repo is one). Free distribution, paid hosting.
4. **Then, and only then, build the hosted bridge.** Do not build infrastructure
   before something is pulling people in.
5. **Talk to ten funded traders before writing any of it.** Ask what killed
   their last account. If the answer is not "I broke a drawdown rule," the wedge
   above is wrong and this plan needs revising rather than executing.

Step 5 is the cheapest and the one most likely to be skipped.

## The bottom line

The thing you have is well-built and safe, and neither of those is what people
pay for. What people pay for is not losing a funded account, and access from a
Mac. Both are close to what is already here.

Build the daily-loss guard next. Talk to ten traders before anything else.
