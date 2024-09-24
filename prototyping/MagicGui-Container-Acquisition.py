import json.tool
import napari.layers
import napari.layers.image
from napari.qt.threading import thread_worker
import pymmcore_plus
import numpy as np
from napari_micromanager import MainWindow
from magicgui import magicgui
from magicgui.tqdm import tqdm
from magicgui.widgets import ComboBox
import pathlib
import datetime
import pandas as pd
import serial

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import napari

import os
import useq
from useq import MDASequence
from pymmcore_plus.mda.handlers import OMEZarrWriter, OMETiffWriter, ImageSequenceWriter
from pymmcore_plus.mda import mda_listeners_connected

PSYCHOPY_PATH = r'C:\sipefield\sipefield-gratings\PsychoPy\Gratings_vis_stim_devSB-JG_v0.6.psyexp'
JSON_PATH = r'C:\sipefield\napari-mesofield\prototyping\camk2-gcamp8.json'
SAVE_DIR = r'D:\jgronemeyer'
DHYANA_CONFIG = r'C:/Program Files/Micro-Manager-2.0/mm-sipefield.cfg'
THOR_CONFIG = r'C:/Program Files/Micro-Manager-2.0/ThorCam.cfg'
PUPIL_JSON = r'C:\sipefield\napari-mesofield\prototyping\camk2-gcamp8_pupil.json'

from magicgui.widgets import Container, CheckBox, create_widget
import json
import keyboard

#TODO test rotary encoder connection
def test_arduino_connection():
    try:
        arduino = serial.Serial('COM4', 9600)
        arduino.close()
        print("Arduino connection successful!")
    except serial.SerialException:
        print("Failed to connect to Arduino on COM4.")
        
#TODO auto-refresh the JSON file path in the GUI each time a new JSON file is added
#TODO Save config for each session
#TODO Add a button to save the current configuration to a JSON file
#TODO dropdown menu for selecting the JSON file from the directory
#TODO Auto-fps calculation based on the number of frames and duration

class ExperimentConfig:
    """## Generate and store parameters loaded from a JSON file. 
    
    #### Example Usage:
        ```
        config = ExperimentConfig()
            # create dict and pandas DataFrame from JSON file path:
        config.load_parameters('path/to/json_file.json')
            # update the 'subject' parameter to '001':
        config.update_parameter('subject', '001') 
            # return the value of the 'subject' parameter:
        config.parameters.get('subject') 
            # return a pandas DataFrame with 'Parameter' and 'Value' columns:
        ```
    """

    def __init__(self):
        self._parameters = {}
        self._output_path = ''
        self._parameters['save_dir'] = os.getcwd() # default save directory

    @property
    def save_dir(self) -> pathlib.Path:
        return self._parameters.get('save_dir', os.getcwd())

    @property
    def protocol(self) -> str:
        return self._parameters.get('protocol', 'default_protocol')

    @property
    def subject(self) -> str:
        return self._parameters.get('subject', 'default_subject')

    @property
    def session(self) -> str:
        return self._parameters.get('session', 'default_session')

    @property
    def task(self) -> str:
        return self._parameters.get('task', 'default_task')

    @property
    def start_on_trigger(self) -> bool:
        return self._parameters.get('start_on_trigger', False)

    @property
    def num_frames(self) -> int:
        return self._parameters.get('num_frames', 0)
    
    @property
    def num_trials(self) -> int:
        num_trials = int(self.num_frames / (5 * 45))
        return num_trials
    
    @property
    def parameters(self) -> dict:
        return self._parameters
    
    @property
    def filename(self):
        return f"{self.protocol}-sub-{self.subject}_ses-{self.session}_task-{self.task}.ome.tiff"

    @property
    def output_path(self):
        # Construct the directory path
        bids_dir = os.path.join(
            f"{self.protocol}",
            f"sub-{self.subject}",
            f"ses-{self.session}",
            'func'
        )
        return os.path.abspath(os.path.join(self.save_dir, bids_dir))

    # Property to compute the full file path, handling existing files
    @property
    def file_path(self):
        file = self.filename
        return self._generate_unique_file_path(file)

    # Property for pupil file path, if needed
    @property
    def pupil_file_path(self):
        file = 'pupil.tiff'
        return self._generate_unique_file_path(file)

    # Helper method to generate a unique file path
    def _generate_unique_file_path(self, file):
        os.makedirs(self.output_path, exist_ok=True)
        base, ext = os.path.splitext(file)
        counter = 1
        file_path = os.path.join(self.output_path, file)
        while os.path.exists(file_path):
            file_path = os.path.join(self.output_path, f"{base}_{counter}{ext}")
            counter += 1
        return file_path
    
    def load_parameters(self, json_file_path) -> None:
        """ 
        Load parameters from a JSON file path into the config object. 
        """
        
        try:
            with open(json_file_path, 'r') as f: 
                self._parameters = json.load(f)
        except FileNotFoundError:
            print(f"File not found: {json_file_path}")
            return
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return

        # Update the dataframe
        self._dataframe = pd.DataFrame([self._parameters])

        # Update the output path
        self._create_bids_directory()
    
    def _create_bids_directory(self):
        """ 
        Create a BIDS-formatted output path based on the loaded parameters.
        """
        save_dir = os.path.abspath(self.save_dir)
        
        # Construct the directory path
        bids_dir = os.path.join(
            f"{self.protocol}",
            f"sub-{self.subject}",
            f"ses-{self.session}",
            'func'
        )

        # Construct the filename
        filename = f"{self.protocol}-sub-{self.subject}_ses-{self.session}_task-{self.task}.ome.tiff"
        self.update_parameter('filename', filename)
        
        # Combine directory and filename
        self._output_path = os.path.join(save_dir, bids_dir)

    def _create_file_path(self, pupil=False):
        """ 
        Create save directory and return directory + filename.tiff for tifffile writer.
        If the filename exists in directory, then append a number to the filename.
        """
        file = self.parameters.get('filename', 'default.tiff')
        if pupil:
            file = 'pupil.tiff'
        os.makedirs(self.output_path, exist_ok=True)
        
        base, ext = os.path.splitext(file)
        counter = 1
        file_path = os.path.join(self.output_path, file)
        
        while os.path.exists(file_path):
            file_path = os.path.join(self.output_path, f"{base}_{counter}{ext}")
            counter += 1
        
        self.update_parameter('save_dir', file_path)
        return file_path

    def _get_json_files(self):
        import glob
        """ Get all JSON files in the same directory as this script """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        json_files = glob.glob(os.path.join(script_dir, "*.json"))
        return json_files
    
    @property
    def dataframe(self):
        data = {'Parameter': list(self._parameters.keys()),
                'Value': list(self._parameters.values())}
        return pd.DataFrame(data)

    def update_parameter(self, key, value):
        """ Update a parameter in the parameters dictionary and DataFrame.
        
        - *key (str)*: The parameter key to update.
        
        - *value*: The new value for the parameter.
        """
        self._parameters[key] = value
        # Update the dataframe
        self._dataframe[key] = [value]
        # Update the output path in case relevant BIDS parameters have changed
        if key in ['subject', 'session', 'task']:
            self._create_bids_directory()

class AcquisitionEngine(Container):
    """ AcquisitionEngine object for the napari-mesofield plugin
    This class is a subclass of the Container class from the magicgui.widgets module.
    The object connects to the Micro-Manager Core object instance and the napari viewer object.
 
    _update_config: updates the experiment configuration from a new json file
    
    run_sequence: runs the MDA sequence with the configuration parameters
    
    launch_psychopy: launches the PsychoPy experiment as a subprocess with ExperimentConfig parameters
    """
    def __init__(self, viewer: "napari.viewer.Viewer", mmc: pymmcore_plus.CMMCorePlus, mmc2: pymmcore_plus.CMMCorePlus = None):
        super().__init__()
        self._viewer = viewer
        self._mmc = mmc
        self._mmc2 = mmc2
        self.config = ExperimentConfig()
        
        #### GUI Widgets ####
        # Dropdown for JSON configuration files
        self._gui_json_dropdown = ComboBox(
            label='Select JSON Config:',
            choices=self.config._get_json_files()
        )
        # Table widget to display the configuration parameters
        self._gui_config_table = create_widget(
            label='Experiment Config:',
            widget_type='Table',
            is_result=True,
            value=self.config.dataframe
        )
        self._gui_config_table.read_only = False  # Allow user input to edit the table
        self._gui_config_table.changed.connect(self._on_table_edit)  # Connect to table update function

        # Record button to start the MDA sequence
        self._gui_record_button = create_widget(
            label='Record', widget_type='PushButton'
        )
        # Launch PsychoPy button to start the PsychoPy experiment
        self._gui_psychopy_button = create_widget(
            label='Launch PsychoPy', widget_type='PushButton'
        )

        #### Callback connections between widget values and functions ####
        # Load the JSON configuration file
        self._gui_json_dropdown.changed.connect(self._update_config)
        # Run the MDA sequence upon button press
        self._gui_record_button.changed.connect(self.rec)
        # Launch the PsychoPy experiment upon button press
        self._gui_psychopy_button.changed.connect(self.launch_psychopy)

        # Add the widgets to the container
        self.extend([
            self._gui_json_dropdown,
            self._gui_config_table,
            self._gui_record_button,
            self._gui_psychopy_button
        ])

    def _update_config(self):
        """Update the experiment configuration from a new JSON file."""
        json_path = self._gui_json_dropdown.value
        if json_path and os.path.isfile(json_path):
            try:
                self.config.load_parameters(json_path)
                # Refresh the GUI table
                self._refresh_config_table()
            except Exception as e:
                print(f"Trouble updating ExperimentConfig from AcquisitionEngine:\n{json_path}\nConfiguration not updated.")
                print(e)

    def _on_table_edit(self, event=None):
        """Update the configuration parameters when the table is edited."""
        # Retrieve the updated data from the table
        table_value = self._gui_config_table.value  # This should be a dict with 'data' and 'columns'

        # Convert the table data into a DataFrame
        df = pd.DataFrame(data=table_value['data'], columns=table_value['columns'])
        try:
            if not df.empty:
                # Update the parameters in the config
                for index, row in df.iterrows():
                    key = row['Parameter']
                    value = row['Value']
                    self.config.update_parameter(key, value)
        except Exception as e:
            print(f"Error updating config from table: check AcquisitionEngine._on_table_edit()\n{e}")

    def _refresh_config_table(self):
        """Refresh the configuration table to reflect current parameters."""
        self._gui_config_table.value = self.config.dataframe

    def rec(self):
        """Run the MDA sequence with the configuration parameters."""
        # Wait for spacebar press if start_on_trigger is True
        wait_for_trigger = self.config.start_on_trigger
        if wait_for_trigger:
            print("Press spacebar to start recording...")
            self.launch_psychopy()
            while not keyboard.is_pressed('space'):
                pass
            self.config.update_parameter('keyb_trigger_timestamp', datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
        # Dhyana MDA
        self._mmc.run_mda(
            MDASequence(time_plan={"interval": 0, "loops": self.config.num_frames}),
            output=self.config.file_path
        )
        # Thor Pupil MDA
        self._mmc2.run_mda(
            MDASequence(time_plan={"interval": 0, "loops": self.config.num_frames}),
            output=self.config.pupil_file_path
        )
    
    def launch_psychopy(self):
        """ 
        Launches a PsychoPy experiment as a subprocess with the current ExperimentConfig parameters 
        """
        import subprocess
        # num_frames = num_trials × trial_time(5 seconds) × framerate (45 fps)
        # num_trials = num_frames / (trial_time * framerate) (255 frames for a 5 seconds trial at 45 fps)
        # Total duration = num_frames / framerate or num_trials * trial_time
        # num_frames = num_trials × trial_time(5 seconds) × framerate (45 fps)
        
        # Build the command arguments
        args = [
            "C:\\Program Files\\PsychoPy\\python.exe",
            "D:\\jgronemeyer\\Experiment\\Gratings_vis_0.6.py",
            f'{self.config.protocol}',
            f'{self.config.subject}',
            f'{self.config.session}',
            f'{self.config.save_dir}',
            f'{self.config.num_trials}'
        ]
        
        subprocess.Popen(args, start_new_session=True)
    
@magicgui(call_button='Start LED', mmc={'bind': pymmcore_plus.CMMCorePlus.instance()})   
def load_arduino_led(mmc):
    """ Load Arduino-Switch device with a sequence pattern and start the sequence """
    
    mmc.getPropertyObject('Arduino-Switch', 'State').loadSequence(['4', '4', '2', '2'])
    mmc.getPropertyObject('Arduino-Switch', 'State').setValue(4) # seems essential to initiate serial communication
    mmc.getPropertyObject('Arduino-Switch', 'State').startSequence()

    print('Arduino loaded')

@magicgui(call_button='Stop LED', mmc={'bind': pymmcore_plus.CMMCorePlus.instance()})
def stop_led(mmc):
    """ Stop the Arduino-Switch LED sequence """
    
    mmc.getPropertyObject('Arduino-Switch', 'State').stopSequence()

def start_dhyana(load_params=True, pupil=False):

    print("launching Dhyana interface...")

    viewer = napari.Viewer()
    viewer.window.add_plugin_dock_widget('napari-micromanager')
    mmc = pymmcore_plus.CMMCorePlus.instance()
    print("Starting ThorCam interface...")
    mmc_thor = pymmcore_plus.CMMCorePlus()
    mmc_thor.loadSystemConfiguration(THOR_CONFIG)
    mmc_thor.setROI("ThorCam", 440, 305, 509, 509)
    mmc_thor.setExposure(20)
    mmc_thor.mda.engine.use_hardware_sequencing = True
    mesofield = AcquisitionEngine(viewer, mmc, mmc_thor)
    #load_mmc_params(mmc)
    viewer.window.add_dock_widget([mesofield, load_arduino_led, stop_led], 
                                  area='right')
    mmc.mda.engine.use_hardware_sequencing = True
    
    if load_params:
        load_dhyana_mmc_params(mmc)
        print("Dhyana parameters loaded.")
        
    print("Dhyana interface launched.")
    viewer.update_console(locals()) # https://github.com/napari/napari/blob/main/examples/update_console.py
    
    if pupil:
        start_thorcam()
  
    napari.run()

def start_thorcam():
    print("Starting ThorCam interface...")
    mmc_thor = pymmcore_plus.CMMCorePlus()
    mmc_thor.loadSystemConfiguration(THOR_CONFIG)
    mmc_thor.setROI("ThorCam", 440, 305, 509, 509)
    mmc_thor.setExposure(20)
    mmc_thor.mda.engine.use_hardware_sequencing = True
    pupil_viewer = napari.view_image(mmc_thor.snap(), name='pupil_viewer')
    pupilcam = AcquisitionEngine(pupil_viewer, mmc_thor)
    pupil_viewer.window.add_dock_widget([pupilcam], area='right')
    #viewer.window.add_dock_widget([record_from_buffer, start_sequence])
    #pupil_cam = AcquisitionEngine(viewer, pupil_mmc, PUPIL_JSON)
    #pupil_viewer.window.add_plugin_dock_widget('napari-micromanager')
    #pupil_viewer.window.add_dock_widget([pupil_cam], area='right')
    
    print("ThorCam interface launched.")
    pupil_viewer.update_console(locals()) # https://github.com/napari/napari/blob/main/examples/update_console.py
    #napari.run()

def load_dhyana_mmc_params(mmc):
    mmc.loadSystemConfiguration(DHYANA_CONFIG)
    mmc.setProperty('Arduino-Switch', 'Sequence', 'On')
    mmc.setProperty('Arduino-Shutter', 'OnOff', '1')
    mmc.setProperty('Dhyana', 'Output Trigger Port', '2')
    mmc.setProperty('Core', 'Shutter', 'Arduino-Shutter')
    mmc.setProperty('Dhyana', 'Gain', 'HDR')
    mmc.setChannelGroup('Channel')
    
# Launch Napari with the custom widget
if __name__ == "__main__":
    print("Starting Sipefield Napari Acquisition Interface...")
    start_dhyana(load_params=False, pupil=False)
    
    
    
    # def run_sequence(self):
    #     """ 
    #     Runs the Multi-Dimensional Acquisition sequence with the current ExperimentConfig parameters 
    #     """
    #     wait_for_trigger = self.config.start_on_trigger
    #     #TODO key error handling for integer
    #     n_frames = int(self.config.parameters.get('num_frames', 100)) #default 100 frames if not specified
    #     os.makedirs(self.config._output_path, exist_ok=True)
        
    #     # Create the MDA sequence. Note: time_plan has an interval 0 to start a ContinuousAcquisitionSequence
    #     sequence = useq.MDASequence(
    #         time_plan={"interval":0, "loops": n_frames}, 
    #     )
        
    #     # Wait for spacebar press if start_on_trigger is True
    #     if wait_for_trigger:
    #         print("Press spacebar to start recording...")
    #         while not keyboard.is_pressed('space'):
    #             pass
    #         self.config.update_parameter('keyb_trigger_timestamp', datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
        
    #     self._mmc.run_mda(sequence, output=self.config._output_path)
   
    #     return