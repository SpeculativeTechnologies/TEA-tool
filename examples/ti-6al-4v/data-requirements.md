# Ti-6Al-4V Incumbent Chain Data Requirements

## Entities

Each entity has a scope frame used by extraction and scope-fit review.

| ID | Display name | Output | Scope frame | Known out of scope | Estimation policy |
|---|---|---|---|---|---|
| 1A | Chlorination | TiCl4 | Fluidized-bed carbochlorination of chloride-grade TiO2 with petroleum coke and Cl2 to metal-grade TiCl4. | FFC-Cambridge, OS, MER, sulfate TiO2 pigment routes, plasma chlorination. | first_principles_only |
| 1B | Kroll Process | Ti sponge | Kroll magnesiothermic reduction of purified TiCl4 by molten Mg under argon, including vacuum distillation. | Hunter sodium process, Armstrong, TiRO, direct electrowinning. | first_principles_only |
| 1C | MgCl2 Electrolysis | Mg | Industrial molten-salt electrolysis of spent anhydrous MgCl2, returning Mg and Cl2 to upstream units. | Pidgeon magnesium, SOM electrolysis, carbothermic MgO reduction. | comparables_first |
| 2A | Bayer Process | Alumina | Bayer digestion, precipitation, and calcination to smelter-grade alumina. | Sinter/lime-soda, acid leach, Pedersen process. | first_principles_only |
| 2B | Hall-Heroult Electrolysis | Al metal | Incumbent Hall-Heroult electrolysis with consumable carbon anodes. | Inert anode, carbothermic aluminum, AlCl3 chloride electrolysis. | first_principles_only |
| 4 | Electrode Compaction & Welding | Consumable electrode | Virgin-feed Ti sponge, Al-V master alloy, and Al pressed and welded under inert atmosphere. | WAAM, powder metallurgy/HIP, scrap-dominant electrode prep. | comparables_first |
| 5 | Double VAR Melt | VAR ingot | Double vacuum arc remelting of consumable electrodes into aerospace-grade Ti-6Al-4V ingot. | Triple VAR, EBCHM, PAM, single VAR. | comparables_first |
| 6 | Press Forge to Billet | Wrought billet | Hot working and ingot breakdown by open-die press forging. | WAAM, near-net powder or additive manufacturing, ShAPE recycled-chip extrusion. | comparables_first |

## Parameter catalog

| Parameter ID | Label | Rule type | Applies to | First class | Notes |
|---|---|---|---|---|---|
| specific_capex | Specific CapEx | CAPEX | all | true | Capital cost per annual tonne of entity output. |
| scaling_exponent | Scaling exponent | PASSTHROUGH | all | false | Convention value, not searched per cell. |
| electricity | Electricity | INTENSITY | all | true | kWh per entity output. |
| thermal_energy | Thermal energy | INTENSITY | all | true | MJ per entity output. |
| feedstock_quantity | Feedstock quantity | INTENSITY | all | false | kg feedstock per entity output. |
| stoichiometry | Stoichiometry | JSON | 1A, 1B, 1C, 2A, 2B | false | Structured reaction stoichiometry. |
| output_notes | Output / co-product notes | TEXT | all | false | Free-text notes. |
| consumables.cl2_makeup | Cl2 make-up | INTENSITY | 1A | false | kg per entity output. |
| consumables.argon | Argon | INTENSITY | 1B, 5 | false | kg per entity output. |
| Ti_yield | Ti yield | FRACTION | 1A, 1B, 4, 5, 6 | false | Element-of-interest basis. |
| Al_yield | Al yield | FRACTION | 2A, 2B, 4, 5, 6 | false | Element-of-interest basis. |
| V_yield | V yield | FRACTION | 4, 5, 6 | false | Element-of-interest basis. |
| Mg_recovery | Mg recovery | FRACTION | 1C | false | Element-of-interest basis. |
| Cl2_recovery | Cl2 recovery | FRACTION | 1C | false | Element-of-interest basis. |

## Reference values

Reference values are searched context-free and carried under the reserved
global `REF` entity in the compiled config.

| Parameter ID | Label | Rule type | Canonical unit | Market basis |
|---|---|---|---|---|
| electricity_price | Industrial electricity price | MONETARY | USD/kWh | US industrial bulk |
| natural_gas_price | Industrial natural gas price | MONETARY | USD/MMBtu | US industrial |
| al_v_master_alloy_price | Al-V master alloy price | MONETARY | USD/kg | Spot, about 85V/15Al master alloy |

## Applicability

Applicability is as declared in the parameter catalog. Reference values apply
only to `REF`. All other parameters apply to the listed entities or all real
entities when `all` is given.

## Estimation

Use `first_principles_only` for entities 1A, 1B, 2A, and 2B. Use
`comparables_first` for entities 1C, 4, 5, and 6.

Comparable similarity dimensions:

- mechanism
- cost_driver
- scale
- temperature_atmosphere
- product_form_factor

Hard rule: mechanism must match; at most one other dimension may be partial;
no dimension may be a mismatch.

## Quality tags

Use A, B, C, D, and E. E is reserved for estimates. Analyst overrides of held
estimates are re-tagged to D.

## Conventions needed

- inflation_index:CEPCI
- currency_rates
- unit_conversions
- scaling_exponents

