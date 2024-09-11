import pymmcore_plus
import useq
import numpy as np
from pymmcore_plus.mda.handlers import OMEZarrWriter, OMETiffWriter, ImageSequenceWriter
from pymmcore_plus.mda import mda_listeners_connected

mmc = pymmcore_plus.CMMCorePlus()
mmc.loadSystemConfiguration(r'C:\Program Files\Micro-Manager-2.0\mm-sipefield.cfg')
mmc.mda.engine.use_hardware_sequencing = True
mmc.setProperty('Arduino-Switch', 'Sequence', 'On')
mmc.setProperty('Arduino-Shutter', 'OnOff', '1')
mmc.setProperty('Dhyana', 'Output Trigger Port', '2')
mmc.setProperty('Core', 'Shutter', 'Arduino-Shutter')
mmc.setProperty('Dhyana', 'Gain', 'HDR')
mmc.setChannelGroup('Channel')
mmc.setProperty('Arduino-Switch', 'State', 'Blue')

@mmc.mda.events.frameReady.connect 
def on_frame(image: np.ndarray, event: useq.MDAEvent):
    # do what you want with the data
    print(
        f"received frame: {image.shape}, {image.dtype} "
        f"@ index {event.index}, z={event.z_pos}"
    )

sequence = useq.MDASequence(
    time_plan={"interval":0, "loops": 120},
    # channels=[
    #     {"config": "Blue", "exposure": 20, "camera": "Dhyana"},
    #     {"config": "Violet", "exposure": 20, "camera": "Dhyana"},
    # ]
)

#zarr_writer = OMEZarrWriter(r'C:\dev\Output', minify_attrs_metadata=True)

# with mda_listeners_connected(zarr_writer):
#     mmc.mda.run(sequence)

with mda_listeners_connected(ImageSequenceWriter(r'C:\dev\Output\tiff')):
    mmc.mda.run(sequence)
