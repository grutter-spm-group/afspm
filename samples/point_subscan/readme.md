# Point Subscan Experiment

In the point subscan experiment, the ```experiment``` component scans a 'full' scan region (```full_scan_origin``` and ```full_scan_size``` in config) and waits to receive points of interest from some other component.
If those points are received, it proceeds to run the next ```sub_scans_per_full_scan``` scans by setting the scan region to be of size ```sub_scan_phys_size```, centered at the highest-scored point received.

The ```roi_analysis``` component monitors the received 'full' scans and analyzes them for points of interest.
In theory, this could involve a machine-learnt classifier that searches, for example, for particular defects.
In practice, the method currently simply grabs points randomly from within the scan region.

Some additional optional components defined in the config:
- [```ui```] is an AfspmControlUI, giving the user the ability to switch to manual mode, end the experiment, and flush any logged problems.
- [```tip_detector```] is a fake 'Tip Detector' (```tip_analysis.py```) that flags there is a problemw with the tip every ```scan_period_raise_problem```.
- [```visualizer```] is a generic visualizer that displays the 'full' and 'sub' scans as they are received.

Note that this config file was created by maximally using ```AfspmComponent / ScanningComponent``` callbacks, rather than expliciting classes each time.
As such, ```experiment.py```, ```roi_analysis```, and ```tip_analysis``` all use appropriate callbacks.
Not that all of these use data structures to hold state in between callback calls.
For example, ```experiment.py``` contains a dataclass `ExperimentData` (declared as [```exp_data```] in the config) which is passed to the callback via the ```next_params_kwargs```  argument of the spawned ScanningComponent.
