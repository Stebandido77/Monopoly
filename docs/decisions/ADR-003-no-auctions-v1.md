# ADR-003: Sin subastas en v1.0 — el banco recupera

## Status

**Accepted — definitive para v1.0.** Una v1.1 podría añadir subastas; en
ese caso este ADR sería *superseded by* el nuevo, no eliminado: las
corridas de benchmark anteriores deben seguir siendo reproducibles
contra el conjunto de reglas aquí definido.

## Fecha

2026-04-27 (durante Fase 2).

## Contexto

Las reglas oficiales de Hasbro especifican subastas en dos situaciones:

1. **Compra rechazada.** Si un jugador cae sobre una propiedad sin dueño
   y decide *no* comprarla, el banco la subasta entre los demás
   jugadores con un precio inicial libre.
2. **Bancarrota contra el banco.** Si la deuda es con el banco y el
   jugador se declara en bancarrota, todas sus propiedades vuelven al
   banco y se subastan inmediatamente entre los jugadores restantes.

Implementar subastas en v1.0 implicaría:

- Añadir un nuevo decision-point `Strategy.bid(tile, current_high_bid)`,
  con la complejidad asociada (los baselines y las estrategias derivadas
  necesitan implementarlo).
- Un loop de pujas con resolución determinística — quién puja primero,
  cómo se resuelven empates, cuándo termina la subasta — ninguno de
  cuyos detalles está totalmente especificado en el reglamento Hasbro
  (es deliberadamente abierto).
- Tests que cubran el comportamiento del loop de subasta, lo que
  multiplica la superficie de riesgo del motor sin aportar al objetivo
  central del proyecto (*comparar estrategias derivadas de optimización
  vs. heurísticas vs. probabilísticas*).

## Decisión

**v1.0 omite subastas.** En su lugar:

1. **Compra rechazada** (caso 1): la propiedad permanece sin dueño en
   manos del banco. Cualquier jugador futuro que caiga ahí tendrá la
   misma oportunidad de compra al precio listado.
2. **Bancarrota contra el banco** (caso 2): las propiedades del deudor
   regresan al banco *sin subasta*; sus casas y hoteles vuelven al
   inventario; las hipotecas se levantan automáticamente (es decir, el
   banco no cobra interés a sí mismo). La propiedad queda disponible
   para compra a precio listado por el siguiente jugador que caiga ahí.
3. **Bancarrota contra otro jugador** (caso fuera de las subastas, pero
   relacionado): aquí sí se aplica la transferencia al acreedor (ver
   código y tests en `tests/test_bankruptcy_creditor.py`).

La omisión está implementada en `Game.buy_property` (cuando la
estrategia rechaza, se hace un `_emit_action` y la función retorna
`False` sin más) y en `Game.check_bankruptcy(player, creditor=None)`
(reclama al banco).

## Consecuencias

1. **Resultados de benchmark.** Los precios pagados promedio por
   propiedad en v1.0 son sistemáticamente menores que con subastas, ya
   que sin la presión de la puja un comprador siempre compra al precio
   listado. Cualquier paper que compare contra literatura clásica de
   Monopoly debe reportar este detalle.
2. **Distribución de propiedades más lenta.** Sin subastas las
   propiedades quedan más tiempo en manos del banco, alargando la
   primera fase del juego. Empíricamente esto ya se observa en el smoke
   test de 4 jugadores × 500 turnos: el juego tiende a no terminar
   dentro del límite de turnos.
3. **Reincorporación al banco simplifica la conservación de inventario.**
   El invariante `available_houses + Σ casas_en_juego == 32` (y similar
   para hoteles) se mantiene de forma trivial: la bancarrota contra el
   banco devuelve siempre todas las construcciones al inventario.
4. **Extension point preservado.** La firma de `Strategy` no menciona
   `bid`, pero añadirla en v1.1 no rompe estrategias existentes (sería
   un nuevo método con default no-op vía `getattr` probe, igual que
   `decide_build` etc. en este ADR).

## Relacionado

- ADR-001 (cierre del path `"card"` en `handle_jail`).
- ADR-002 (reglas oficiales para impuestos y Free Parking).
- `tests/test_bankruptcy_creditor.py` cubre el caso de bancarrota con
  acreedor; el caso de bancarrota al banco está cubierto por
  `tests/test_rent.py::test_bankrupt_player_returns_properties_to_the_bank`
  y `tests/test_bankruptcy_creditor.py::test_bank_bankruptcy_*`.
