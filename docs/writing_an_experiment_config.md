# Writing an Experiment Configuration File


In general, we recommend you review the various ```config.toml``` files in the ```samples ```subdirectory to get a better feel for doing this.

## Parser Overview

The TOML configuration files are treated by our main executable, ```spawn.py``` as a dict-of-dicts (refer to TOML guides if curious). When it reads it, it:
1. Recursively expands variables.
2. Filters out components.
3. Constructs each component.

The main logic for performing this is in ```afspm/utils/parser.py```. We suggest you review the pydocs in there in addition to the explanation here.

### Expanding Variables

All variable names can be referenced as strings later on in the configuration file.
During parsing, they will be replaced. For example, a variable:

```physical_units = 'nm'```

can be referenced further on:

```toml
[exp_data]  # TODO: Try just as dict
class = 'experiment.ExperimentData'
phys_units = 'physical_units'
```

and the parser will replace 'physical_units' with 'nm':

```toml
[exp_data]  # TODO: Try just as dict
class = 'experiment.ExperimentData'
phys_units = 'nm'
```

before feeding this config to the appropriate constructor.

Note that this extends beyond simple single variables: dictionaries can similarly be referenced. In fact, this is required to be able to set up the various components. For example, to construct a Subscriber node for a given component, we would set one up:

```toml
[sub]
class = 'afspm.io.pubsub.subscriber.Subscriber'
sub_url = 'analysis_url'
# [...]
```

and then reference this dict later:

```toml
[experiment]
component = true
class = 'afspm.components.scan.handler.ScanningComponent'

subscriber = 'sub'
# [...]
```

This variable replacement is done recursively throughout the dict-of-dicts. Thus, in the end we end up with 'component' dicts (described below) where all of the variables needed to instantiate them are defined. 

The recursive nature of the operation is why we call this 'expanding' variables. The top-level method for this is ```expand_variables_in_dict()```

### Filtering out Components

This one is easy: any dictionary with a key:val pair of 'component': true is treated as a component. The parsing script thus filters out the dicts containing this key:val pair.

### Constructing each Component

To construct each component, the parser recursively goes down the component dict-of-dicts, searching for dicts with a 'class' key:val pair. For each of those, it instantiates a class of the val.

For example, for the (variable-expanded) Subscriber (which presumably is referenced in a component):

```toml
[sub]
class = 'afspm.io.pubsub.subscriber.Subscriber'
sub_url = "tcp://127.0.0.1:9002"
# [...]
```

it instantiates an ```afspm.io.pubsub.subscriber.Subscriber``` class, feeding it as input a kwargs dict created from the remaining key:val pairs of that dict. In this case, for example, it would feed ```"tcp://127.0.0.1:9002"``` for argument ```sub_url```.

Once all the lower-level dicts corresponding to classes have been instantiated, it instantiates the component (which also has a 'class' key), feeding the input arguments in the same way. For example, for the previously mentioned `experiment` component:

```toml
[experiment]
component = true
class = 'afspm.components.scan.handler.ScanningComponent'

subscriber = 'sub'
# [...]
```
it feeds the just instantiated Subscriber class as input argument 'Subscriber'.

In this manner, all components are instantiated and created in their own processes.

The logic for this is primarily in ```construct_and_run_component()```. Note that all components are spawned as their own processes, so this method is fed as the target method when creating the process. This logic can be found in ```afspm/components/monitor.py```, in the method ```_startup_component()```.

## Configuration Overview

As mentioned in overview.pdf, writing a configuration file can generally be split into:
- setting up general variables;
- defining intermediary classes (primarily I/O nodes); and
- defining the components.

Throughout this explanation, we will reference the config file at ```samples/point_subscan/config.toml```.

## Setting up General Variables

At the top of the config file, we generally recommend writing all socket addresses and common variables you would like to pass as configuration to the various components.

### Socket Addresses

An example socket address might be:

```pub_url = "tcp://127.0.0.1:9000"```

where 'tcp://127.0.0.1' corresponds to 'localhost', indicating that it is a TCP/IP address on the local computer; and '9000' corresponds to the port we will be using for that address.

Unfortunately, defining socket addresses is a manual procedure. While I have not yet run into socket address conflicts while running, I acknowledge this aspect of setting up a config file is tedious. I'm sorry!

Note that we can use non-local addresses to connect components across multiple computers. Here, we would replace the 'localhost' IP address with the IP address associated with the computer where we wish to create the socket address.

## Defining Intermediary Classes

The main 'intermediary' classes we declare will be our I/O nodes, crucial to set up a component. See the Subscriber definition above for an example. 

In addition to this, another common class one may set up are those associatd with a unique cache setup. In our example config file, there is a section commented ```# --- Cache Aspects --- #```. Here, we see the definition of two different ```Scan2d ``` envelopes, corresponding to two different physical sizes (```[full_scan_id]``` and ```[small_scan_id]```):


```toml
[full_scan_id]  # This should be specific to one channel
class = 'afspm.io.pubsub.logic.pbc_logic.create_roi_scan_envelope'
size = 'full_scan_size'
channel = 'channel_id'

[small_scan_id]  # This should be specific to one channel
class = 'afspm.io.pubsub.logic.pbc_logic.create_roi_scan_envelope'
size = 'small_scan_size'
channel = 'channel_id'
```

These are used in the definition of ```[proto_hist_list]```, which states how big the cache should be for each of these two ```Scan2d```s:


```toml
[proto_hist_list]  # This *should* mean to make a cache of these for each channel
class = 'afspm.io.pubsub.logic.pbc_logic.create_roi_proto_hist_list'
sizes_with_hist_list = [['full_scan_size', 1], ['small_scan_size', 'sscans_per_fscan']]
```

```[proto_hist_list]``` is fed as the ```proto_with_history_list``` input to our cache logic, of the type ```PBCScanLogic```:


```toml
[pbc_scan_logic]
class = 'afspm.io.pubsub.logic.pbc_logic.PBCScanLogic'
proto_with_history_list = 'proto_hist_list'
```

This is then used as the input ```cache_logic``` for the cache-linked methods ```extract_proto()``` and ```update_cache()```, which are used both by the ```PubSubCache``` and ```Subscriber``` when receiving/sending messages:

```toml
[roi_cache_kwargs]
cache_logic = 'pbc_scan_logic'

[scheduler_psc]
class = 'afspm.io.pubsub.cache.PubSubCache'
url = 'psc_url'
sub_url = 'pub_url'
update_cache_kwargs = 'roi_cache_kwargs'
```

This is a bit circuitous and confusing, but makes more sense if one reviews the associated methods. For example, ```extract_proto()``` does the following:

```python
def extract_proto(msg: list[bytes], cache_logic: CacheLogic
                  ) -> Message:
    """Non-class method for extracting proto given a CacheLogic instance.

    See CacheLogic.extract_proto() for more info.
    """
    return cache_logic.extract_proto(msg)
```

So the ```cache_logic``` fed is the ```CacheLogic``` class that will be used to extract a proto.

## Defining Components

As alluded to above, the only difference between a component and other classes that are to be instantiated is the inclusion of a key:val pair with the key 'component'. For example, the following:

```toml
[metadata]
component = true
class = 'afspm.components.scan.metadata.ScanMetadataWriter'
subscriber = 'sub_spm'
```

will instantiate a component ScanMetadataWriter, feeding it the expanded Subscriber linked to the key 'sub_spm' earlier in the config file.

Note that you can stop components from being instantiated by commenting out the 'component' key:val pair. This is another way to limit which components are instantiated (you can also do so with the input arguments to the spawn command).
