# Third-party components

The MIT licence covers original application code and documentation. It does not replace the licences of dependencies, fonts or model weights.

- Barlow Condensed and IBM Plex font licence notices are retained under `services/web/public/fonts/`.
- JavaScript package versions are recorded in `services/web/package-lock.json`; Python dependencies are listed by service. Upstream package notices remain applicable when installing or distributing those dependencies.
- WNTR and its EPANET components are installed from their upstream distribution. This repository does not claim ownership of those hydraulic engines.
- Ollama models and Hugging Face weights are downloaded separately. Check the exact model's upstream licence before use or redistribution. This repository includes no model weights.
- Recorded examples under `services/web/public/research/` come from this lab's simulated simulations and local model experiments. Model-generated text is unverified evidence, not an endorsement, faithful internal reasoning, or a proven control recommendation.

The public source package excludes installed dependencies, local databases and arbitrary local audit archives. A full third-party redistribution review is needed if shipping a prebuilt appliance or container bundle.
