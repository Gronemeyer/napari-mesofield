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
import tifffile
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

experimental_config = {'save_dir': '/path/to/save/directory',
                            'num_frames': 5000,
                            'start_on_trigger': True,
                            'protocol_id': '---',
                            'subject_id': '---',
                            'session_id': '---'}

from magicgui.widgets import Container, CheckBox, create_widget
import json
import keyboard
class ExperimentConfig():
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
    
    def df(self):
        return pd.DataFrame(self._config.items(), columns=['Parameter', 'Value'])
    
    def __update_bids_output_directory(self):
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        save_dir = self._config['save_dir']
        protocol_id = self._config['protocol_id']
        subject_id = self._config['subject_id']
        session_id = self._config['session_id']
        params = [date, protocol_id, subject_id, session_id]
        #self.bids = pathlib.Path(save_dir) / '{}_{}_{}_{}'.format(*params)
        bids = pathlib.Path(self._config['save_dir']) / f'{date}_{self._config["protocol_id"]}_{self._config["subject_id"]}_{self._config["session_id"]}'
        self._config['bids'] = bids
        return bids
    
    def _update_bids_output_directory(self):
        """
        Make a BIDS formatted directory 
        
        Accesses global variables for protocol_id, subject_id, session_id
        
        Organizes the directory structure as follows:
        path/protocol_id-subject_id/ses-session_id/anat
        """
        save_dir = self._config['save_dir']
        protocol_id = self._config['protocol_id']
        subject_id = self._config['subject_id']
        session_id = self._config['session_id']
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') # get current timestamp
        anat_dir = os.path.join(save_dir, f"{protocol_id}-{subject_id}", f"ses-{session_id}", "anat")
        os.makedirs(anat_dir, exist_ok=True) # create the directory if it doesn't exist
        bids_sub_dir = os.path.join(anat_dir, f"sub-{subject_id}_ses-{session_id}_{timestamp}")
        self._config['sub_dir'] = bids_sub_dir

    
    def update_from_json(self, json_path: str):
        self._config = self._load_json_config(json_path)
        self._update_bids_output_directory()


class AcquisitionEngine(Container):
    def __init__(self, viewer: "napari.viewer.Viewer", mmc: pymmcore_plus.CMMCorePlus, config_path: str = JSON_PATH):
        super().__init__()
        self._viewer = viewer
        self._mmc = mmc
        self.config = ExperimentConfig(config_path)        
        
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
        
        self._gui_trigger_checkbox = CheckBox(text='Start on Trigger')
        self._gui_trigger_checkbox.value = self.config.start_on_trigger
        
        ### Callback connections between widget values and functions
        self._gui_trigger_checkbox.changed.connect(lambda: self.config.__setattr__('start_on_trigger', self._gui_trigger_checkbox.value))
        self._gui_json_directory.changed.connect(self._update_experiment_config)
        self._gui_record_button.changed.connect(self.run_sequence)
        
        self.extend(
            [
                self._gui_trigger_checkbox,
                self._gui_json_directory,
                self._gui_config_table,
                self._gui_record_button
            ]
        )
        
    def _update_experiment_config(self):
        json_path = self._gui_json_directory.value
        self.config.update_from_json(json_path)
        self.config.start_on_trigger = self._gui_trigger_checkbox.value
        self._gui_config_table.value = self.config.df()
    
    def run_sequence(self):
        n_frames = self.config.num_frames
        
        self.config.sequence = useq.MDASequence(
            time_plan={"interval":0, "loops": n_frames}, 
        )
        
        if self.config.start_on_trigger:
            print("Press spacebar to start recording...")
            keyboard.wait('space')
            
        with mda_listeners_connected(ImageSequenceWriter(self.config.sub_dir)):
            self._mmc.mda.run(self.config.sequence)
            
        return

@magicgui(call_button='load arduino', mmc={'bind': pymmcore_plus.CMMCorePlus.instance()})   
def load_mmc_params(mmc):
    mmc.getPropertyObject('Arduino-Switch', 'State').loadSequence(['4', '4', '2', '2'])
    mmc.mda.engine.use_hardware_sequencing = True
    mmc.setProperty('Arduino-Switch', 'Sequence', 'On')
    mmc.setProperty('Arduino-Shutter', 'OnOff', '1')
    mmc.setProperty('Dhyana', 'Output Trigger Port', '2')
    mmc.setProperty('Core', 'Shutter', 'Arduino-Shutter')
    mmc.setProperty('Dhyana', 'Gain', 'HDR')
    mmc.setChannelGroup('Channel')
    mmc.getPropertyObject('Arduino-Switch', 'State').setValue(4)
    mmc.getPropertyObject('Arduino-Switch', 'State').startSequence()

    print('Arduino loaded')

@magicgui(call_button='Stop LED', mmc={'bind': pymmcore_plus.CMMCorePlus.instance()})
def stop_led(mmc):
    mmc.getPropertyObject('Arduino-Switch', 'State').stopSequence()

@magicgui(call_button='Launch PsychoPy')
def launch_psychopy():
    os.startfile(PSYCHOPY_PATH)

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

def start_napari():
    
    print("launching interface...")
    mmc = pymmcore_plus.CMMCorePlus.instance()
    mmc.loadSystemConfiguration(DHYANA_CONFIG)
    #pupil_mmc = pymmcore_plus.CMMCorePlus()
    #pupil_mmc.loadSystemConfiguration(THOR_CONFIG)
    viewer = napari.Viewer()
    #pupil_viewer = napari.Viewer()
    #pupil_cam = AcquisitionEngine(viewer, pupil_mmc, PUPIL_JSON)
    mesofield = AcquisitionEngine(viewer, mmc)
    #pupil_viewer.window.add_plugin_dock_widget('napari-micromanager')
    #pupil_viewer.window.add_dock_widget([pupil_cam], area='right')
    viewer.window.add_plugin_dock_widget('napari-micromanager')
    viewer.window.add_dock_widget([mesofield, load_mmc_params, launch_psychopy, stop_led], 
                                  area='right')

    print("interface launched.")

    viewer.update_console(locals()) # https://github.com/napari/napari/blob/main/examples/update_console.py
    napari.run()

# Launch Napari with the custom widget
if __name__ == "__main__":
    print("Starting Sipefield Napari Acquisition Interface...")
    start_napari()