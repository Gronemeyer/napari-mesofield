import napari.layers
import napari.layers.image
from napari.qt.threading import thread_worker
import pymmcore_plus
import numpy as np
from napari_micromanager import MainWindow
from magicgui import magicgui
from magicgui.tqdm import tqdm
from magicgui.widgets import Table  

import pathlib
import datetime

import pandas as pd
import os
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import napari

JSON_PATH = r'C:\sipefield\PyLab\pylab\load-exp-params.json'
SAVE_DIR = r'C:/Users/John/Documents/Python Scripts/napari-micromanager/napari-micromanager/examples/data'
MM_CONFIG = r'C:/Program Files/Micro-Manager-2.0/mm-sipefield.cfg'
THOR_CONFIG = r'C:/Program Files/Micro-Manager-2.0/ThorCam.cfg'
PSYCHOPY_PATH =  r'C:\dev\sipefield-gratings\PsychoPy\Gratings_vis_stim_devSB-JG_v0.6.psyexp'

experiment_config = {
                     'save_dir': '/path/to/save/directory',
                     'num_frames': 5000,
                     'start_on_trigger': True,
                     'protocol_id': '---',
                     'subject_id': '---',
                     'session_id': '---'
                    }



@magicgui(call_button='new mmc')
def pupil_cam():
    mmc2 = pymmcore_plus.CMMCorePlus()
    mmc2.loadSystemConfiguration(THOR_CONFIG)
    mmc2.setROI("ThorCam", 440, 305, 509, 509)
    viewer2 = napari.view_image(mmc2.snap(), name='pupil_viewer')
    viewer2.window.add_dock_widget([record_from_buffer])

@magicgui(call_button='Launch PsychoPy')
def launch_psychopy():
    os.startfile(PSYCHOPY_PATH)


@magicgui(auto_call=True, result_widget=True)
def display_experimental_config_table() -> Table:
    load_json_file(json_path)

def load_json_file(json_path: pathlib.Path) -> Table:
    
    def load_json_config(json_path: pathlib.Path) -> pd.DataFrame:
        import json
        global experiment_config # debugging
        config_df = pd.DataFrame(experiment_config.items(), columns=['key', 'value'])

        # Create a pandas dataframe from the JSON file; update and return the local config_df
        with open(json_path) as file:
            experiment_config = json.load(file)
            for key, value in experiment_config.items():
                config_df.loc[config_df['key'] == key, 'value'] = value
        return config_df

    # config_table = Table(value=load_json_config(json_path))
    # config_table.show(run=True)
    # return config_table
    load_json_config(json_path)

@magicgui(call_button='Record', 
          mmc={'bind': pymmcore_plus.CMMCorePlus.instance()},
          auto_call=True,)
def record_from_buffer(mmc: pymmcore_plus.CMMCorePlus, 
                       trigger: bool = experiment_config['start_on_trigger'],
                       save_directory=pathlib.Path(SAVE_DIR),
                       date=datetime.datetime.now().strftime("%Y-%m-%d"),
                       num_frames: int = experiment_config['num_frames'],
                       protocol_id: str = experiment_config['protocol_id'],
                       subject_id: str = experiment_config['subject_id'],
                       session_id: str = experiment_config['session_id'],
):
    """Update viewer with the latest image from the circular buffer."""
    viewer = napari.current_viewer()
    def save_image_to_disk(frame: tuple) -> np.array:
        image, metadata = frame
        print('recieved:', image, 'with MD', metadata)
        try:
            recorded = viewer.layers["recording"]
            recorded.data = frame[0]
        except KeyError:
            recorded = viewer.add_image(image, name="recording")
    

    @thread_worker(connect={'yielded': save_image_to_disk})
    def grab_frame_from_buffer() -> np.array:
        while not trigger:
            pass
        with tqdm() as pbar:
            while mmc.isSequenceRunning():
                while mmc.getRemainingImageCount() == 0:
                    pass
                try:
                    yield mmc.popNextImageAndMD()
                except (RuntimeError, IndexError):
                    # circular buffer empty
                    pass

    @mmc.events.continuousSequenceAcquisitionStarted.connect             
    def read_mmc_event():
        print('Psychopy detected the start of mmc event')

    grab_frame_from_buffer()

@magicgui(call_button='Record2', viewer={'bind': napari.current_viewer()})
def record_from_layer(viewer: napari.Viewer):
    viewer.layers[0].events.set_data.connect(lambda e: print(viewer.layers[0].data[0]))

@magicgui(call_button='load arduino', mmc={'bind': pymmcore_plus.CMMCorePlus.instance()})   
def load_arduino(mmc):
    mmc.getPropertyObject('Arduino-Switch', 'State').loadSequence(['4', '4', '2', '2'])
    mmc.getPropertyObject('Arduino-Switch', 'State').startSequence()
    
@magicgui(call_button='unload arduino', mmc={'bind': pymmcore_plus.CMMCorePlus.instance()})   
def unload_arduino(mmc):
    mmc.getPropertyObject('Arduino-Switch', 'State').stopSequence()


def start_napari():
    
    print("launching interface...")
    viewer = napari.Viewer()
    viewer.window.add_plugin_dock_widget('napari-micromanager')
    viewer.window.add_dock_widget([pupil_cam,  
                                   record_from_buffer, 
                                   record_from_layer,
                                   load_arduino,
                                   unload_arduino,
                                   display_experimental_config_table,
                                   launch_psychopy], 
                                  area='right')
    
    
    # Launch second MMCore instance in seperate napari viewer
    # mmc2 = pymmcore_plus.CMMCorePlus()
    # mmc2.loadSystemConfiguration(THOR_CONFIG)
    # mmc2.setROI("ThorCam", 440, 305, 509, 509)
    # start_sequence.mmc.value = mmc2
    # viewer2 = napari.view_image(mmc2.snap(), name='pupil_viewer')
    #viewer2.window.add_dock_widget([record_from_buffer, start_sequence])
    
    napari.run()
    print("interface launched.")
    mmc = pymmcore_plus.CMMCorePlus.instance()
    mmc.mda.engine.use_hardware_sequencing = True
    mmc.setProperty('Arduino-Switch', 'Sequence', 'On')
    mmc.setProperty('Arduino-Shutter', 'OnOff', '0')
    mmc.setProperty('Dhyana', 'Output Trigger Port', '2')
    mmc.setProperty('Core', 'Shutter', 'Arduino-Shutter')
    mmc.setProperty('Dhyana', 'Gain', 'HDR')
    #MainWindow(viewer, MM_CONFIG)
    viewer.update_console(locals()) # https://github.com/napari/napari/blob/main/examples/update_console.py

# Launch Napari with the custom widget
if __name__ == "__main__":
    print("Starting Sipefield Napari Acquisition Interface...")
    start_napari()


