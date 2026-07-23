# Keep Scanning Experiment

In this experiment, the ```experiment``` component keeps scanning the defined scan (from the config) forever (or until the experiment is ended).

It is worth evaluating because it makes use of the ```extra_config_file``` option in spawn.
This allows us to have a separate 'sub-config' that holds microscope-specific aspects of a config.
In this example, we have two different [```translator```] definitions:
- In ```image.toml```, we have a fake ImageTranslator that we can use to test our experiment locally.
- In ```asylum.toml```, we have an AsylumTranslator that we can use to run the experiment on an Asylum system.

To run:

```sh
poetry run spawn config.toml --extra_config_file=image.toml
```

(or ```asylum.toml```, as needed).

Note also that we have at least one microscope-specific parameter that changes between the two sub-configs: ```scan_wait_s```.
We take longer to wait between scans in our 'fake' testing case (```image.toml```) versus in our real experiment (```asylum.toml```).
