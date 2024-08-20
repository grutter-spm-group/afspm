"""Script to initialize/summon gxsm.

Gxsm needs to be spawned *within* the gxsm Python Remote console UI. Due to
additional peculiarities, we cannot call the spawn_components() method either.
Thus, to run we must call spawn_monitorless_component().

This script is just a helper to spawn gxsm. Just load this script in the Python
Remote console UI, and run it! Change the hardcoded parameters as needed.

What are these peculiarities we mention?
----------------------------------------

The main gxsm python package is an C-API extension module. It gets properly
'summoned' separately from our script, *and then* our script is called. The net
effect of this is that:

- We cannot spawn a new process and expect 'import gxsm' to work; it won't!
Therefore, we cannot use spawn_components(), as it places each component into
its own process.
"""


CONFIG_FILE = './config.toml'
GXSM_ID = 'translator'
LOG_FILE = 'log.txt'
LOG_TO_STDOUT = 'True'
LOG_LEVEL = 'DEBUG'


if __name__ == '__main__':
    from afspm import spawn
    spawn.spawn_monitorless_component(CONFIG_FILE,
                                      GXSM_ID,
                                      LOG_FILE,
                                      LOG_TO_STDOUT,
                                      LOG_LEVEL)
