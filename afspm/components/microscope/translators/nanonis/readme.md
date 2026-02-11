# Nanonis Microscope Translator Guide

Nanonis provides a TCP programming interface.
We interface with it by connecting to the Nanonis server and sending/receiving messages according to the format defined in their Nanonis TCP Protocol document.
Note that Nanonis also seems to provide a wrapper Python interface [here]( https://github.com/SPECS-Zurich-GmbH/nanonis_spm).
We chose to implement our own Python wrapper to validate that one can use our framework to integrate with inter-process communication (IPC) intrefaces.

## Usage

### Setup

Ensure that the server port used to connect matches one of the 4 connections in the Nanonis interface (System -> Options -> TCP Programming Interface).
This port corresponds to the input argument 'port' in the NanonisClient (which is a 'client' input argument for the NanonisTranslator).

### Starting Your Experiment
Start your experiment via your config file in afspm:
```shell
poetry run spawn /path/to/config/config.toml

## Notes
