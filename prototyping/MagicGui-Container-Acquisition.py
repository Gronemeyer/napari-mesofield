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

JSON_PATH = r'C:\sipefield\PyLab\pylab\load-exp-params.json'
SAVE_DIR = r'C:/Users/John/Documents/Python Scripts/napari-micromanager/napari-micromanager/examples/data'
MM_CONFIG = r'C:/Program Files/Micro-Manager-2.0/mm-sipefield.cfg'
THOR_CONFIG = r'C:/Program Files/Micro-Manager-2.0/ThorCam.cfg'

experimental_config = {'save_dir': '/path/to/save/directory',
                            'num_frames': 5000,
                            'start_on_trigger': True,
                            'protocol_id': '---',
                            'subject_id': '---',
                            'session_id': '---'}

from magicgui.widgets import Container, CheckBox, create_widget
import json
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
    
    def _update_bids_output_directory(self):
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        save_dir = self._config['save_dir']
        protocol_id = self._config['protocol_id']
        subject_id = self._config['subject_id']
        session_id = self._config['session_id']
        params = (date, protocol_id, subject_id, session_id)
        self.bids = pathlib.Path(save_dir) / '%s_%s_%s_%s' % tuple(params)
    


class AcquisitionEngine(Container):
    def __init__(self, viewer: "napari.viewer.Viewer", mmc: pymmcore_plus.CMMCorePlus):
        super().__init__()
        self._viewer = viewer
        self._mmc = mmc
        self.config = ExperimentConfig(JSON_PATH)
        
        
        self._gui_save_directory = create_widget(
            label='Save to:', widget_type='FileEdit', value=SAVE_DIR
        )
        self._gui_json_directory = create_widget(
            label='JSON Config Path:', widget_type='FileEdit', value=JSON_PATH
        )
        self._gui_load_json_file = create_widget(
            label='Load JSON Config:', widget_type='PushButton', auto_call=True
        )
        self._gui_config_table = create_widget(
            label='Experiment Config:', widget_type='Table', is_result=True, value=self.experiment_config
        )
        
        self._gui_trigger_checkbox = CheckBox(text='Start on Trigger')
        
        ### Callback connections between widget values and functions
        self._trigger_checkbox.changed.connect(self.record_from_buffer)
        self._load_json_file.label_changed.connect(self._load_json_config)
        
        self.extend(
            [
                self._gui_trigger_checkbox,
                self._gui_save_directory,
                self._gui_json_directory,
                self._gui_config_table,
            ]
        )
    
    @staticmethod
    def _load_json_config(json_path: str):
        import json

        config_df = pd.DataFrame(columns=['Parameter', 'Value'])

        # Create a pandas dataframe from the JSON file; update and return the local config_df
        with open(json_path) as file:
            df = json.load(file)
            # assign the key to the first column and the value to the second column, row by row
            for key, value in df.items():
                config_df.loc[len(config_df)] = [key, value]
                
        return config_df
    
    def _bids_output_directory(self, date=datetime.datetime.now().strftime("%Y-%m-%d")):
        return pathlib.Path(self.experiment_config['save_dir']) / f'{date}_{self.experiment_config["protocol_id"]}_{self.experiment_config["subject_id"]}_{self.experiment_config["session_id"]}'
    
    def _create_experiment_configurator(self):
        config = ExperimentConfig(self._gui_json_directory.value)
        return config.df()
    
    def record_from_buffer(self, mmc: pymmcore_plus.CMMCorePlus, 
                       trigger: bool = experimental_config['start_on_trigger'],
    ):
        def save_image_to_disk(frame: tuple) -> np.array:
            image, metadata = frame
            print('recieved:', image, 'with MD', metadata)
            try:
                recorded = self._viewer.layers['recording']
                recorded.data = frame[0]
            except KeyError:
                recorded = self._viewer.add_image(image, name='recording')

        @thread_worker(connect={'yielded': save_image_to_disk})
        def grab_frame_from_buffer() -> np.array:
            while not self._trigger_checkbox.value:
                pass
            while mmc.isSequenceRunning():
                while mmc.getRemainingImageCount() == 0:
                    pass
                try:
                    yield mmc.popNextImageAndMD()
                except (RuntimeError, IndexError):
                    # circular buffer empty
                    pass

        grab_frame_from_buffer()

def start_napari():
    
    print("launching interface...")
    mmc = pymmcore_plus.CMMCorePlus.instance()
    viewer = napari.Viewer()
    widget = AcquisitionEngine(viewer, mmc)
    viewer.window.add_plugin_dock_widget('napari-micromanager')
    viewer.window.add_dock_widget(widget, area='right')
    
    
    napari.run()
    print("interface launched.")
    mmc.mda.engine.use_hardware_sequencing = True
    mmc.setProperty('Arduino-Switch', 'Sequence', 'On')
    mmc.setProperty('Arduino-Shutter', 'OnOff', '0')
    mmc.setProperty('Dhyana', 'Output Trigger Port', '2')
    mmc.setProperty('Core', 'Shutter', 'Arduino-Shutter')
    mmc.setProperty('Dhyana', 'Gain', 'HDR')
    viewer.update_console(locals()) # https://github.com/napari/napari/blob/main/examples/update_console.py

# Launch Napari with the custom widget
if __name__ == "__main__":
    print("Starting Sipefield Napari Acquisition Interface...")
    start_napari()