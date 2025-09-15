#  I/O Overview

As described in overview.pdf, there are two main communication paths between the microscope and other components: publisher-subscriber (```pubsub```) and control-request (```control```). In addition to this, components are monitored via a heartbeat mechanism that is handled automatically (```heartbeat```). Pretty much all data is defined in protobuffers, with the various source files in the ```protos``` directory.

# pubsub

In the publisher-subscriber path, we have: a Publisher, that connects to a node and publishes information; and Subscribers, which connect to the same node and subscribe to the data they would like to receive. 

(Pretty much) all messages sent via the ```pubsub``` path are of the form:

| ```Envelope ```| ```Data Structure``` | ```Timestamp``` |

Where ```Envelope ``` is a string defining a 'topic', ```Data Structure``` is a serialized protobuffer data structure, and ```Timestamp``` is a timestamp of when the message was created. Thus, the envelope defines the data structure that is being sent, and subscribers can choose to subscribe to all data structures sent (the default, where '' is used as the subscription), or to only specific ones they require.

In the case of our microscope communication, data is passed between 3 node types:
- The MicroscopeTranslator has a Publisher node which it uses to publish any state changes.
- The MicroscopeScheduler connects to this and caches data received via a PubSubCache node. It functions as an intermediary, such that other components can connect to it in the same manner they might connect directly to the MicroscopeTranslator.
- Other components, that have Subscriber nodes which connect to the MicroscopeScheduler to receive information.

All three of these node types take as input methods that map from an envelope to a data structure, so that they can know what data structure they are sending/receiving based on the envelope they received.  The defaults used for these can be found in ```afspm.io.pubsub.defaults.py```. The PubSubCache has a mapping for the data it receives (from the Publisher) and a mapping for the data it sends out, allowing more complicated mappings for caching purposes.

## Timestamping

As mentioned earlier, all messages sent via the ```pubsub``` path include a timestamp. It's purpose is to allow new components to subscribe and receive cached data, without this cached data confusing already existing components. When a new component connects and subscribes to the PubSubCache, it re-sends all messages in its cache; this is done so that the new component may become up-to-date with the current state of an experiment. However, since the publisher sends out messages in a one-to-many fashion, all other subscribed components receive these messages. All subscribers implicitly hold the timestamp of the last received messages, and are able to ignore these cached messages, because they predate the latest message. This behaviour (not reacting to 'old' messages) is part of the Subscriber behaviour and requires no extra handling/consideration by component developers.

## Signals

There are some minor exceptions to the above way data is sent. These are explicit signals we send out that do not involve data structure. To send these, the message packet looks like:

| ```Signal ``` |

Where ```Signal ``` is a string, like Envelope before. In other words, we only send a single string. Note that these signals are registered by default by all Subscribers, so you should receive them regardless of your chosen topics.

### 'KILL' Signal

The 'KILL' signal is sent out to indicate that the experiment is ending and any component reading it should shut down. It is sent out by the Publisher or PubSubCache.

# control 

In the control-request path, we have: a ControlServer, that receives requests and responds to them; and ControlClients, that make requests and receive responses.

All requests in the control-request path are of the form:

| ```Request ID``` | ```Data Structure``` |

Where ```Request ID``` is an integer associated with the ControlRequest enumeration in ```control.proto```, and ```Data Structure``` is a serialized protobuffer data structure. There is an explicit mapping from ```Request ID``` to the expected data structure, which can be found at ```afspm/io/control/commands.py``` (```REQ\_TO\_OBJ\_MAP```).

All responses in the control-request path are of one of the following two forms:

(1) | ```Response ID``` |

(2) | ```Response ID``` | ```Data Structure``` |

Where ```Response ID``` is an integer associated with the ControlRequest enumeration in ```control.proto```, and ```Data Structure``` is a serialized protobuffer data structure. Almost all responses are of form (1); the exceptional cases are listed in ```afspm/io/control/commands.py```  (```REQ\_TO\_RETURN\_OBJ\_MAP```).

In the case of our microscope communication, data is passed between 3 I/O node types:
- The MicroscopeTranslator has a ControlServer node, which receives requests from other components and responds to them.
- The MicroscopeScheduler has a ControlRouter node, which routes requests from other components to the MicroscopeTranslator.
- Other components have ControlClient nodes, which send requests and receive responses.

Note that the MicroscopeScheduler, via the ControlRouter node, handles access to the MicroscopeTranslator. A subset of requests are handled only by the MicroscopeScheduler and can be sent by any component at any time. These are listed in ```control.proto``` as 'specific to ControlRouter', and entail requesting/releasing control, adding/removing problems. The main 'microscope communication' requests can only be send if a component is in control. Additionally, some 'admin' controls exist; these can technically be sent by any component, but we suggest not using them unless necessary for your component.

# heartbeat

All components, on startup, create HeartBeater I/O nodes. These nodes publish 'beats' to an automatically determined socket location. An AfspmComponentsMonitor is responsible for starting them up, and contains HeartbeatListener I/O nodes that subscribe to the socket location. In this way, the monitor is able to ensure all components are still alive. If it detects that a component has died or frozen (meaning it has not sent a heartbeat in too long), it kills the process and restarts it.

All heartbeat messages are of the type:

| ```HBMessage ```|

where ```HBMessage ```is an integer corresponding to the HBMessage enum at ```afspm/io/heartbeat/heartbeat.py```.

Note that the Heartbeater I/O node will send a ```KILL``` enum value out when the component is closing. It does this to inform the HeartbeatListener that it is intentionally closing and thus should not be restarted.
