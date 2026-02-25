# Omicron SXM Translator Guide

The Omicron SXM controller provides the following interfacing logic:

- A Pascal-like scripting interface;
- A Windows DDE-based inter-process communication interface (language-agnostic);
- A series of Python scripts to interface via this DDE interface.

We implemented our translator using a modified version of one of the Python scripts provided.
This is because we found some error conditions that appeared to not be handled by the script.
The modified script is saved here as sxm.py.

# Usage

## Setup

Ensure that the SXM Windows application is open. Make sure that the 'continuous scan' button is deselected.

## Starting Your Experiment

Start your experiment via your config file in afspm:
```shell
poetry run spawn /path/to/config/config.toml

# Limitations

## Scan Configuration

There does not appear to be an API call to enable/disable continuous scanning.
As such, you should disable it manually before running your script.

## Scan Stopping

The API allows the user to *pause* a scan, but not to stop one.
This diverges from the user interface, which allows a user to pause or stop by deselecting the 'play' button in the main menu.
One can choose between continuous running (pause) or stopping on deselection (by right-clicking the button and selecting the appropriate menu item).

## Spectroscopy Stopping

The API does not allow the user to pause a spectroscopy.
This diverges from the user interface, which allows a user to do so by deselecting the 'play' button in the Spectroscopy window.
Note that this causes the last successful spectroscopy to be saved as if it were a new spectroscopy; this is a known bug.

## Coordinate System Mismatch Between ProbePosition Get() and Set()

There is a coordinate system (CS) mismatch between getting and setting the probe position.
The get() command CS appears to be scan setting invariant.
The set() command's CS matches that displayed as 'Current Position' in the user interface 'Scripting' window.
In this CS, the position varies as a function of the scan offset, according to the following formula:

`set_pos = get_pos + offset / CONSTANT`

where CONSTANT appears different between x- and y-dimensions.

To account for this, the SXMParameterHandler accepts a tuple `cs_correction_ratio` as an input argument to its constructor.
A default calculated for our microscope is provided.
To calculate for your own microscope: set your probe position to a position with the scan offset (0,0) and with it at a particular offset; subtract the written positions ('Current Position' in the Scripting window) and divide them by the scan offset.

# Notes

## Autosave Settings

When running the translator, we set the spectroscopy and scan to autosave. We do not return to the prior settings on shutdown.

## Probe Position Setting

In order to move the probe position on setting, we do the following:

- Change to our 'fake' spectroscopy mode.
- Run the spectroscopy.
- Once the spectroscopy ends, delete the saved file (it was useless data).
- Return to our true spectroscopy mode.

This appears to be the most straightforward way to do so with the existing API.
If unusual behaviour is seen during probe position setting, this logic may be the source.

### Setting and Configuring 'Moving' Mode

Since we cannot get the spectroscopy settings, we cannot store the prior settings and revert to them after the move is done.
The most reasonable option we have found is to allow the user to define from either X(z) or X(U) modes as the 'fake' spectroscopy mode, meaning a mode that will not be used during their experiment.
On startup, we switch to this mode and set a number of parameters (delays, acquisition time, dz, and bias values) to very short/minimal values.
The goal is to make it so that said spectroscopy runs quickly and minimally affects the experiment.

## Limitation on External Scripts Running

While the SXMTranslator is running no other DDEClients may send messages to the SXM application via the DDE.
This is because there does not appear a way to associate a response to a request, and the DDE Server responds to all clients.
Therefore, we could receive a response from a different client and associate it to our response.
