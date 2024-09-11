import pandas as pd
import seaborn as sns
import numpy as np
import os
import matplotlib.pyplot as plt
import json
from tifffile import imread
from tqdm import tqdm

DATA_DIR = r'D:\jgronemeyer'
PROTOCOL = r'Camkii-gcamp8'
SUBJECT = r'gs18'
SESSION = r'ses-3'
BEHAVIOR = r'wheel_df.csv'

# Load the data
# Construct the file path
beh_path = os.path.join(DATA_DIR, PROTOCOL, SUBJECT, SESSION, 'beh')
anat_path = os.path.join(DATA_DIR, PROTOCOL, SUBJECT, SESSION, 'anat')

# Load the tiff files
tiff_files = []
for folder in os.listdir(anat_path):
    folder_path = os.path.join(anat_path, folder)
    if os.path.isdir(folder_path) and folder.startswith(f'sub-{SUBJECT}_{SESSION}_'):
        for file in os.listdir(folder_path):
            if file.endswith('.tiff'):
                file_path = os.path.join(folder_path, file)
                tiff_files.append(file_path)

# Load the metadata from the json file
# metadata_file = os.path.join(anat_path, '_frame_metadata.json')
# with open(metadata_file, 'r') as f:
#     metadata = json.load(f)

# Read the tiff files using imread
tiff_data = []
for file_path in tiff_files:
    tiff_data.append(imread(file_path))

# Display the tiff data with progress bar
for i, data in tqdm(enumerate(tiff_data), total=len(tiff_data), desc='Loading TIFF files'):
    plt.subplot(len(tiff_data), 1, i+1)
    plt.imshow(data)
    plt.title(f'TIFF File {i+1}')
    plt.axis('off')

# Adjust the layout
plt.tight_layout()

# Show the plots
plt.show()


