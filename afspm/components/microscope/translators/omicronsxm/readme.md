# Omicron SXM Translator Guide

The Omicron SXM controller provides the following interfacing logic:

- A Pascal-like scripting interface;
- A Windows DDE-based inter-process communication interface (language-agnostic);
- A series of Python scripts to interface via this DDE interface.

We implemented our translator using a modified version of one of the Python scripts provided.
This is because we found some error conditions that appeared to not be handled by the script.
The modified script is saved here as sxm.py (and was based off of SXMRemote.py from their scripts).

# Version Support

This translator has been tested on SXM version 28.8.
A number of the limitations noted (scan/spec stopping) may be tied to this version.

# Usage

## Setup

Ensure that the SXM Windows application is open. Make sure that the 'continuous scan' button is deselected (right-click on the Scan/Play button in the main menu).

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

Because of this, scan stopping is currently not supported.

## Spectroscopy Stopping

The API does not allow the user to pause a spectroscopy.
This diverges from the user interface, which allows a user to do so by deselecting the 'play' button in the Spectroscopy window.
Note that this causes the last successful spectroscopy to be saved as if it were a new spectroscopy.

Because of this, spectroscopy stopping is currently not supported.

## Coordinate System Mismatch Between ProbePosition Get() and Set()

There is a coordinate system (CS) mismatch between getting and setting the probe position.
The get() command CS appears to be scan setting invariant.
The set() command's CS matches that displayed as 'Current Position' in the user interface 'Scripting' window.
In this CS, the position varies as a function of the scan offset, according to the following formula:

`set_pos = get_pos + offset / CONSTANT`

where CONSTANT appears different between x- and y-dimensions.

To account for this, the SXMParameterHandler accepts a tuple `cs_correction_ratio` as an input argument to its constructor.
A default calculated for our microscope is provided.

To calculate for your own microscope: set your probe position to a position with the scan offset (0,0) and with it at a particular offset; subtract the displayed positions ('Current Position' in the Scripting window) and divide them by the scan offset.

## Setting Pixel Resolution

Setting the pixel resolution for the x-dimension (columns) via the software interface is restricted to the following set: [32, 64, 128, 256, 512].
Curiously, this limitation does not exist via the user interface.

Because of this, setting the pixel resolution will throw an error if an unsupported resolution is input.

## Probe Position Setting

In this interface, setting the probe position does not actually move it.
Doing so requires (according to advice in their documentation) forcing a fake spectroscopy.

The translator implements this logic -- see below for more information.

## Spectroscopy Settings

The various spectroscopy settings (beyond simply starting/stopping) can be set via the interface, but not gotten.

## Running Additional External Scripts

While the SXMTranslator is running no other DDEClients may send messages to the SXM application via the DDE.
This is because there does not appear a way to associate a response to a request, and the DDE Server responds to all clients.
Therefore, we could receive a response from a different client and associate it to our response.

Note that responses are pre-pended with a command index of sorts.
Initially, we hoped that this index associated it to its request; if so, one could maintain a similar counter and throw out responses until the associated response was detected.
However, upon further testing, this appears to not be the case.
We therefore are stuck with the limitation described.

## Running Spectroscopies

In contrast with all the other requests we have sent, the 'StartSpect;' request is synchronous, only returning a response once the spectroscopy has finished.
This is the main cause of the above limitation, as we cannot predict when it will return.

# Notes

## Autosave Settings

When running the translator, we set the spectroscopy and scan to autosave. We do not return to the prior settings on shutdown.

## Probe Position Setting

In order to move the probe position on setting, we do the following:

- Change to a 'fake' spectroscopy mode.
- Run the spectroscopy.
- Once the spectroscopy ends, delete the saved file (it was useless data).
- Return to our true spectroscopy mode.

This appears to be the most straightforward way to do so with the existing interface.
If unusual behaviour is seen during probe position setting, this logic may be the source.

### Setting and Configuring 'Fake' Spectroscopy Mode

Since we cannot get the spectroscopy settings, we cannot store the prior settings and revert to them after the move is done.
The most reasonable option we have found is to allow the user to define from either X(z) or X(U) modes as the 'fake' spectroscopy mode, meaning a mode that will not be used during their experiment.
On startup, we temporarily switch to this mode and set a number of parameters (delays, acquisition time, dz, and bias values) to very short/minimal values.
The goal is to make it so that said spectroscopy runs quickly and minimally affects the experiment.

## Running Spectroscopies

Due to the spectroscopy limitation, we pause all polling of data during spectroscopies.
We are able to detect that a spectroscopy has ended via a callback; at that point, we start polling again.

# Testing

## Pixel resolution setting

When running test_translator with this translator, please ensure the pixel resolution is set to 64.
This allows the existing tests to pass, which multiply/divide the prior resolution.

