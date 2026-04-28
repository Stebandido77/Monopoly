# ADR-001: JailAction "card" tratada como "roll" en Fase 1

**Status:** Resuelto en Fase 2

**Fecha de apertura:** 2026-04-27
**Fecha de cierre:** 2026-04-27 (Fase 2)

## Contexto

En Fase 1 del proyecto se implementó el motor mínimo del juego sin mazos
de Suerte ni Comunidad. La interfaz `Strategy.decide_jail_action` define
el literal `JailAction = Literal["pay", "roll", "card"]`, pero la opción
`"card"` (usar carta "Sal de cárcel gratis") no tenía aún una mecánica
detrás porque las cartas no existían en ese punto del proyecto.

## Decisión original (Fase 1)

Durante Fase 1, `Game.handle_jail` aceptaba `action="card"` pero lo
trataba internamente como `"roll"` (intentar dobles). No se levantaba
error ni warning para no romper la interfaz Strategy.

## Resolución (Fase 2)

Con la implementación de `Card`, `Deck` y los YAML
`data/chance_cards.yaml` / `data/community_chest_cards.yaml`,
`Game.handle_jail` ahora cierra el ciclo:

1. Si `action == "card"` y `player.jail_free_cards` no está vacío,
   consume una carta del jugador, libera al jugador (`in_jail = False`),
   reinicia `jail_turns` y `doubles_streak`, y devuelve la carta al fondo
   del mazo de origen (chance o community_chest, según el campo
   `payload['deck']` de la carta).
2. Si `action == "card"` pero el jugador no tiene cartas, el
   comportamiento degrada silenciosamente a `"roll"` (intentar dobles),
   manteniendo la retrocompatibilidad y evitando errores.

Las cartas "Get Out of Jail Free" se distinguen del resto del mazo: al
ser robadas (efecto `get_out_of_jail`) **no** vuelven al mazo, sino que
quedan en `Player.jail_free_cards` hasta su uso. Solo entonces regresan
al fondo del mazo correspondiente.

## Tests que cubren el cierre

- `tests/test_cards.py::test_get_out_of_jail_card_stays_with_player`
  — la carta queda con el jugador y no vuelve al mazo en el momento de
  la draw.
- `tests/test_cards.py::test_using_jail_card_returns_it_to_origin_deck`
  — `action="card"` con carta retenida la libera al fondo del mazo
  correcto (community_chest en este test).
- `tests/test_cards.py::test_action_card_without_held_card_falls_through_to_roll`
  — `action="card"` sin carta degrada a `"roll"` con `jail_turns`
  incrementado.

## Consecuencias

- La firma del Protocol `Strategy.decide_jail_action` no cambia. Las
  estrategias existentes que devuelven `"card"` ya tienen la mecánica
  detrás.
- Los tests de cárcel ahora cubren el path `"card"` explícitamente.
- Conservación de cartas: el invariante "16 cartas en mazo + cartas en
  manos de jugadores == 16 cartas totales del mazo" se mantiene mientras
  la carta no se descarta. Bancarrota libera las cartas retenidas
  (`Game._return_held_jail_cards`) para mantener el invariante.
