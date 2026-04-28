# ADR-001: JailAction "card" tratada como "roll" en Fase 1

**Status:** Temporal — se cierra en Fase 2 al implementar mazos de cartas

**Fecha:** 2026-04-27

**Contexto**

En Fase 1 del proyecto se implementó el motor mínimo del juego sin mazos de
Suerte ni Comunidad. La interfaz `Strategy.decide_jail_action` define el
literal `JailAction = Literal["pay", "roll", "card"]`, pero la opción
`"card"` (usar carta "Sal de cárcel gratis") no tiene aún una mecánica
detrás porque las cartas no existen en este punto del proyecto.

**Decisión**

Durante Fase 1, `Game.handle_jail` acepta `action="card"` pero lo trata
internamente como `"roll"` (intentar dobles). No se levanta error ni
warning para no romper la interfaz Strategy.

**Consecuencias**

- Las estrategias que devuelvan `"card"` en Fase 1 tendrán comportamiento
  equivalente a tirar dados.
- Los tests de cárcel no validan el path `"card"` en Fase 1.
- La firma del Protocol queda preparada para Fase 2 sin cambios
  retrocompatibles.

**Cierre planeado**

Al implementar `ChanceDeck` y `CommunityChestDeck` en Fase 2 (ADR-003 o
documentación correspondiente), `handle_jail` debe:
1. Si `action == "card"` y el jugador tiene una carta "Sal de cárcel
   gratis" en su inventario, consumirla y liberar al jugador sin penalidad.
2. Si `action == "card"` pero el jugador no tiene la carta, comportamiento
   degrada a `"roll"`.

Este ADR debe actualizarse a `Status: Resuelto` cuando esa lógica esté
implementada y testeada.
