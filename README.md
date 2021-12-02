# Voltage controller
## Description
This program provides an interface for managing a set of high voltage power sources.

The program is tested for python 3.6 and python 3.8.

## Installation
Before installation, you need to install GTK3.
Also you must install PyGObject dependencies,
the list of required packages depends on the Linux distribution.
but in most cases it is gobject-introspection.

Follow the steps below to install the program.
```
python3.6 -m venv .venv --clear
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Running
Before running the program you should activate the virtual environment:
```
source .venv/bin/activate
```

Now you can run the program with the command of the form:
```
python main.py [-h] [--profile PATH] DEVICES
```
For example
```
python main.py --profile voltage-profile.csv device-list.csv
```
Sample configuration files are located in the config-emulator and config-real directories.
Also you may want to alter some parameters in ```config.py```.
For example, to change the maximum allowed difference between set and measured voltage,
you can change these lines in the ```config.py```:
```py
check_settings.max_voltage_difference = 10
check_settings.max_voltage_when_off = 100000
```

## Project structure
- ```checks.py``` -- device state checking.
- ```config.py``` -- program parameters. You may modify this file to configure program.
    Here you can setup logging and modify state checking parameters,
    such as allowed voltage deviation.
- ```settings.py``` -- definitions of settings used by the program and their default values.
    Do not modify this file if you want to configure application, modify ```config.py``` instead.
- ```data_logger.py``` -- records the history of device parameters.
- ```files.py``` -- functions for reading files used by the program.
- ```main.py``` -- application entry point. It is responsible for setting up the environment and launching the GUI.

### Device module
This module is responsible for low level device communication.
- ```command.py``` -- classes for encoding and decoding protocol packets.
- ```registers.py``` -- codes of the registers used by the device.
- ```device.py``` -- classes that provide access to device registers over TCP/IP.

### GUI module
This module is responsible for interacting with GTK3 it provides user interface for device module.
All classes in this module except ```Worker``` provide some part of GUI.
The worker performs all communication with the device in a separate thread
and provides methods for querying and changing device state.
```main.py``` is the entry point of GUI it performs gui initialization and starts ```MainWindow```.
