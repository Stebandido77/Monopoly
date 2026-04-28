# ADR-002: House rules for ambiguous tax and Free Parking values

## Status

**Accepted — definitive.** This decision is permanent, not a temporary
placeholder. Future ADRs may *supersede* it but a benchmark run that
predates a supersession should be reproducible against the rule set
defined here.

## Context

The Monopoly rules text has shifted across editions (1936 → 2008
simplification → later reprints), and the most popular house rule
("Free Parking pot") is not in any official rule book at all. The
project benchmarks strategies and publishes statistical comparisons,
so the exact rule set must be fixed and stated in writing — otherwise
results across runs (or against published Monopoly literature) become
incomparable.

Three spaces require an explicit choice:

| Space | Variants in the wild |
|---|---|
| Free Parking (pos 20) | Official: nothing happens. Common house rule: pot of accumulated taxes / fines paid to whoever lands here. |
| Income Tax (pos 4) | Pre-2008: pay 10% of total assets *or* $200, player chooses. Post-2008: fixed $200. |
| Luxury Tax (pos 38) | Classic (pre-2008): $75. Modern (post-2008 reprints): $100. Some recent printings revert to $75. |

## Decision

The values below are the canonical rule set for this project. They are
written into `data/board.yaml` and treated as the source of truth.

| Space | Value used | Era / source |
|---|---|---|
| Free Parking | **No money accumulates.** Landing has no monetary effect. | Official Hasbro rules (every era). |
| Income Tax | **$200 fixed.** No 10%-of-assets option. | Modern (post-2008). |
| Luxury Tax | **$75.** | Classic (pre-2008). |

The combination is deliberately hybrid:

- **Income Tax — modern.** The pre-2008 10%-or-$200 choice introduced a
  strategic decision that depends on bankroll and asset valuation. We
  collapse it to the modern $200 because (a) it matches what most
  players see in a contemporary box and (b) the 10% option creates
  pathological dependencies on a "total assets" definition that the
  rules do not pin down precisely (e.g. mortgaged value vs face value).
- **Luxury Tax — classic.** We keep the historical $75. The 2008 bump to
  $100 is a flat-rate change that disproportionately drains players
  caught in the dark-blue endgame; the classic $75 preserves the
  pre-2008 strategic landscape that most existing Monopoly literature
  was written against.
- **Free Parking — official.** The pot house rule is endemic in casual
  play but materially extends average game length and damages the
  comparability of any benchmark we publish. We follow the rule book.

## Consequences

1. **Reproducibility floor.** Two runs with the same `board.yaml`, the
   same seed, and the same strategies will produce identical results.
   Any change to these three values must come with a new ADR and is a
   breaking change for benchmark comparability.
2. **Comparability with published Monopoly analyses.** Most existing
   academic / blog-post analyses of Monopoly target either pre-2008 or
   post-2008 editions consistently. Our hybrid means readers will
   occasionally find a $25 discrepancy per Luxury-Tax landing against
   modern-edition references; this should be flagged in any paper we
   publish.
3. **Free Parking pot users will see shorter games.** Casual players
   who tested the engine and expected the pot rule will see games end
   faster than the Monopoly experience they remember. This is by
   design.

## Related

- `data/board.yaml` (`tax_amount` for positions 4 and 38; the absence
  of any monetary effect on position 20).
- Future ADR on Chance / Community Chest card decks (cards are
  out-of-scope for Phase 1; verbose mode logs landings explicitly).
