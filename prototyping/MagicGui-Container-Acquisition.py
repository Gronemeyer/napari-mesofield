import json.tool
import napari.layers
import napari.layers.image
from napari.qt.threading import thread_worker
import pymmcore_plus
import numpy as np
from napari_micromanager import MainWindow
from magicgui import magicgui
from magicgui.tqdm import tqdm
import pathlib
import datetime
import pandas as pd

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
        config.get_parameters_dataframe()
        ```
    """

    def __init__(self):
        """ Initialize the ExperimentParameters class. 
        """
        
        self._parameters = {}
        self._dataframe = pd.DataFrame()
        self._output_path = ''

    def load_parameters(self, json_file_path) -> None:
        """ Load parameters from a JSON file path. 
        """
        
        try:
            with open(json_file_path, 'r') as f: # TODO: open json file in writing mode to update parameters
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
        self._create_bids_output_path()
        
    def _create_bids_output_path(self):
        """ Create a BIDS-formatted output path based on the loaded parameters.
        """
        
        # Implement logic to create BIDS formatted output path
        # For example, BIDS output path can be constructed using subject, session, task, etc.
        subject = self._parameters.get('subject', 'unknown')
        session = self._parameters.get('session', 'unknown')
        task = self._parameters.get('task', 'unknown')
        save_dir = self._parameters.get('save_dir', 'unknown')

        # Construct the directory path
        directory_path = os.path.join(
            f"sub-{subject}",
            f"ses-{session}",
            'func'
        )

        # Construct the filename
        filename = f"sub-{subject}_ses-{session}_task-{task}.ome.tiff"
        self.update_parameter('filename', filename)
        # Combine directory and filename
        self._output_path = os.path.join(save_dir, directory_path)

    def __getattr__(self, val):
        """ 
        Allow getting a parameter directly as an attribute.
        """
        if val in self._parameters:
            return self._parameters[val]
        raise AttributeError(f"'ExperimentConfig' object has no attribute '{val}'")

    @property
    def parameters(self) -> dict:
        """  
        Get the parameters dictionary.  
        """
        return self._parameters

    @property
    def dataframe(self) -> pd.DataFrame:
        """ 
        Get the parameters as a pandas DataFrame. 
        """
        return self._dataframe

    @property
    def output_path(self) -> str:
        """ 
        Get the BIDS-formatted output path. 
        """
        return self._output_path

    def update_parameter(self, key, value):
        """ 
        Update a parameter in the parameters dictionary and DataFrame.
        
        - *key (str)*: The parameter key to update.
        
        - *value*: The new value for the parameter.
        """
        self._parameters[key] = value
        # Update the dataframe
        self._dataframe[key] = [value]
        # Update the output path in case relevant BIDS parameters have changed
        if key in ['subject', 'session', 'task']:
            self._create_bids_output_path()

    def reload_parameters(self, json_file_path: str):
        """ 
        Reload parameters from a new JSON file. 
        """
        self.load_parameters(json_file_path)
        
    def get_parameters_dataframe(self):
        """ Returns the parameters as a DataFrame with 'Parameter' and 'Value' columns.
        """
        data = {'Parameter': list(self._parameters.keys()),
                'Value': list(self._parameters.values())}
        return pd.DataFrame(data)

class AcquisitionEngine(Container):
    """ AcquisitionEngine object for the napari-mesofield plugin
    This class is a subclass of the Container class from the magicgui.widgets module.
    The object connects to the Micro-Manager Core object instance and the napari viewer object.
 
    _update_config: updates the experiment configuration from a new json file
    
    run_sequence: runs the MDA sequence with the configuration parameters
    
    launch_psychopy: launches the PsychoPy experiment as a subprocess with ExperimentConfig parameters
    """
    def __init__(self, viewer: "napari.viewer.Viewer", mmc: pymmcore_plus.CMMCorePlus):
        super().__init__()
        self._viewer = viewer
        self._mmc = mmc
        self.config = ExperimentConfig()   
        
        #### GUI Widgets ####
        # File directory for JSON configuration
        self._gui_json_directory = create_widget(
            label='JSON Config Path:', widget_type='FileEdit', options={'filter': '*.json'}
        )
        # Table widget to display the configuration parameters
        self._gui_config_table = create_widget(
            label='Experiment Config:', widget_type='Table', is_result=True, 
            value=self.config.get_parameters_dataframe()
        )
        self._gui_config_table.read_only = False  # Allow user input to edit the table #TODO: is this necessary?
        self._gui_config_table.changed.connect(self._on_table_edit) # Connect to table update function
        
        # Record button to start the MDA sequence
        self._gui_record_button = create_widget(
            label='Record', widget_type='PushButton'
        )
        # Launch PsychoPy button to start the PsychoPy experiment
        self._gui_psychopy_button = create_widget(
            label='Launch PsychoPy', widget_type='PushButton'
        )
        
        #### Callback connections between widget values and functions ####
        # Checkbox to start the MDA sequence on trigger
        self._gui_trigger_checkbox = CheckBox(text='Start on Trigger')
        self._gui_trigger_checkbox.value = self.config.parameters.get('start_on_trigger', False)
        self._gui_trigger_checkbox.changed.connect(self._on_trigger_checkbox_changed) 
        # Load the JSON configuration file
        self._gui_json_directory.changed.connect(self._update_config)
        # Run the MDA sequence upon button press
        self._gui_record_button.changed.connect(lambda: self._mmc.run_mda(MDASequence(time_plan={"interval":0, "loops": self.config.num_frames}), 
                                                                          output=self._create_save_directory()))
        # Launch the PsychoPy experiment upon button press
        self._gui_psychopy_button.changed.connect(self.launch_psychopy)
        # Update the configuration parameters when the table is edited
        self._gui_config_table.changed.connect(self._on_table_edit)
        
        # Add the widgets to the container
        self.extend(
            [
                self._gui_trigger_checkbox,
                self._gui_json_directory,
                self._gui_config_table,
                self._gui_record_button,
                self._gui_psychopy_button
            ]
        )
    
    def _create_save_directory(self):
        file = self.config.filename
        dir = self.config.output_path
        os.makedirs(dir, exist_ok=True)
        file_dir = os.path.join(dir, file)
        os.makedirs(file_dir, exist_ok=True)
        return file_dir
    
    def _update_config(self):
        # utility function to update the experiment configuration from a new json file loaded to the json FileEdit widget
        json_path = self._gui_json_directory.value
        if json_path and os.path.isfile(json_path):
            #try:
            self.config.reload_parameters(json_path)
            self.config.update_parameter('start_on_trigger', self._gui_trigger_checkbox.value)
            # Refresh the GUI table
            self._refresh_config_table()
            # except Exception as e:
            #     print(f"Invalid json_path: {json_path}. Skipping configuration update.")
    
    def _on_table_edit(self, event=None):
        """
        Update the configuration parameters when the table is edited.
        """
        # Retrieve the updated DataFrame from the table
        table_value = self._gui_config_table.value
        df = pd.DataFrame(**table_value)
        if not df.empty:
            # Update the parameters in the config
            for index, row in df.iterrows():
                key = row['Parameter']
                value = row['Value']
                self.config.update_parameter(key, value)
            # Update other GUI elements if necessary
            self._refresh_gui_elements()

    def _refresh_gui_elements(self):
        """
        Refresh GUI elements that may depend on configuration parameters.
        """
        # Update trigger checkbox if 'start_on_trigger' was changed via the table
        value = bool(self.config.parameters.get('start_on_trigger'))
        if value is None:
            value = bool(self._gui_trigger_checkbox.value)
        self._gui_trigger_checkbox.value = value
        # Refresh other GUI elements as needed
        
    def _on_trigger_checkbox_changed(self):
        self.config.update_parameter('start_on_trigger', self._gui_trigger_checkbox.value)
        # Refresh the table
        self._refresh_config_table()
    
    def _refresh_config_table(self):
        """
        Refresh the configuration table to reflect current parameters.
        """
        # Update the table value
        self._gui_config_table.value = self.config.get_parameters_dataframe()
    
    def launch_psychopy(self):
        """ 
        Launches a PsychoPy experiment as a subprocess with the current ExperimentConfig parameters 
        """
        
        # TODO: Error handling for presence of ExperimentConfig parameters required for PsychoPy experiment
        import subprocess
        self.config.update_parameter('num_trials', 2) # TODO: Link implicity to the number of frames in the MDA sequence to coordinate synchronous timing
        subprocess.Popen(["C:\Program Files\PsychoPy\python.exe", "D:\jgronemeyer\Experiment\Gratings_vis_0.6.py", 
                         f'{self.config.protocol}', f'{self.config.subject}', f'{self.config.session}', f'{self.config.save_dir}',
                         f'{self.config.num_trials}'], start_new_session=True)

    def run_sequence(self):
        """ 
        Runs the Multi-Dimensional Acquisition sequence with the current ExperimentConfig parameters 
        """
        wait_for_trigger = self.config.start_on_trigger
        #TODO key error handling for integer
        n_frames = int(self.config.parameters.get('num_frames', 100)) #default 100 frames if not specified
        os.makedirs(self.config._output_path, exist_ok=True)
        
        # Create the MDA sequence. Note: time_plan has an interval 0 to start a ContinuousAcquisitionSequence
        sequence = useq.MDASequence(
            time_plan={"interval":0, "loops": n_frames}, 
        )
        
        # Wait for spacebar press if start_on_trigger is True
        if wait_for_trigger:
            print("Press spacebar to start recording...")
            while not keyboard.is_pressed('space'):
                pass
            self.config.update_parameter('keyb_trigger_timestamp', datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
        
        self._mmc.run_mda(sequence, output=self.config._output_path)
   
        return

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

def start_dhyana():

    print("launching Dhyana interface...")
    
    def load_mmc_params(mmc):
        print('Loading Dhyana parameters')
        mmc.loadSystemConfiguration(DHYANA_CONFIG)
        mmc.setProperty('Arduino-Switch', 'Sequence', 'On')
        mmc.setProperty('Arduino-Shutter', 'OnOff', '1')
        mmc.setProperty('Dhyana', 'Output Trigger Port', '2')
        mmc.setProperty('Core', 'Shutter', 'Arduino-Shutter')
        mmc.setProperty('Dhyana', 'Gain', 'HDR')
        mmc.setChannelGroup('Channel')

    viewer = napari.Viewer()
    viewer.window.add_plugin_dock_widget('napari-micromanager')
    mmc = pymmcore_plus.CMMCorePlus.instance()
    mesofield = AcquisitionEngine(viewer, mmc)
    #load_mmc_params(mmc)
    viewer.window.add_dock_widget([mesofield, load_arduino_led, stop_led], 
                                  area='right')
    mmc.mda.engine.use_hardware_sequencing = True
    print("Dhyana interface launched.")
    
    viewer.update_console(locals()) # https://github.com/napari/napari/blob/main/examples/update_console.py
    napari.run()

def start_thorcam():
    mmc2 = pymmcore_plus.CMMCorePlus()
    mmc2.loadSystemConfiguration(THOR_CONFIG)
    mmc2.setROI("ThorCam", 440, 305, 509, 509)
    viewer = napari.view_image(mmc2.snap(), name='pupil_viewer')
    #viewer.window.add_dock_widget([record_from_buffer, start_sequence])
    #pupil_cam = AcquisitionEngine(viewer, pupil_mmc, PUPIL_JSON)
    #pupil_viewer.window.add_plugin_dock_widget('napari-micromanager')
    #pupil_viewer.window.add_dock_widget([pupil_cam], area='right')

# Launch Napari with the custom widget
if __name__ == "__main__":
    print("Starting Sipefield Napari Acquisition Interface...")
    start_dhyana()
    
    
    
    
    
    
    
    
    
    
    
    
    
    
# @magicgui(call_button='Record', viewer={'bind': napari.current_viewer()})
# def pupil_sequence(mesofield: AcquisitionEngine):
    
#     sequence = useq.MDASequence(
#         time_plan={"interval":0, "loops": n_frames}, 
#     )
    
#     if mesofield.config.start_on_trigger:
#         print("Press spacebar to start recording...")
#         keyboard.wait('space')
#         with mda_listeners_connected(ImageSequenceWriter(mesofield.config.sub_dir)):
#             mesofield._mmc.mda.run(mesofield.config.sequence)
#     else:
#         with mda_listeners_connected(ImageSequenceWriter(mesofield.config.sub_dir)):
#             mesofield._mmc.mda.run(mesofield.config.sequence)
#     return

# @magicgui(call_button='Launch Pupil Camera')
# def pupil_cam(mesofield: ExperimentConfig):
#     n_frames = mesofield.config.num_frames
#     mmc2 = pymmcore_plus.CMMCorePlus()
#     mmc2.loadSystemConfiguration(THOR_CONFIG)
#     mmc2.setROI("ThorCam", 440, 305, 509, 509)
#     viewer2 = napari.view_image(mmc2.snap(), name='pupil_viewer')
#     viewer2.window.add_dock_widget([pupil_sequence], area='right')