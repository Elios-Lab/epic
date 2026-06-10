# Digital Twin Catalog

> Related: [Digital Twins](digital-twins.md) — how to implement a new twin · [Sensors](sensors.md) · [Faults](faults.md) · [Physical Quantities](quantities.md)

This document describes the five digital twins that ship with EPIC. Each twin is a self-contained Python package under `epic_twins/`, registered at application startup and exposed through `GET /api/v1/twins`. Where the companion document [Digital Twins](digital-twins.md) explains how to build a new twin, this catalog explains what the existing ones actually simulate: the physics behind each model, the quantities it exposes, the faults it can inject, and the initial conditions an organizer can override when authoring a contest.

A note on fidelity is in order before the individual descriptions. These twins are intentionally simple. They are first-order behavioral models, not high-fidelity engineering simulators: their purpose is to produce sensor streams that are physically plausible, react believably to faults, and remain fast enough to run in real time at tens of hertz. For a machine learning competition this is exactly what is needed — the difficulty of the challenge comes from noise, drift, fault dynamics, and the forecasting horizon, not from the complexity of the underlying differential equations.

All five twins share the same internal structure. Each one keeps a private fault schedule received from the contest configuration, advances an internal clock on every `step()` call, activates and deactivates faults when the clock crosses the scheduled start and end times, and applies the effects of every active fault directly to the new state before returning it. The simulation engine never sees any of this machinery; it only calls the `DigitalTwin` interface methods. Severity is a number between 0 and 1 that scales the strength of every fault effect, and because most fault effects accumulate over time (they are proportional to the time step `dt`), a fault left active for a long period produces a gradual, realistic degradation rather than a sudden jump.

---

## Mass-Spring-Damper (`mass_spring_damper`)

The mass-spring-damper is the simplest twin in the catalog and the best starting point for understanding the platform. It simulates a single mass attached to a spring and a viscous damper, driven by a sinusoidal external force of 0.5 N at 1 Hz. At every step the twin integrates the classical equation of motion — acceleration equals force minus damping times velocity minus stiffness times position, all divided by mass — using simple semi-implicit Euler integration. The result is a smooth oscillatory motion whose amplitude and phase shift respond to any change in the physical parameters, which is precisely what the faults exploit.

The twin exposes four physical quantities: linear position, linear velocity, linear acceleration, and temperature. The first three describe the motion of the mass, while temperature exists mainly as a side channel for the friction fault. Any sensor measuring one of these quantities can be attached, which in the built-in library means the position, velocity, acceleration, and temperature sensors.

The default configuration starts the mass at 0.1 m from rest, with a mass of 1 kg, a stiffness of 10 N/m, a damping coefficient of 0.5 N·s/m, and an ambient temperature of 20 °C. An organizer can override any of these through the contest's `initial_conditions` field, using the keys `position`, `velocity`, `temperature`, `mass`, `stiffness`, and `damping`.

Three faults are available. *Reduced stiffness* (`reduced_stiffness`) progressively weakens the spring, multiplying the stiffness by a factor slightly below one at every step; the stiffness never falls below 1 N/m, and the visible effect is an oscillation that slowly lengthens its period and changes amplitude. *Increased damping* (`increased_damping`) does the opposite kind of damage, growing the damping coefficient so that the oscillation dies down faster than it should. *Increased friction* (`increased_friction`) combines a mild damping increase with a steady temperature rise, so it is the only fault on this twin that becomes visible through the temperature sensor as well as through the motion.

The built-in contest template `spring_damper_stiffness_loss` uses this twin with position, velocity, and temperature sensors at 20 Hz, and schedules a stiffness-loss fault of severity 0.6 starting fifteen seconds into the simulation.

---

## Industrial Centrifugal Pump (`industrial_pump`)

The industrial pump twin models a centrifugal pump operating in steady state, with slow periodic load variation. Flow rate and discharge pressure oscillate gently around their nominal values (a 3% and 2% modulation at 0.2 Hz, slightly out of phase with each other), which gives participants a realistic baseline signal that is neither constant nor trivially periodic. On top of this baseline, the twin maintains a hidden *wear* variable between 0 and 1 that grows slowly throughout the simulation. Wear is never directly observable, but it drives both the temperature trend and the vibration baseline: as wear accumulates, the pump runs hotter and vibrates more. This hidden-state design makes the pump a natural candidate for predictive-maintenance-flavored challenges, because the observable signals carry indirect evidence of a degradation process the participant cannot measure directly.

The twin exposes flow rate, pressure, temperature, and vibration, matching the built-in flow rate (m³/h), pressure (bar), temperature (°C), and vibration (mm/s) sensors. Defaults place the pump at 120 m³/h, 4 bar, 35 °C, a vibration baseline of 1 mm/s, and an initial wear of 0.05; all of these can be overridden through `initial_conditions` using the keys `flow_rate`, `pressure`, `temperature`, `vibration`, and `wear`.

The three available faults reflect the classic failure modes of a real centrifugal pump. *Cavitation* (`cavitation`) simulates vapor bubbles forming at the impeller: the flow rate drops by up to 12% at full severity and vibration jumps immediately, making it the most abrupt and detectable of the three. *Bearing wear* (`bearing_wear`) accelerates the hidden wear variable and adds both vibration and a slow temperature climb, producing a gradual degradation signature spread across multiple sensors. *Filter clog* (`filter_clog`) restricts the flow while raising discharge pressure, a distinctive combination — flow down, pressure up — that differentiates it cleanly from cavitation for fault-diagnosis purposes.

The `pump_bearing_fault` template runs this twin at 10 Hz with all four sensors active and a bearing-wear fault of severity 0.7 starting at twenty seconds.

---

## Three-Phase Induction Motor (`electric_motor`)

The electric motor twin represents a three-phase induction motor running at a nominal operating point, with two superimposed periodic effects: a 50 Hz supply-frequency ripple on current and voltage, and a slow 0.5 Hz load oscillation on speed and torque. Temperature rises continuously at a rate proportional to the load factor, so even a healthy motor warms up slowly over the course of a contest — participants who model temperature as a constant will be systematically wrong, which is intentional.

The twin exposes five quantities — current, voltage, rotational speed, temperature, and torque — of which the first four have matching built-in sensors (current in A, voltage in V, rotational speed in RPM, temperature in °C). Torque is exposed as a quantity but has no built-in sensor yet, so it remains a latent variable in practice. Defaults are 12 A, 400 V, 1450 RPM, 40 °C, and 80 N·m, overridable through the keys `current`, `voltage`, `speed`, `temperature`, and `torque`.

The fault set covers electrical, mechanical, and thermal failure modes. *Voltage imbalance* (`voltage_imbalance`) is the electrical fault: current rises by up to 12%, torque drops by up to 10%, and the motor heats faster, all proportional to severity. *Bearing fault* (`bearing_fault`) is the mechanical one, adding a progressive speed deviation and extra heat. *Overheating* (`overheating`) is the most interesting from a modeling standpoint because it has a threshold behavior: it accelerates the temperature rise unconditionally, but only once the motor crosses 80 °C does it start degrading speed and torque, with the degradation growing as the temperature climbs further. A contest long enough for the motor to cross that threshold therefore exhibits a regime change in the sensor streams.

The `motor_voltage_imbalance` template samples this twin at 50 Hz — the highest rate among the templates, chosen to make the supply-frequency ripple visible — with a voltage-imbalance fault of severity 0.5 from ten seconds onward.

---

## Rotating Shaft and Gearbox (`rotating_machinery`)

The rotating machinery twin models a driven shaft with a gearbox, the canonical subject of industrial vibration monitoring. Its baseline behavior combines three periodic components at different frequencies: a slow 0.15 Hz load oscillation that modulates power consumption by ±8%, a small 0.5 Hz speed wobble, and a faster 1.5 Hz vibration component. Temperature rises with the load factor, and the twin also tracks a shaft-deflection variable that oscillates gently in healthy operation. Shaft deflection, like pump wear, is internal: it is not exposed as a physical quantity, but the faults push on it and its effects feed the observable vibration signal.

Exposed quantities are rotational speed, vibration, temperature, and power, matching the built-in rotational speed (RPM), vibration (mm/s), temperature (°C), and power (W) sensors. The defaults describe a substantial industrial machine: 1800 RPM, 75 kW, a vibration baseline of 1.2 mm/s, and 45 °C, overridable through `speed`, `vibration`, `temperature`, `power`, and `shaft_deflection`.

The faults are the three classics of rotating-equipment diagnostics. *Unbalance* (`unbalance`) adds vibration proportionally to the current shaft speed — its signature scales with RPM, exactly as a real mass imbalance does. *Misalignment* (`misalignment`) raises vibration by a speed-independent amount and additionally increases power draw by up to 8% and heats the machine, reflecting the extra work done against the misaligned coupling. *Gear tooth wear* (`gear_tooth_wear`) produces a slower, accumulating signature: moderate immediate vibration plus steadily growing heat and shaft deflection, suited to long-horizon degradation scenarios.

The `gearbox_tooth_wear` template runs at 25 Hz with all four sensors and a gear-tooth-wear fault of severity 0.8 starting at twenty-five seconds.

---

## Smart Commercial Building Floor (`smart_building`)

The smart building twin is deliberately different from the other four: it simulates an environment rather than a machine, and its dynamics are driven by occupancy and thermal exchange rather than by rotating parts. The model represents one floor of a commercial building with an HVAC system holding a target temperature of 22 °C against an outdoor temperature of 30 °C. Occupancy fluctuates around its nominal value with a short sinusoidal cycle, and every occupant adds CO₂ and humidity to the indoor air while ventilation pulls CO₂ back down toward an outdoor baseline of roughly 420 ppm. Indoor temperature is the balance of two opposing terms — heat leaking in through the building envelope and the HVAC correction pulling toward the setpoint — while HVAC power itself is observable as it ramps up and down with the magnitude of the temperature error. CO₂ is floored at 400 ppm and humidity is clamped between 20% and 80%, so the signals stay within physically sensible ranges.

The twin exposes temperature, humidity, CO₂ concentration, and occupancy, all four with matching built-in sensors (temperature in °C, relative humidity in %RH, CO₂ in ppm, occupancy in people). Defaults are 22 °C, 45% relative humidity, 650 ppm of CO₂, 20 occupants, and 3.5 kW of HVAC capacity, with overridable keys `temperature`, `humidity`, `co2`, `occupancy`, `hvac_power`, `target_temperature`, and `outdoor_temperature`. The last two are particularly useful for authoring scenarios: raising the outdoor temperature or lowering the HVAC capacity changes the whole thermal balance of the simulation without touching any code.

The faults model building-operations incidents rather than mechanical damage. *HVAC failure* (`hvac_failure`) scales the conditioning power down — at full severity the HVAC stops entirely — and lets CO₂ accumulate, so the indoor climate drifts toward outdoor conditions while air quality degrades. *Occupancy spike* (`occupancy_spike`) injects a sustained crowd of additional people with the corresponding CO₂ and humidity load, simulating an event or an over-booked floor. *Sensor drift* (`sensor_drift`) progressively biases the temperature and humidity values; conceptually this represents miscalibrated building instrumentation, and it is worth noting that it is implemented as a twin fault acting on the latent state, which means it also shifts the recorded ground truth — unlike the per-sensor drift parameter described in [Sensors](sensors.md), which corrupts only the measurement.

The `building_hvac_failure` template runs at 2 Hz — environmental dynamics are slow, and a low sampling rate keeps the data volume proportionate — with an HVAC failure of severity 0.9 from thirty seconds onward.

---

## Choosing a twin for a contest

For a first contest or a teaching scenario, the mass-spring-damper is the natural choice: its dynamics are visible to the naked eye in a plotted sensor stream, the connection between fault and effect is easy to explain, and a simple physical model can compete respectably, which keeps the focus on methodology. The industrial pump and the rotating machinery twins suit predictive-maintenance narratives, because both carry hidden degradation states whose indirect signatures reward feature engineering across multiple sensors. The electric motor offers the richest spectral content thanks to its 50 Hz supply ripple and is the best fit when the pedagogical goal involves higher sampling rates or frequency-domain analysis. The smart building, finally, is the slowest and most accessible of the five for audiences without an engineering background, and its configurable setpoint and outdoor conditions make it the most flexible for scenario design through configuration alone.

Whatever the choice, the contest author workflow is identical for every twin, because the platform interacts with all of them through the same interface. The available sensors are constrained only by the quantities the twin exposes, the fault schedule accepts any of the fault identifiers listed above for the chosen twin, and every parameter mentioned in this catalog is set through the same `initial_conditions`, `sensor_configs`, and `fault_schedule` fields of the contest configuration described in [Contest Authoring](contest-authoring.md).
