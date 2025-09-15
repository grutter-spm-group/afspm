# Writing afspm Components

All components (which inherit from AfspmComponentBase) have Subscriber and ControlClient I/O nodes, allowing them to be set up to listen to messages published by the MicroscopeTranslator and send requests to it.

In general, we recommend considering one of the following when creating a component:
- AfspmComponent (```afspm/components/component.py```)
- ScanningComponent (```afspm/components/scan/handler.py```)

Unless you have additional needs, use of these components allows you to restrict your development to that of writing one/two methods and optionally defining a data structure that will persist throughout the experiment.

## AfspmComponent

AfspmComponents have an optional Publisher I/O node that can be used to send information to other components. For the main component logic, there are two callables which can be provided:
- ```message_received_method()```: this method is called whenever a message is received by the Subscriber I/O node. This is usually the main method one would consider, as it allows a component to perform some processing when a desired message type is received. It is called by the internal ```on_message_received()``` method.
- ```per_loop_method()```: this method is called on every step through the component's main loop. This means it is called at a set frequency, and is not associated with any event having occurred. It can be used by component developers if they wish to have some form of processing that occurs at regular intervals. It is called by the internal ```run_per_loop()``` method

Both these methods are fed a Python dict ```methods_kwargs```(in addition to any default inputs). This dictionary persists throughout the experiment, and allows developers to hold state if desired.

### Example Usage of AfspmComponent

Please review the ```roi_analysis``` component in ```samples/point_subscan/config.toml``` for an example of a component written using this logic. It uses a persistent ```ROIAnalysisData``` data structure to store state, and a method ```analyze_full_scan()``` to perform the ```message_received_method``` logic. Both of these can be found in ```samples/point_subscan/roi_analysis.py```.

## ScannningComponent

ScanningComponents use a helper class (ScanHandler) to simplify requesting scans/spectroscopies from the microscope. 

For the main component logic, there is a callable ```get_next_params``` which can be used to decide where to scan/spec next; it is called when a new ScopeState has been received and no scans/specs are currently in progress. This method also has an associated Python dict ```methods_kwargs``` that can be used to hold state throughout the experiment.

Note that the configuration provided for ScanningComponent should contain the ExperimentProblem it resolves (```EP_NONE``` if it is a general component). This is used when requesting control to the MicroscopeScheduler.

### Example Usage of ScanningComponent

Please review the ```experiment``` component in ```samples/point_subscan/config.toml``` for an example of a component written suing this logic. It uses a persistent ```ExperimentData``` data structure to store state, and a method ```get_next_scan_params()``` to decide where to scan next. Both of these can be found in ```samples/point_subscan/experiment.py```.
