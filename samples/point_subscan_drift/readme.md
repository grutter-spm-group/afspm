# Point Subscan Drift Experiment

This config file is a 'child' of the point subscan experiment, where we modify it to (a) have a fake thermal drift happening, and (b) we us a DriftCompensatedMediator to correct for it.

The main differences:
- The ```translator``` component  is a 'DriftImageTranslator', which fakes a linear drift.
- The ```mediator ``` component is a 'DriftCompensatedMediator', which attempts to detect and account for drift.
- A ```rescanner``` component is a linked 'DriftRescanner', which can force a rescan if the drift compensation is insufficient at some point.
  It effectively corrects for a 'too-far' drift between any two scans.

