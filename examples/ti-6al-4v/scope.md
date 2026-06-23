# Ti-6Al-4V Incumbent Chain Scope

## Goal and framing

This example analyzes the incumbent primary-production chain for aerospace-grade
Ti-6Al-4V billet. The workflow endpoint is a populated input set for a TEA model
that the analyst already owns. The model itself is outside this run.

The example is intentionally industrial: it exercises process-unit entities,
per-unit-output intensities, yields, CapEx handling, CEPCI escalation, and a
comparison oracle copied from the older Vicky TEA Run 2.

## System boundary

In scope:

- Chloride-route titanium feed preparation from chloride-grade rutile to TiCl4.
- Kroll reduction of TiCl4 to titanium sponge.
- Regeneration of Mg and Cl2 through MgCl2 electrolysis.
- Alumina and aluminum production needed for alloying additions.
- Electrode compaction and welding.
- Double vacuum arc remelting.
- Press forging to wrought Ti-6Al-4V billet.

Out of scope:

- Alternative titanium routes such as FFC-Cambridge, OS, MER, Armstrong, TiRO,
  and direct TiO2 electro-reduction.
- Scrap/revert-dominant alloy production.
- Additive manufacturing, powder metallurgy, and near-net-shape routes.
- Running the final TEA model or back-cast. Validation targets are recorded only
  for analyst use after hand-off.

## Functional unit

The functional unit is 1 kg of Ti-6Al-4V billet. Parameters declared as
`per = entity_output` normalize against each producing entity's own output,
while the final model can carry those values through its mass-balance logic.

## Entity decomposition

| Entity | Name | Output | Description |
|---|---|---|---|
| 1A | Chlorination | TiCl4 | Rutile concentrate reacts with coke and chlorine to produce TiCl4. |
| 1B | Kroll Process | Ti sponge | Purified TiCl4 is reduced with molten magnesium under inert conditions. |
| 1C | MgCl2 Electrolysis | Mg | Spent MgCl2 is electrolyzed to regenerate Mg and Cl2. |
| 2A | Bayer Process | Alumina | Bauxite is digested, precipitated, and calcined to smelter-grade alumina. |
| 2B | Hall-Heroult Electrolysis | Al metal | Alumina is reduced in molten cryolite using carbon anodes. |
| 4 | Electrode Compaction & Welding | Consumable electrode | Ti sponge, Al, and Al-V master alloy are pressed and welded into VAR electrodes. |
| 5 | Double VAR Melt | VAR ingot | Consumable electrodes are double vacuum-arc remelted into alloy ingot. |
| 6 | Press Forge to Billet | Wrought billet | VAR ingot is hot-worked into billet. |

## Basis assumptions

| Item | Value |
|---|---|
| Currency | USD |
| Base year | 2025 |
| Inflation index | CEPCI |
| Geography | United States where geography is needed |
| Quality tags | A, B, C, D, E |

## Scenarios

This example represents one incumbent system only. Comparison TEAs should run a
second system and use `pinned-inputs.csv` to hold shared values constant.

## Headline metrics

The downstream model is expected to produce cost per kg billet and intermediate
cost contributions, but this tool stops at populated inputs.

## Validation targets

| Metric | Target | Source |
|---|---|---|
| Ti sponge price | 11 to 12.5 USD/kg | Argus TG100 Sep-2025 |

