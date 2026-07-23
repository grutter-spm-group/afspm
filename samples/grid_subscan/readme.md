# Grid Subscan Experiment

The grid subscan experiment divides a scan region (```full_scan_origin``` and ```full_scan_size``` in config) into a set number of sub-regions ( ```sub_rois_per_dim``` in config).
The experiment (```roi_experimenter.py```) runs by:
- Running a 'full scan'.
- For the ```sscans_per_fscan``` subsequent scans, it randomly selects a sub-scan and runs it.

Some additional optional components defined in the config:
- [```ui```] is an AfspmControlUI, giving the user the ability to switch to manual mode, end the experiment, and flush any logged problems.
- [```tip_detector```] is a fake 'Tip Detector' (```freq_trigger_tip_detector.py```) that flags there is a problemw with the tip every ```scan_period_raise_problem```.
- [```visualizr```] is a generic visualizer that displays the 'full' and 'sub' scans as they are received.

Note that, in this config, all written components were written as their own classes (e.g. ROIExperimenter), that inherit from the appropriate base classes.
This is as opposed to using base classes directly and only defining needed callback methods.
For an example of that, see the ```grid_subscan``` sample.
