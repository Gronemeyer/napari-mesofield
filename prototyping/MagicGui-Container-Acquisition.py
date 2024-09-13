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

class ExperimentConfig():
    """ 
    Class to dynamically handle an experiment configuration loaded from a json file
    
    Attributes:
    - config: dict containing the configuration parameters loaded from a json file
    
    Methods:
    df() -> pd.DataFrame: returns a pandas DataFrame of the configuration parameters
    _update_bids_output_directory(): updates the BIDS formatted output directory
    update_from_json(json_path: str): updates the configuration parameters from a new json file
    
    """
    def __init__(self, json_path: str):
        self._config = self._load_json_config(json_path)
        
    def _load_json_config(self, json_path: str):
        with open(json_path) as file:
            config = json.load(file)
        return config
    
    def __getattr__(self, key):
        return self._config.get(key)
    
    def __setattr__(self, key, value):
        if key == '_config':
            super().__setattr__(key, value)
        else:
            self._config[key] = value
            self._update_bids_output_directory()
    
    def __str__(self):
        return str(self._config)
    
    def df(self) -> pd.DataFrame:
        return pd.DataFrame(self._config.items(), columns=['Parameter', 'Value'])
    
    def _update_bids_output_directory(self):
        """
        Make a BIDS formatted directory 

        Organizes the directory structure as follows:
        save_dir/protocol_id-subject_id/ses-session_id/anat
        """
        try:
            save_dir = self._config['save_dir']
            protocol = self._config['protocol']
            subject = self._config['subject']
            session = self._config['session']
        except KeyError:
            raise KeyError("Missing required keys to build BIDS formatted directory from json configuration file.")

        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') # get current timestamp
        anat_dir = os.path.join(save_dir, f"{protocol}", f"sub-{subject}", f"ses-{session}", "func")
        os.makedirs(anat_dir, exist_ok=True) # create the directory if it doesn't exist
        bids_sub_dir = os.path.join(anat_dir, f"sub-{subject}_ses-{session}_{timestamp}.tiff") # the .tiff tells the record button lambda function to save as tiff
        self._config['sub_dir'] = bids_sub_dir
    
    def update_from_json(self, json_path: str):
        self._config = self._load_json_config(json_path)
        self._update_bids_output_directory()

class AcquisitionEngine(Container):
    """ AcquisitionEngine object for the napari-mesofield plugin
    This class is a subclass of the Container class from the magicgui.widgets module.
    The object connects to the Micro-Manager Core object instance and the napari viewer object.

    __init__: initializes the AcquisitionEngine Widget
        self.config is an ExperimentConfig object that loads the configuration parameters from a json file
        
        self._gui_json_directory: a FileEdit widget to load a new json file
            connects to the _update_experiment_config() method
        self._gui_load_json_file: a PushButton widget to load the new json file
            connects to the _update_experiment_config() method
        self._gui_config_table: a Table widget to display the configuration parameters
            connects to the _update_experiment_config() method
        self._gui_record_button: a PushButton widget to start recording
            connects to the run_sequence() method
        self._gui_psychopy_button: a PushButton widget to launch the PsychoPy experiment
            connects to the launch_psychopy() method
        self._gui_trigger_checkbox: a CheckBox widget to start recording on trigger
        
    _update_experiment_config: updates the experiment configuration from a new json file
    run_sequence: runs the MDA sequence with the configuration parameters
    launch_psychopy: launches the PsychoPy experiment as a subprocess with ExperimentConfig parameters
    """
    def __init__(self, viewer: "napari.viewer.Viewer", mmc: pymmcore_plus.CMMCorePlus, config_path: str = JSON_PATH):
        super().__init__()
        self._viewer = viewer
        self._mmc = mmc
        self.config = ExperimentConfig(config_path)    
        self.sequence = self.config.sequence = useq.MDASequence( time_plan={"interval":0, "loops": 500},)    
        
        #### GUI Widgets ####
        self._gui_json_directory = create_widget(
            label='JSON Config Path:', widget_type='FileEdit', value=JSON_PATH
        )
        self._gui_load_json_file = create_widget(
            label='Load JSON Config:', widget_type='PushButton'
        )
        self._gui_config_table = create_widget(
            label='Experiment Config:', widget_type='Table', is_result=True, 
            value=self.config.df()
        )
        self._gui_record_button = create_widget(
            label='Record', widget_type='PushButton'
        )
        self._gui_psychopy_button = create_widget(
            label='Launch PsychoPy', widget_type='PushButton'
        )
        
        #### Callback connections between widget values and functions ####
        self._gui_trigger_checkbox = CheckBox(text='Start on Trigger')
        self._gui_trigger_checkbox.value = self.config.start_on_trigger
        self._gui_trigger_checkbox.changed.connect(lambda: self.config['start_on_trigger', self._gui_trigger_checkbox.value]) #TODO dynamically update trigger status
        self._gui_json_directory.changed.connect(self._update_experiment_config)
        self._gui_record_button.changed.connect(lambda: self._mmc.run_mda(self.config.sequence, output=self.config.sub_dir))
        self._gui_psychopy_button.changed.connect(self.launch_psychopy)
        
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
        
    def _update_experiment_config(self):
        # utility function to update the experiment configuration from a new json file loaded to the json FileEdit widget
        json_path = self._gui_json_directory.value
        self.config.update_from_json(json_path)
        self.config.start_on_trigger = self._gui_trigger_checkbox.value # TODO: update the start_on_trigger value checkbox in gui (?)
        self._gui_config_table.value = self.config.df()
    
    def launch_psychopy(self):
        """ Launches a PsychoPy experiment as a subprocess with the current ExperimentConfig parameters """
        
        # TODO: Error handling for presence of ExperimentConfig parameters required for PsychoPy experiment
        import subprocess
        self.config.num_trials = 2 # TODO: Link implicity to the number of frames in the MDA sequence to coordinate synchronous timing
        subprocess.Popen(["C:\Program Files\PsychoPy\python.exe", "D:\jgronemeyer\Experiment\Gratings_vis_0.6.py", 
                         f'{self.config.protocol}', f'{self.config.subject}', f'{self.config.session}', f'{self.config.save_dir}',
                         f'{self.config.num_trials}'], start_new_session=True)

    def run_sequence(self):
        """ Runs the Multi-Dimensional Acquisition sequence with the current ExperimentConfig parameters """
        import napari_micromanager as nm
        wait_for_trigger = self.config.start_on_trigger
        n_frames = self.config.num_frames
        
        # Create the MDA sequence. Note: time_plan has an interval 0 to start a ContinuousAcquisitionSequence
        self.config.sequence = useq.MDASequence(
            time_plan={"interval":0, "loops": n_frames}, 
        )
        
        # Wait for spacebar press if start_on_trigger is True
        if wait_for_trigger:
            print("Press spacebar to start recording...")
            while not keyboard.is_pressed('space'):
                pass
            self.config.keyb_start = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Run the MDA sequence with the ImageSequenceWriter context manager to save each image from the MMCore sequence to ExperimentConfig.sub_dir
        with mda_listeners_connected(self.config.writer):
            self._mmc.run_mda(self.config.sequence)
   
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
    
    napari.run()
    viewer.update_console(locals()) # https://github.com/napari/napari/blob/main/examples/update_console.py

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